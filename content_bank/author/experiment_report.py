"""Extended experiment metrics computed from a run's persisted artifacts (#35).

Reads the append-only ``calls.jsonl`` telemetry, the per-unit gate traces, and
the drafts to report calls/tokens by stage/backend/model, first-pass and final
gate rates, repairs, per-unit and per-accepted-item efficiency, and — merging in
the deterministic + D1-D8-fit evaluator report — whether the fit evaluator is the
same model as the drafter.
"""
from __future__ import annotations

import collections
import json
import pathlib


def _read_jsonl(path):
    path = pathlib.Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _tok(usage, key):
    return (usage or {}).get(key) or 0


def build_report(out_dir, *, eval_report=None, draft_route=None,
                 evaluator_route=None):
    """Return the extended experiment metrics dict for one experiment out dir."""
    out_dir = pathlib.Path(out_dir)
    calls = _read_jsonl(out_dir / "calls.jsonl")

    by_stage = collections.Counter()
    by_backend = collections.Counter()
    by_model = collections.Counter()
    tokens_in_by_stage = collections.Counter()
    tokens_out_by_stage = collections.Counter()
    claude_calls = 0
    total_in = total_out = 0
    uncached_in = cache_creation_total = cache_read_total = 0
    cost_total = 0.0
    repair_calls = 0
    repair_tokens = 0
    for c in calls:
        by_stage[c["stage"]] += 1
        by_backend[c["backend"]] += 1
        by_model[c.get("requested_model") or "(default)"] += 1
        u = c.get("usage")
        # True input processed = uncached input + cache-creation + cache-read.
        # With claude prompt caching the uncached `input` field is tiny; the bulk
        # of every prompt lands in the cache buckets, so summing only `input`
        # under-reports input by orders of magnitude.
        ti_uncached = _tok(u, "input")
        cc, cr = _tok(u, "cache_creation"), _tok(u, "cache_read")
        ti = ti_uncached + cc + cr
        to = _tok(u, "output")
        tokens_in_by_stage[c["stage"]] += ti
        tokens_out_by_stage[c["stage"]] += to
        total_in += ti
        total_out += to
        uncached_in += ti_uncached
        cache_creation_total += cc
        cache_read_total += cr
        cost_total += c.get("cost_estimate") or 0.0
        if c["backend"] == "claude":
            claude_calls += 1
        if c["stage"] == "repair":
            repair_calls += 1
            repair_tokens += ti + to

    traces = {}
    for path in sorted((out_dir / "gate_traces").glob("*.json")) \
            if (out_dir / "gate_traces").is_dir() else []:
        traces[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    n_units = len(traces)
    first_pass_clean = sum(1 for t in traces.values() if t.get("first_pass_clean"))
    final_pass = sum(1 for t in traces.values() if t.get("final_pass"))
    repaired_units = [t for t in traces.values() if t.get("rounds")]

    # Accepted items = items in the final drafts, summed across every book's
    # nested run dir (a cross-book experiment has one drafts dir per book).
    accepted_items = 0
    for drafts_dir in _draft_dirs(out_dir):
        for path in sorted(drafts_dir.glob("*.json")):
            try:
                accepted_items += len(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue

    total_tokens = total_in + total_out
    evaluator_is_drafter = bool(
        draft_route and evaluator_route
        and draft_route.backend == evaluator_route.backend
        and draft_route.model == evaluator_route.model)

    report = {
        "calls_total": len(calls),
        "calls_by_stage": dict(by_stage),
        "calls_by_backend": dict(by_backend),
        "calls_by_model": dict(by_model),
        "claude_calls": claude_calls,
        "tokens_in_by_stage": dict(tokens_in_by_stage),
        "tokens_out_by_stage": dict(tokens_out_by_stage),
        "tokens_in_total": total_in,
        "tokens_in_uncached_total": uncached_in,
        "cache_creation_total": cache_creation_total,
        "cache_read_total": cache_read_total,
        "tokens_out_total": total_out,
        "estimated_cost": round(cost_total, 6),
        "units": n_units,
        "accepted_items": accepted_items,
        "first_pass_gate_rate": (first_pass_clean / n_units) if n_units else None,
        "final_gate_rate": (final_pass / n_units) if n_units else None,
        "repaired_units": len(repaired_units),
        "repair_calls": repair_calls,
        "repair_tokens": repair_tokens,
        "tokens_per_unit": (total_tokens / n_units) if n_units else None,
        "tokens_per_accepted_item": (total_tokens / accepted_items)
                                    if accepted_items else None,
        "cost_per_accepted_item": (cost_total / accepted_items)
                                  if accepted_items else None,
        "evaluator_is_drafter": evaluator_is_drafter,
    }
    if eval_report is not None:
        report["evaluator"] = _fit_summary(eval_report)
    return report


def _draft_dirs(out_dir):
    """Every nested <book>/runs/<name>/drafts written by the runner (one per book
    for a cross-book experiment; typically one for a single-book experiment)."""
    return [p for p in sorted(out_dir.glob("*/runs/*/drafts")) if p.is_dir()]


def _fit_summary(eval_report):
    """Fold the evaluator report's per-unit fit into experiment-level totals."""
    totals = collections.Counter()
    for run in (eval_report.get("runs") or {}).values():
        for unit in (run.get("units") or {}).values():
            fit = unit.get("dimension_fit")
            if not fit:
                continue
            for status, n in fit.get("status_counts", {}).items():
                totals[f"fit_{status}"] += n
            totals["fit_missing_dimensions"] += len(
                fit.get("adjusted_missing_dimensions", []))
    return dict(totals)
