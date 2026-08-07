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

from dataclasses import dataclass

from . import (build_brief_prompt, build_draft_prompt, build_section_brief_prompt,
               build_section_draft_prompt, gates, manifest as manifest_mod, routing)
from .gates import run_all
from .llm import llm
from .telemetry import NullSink, record_call
from llm_core import llm_configured


@dataclass
class _Attr:
    """Telemetry attribution shared by every LLM call for one unit."""
    sink: object = None
    experiment: str | None = None
    unit_id: str | None = None
    kind: str | None = None


_NO_ATTR = _Attr()

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


def _llm_with_backoff(prompt, route=None, *, attr=_NO_ATTR, stage=None,
                      tries=4, base=2.0):
    route = route or routing.Route("llm_core")
    last = None
    for attempt in range(1, tries + 1):
        try:
            res = llm(prompt, route)
        except RuntimeError as exc:  # rate-limit / transient; llm_core already retried
            record_call(attr.sink, experiment=attr.experiment, stage=stage,
                        unit_id=attr.unit_id, kind=attr.kind, attempt=attempt,
                        route=route, prompt=prompt, error=str(exc))
            last = exc
            if attempt == tries:
                break
            time.sleep(base ** attempt + random.uniform(0, 1))
            continue
        record_call(attr.sink, experiment=attr.experiment, stage=stage,
                    unit_id=attr.unit_id, kind=attr.kind, attempt=attempt,
                    route=route, prompt=prompt, result=res)
        return res.text
    raise last


_CITATION_REPAIR_HINT = (
    "\n\n## Fixing citation.* flags\n"
    "- untagged_quote: wrap that verbatim quote in "
    '<verse ref="BOOK.CH.V">exact BSB words</verse>, using the canonical ref '
    "shown in the flag (a thread note tags EACH quoted span separately).\n"
    "- malformed: fix the markup so every <verse>/<doctrine> has a matching "
    "close tag and only the attributes shown (verse: ref; doctrine: std then "
    "ref). Do not alter text inside a tag.")


def _repair_prompt(prompt, items, flags):
    hint = (_CITATION_REPAIR_HINT
            if any("citation" in f for fl in flags.values() for f in fl) else "")
    return (prompt
            + "\n\n## Previous attempt (fix and RETURN THE FULL CORRECTED ARRAY)\n"
            + json.dumps(items, ensure_ascii=False)
            + "\n\n## Gate problems to fix (item id -> problems)\n"
            + json.dumps(flags, ensure_ascii=False)
            + hint
            + "\n\nReturn ONLY the corrected JSON array.")


def _merge_flags(*dicts):
    merged = {}
    for d in dicts:
        for k, v in d.items():
            merged.setdefault(k, []).extend(v)
    return merged


def _repair_to_clean(prompt, items, book, allowed, *, max_repair, dim_cap, where,
                     repair_route, attr=_NO_ATTR, trace=None):
    """Drive HARD (run_all) + SOFT (dimension_cap) gates through the repair loop.
    Both tiers are fed to the model each round so it fixes/prunes; after the budget,
    remaining HARD flags fail the unit, remaining SOFT (anti-padding) flags only log
    — a passage may legitimately exceed the cap, so padding never hard-blocks.
    When ``trace`` (a dict) is given, records the initial flags, each repair round,
    item drops, and first-pass/final status for the experiment gate trace."""
    n_in = len(items)
    hard = run_all(book, items, allowed)
    soft = gates.dimension_cap_check(items, cap=dim_cap)
    if trace is not None:
        trace["initial"] = {"hard": hard, "soft": soft}
        trace["first_pass_clean"] = not (hard or soft)
        trace.setdefault("rounds", [])
    rounds = 0
    while (hard or soft) and rounds < max_repair:
        rounds += 1
        repair = _repair_prompt(prompt, items, _merge_flags(hard, soft))
        items = _parse_items(_llm_with_backoff(repair, repair_route, attr=attr,
                                               stage="repair"))
        hard = run_all(book, items, allowed)
        soft = gates.dimension_cap_check(items, cap=dim_cap)
        if trace is not None:
            trace["rounds"].append({"round": rounds, "hard": hard, "soft": soft,
                                    "route": repair_route.model})
    if trace is not None:
        trace["final_pass"] = not hard
        trace["item_drops"] = n_in - len(items)
    if hard:
        raise GateError(f"hard gates unclean after {where}{max_repair} repair(s): {hard}")
    if soft:
        print(f"[warn] padding remains (advisory, not blocking): {soft}")
    return items


def _draft_with_repair(prompt, book, allowed, *, draft_route=None,
                       repair_route=None, max_repair=2,
                       dim_cap=gates.DEFAULT_DIM_CAP, attr=_NO_ATTR, trace=None):
    draft_route = draft_route or routing.Route("llm_core")
    repair_route = repair_route or routing.Route("llm_core")
    items = _parse_items(_llm_with_backoff(prompt, draft_route, attr=attr,
                                           stage="draft"))
    return _repair_to_clean(prompt, items, book, allowed, max_repair=max_repair,
                            dim_cap=dim_cap, where="", repair_route=repair_route,
                            attr=attr, trace=trace)


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


def _stamp_draft_provenance(items, stamp):
    """Record which model/run drafted each item (survives publish → the store).
    `stamp` is {model, backend, run} or None (no stamp — legacy/tests)."""
    if not stamp:
        return items
    for it in items:
        prov = dict(it.get("provenance") or {})
        prov.update(stamp)
        it["provenance"] = prov
    return items


def _save_raw_draft(raw_drafts_dir, unit_id, items):
    """Persist the first-pass (pre-review) draft so a later run can reuse it and
    skip the expensive draft LLM call. No-op when no dir is given."""
    if raw_drafts_dir is None:
        return
    _write_json(pathlib.Path(raw_drafts_dir) / f"{unit_id}.json", items)


def _reuse_raw_draft(reuse_dir, unit_id):
    """Load a frozen pre-review draft from a source run's raw_drafts dir."""
    path = pathlib.Path(reuse_dir) / "raw_drafts" / f"{unit_id}.json"
    if not path.exists():
        raise GateError(
            f"--reuse-drafts: no raw draft for {unit_id} at {path}. The source run "
            "must have been built AFTER raw-draft persistence shipped (re-run it "
            "once to capture raw_drafts/).")
    return json.loads(path.read_text(encoding="utf-8"))


def _reuse_brief(reuse_dir, unit_id):
    """Load the brief a source run saved, so reuse skips the brief LLM call too."""
    path = pathlib.Path(reuse_dir) / "briefs" / f"{unit_id.lower()}.md"
    if not path.exists():
        raise GateError(f"--reuse-drafts: no brief for {unit_id} at {path}")
    return path.read_text(encoding="utf-8")


def _regate(prompt, items, book, allowed, *, repair_route, max_repair,
            dim_cap=gates.DEFAULT_DIM_CAP, attr=_NO_ATTR, trace=None):
    return _repair_to_clean(prompt, items, book, allowed, max_repair=max_repair,
                            dim_cap=dim_cap, where="review+", repair_route=repair_route,
                            attr=attr, trace=trace)


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


def build_pericope(pid, book, *, routes=None, drafts_dir, briefs_dir=None,
                   verdicts_dir=None, manifest_obj, manifest_path, review_on=False,
                   max_repair=2, dim_cap=gates.DEFAULT_DIM_CAP, draft_stamp=None,
                   sink=None, experiment=None, gate_trace_dir=None,
                   raw_drafts_dir=None, reuse_dir=None):
    routes = routes or routing.RouteConfig.single("llm_core")
    attr = _Attr(sink, experiment, pid, "pericope")
    trace = {} if gate_trace_dir else None
    briefs_dir = briefs_dir or _BRIEFS_DIR
    brief_path = pathlib.Path(briefs_dir) / f"{pid.lower()}.md"
    if reuse_dir is not None:
        brief = _reuse_brief(reuse_dir, pid)
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        brief_path.write_text(brief, encoding="utf-8")
        manifest_mod.set_stage(manifest_obj, pid, "briefed")
        manifest_mod.save(manifest_path, manifest_obj)
    elif manifest_obj["units"][pid]["stage"] == "pending" or not brief_path.exists():
        brief = _llm_with_backoff(build_brief_prompt.build(pid, book), routes.brief,
                                  attr=attr, stage="brief")
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
        if reuse_dir is not None:
            items = _reuse_raw_draft(reuse_dir, pid)     # skip the opus draft call
        else:
            items = _parse_items(_llm_with_backoff(prompt, routes.draft, attr=attr,
                                                   stage="draft"))
            _save_raw_draft(raw_drafts_dir, pid, items)
        passage = _passage_text(book, pid)
        verdicts = review_mod.review(items, passage_text=passage, brief=brief,
                                     book=book, unit_id=pid,
                                     r1_route=routes.review_r1,
                                     r2_route=routes.review_r2,
                                     sink=sink, experiment=experiment, kind="pericope")
        _save_verdicts(verdicts_dir, pid, verdicts)
        items = review_mod.revise(items, verdicts, passage_text=passage, brief=brief,
                                  route=routes.revise, sink=sink,
                                  experiment=experiment, unit_id=pid, kind="pericope")
        items = _regate(prompt, items, book, allowed, repair_route=routes.repair,
                        max_repair=max_repair, dim_cap=dim_cap, attr=attr, trace=trace)
    else:
        items = _draft_with_repair(prompt, book, allowed, draft_route=routes.draft,
                                   repair_route=routes.repair, max_repair=max_repair,
                                   dim_cap=dim_cap, attr=attr, trace=trace)

    if gate_trace_dir:
        _write_json(pathlib.Path(gate_trace_dir) / f"{pid}.json", trace)
    _stamp_draft_provenance(items, draft_stamp)
    _write_json(pathlib.Path(drafts_dir) / f"{pid}.json", items)
    manifest_mod.set_stage(manifest_obj, pid, "drafted")
    manifest_mod.save(manifest_path, manifest_obj)
    return "drafted"


def build_section(sid, book, *, routes=None, drafts_dir, briefs_dir=None,
                  verdicts_dir=None, manifest_obj, manifest_path, review_on=False,
                  max_repair=2, dim_cap=gates.DEFAULT_DIM_CAP, draft_stamp=None,
                  sink=None, experiment=None, gate_trace_dir=None,
                  raw_drafts_dir=None, reuse_dir=None):
    routes = routes or routing.RouteConfig.single("llm_core")
    attr = _Attr(sink, experiment, sid, "section")
    trace = {} if gate_trace_dir else None
    briefs_dir = briefs_dir or _BRIEFS_DIR
    brief_path = pathlib.Path(briefs_dir) / f"{sid.lower()}.md"
    if reuse_dir is not None:
        brief = _reuse_brief(reuse_dir, sid)
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        brief_path.write_text(brief, encoding="utf-8")
        manifest_mod.set_stage(manifest_obj, sid, "briefed")
        manifest_mod.save(manifest_path, manifest_obj)
    elif manifest_obj["units"][sid]["stage"] == "pending" or not brief_path.exists():
        brief = _llm_with_backoff(build_section_brief_prompt.build(sid, book),
                                  routes.brief, attr=attr, stage="brief")
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
        if reuse_dir is not None:
            items = _reuse_raw_draft(reuse_dir, sid)     # skip the opus draft call
        else:
            items = _parse_items(_llm_with_backoff(prompt, routes.draft, attr=attr,
                                                   stage="draft"))
            _save_raw_draft(raw_drafts_dir, sid, items)
        verdicts = review_mod.review(items, passage_text=passage, brief=brief,
                                     book=book, unit_id=sid,
                                     r1_route=routes.review_r1,
                                     r2_route=routes.review_r2,
                                     sink=sink, experiment=experiment, kind="section")
        _save_verdicts(verdicts_dir, sid, verdicts)
        items = review_mod.revise(items, verdicts, passage_text=passage, brief=brief,
                                  route=routes.revise, sink=sink,
                                  experiment=experiment, unit_id=sid, kind="section")
        items = _regate(prompt, items, book, allowed, repair_route=routes.repair,
                        max_repair=max_repair, dim_cap=dim_cap, attr=attr, trace=trace)
    else:
        items = _draft_with_repair(prompt, book, allowed, draft_route=routes.draft,
                                   repair_route=routes.repair, max_repair=max_repair,
                                   dim_cap=dim_cap, attr=attr, trace=trace)
    if gate_trace_dir:
        _write_json(pathlib.Path(gate_trace_dir) / f"{sid}.json", trace)
    _stamp_draft_provenance(items, draft_stamp)
    _write_json(pathlib.Path(drafts_dir) / f"{sid}.json", items)
    manifest_mod.set_stage(manifest_obj, sid, "drafted")
    manifest_mod.save(manifest_path, manifest_obj)
    return "drafted"


def _default_manifest_path(book):
    return pathlib.Path("work/content_bank_build") / book / "manifest.json"


def _check_routes_available(routes, stages=routing.STAGES):
    """Fail fast if any route in use lacks its credential/CLI. Checks each
    distinct (backend, model) once, so a hybrid experiment surfaces every gap.
    ``stages`` limits the check (reuse mode skips brief+draft, which don't run)."""
    seen = set()
    for stage in stages:
        r = getattr(routes, stage)
        key = (r.backend, r.model)
        if key in seen:
            continue
        seen.add(key)
        if r.backend == "claude":
            if shutil.which("claude") is None:
                raise LLMUnavailable(
                    "a route uses backend=claude but the 'claude' CLI is not on "
                    "PATH; install Claude Code or use llm_core")
        elif not llm_configured(_effective_model(r.backend, r.model)):
            raise LLMUnavailable(
                f"no credential for route model {_effective_model(r.backend, r.model)!r}"
                " (set ARK_API_KEY for Volcengine or GEMINI_API_KEY/GOOGLE_API_KEY "
                "for Gemini, or configure llm_api_key); see CLAUDE.md")


def run(book, *, units=None, kind="all", review_on=False, max_repair=2,
        limit=None, manifest_path=None, drafts_dir=None, briefs_dir=None,
        verdicts_dir=None, run_root=None, backend="llm_core", model=None,
        routes=None, dim_cap=gates.DEFAULT_DIM_CAP, sink=None, experiment=None,
        gate_trace_dir=None, raw_drafts_dir=None, reuse_dir=None):
    sink = sink or NullSink()
    # Explicit per-stage routing replaces the old process-wide env switching.
    # The normal CLI passes backend/model -> a single-model RouteConfig; the
    # experiment runner passes an explicit hybrid `routes`.
    if routes is None:
        routes = routing.RouteConfig.single(backend, model)
    draft_backend, draft_model = routes.draft.backend, routes.draft.model
    # Reuse mode skips brief+draft, so those routes' credentials aren't needed;
    # only the downstream (repair/review/revise) routes must be available.
    if reuse_dir is None:
        _check_routes_available(routes)
    else:
        _check_routes_available(
            routes, ("repair", "review_r1", "review_r2", "revise"))

    slug = _run_slug(draft_backend, draft_model)
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
        print(f"[run] model={_effective_model(draft_backend, draft_model)} "
              f"slug={slug} -> {layout['run_dir']}")

    # Persist the pre-review draft next to the drafts (unless reusing frozen ones).
    if raw_drafts_dir is None and reuse_dir is None:
        raw_drafts_dir = pathlib.Path(drafts_dir).parent / "raw_drafts"

    if units:
        todo = list(units)
    else:
        todo = manifest_mod.units_at(m, "pending") + manifest_mod.units_at(m, "briefed")
        if kind != "all":
            todo = [u for u in todo if m["units"][u]["kind"] == kind]
    if limit:
        todo = todo[:limit]

    draft_stamp = {"model": _effective_model(draft_backend, draft_model),
                   "backend": draft_backend, "run": slug}
    ok, failed = [], {}
    for uid in todo:
        meta = m["units"][uid]
        try:
            if meta["kind"] == "pericope":
                build_pericope(uid, book, routes=routes, drafts_dir=drafts_dir,
                               briefs_dir=briefs_dir, verdicts_dir=verdicts_dir,
                               manifest_obj=m, manifest_path=manifest_path,
                               review_on=review_on, max_repair=max_repair,
                               dim_cap=dim_cap, draft_stamp=draft_stamp,
                               sink=sink, experiment=experiment,
                               gate_trace_dir=gate_trace_dir,
                               raw_drafts_dir=raw_drafts_dir, reuse_dir=reuse_dir)
            else:
                build_section(uid, book, routes=routes, drafts_dir=drafts_dir,
                              briefs_dir=briefs_dir, verdicts_dir=verdicts_dir,
                              manifest_obj=m, manifest_path=manifest_path,
                              review_on=review_on, max_repair=max_repair,
                              dim_cap=dim_cap, draft_stamp=draft_stamp,
                              sink=sink, experiment=experiment,
                              gate_trace_dir=gate_trace_dir,
                              raw_drafts_dir=raw_drafts_dir, reuse_dir=reuse_dir)
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
    ap.add_argument("--group", action="store_true",
                    help="batch each section-group (a section + its pericopes) into "
                         "one LLM call per stage; cuts request count on the "
                         "claude/Opus subscription backend. --units selects groups by "
                         "section id; --limit bounds the number of groups")
    ap.add_argument("--draft-batch-size", type=int, default=4,
                    help="in --group mode, cap units per DRAFT call (default 4; the "
                         "draft stage is where the model drops units at large group "
                         "sizes). Other stages stay full-group; <=0 disables the cap. "
                         "Ignored for non-group builds")
    a = ap.parse_args(argv)
    if a.group:
        from . import build_group
        res = build_group.group_run(
            a.book, units=a.units, review_on=a.review, max_repair=a.max_repair,
            limit=a.limit, run_root=a.run_root, backend=a.backend, model=a.model,
            dim_cap=a.dim_cap, draft_batch_size=a.draft_batch_size)
        print(f"\nDone. ok={len(res['ok'])} failed={len(res['failed'])}")
        return 1 if res["failed"] else 0
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
