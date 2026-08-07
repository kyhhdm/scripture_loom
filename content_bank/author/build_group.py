"""Group-batched execution: one LLM call per stage over a section-group.

A *group* is a section plus the pericopes in its span. Group mode batches all of a
group's units into a single ``{"units": {unit_id: payload}}`` envelope per stage
(brief, draft, repair, review r1/r2, revise), splits the envelope back into per-unit
artifacts, and hands each slice to the UNCHANGED per-unit gates / repair / manifest /
store code in ``build_cli``. Motivation: the ``claude``/Opus subscription backend
meters request count as well as tokens, so a section spanning N pericopes drops from
~4(N+1) calls to ~5.

A ``stop_reason``-driven bisection guard (``group_call``) protects the call-count win
from truncation: an oversized group is split and its halves retried down to singletons;
a singleton that still truncates raises for that unit only. See
``docs/superpowers/specs/2026-08-07-group-batched-content-build-design.md``.
"""
import json
import pathlib
import re

from corpus.lib import sections as _sections

from . import build_cli, build_group_prompt, gates, manifest as manifest_mod, routing
from . import review as review_mod
from ..lib import corpus_bridge
from .llm import llm
from .telemetry import NullSink, record_call


class Truncated(Exception):
    """Envelope missing units / unparseable — trigger bisection."""


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def groups_for_book(book):
    """``[(section_id, [pericope_id, ...]), ...]`` — each section with its span's
    pericopes (in order). Sections partition the book, so every pericope appears once."""
    peris = corpus_bridge.pericopes(book)
    ids = [p["id"] for p in peris]
    out = []
    for sec in _sections.load(book)["sections"]:
        i, j = ids.index(sec["first_pericope"]), ids.index(sec["last_pericope"])
        out.append((sec["id"], ids[i:j + 1]))
    return out


def unit_ids_for_group(section_id, pericope_ids):
    """The batched-stage unit list for a group: the section first, then its pericopes."""
    return [section_id, *pericope_ids]


def parse_units(text, expected_ids):
    """Extract ``{"units": {...}}`` and return ``{id: payload}`` for ``expected_ids``.
    Raise ``Truncated`` if the object is unparseable or any expected id is missing."""
    m = _FENCE.search(text)
    body = m.group(1) if m else text
    s, e = body.find("{"), body.rfind("}")
    if s == -1 or e <= s:
        raise Truncated(f"no JSON object in output: {text[:200]!r}")
    try:
        obj = json.loads(body[s:e + 1])
    except json.JSONDecodeError as exc:
        raise Truncated(str(exc))
    units = obj.get("units") if isinstance(obj, dict) else None
    if not isinstance(units, dict):
        raise Truncated("no 'units' object")
    missing = [u for u in expected_ids if u not in units]
    if missing:
        raise Truncated(f"missing units: {missing}")
    return {u: units[u] for u in expected_ids}


def group_call(build_prompt, unit_ids, *, route, sink=None, experiment=None,
               stage="draft", section_id=None):
    """One batched envelope call over ``unit_ids``. On truncation (``max_tokens`` stop,
    a missing unit, or an unparseable envelope) bisect the unit list and merge the
    halves; a singleton that still fails raises ``Truncated`` (isolated to that unit).

    ``build_prompt(ids) -> str`` is re-invoked per sub-list so bisection rebuilds the
    prompt for the smaller group."""
    unit_ids = list(unit_ids)
    prompt = build_prompt(unit_ids)
    res = llm(prompt, route)
    record_call(sink, experiment=experiment, stage=stage,
                unit_id=section_id or (unit_ids[0] if unit_ids else None),
                kind="group", attempt=1, route=route, prompt=prompt, result=res)
    truncated = res.stop_reason == "max_tokens"
    if not truncated:
        try:
            return parse_units(res.text, unit_ids)
        except Truncated:
            truncated = True
    if len(unit_ids) == 1:
        raise Truncated(f"singleton {unit_ids[0]} still truncated/omitted")
    mid = len(unit_ids) // 2
    left = group_call(build_prompt, unit_ids[:mid], route=route, sink=sink,
                      experiment=experiment, stage=stage, section_id=section_id)
    right = group_call(build_prompt, unit_ids[mid:], route=route, sink=sink,
                       experiment=experiment, stage=stage, section_id=section_id)
    return {**left, **right}


def build_group_briefs(unit_ids, book, *, route, sink=None, experiment=None,
                       section_id=None):
    """One batched brief call → ``{unit_id: brief_markdown}``."""
    return group_call(lambda ids: build_group_prompt.brief_envelope(ids, book),
                      unit_ids, route=route, sink=sink, experiment=experiment,
                      stage="brief", section_id=section_id)


def _allowed_for(book, unit_id):
    if build_group_prompt._unit_kind(unit_id) == "section":
        return gates.section_allowed(book, unit_id)
    return gates.pericope_allowed(book, unit_id)


def group_draft_items(unit_ids, book, briefs, *, route, sink=None, experiment=None,
                      section_id=None):
    """One batched draft call → ``{unit_id: raw items}`` (no gates). The gate+repair
    pass is applied per-unit by the caller, at the point that matches the per-unit
    builder (after draft when review is off, after revise when review is on)."""
    return group_call(
        lambda ids: build_group_prompt.draft_envelope(ids, book, briefs),
        unit_ids, route=route, sink=sink, experiment=experiment,
        stage="draft", section_id=section_id)


def build_group_drafts(unit_ids, book, briefs, *, routes, max_repair=2,
                       dim_cap=gates.DEFAULT_DIM_CAP, sink=None, experiment=None,
                       section_id=None, traces=None):
    """The no-review path: one batched draft call → per-unit gates + bounded repair →
    ``{unit_id: items}`` (mirrors the per-unit ``_draft_with_repair``). Gates are
    per-unit and deterministic; only the repair LLM call costs a request."""
    raw = group_draft_items(unit_ids, book, briefs, route=routes.draft, sink=sink,
                            experiment=experiment, section_id=section_id)
    out = {}
    for u in unit_ids:
        allowed = _allowed_for(book, u)
        prompt = build_group_prompt._draft_subpack(u, book, briefs[u])
        trace = {} if traces is not None else None
        out[u] = build_cli._repair_to_clean(
            prompt, raw[u], book, allowed, max_repair=max_repair, dim_cap=dim_cap,
            where="group-", repair_route=routes.repair, trace=trace)
        if traces is not None:
            traces[u] = trace
    return out


def _ctx_for(book, unit_id):
    if build_group_prompt._unit_kind(unit_id) == "section":
        return {"passage_text": build_cli._section_text(book, unit_id)}
    return {"passage_text": build_cli._passage_text(book, unit_id)}


def _save_group_verdicts(verdicts_dir, group_verdicts, unit_ids):
    """Persist per-unit item-keyed verdict files from the batched review output."""
    if verdicts_dir is None:
        return
    for u in unit_ids:
        by_item = {}
        for r in group_verdicts:
            for iid, v in (r.get("verdicts_by_unit", {}).get(u) or {}).items():
                by_item.setdefault(iid, []).append({
                    "reviewer": r.get("reviewer"), "verdict": v.get("verdict"),
                    "notes": v.get("notes")})
        build_cli._write_json(verdicts_dir / f"{u}.json", by_item)


def _build_one_group(section_id, pericope_ids, book, *, routes, briefs_dir,
                     drafts_dir, verdicts_dir, gate_trace_dir, m, manifest_path,
                     review_on, max_repair, dim_cap, draft_stamp, sink, experiment):
    """Drive one group through the batched pipeline, writing per-unit artifacts and
    advancing each unit's manifest stage. Units already ``drafted`` are skipped.

    The stage order mirrors the per-unit builder exactly so gate traces are
    comparable: brief → draft → (review → revise → **gate+repair**) when review is on;
    brief → draft → **gate+repair** when it is off. The gate+repair pass runs once, at
    the same point the per-unit builder gates, so ``first_pass_gate_rate`` measures the
    same thing across execution modes."""
    briefs_dir, drafts_dir = pathlib.Path(briefs_dir), pathlib.Path(drafts_dir)
    unit_ids = [u for u in unit_ids_for_group(section_id, pericope_ids)
                if m["units"][u]["stage"] != "drafted"]
    if not unit_ids:
        return []

    briefs = build_group_briefs(unit_ids, book, route=routes.brief, sink=sink,
                                experiment=experiment, section_id=section_id)
    briefs_dir.mkdir(parents=True, exist_ok=True)
    for u in unit_ids:
        (briefs_dir / f"{u.lower()}.md").write_text(briefs[u], encoding="utf-8")
        manifest_mod.set_stage(m, u, "briefed")
    manifest_mod.save(manifest_path, m)

    traces = {}
    if review_on:
        raw = group_draft_items(unit_ids, book, briefs, route=routes.draft, sink=sink,
                                experiment=experiment, section_id=section_id)
        ctx = {u: _ctx_for(book, u) for u in unit_ids}
        for u in unit_ids:
            ctx[u]["brief"] = briefs[u]
        group_verdicts = review_mod.review_group(
            raw, ctx_by_unit=ctx, book=book, r1_route=routes.review_r1,
            r2_route=routes.review_r2, sink=sink, experiment=experiment,
            section_id=section_id)
        if verdicts_dir is not None:
            _save_group_verdicts(pathlib.Path(verdicts_dir), group_verdicts, unit_ids)
        revised = review_mod.revise_group(
            raw, group_verdicts, ctx_by_unit=ctx, route=routes.revise, sink=sink,
            experiment=experiment, section_id=section_id)
        drafts = {}
        for u in unit_ids:
            allowed = _allowed_for(book, u)
            prompt = build_group_prompt._draft_subpack(u, book, briefs[u])
            trace = {}
            drafts[u] = build_cli._regate(prompt, revised[u], book, allowed,
                                          repair_route=routes.repair,
                                          max_repair=max_repair, dim_cap=dim_cap,
                                          trace=trace)
            traces[u] = trace
    else:
        drafts = build_group_drafts(unit_ids, book, briefs, routes=routes,
                                    max_repair=max_repair, dim_cap=dim_cap, sink=sink,
                                    experiment=experiment, section_id=section_id,
                                    traces=traces)

    if gate_trace_dir is not None:
        for u in unit_ids:
            build_cli._write_json(pathlib.Path(gate_trace_dir) / f"{u}.json",
                                  traces.get(u, {}))
    for u in unit_ids:
        items = build_cli._stamp_draft_provenance(drafts[u], draft_stamp)
        build_cli._write_json(drafts_dir / f"{u}.json", items)
        manifest_mod.set_stage(m, u, "drafted")
        manifest_mod.save(manifest_path, m)
    return unit_ids


def group_run(book, *, units=None, review_on=True, max_repair=2, limit=None,
              run_root=None, backend="llm_core", model=None, routes=None,
              dim_cap=gates.DEFAULT_DIM_CAP, sink=None, experiment=None,
              manifest_path=None, drafts_dir=None, briefs_dir=None, verdicts_dir=None,
              gate_trace_dir=None):
    """Batched per-group build. ``units`` selects groups by section id; omitted, walks
    every group with a not-yet-``drafted`` unit. ``limit`` bounds the number of groups.

    Two output modes, matching ``build_cli.run``: passing ``manifest_path``/
    ``drafts_dir`` uses those explicit dirs (the experiment runner directs output to
    ``runs/<name>/`` and captures ``gate_trace_dir``); otherwise the per-model run
    layout ``runs/<slug>/`` is computed from ``run_root``. Returns
    ``{"ok": [unit_id,...], "failed": {unit_id: error}}``."""
    sink = sink or NullSink()
    if routes is None:
        routes = routing.RouteConfig.single(backend, model)
    build_cli._check_routes_available(routes)

    draft_backend, draft_model = routes.draft.backend, routes.draft.model
    slug = build_cli._run_slug(draft_backend, draft_model)
    if manifest_path is not None or drafts_dir is not None:
        # Explicit-dir mode (experiment runner / advanced use).
        manifest_path = pathlib.Path(manifest_path
                                     or build_cli._default_manifest_path(book))
        m = manifest_mod.load(manifest_path)
        drafts_dir = pathlib.Path(drafts_dir or manifest_path.parent / "drafts")
        briefs_dir = (pathlib.Path(briefs_dir) if briefs_dir
                      else manifest_path.parent / "briefs")
        verdicts_dir = (pathlib.Path(verdicts_dir) if verdicts_dir
                        else manifest_path.parent / "verdicts")
    else:
        layout = build_cli._run_layout(book, slug, root=run_root)
        m = build_cli._load_run_manifest(book, layout, root=run_root)
        manifest_path = layout["manifest"]
        drafts_dir, briefs_dir, verdicts_dir = (
            layout["drafts"], layout["briefs"], layout["verdicts"])
        print(f"[group-run] model={build_cli._effective_model(draft_backend, draft_model)} "
              f"slug={slug} -> {layout['run_dir']}")
    for d in (drafts_dir, briefs_dir, verdicts_dir):
        pathlib.Path(d).mkdir(parents=True, exist_ok=True)

    draft_stamp = {"model": build_cli._effective_model(draft_backend, draft_model),
                   "backend": draft_backend, "run": slug}

    groups = groups_for_book(book)
    if units:
        want = set(units)
        groups = [g for g in groups if g[0] in want]
    if limit:
        groups = groups[:limit]

    ok, failed = [], {}
    for section_id, pericope_ids in groups:
        try:
            built = _build_one_group(
                section_id, pericope_ids, book, routes=routes, briefs_dir=briefs_dir,
                drafts_dir=drafts_dir, verdicts_dir=verdicts_dir,
                gate_trace_dir=gate_trace_dir, m=m, manifest_path=manifest_path,
                review_on=review_on, max_repair=max_repair, dim_cap=dim_cap,
                draft_stamp=draft_stamp, sink=sink, experiment=experiment)
            ok.extend(built)
            for u in built:
                print(f"[ok] {u}")
        except (build_cli.GateError, Truncated, RuntimeError, ValueError) as exc:
            pending = [u for u in unit_ids_for_group(section_id, pericope_ids)
                       if m["units"][u]["stage"] != "drafted"]
            for u in pending:
                failed[u] = str(exc)
            print(f"[FAIL] group {section_id}: {exc}")
    return {"ok": ok, "failed": failed}
