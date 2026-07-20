"""Standalone content-bank draft builder (issue #16).

Walks a per-book manifest and, per unit, drives the deterministic pipeline:
prompt-builder -> llm() -> parse -> gates (+ bounded repair) -> gated draft file.
Optional --review adds a two-lens adversarial pass. Items are written
review_status "draft"; staging into the store stays a separate human-gated step.
"""
import argparse
import json
import os
import pathlib
import random
import re
import shutil
import time

from . import (build_brief_prompt, build_draft_prompt,
               build_section_brief_prompt, gates, manifest as manifest_mod)
from .gates import run_all
from .llm import llm
from llm_core import llm_configured

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_BRIEFS_DIR = pathlib.Path(__file__).parent / "briefs"


class GateError(Exception):
    """Gates never came clean within the repair budget."""


class LLMUnavailable(Exception):
    """No LLM credential configured; the run cannot proceed."""


def _parse_items(text):
    m = _FENCE.search(text)
    body = m.group(1) if m else text
    start = body.find("[")
    end = body.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"no JSON array in LLM output: {text[:200]!r}")
    return json.loads(body[start:end + 1])


def _llm_with_backoff(prompt, *, tries=4, base=2.0):
    last = None
    for attempt in range(1, tries + 1):
        try:
            return llm(prompt)
        except RuntimeError as exc:  # rate-limit / transient; llm_core already retried
            last = exc
            if attempt == tries:
                break
            time.sleep(base ** attempt + random.uniform(0, 1))
    raise last


def _repair_prompt(prompt, items, flags):
    return (prompt
            + "\n\n## Previous attempt (fix and RETURN THE FULL CORRECTED ARRAY)\n"
            + json.dumps(items, ensure_ascii=False)
            + "\n\n## Gate problems to fix (item id -> problems)\n"
            + json.dumps(flags, ensure_ascii=False)
            + "\n\nReturn ONLY the corrected JSON array.")


def _draft_with_repair(prompt, book, allowed, *, max_repair=2):
    items = _parse_items(_llm_with_backoff(prompt))
    flags = run_all(book, items, allowed)
    rounds = 0
    while flags and rounds < max_repair:
        rounds += 1
        items = _parse_items(_llm_with_backoff(_repair_prompt(prompt, items, flags)))
        flags = run_all(book, items, allowed)
    if flags:
        raise GateError(f"gates unclean after {max_repair} repair(s): {flags}")
    return items


def _write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def _regate(prompt, items, book, allowed, *, max_repair):
    flags = run_all(book, items, allowed)
    rounds = 0
    while flags and rounds < max_repair:
        rounds += 1
        items = _parse_items(_llm_with_backoff(_repair_prompt(prompt, items, flags)))
        flags = run_all(book, items, allowed)
    if flags:
        raise GateError(f"gates unclean after review+{max_repair} repair(s): {flags}")
    return items


def _passage_text(book, pid):
    from ..lib import corpus_bridge
    p = {x["id"]: x for x in corpus_bridge.pericopes(book)}[pid]
    return corpus_bridge.passage_text(p["range"])


def _section_text(book, sid):
    from ..lib import corpus_bridge
    from corpus.lib import sections as _sections
    sec = {s["id"]: s for s in _sections.load(book)["sections"]}[sid]
    peris = corpus_bridge.pericopes(book)
    ids = [p["id"] for p in peris]
    i, j = ids.index(sec["first_pericope"]), ids.index(sec["last_pericope"])
    return "\n\n".join(corpus_bridge.passage_text(p["range"]) for p in peris[i:j + 1])


def build_pericope(pid, book, *, drafts_dir, briefs_dir=None, manifest_obj,
                   manifest_path, review_on=False, max_repair=2):
    briefs_dir = briefs_dir or _BRIEFS_DIR
    brief_path = pathlib.Path(briefs_dir) / f"{pid.lower()}.md"
    if manifest_obj["units"][pid]["stage"] == "pending":
        brief = _llm_with_backoff(build_brief_prompt.build(pid, book))
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        brief_path.write_text(brief, encoding="utf-8")
        manifest_mod.set_stage(manifest_obj, pid, "briefed")
        manifest_mod.save(manifest_path, manifest_obj)
    else:
        brief = brief_path.read_text(encoding="utf-8")

    allowed = gates.pericope_allowed(book, pid)
    prompt = build_draft_prompt.build(pid, book, brief)
    if review_on:
        from . import review as review_mod
        items = _parse_items(_llm_with_backoff(prompt))
        passage = _passage_text(book, pid)
        verdicts = review_mod.review(items, passage_text=passage, brief=brief,
                                     book=book, unit_id=pid)
        items = review_mod.revise(items, verdicts, passage_text=passage, brief=brief)
        items = _regate(prompt, items, book, allowed, max_repair=max_repair)
    else:
        items = _draft_with_repair(prompt, book, allowed, max_repair=max_repair)

    _write_json(pathlib.Path(drafts_dir) / f"{pid}.json", items)
    manifest_mod.set_stage(manifest_obj, pid, "drafted")
    manifest_mod.save(manifest_path, manifest_obj)
    return "drafted"


def build_section(sid, book, *, drafts_dir, manifest_obj, manifest_path,
                  review_on=False, max_repair=2):
    allowed = gates.section_allowed(book, sid)
    prompt = build_section_brief_prompt.build(sid, book)
    if review_on:
        from . import review as review_mod
        passage = _section_text(book, sid)
        items = _parse_items(_llm_with_backoff(prompt))
        verdicts = review_mod.review(items, passage_text=passage, brief="",
                                     book=book, unit_id=sid)
        items = review_mod.revise(items, verdicts, passage_text=passage, brief="")
        items = _regate(prompt, items, book, allowed, max_repair=max_repair)
    else:
        items = _draft_with_repair(prompt, book, allowed, max_repair=max_repair)
    _write_json(pathlib.Path(drafts_dir) / f"{sid}.json", items)
    manifest_mod.set_stage(manifest_obj, sid, "drafted")
    manifest_mod.save(manifest_path, manifest_obj)
    return "drafted"


def _default_manifest_path(book):
    return pathlib.Path("work/content_bank_build") / book / "manifest.json"


def run(book, *, units=None, kind="all", review_on=False, max_repair=2,
        limit=None, manifest_path=None, drafts_dir=None, briefs_dir=None,
        backend="llm_core", model=None):
    os.environ["SCRIPTURE_LOOM_LLM_BACKEND"] = backend
    if model:
        os.environ["SCRIPTURE_LOOM_LLM_MODEL"] = model
    else:
        os.environ.pop("SCRIPTURE_LOOM_LLM_MODEL", None)
    if backend == "claude":
        if shutil.which("claude") is None:
            raise LLMUnavailable(
                "backend=claude but the 'claude' CLI is not on PATH; install "
                "Claude Code or use --backend llm_core")
    elif not llm_configured():
        raise LLMUnavailable(
            "no LLM credential (set ARK_API_KEY or llm_api_key); see CLAUDE.md")
    manifest_path = pathlib.Path(manifest_path or _default_manifest_path(book))
    m = manifest_mod.load(manifest_path)
    drafts_dir = pathlib.Path(drafts_dir or manifest_path.parent / "drafts")

    if units:
        todo = list(units)
    else:
        todo = manifest_mod.units_at(m, "pending") + manifest_mod.units_at(m, "briefed")
        if kind != "all":
            todo = [u for u in todo if m["units"][u]["kind"] == kind]
    if limit:
        todo = todo[:limit]

    ok, failed = [], {}
    for uid in todo:
        meta = m["units"][uid]
        try:
            if meta["kind"] == "pericope":
                build_pericope(uid, book, drafts_dir=drafts_dir, briefs_dir=briefs_dir,
                               manifest_obj=m, manifest_path=manifest_path,
                               review_on=review_on, max_repair=max_repair)
            else:
                build_section(uid, book, drafts_dir=drafts_dir, manifest_obj=m,
                              manifest_path=manifest_path, review_on=review_on,
                              max_repair=max_repair)
            ok.append(uid)
            print(f"[ok] {uid}")
        except (GateError, RuntimeError, ValueError) as exc:
            failed[uid] = str(exc)
            print(f"[FAIL] {uid}: {exc}")
    return {"ok": ok, "failed": failed}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Standalone content-bank draft builder")
    ap.add_argument("--book", required=True)
    ap.add_argument("--units", nargs="*")
    ap.add_argument("--kind", choices=("pericope", "section", "all"), default="all")
    ap.add_argument("--review", action="store_true")
    ap.add_argument("--max-repair", type=int, default=2)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--manifest")
    ap.add_argument("--drafts-dir")
    ap.add_argument("--backend", choices=("llm_core", "claude"), default="llm_core",
                    help="llm_core = deepseek via API credits (default); "
                         "claude = Claude Code headless via subscription")
    ap.add_argument("--model", help="override the model (e.g. deepseek-v4-pro for "
                    "llm_core, or opus/sonnet for claude); default = backend's own")
    a = ap.parse_args(argv)
    res = run(a.book, units=a.units, kind=a.kind, review_on=a.review,
              max_repair=a.max_repair, limit=a.limit, manifest_path=a.manifest,
              drafts_dir=a.drafts_dir, backend=a.backend, model=a.model)
    print(f"\nDone. ok={len(res['ok'])} failed={len(res['failed'])}")
    return 1 if res["failed"] else 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
