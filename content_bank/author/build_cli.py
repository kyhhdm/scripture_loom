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

from . import (build_brief_prompt, build_draft_prompt, build_section_brief_prompt,
               build_section_draft_prompt, gates, manifest as manifest_mod)
from .gates import run_all
from .llm import llm
from llm_core import llm_configured

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_BRIEFS_DIR = pathlib.Path(__file__).parent / "briefs"
_BUILD_ROOT = pathlib.Path("work/content_bank_build")


def _effective_model(backend, model):
    """The model that will actually run: the override, else the backend's default."""
    if model:
        return model
    return "opus" if backend == "claude" else "deepseek-v4-flash"


def _run_slug(backend, model):
    """Directory-safe id for a run, from its effective model (full model id)."""
    m = _effective_model(backend, model).lower()
    return re.sub(r"[^a-z0-9.]+", "-", m).strip("-")


def _run_layout(book, slug, *, root=None):
    """The per-model run dir and its {manifest,briefs,drafts,verdicts} paths."""
    run_dir = pathlib.Path(root or _BUILD_ROOT) / book / "runs" / slug
    return {
        "run_dir": run_dir,
        "manifest": run_dir / "manifest.json",
        "briefs": run_dir / "briefs",
        "drafts": run_dir / "drafts",
        "verdicts": run_dir / "verdicts",
    }


def _load_run_manifest(book, layout, *, root=None):
    """Load the run's own stage ledger, seeding it from the canonical book manifest
    (all units 'pending') on first use so each model tracks progress independently."""
    if layout["manifest"].exists():
        return manifest_mod.load(layout["manifest"])
    canonical = manifest_mod.load(pathlib.Path(root or _BUILD_ROOT) / book /
                                  "manifest.json")
    pericopes = [u for u, meta in canonical["units"].items()
                 if meta["kind"] == "pericope"]
    sections = [u for u, meta in canonical["units"].items()
                if meta["kind"] == "section"]
    m = manifest_mod.init_manifest(book, pericopes, sections)
    manifest_mod.save(layout["manifest"], m)
    return m


def _verdicts_by_item(review_out):
    """Convert review()'s reviewer-keyed output into the item-keyed file format
    ({id: [{reviewer, verdict, notes}]}) that compare_html and the stored files use."""
    by_item = {}
    for r in review_out:
        for iid, v in (r.get("verdicts") or {}).items():
            by_item.setdefault(iid, []).append({
                "reviewer": r.get("reviewer"),
                "verdict": v.get("verdict"),
                "notes": v.get("notes"),
            })
    return by_item


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


def _merge_flags(*dicts):
    merged = {}
    for d in dicts:
        for k, v in d.items():
            merged.setdefault(k, []).extend(v)
    return merged


def _repair_to_clean(prompt, items, book, allowed, *, max_repair, dim_cap, where):
    """Drive HARD (run_all) + SOFT (dimension_cap) gates through the repair loop.
    Both tiers are fed to the model each round so it fixes/prunes; after the budget,
    remaining HARD flags fail the unit, remaining SOFT (anti-padding) flags only log
    — a passage may legitimately exceed the cap, so padding never hard-blocks."""
    hard = run_all(book, items, allowed)
    soft = gates.dimension_cap_check(items, cap=dim_cap)
    rounds = 0
    while (hard or soft) and rounds < max_repair:
        rounds += 1
        repair = _repair_prompt(prompt, items, _merge_flags(hard, soft))
        items = _parse_items(_llm_with_backoff(repair))
        hard = run_all(book, items, allowed)
        soft = gates.dimension_cap_check(items, cap=dim_cap)
    if hard:
        raise GateError(f"hard gates unclean after {where}{max_repair} repair(s): {hard}")
    if soft:
        print(f"[warn] padding remains (advisory, not blocking): {soft}")
    return items


def _draft_with_repair(prompt, book, allowed, *, max_repair=2,
                       dim_cap=gates.DEFAULT_DIM_CAP):
    items = _parse_items(_llm_with_backoff(prompt))
    return _repair_to_clean(prompt, items, book, allowed, max_repair=max_repair,
                            dim_cap=dim_cap, where="")


def _write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def _save_verdicts(verdicts_dir, unit_id, review_out):
    """Persist the adversarial review as item-keyed verdicts, if a dir is given."""
    if verdicts_dir is None:
        return
    _write_json(pathlib.Path(verdicts_dir) / f"{unit_id}.json",
                _verdicts_by_item(review_out))


def _regate(prompt, items, book, allowed, *, max_repair, dim_cap=gates.DEFAULT_DIM_CAP):
    return _repair_to_clean(prompt, items, book, allowed, max_repair=max_repair,
                            dim_cap=dim_cap, where="review+")


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


def build_pericope(pid, book, *, drafts_dir, briefs_dir=None, verdicts_dir=None,
                   manifest_obj, manifest_path, review_on=False, max_repair=2,
                   dim_cap=gates.DEFAULT_DIM_CAP):
    briefs_dir = briefs_dir or _BRIEFS_DIR
    brief_path = pathlib.Path(briefs_dir) / f"{pid.lower()}.md"
    if manifest_obj["units"][pid]["stage"] == "pending" or not brief_path.exists():
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
        _save_verdicts(verdicts_dir, pid, verdicts)
        items = review_mod.revise(items, verdicts, passage_text=passage, brief=brief)
        items = _regate(prompt, items, book, allowed, max_repair=max_repair,
                        dim_cap=dim_cap)
    else:
        items = _draft_with_repair(prompt, book, allowed, max_repair=max_repair,
                                   dim_cap=dim_cap)

    _write_json(pathlib.Path(drafts_dir) / f"{pid}.json", items)
    manifest_mod.set_stage(manifest_obj, pid, "drafted")
    manifest_mod.save(manifest_path, manifest_obj)
    return "drafted"


def build_section(sid, book, *, drafts_dir, briefs_dir=None, verdicts_dir=None,
                  manifest_obj, manifest_path, review_on=False, max_repair=2,
                  dim_cap=gates.DEFAULT_DIM_CAP):
    briefs_dir = briefs_dir or _BRIEFS_DIR
    brief_path = pathlib.Path(briefs_dir) / f"{sid.lower()}.md"
    if manifest_obj["units"][sid]["stage"] == "pending" or not brief_path.exists():
        brief = _llm_with_backoff(build_section_brief_prompt.build(sid, book))
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        brief_path.write_text(brief, encoding="utf-8")
        manifest_mod.set_stage(manifest_obj, sid, "briefed")
        manifest_mod.save(manifest_path, manifest_obj)
    else:
        brief = brief_path.read_text(encoding="utf-8")

    allowed = gates.section_allowed(book, sid)
    prompt = build_section_draft_prompt.build(sid, book, brief)
    if review_on:
        from . import review as review_mod
        passage = _section_text(book, sid)
        items = _parse_items(_llm_with_backoff(prompt))
        verdicts = review_mod.review(items, passage_text=passage, brief=brief,
                                     book=book, unit_id=sid)
        _save_verdicts(verdicts_dir, sid, verdicts)
        items = review_mod.revise(items, verdicts, passage_text=passage, brief=brief)
        items = _regate(prompt, items, book, allowed, max_repair=max_repair,
                        dim_cap=dim_cap)
    else:
        items = _draft_with_repair(prompt, book, allowed, max_repair=max_repair,
                                   dim_cap=dim_cap)
    _write_json(pathlib.Path(drafts_dir) / f"{sid}.json", items)
    manifest_mod.set_stage(manifest_obj, sid, "drafted")
    manifest_mod.save(manifest_path, manifest_obj)
    return "drafted"


def _default_manifest_path(book):
    return pathlib.Path("work/content_bank_build") / book / "manifest.json"


def run(book, *, units=None, kind="all", review_on=False, max_repair=2,
        limit=None, manifest_path=None, drafts_dir=None, briefs_dir=None,
        verdicts_dir=None, run_root=None, backend="llm_core", model=None,
        dim_cap=gates.DEFAULT_DIM_CAP):
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

    slug = _run_slug(backend, model)
    if manifest_path is not None or drafts_dir is not None:
        # Legacy / explicit-dir mode (advanced use and existing tests).
        manifest_path = pathlib.Path(manifest_path or _default_manifest_path(book))
        m = manifest_mod.load(manifest_path)
        drafts_dir = pathlib.Path(drafts_dir or manifest_path.parent / "drafts")
        briefs_dir = pathlib.Path(briefs_dir) if briefs_dir else None
        verdicts_dir = (pathlib.Path(verdicts_dir) if verdicts_dir
                        else manifest_path.parent / "verdicts")
    else:
        # Per-model run layout: runs/<slug>/{manifest,briefs,drafts,verdicts}.
        layout = _run_layout(book, slug, root=run_root)
        m = _load_run_manifest(book, layout, root=run_root)
        manifest_path = layout["manifest"]
        drafts_dir = pathlib.Path(drafts_dir) if drafts_dir else layout["drafts"]
        briefs_dir = pathlib.Path(briefs_dir) if briefs_dir else layout["briefs"]
        verdicts_dir = (pathlib.Path(verdicts_dir) if verdicts_dir
                        else layout["verdicts"])
        print(f"[run] model={_effective_model(backend, model)} slug={slug} "
              f"-> {layout['run_dir']}")

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
                               verdicts_dir=verdicts_dir, manifest_obj=m,
                               manifest_path=manifest_path, review_on=review_on,
                               max_repair=max_repair, dim_cap=dim_cap)
            else:
                build_section(uid, book, drafts_dir=drafts_dir, briefs_dir=briefs_dir,
                              verdicts_dir=verdicts_dir, manifest_obj=m,
                              manifest_path=manifest_path, review_on=review_on,
                              max_repair=max_repair, dim_cap=dim_cap)
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
    ap.add_argument("--review", dest="review", action="store_true", default=True,
                    help="run the adversarial review + revise pass (default ON)")
    ap.add_argument("--no-review", dest="review", action="store_false",
                    help="skip the adversarial review pass")
    ap.add_argument("--max-repair", type=int, default=2)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--manifest")
    ap.add_argument("--drafts-dir")
    ap.add_argument("--briefs-dir")
    ap.add_argument("--verdicts-dir")
    ap.add_argument("--run-root", help="build root holding runs/<model>/ "
                    "(default work/content_bank_build)")
    ap.add_argument("--backend", choices=("llm_core", "claude"), default="llm_core",
                    help="llm_core = deepseek via API credits (default); "
                         "claude = Claude Code headless via subscription")
    ap.add_argument("--model", help="override the model (e.g. deepseek-v4-pro for "
                    "llm_core, or opus/sonnet for claude); default = backend's own")
    ap.add_argument("--dim-cap", type=int, default=gates.DEFAULT_DIM_CAP,
                    help="anti-padding: soft per-dimension item cap per unit "
                         f"(default {gates.DEFAULT_DIM_CAP}); over-cap dimensions are "
                         "fed to the repair loop, then logged (never hard-fail)")
    a = ap.parse_args(argv)
    res = run(a.book, units=a.units, kind=a.kind, review_on=a.review,
              max_repair=a.max_repair, limit=a.limit, manifest_path=a.manifest,
              drafts_dir=a.drafts_dir, briefs_dir=a.briefs_dir,
              verdicts_dir=a.verdicts_dir, run_root=a.run_root,
              backend=a.backend, model=a.model, dim_cap=a.dim_cap)
    print(f"\nDone. ok={len(res['ok'])} failed={len(res['failed'])}")
    return 1 if res["failed"] else 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
