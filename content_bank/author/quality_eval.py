"""Evaluate content-build runs with deterministic metrics and D1-D8 fit review.

The deterministic layer reports item volume, dimension coverage/padding, gates,
word counts, citation tags, difficulty, and saved adversarial-review failures.
The optional semantic layer asks one configurable reviewer model per run/unit to
classify every item's *dominant exercised skill* against the canonical D1-D8
definitions. It never modifies drafts or promotes content.

CLI example::

    uv run python -m content_bank.author.quality_eval \
        --book PHP --runs gemini-3.6-flash,opus --units PHP-002 \
        --fit-backend claude --fit-model sonnet
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import pathlib
import re

from . import compare_html, dimensions, gates
from .llm import llm_text, route_from_env


def _env_fit_reviewer(prompt, model=None):
    """Transitional default fit reviewer: route via the legacy env backend.
    Task C2 replaces this with an explicit evaluator Route."""
    return llm_text(prompt, route_from_env(model))

DIM_ORDER = tuple(f"D{i}" for i in range(1, 9))
FIT_STATUSES = {"accurate", "mixed", "misclassified"}
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_VERSE = re.compile(r"<verse\b")
_DOCTRINE = re.compile(r"<doctrine\b")


def _english(item):
    return (item.get("text") or {}).get("en") or ""


def _reference_text(item):
    return (((item.get("leader_reference") or {}).get("text") or {}).get("en")
            or "")


def _word_count(text):
    return len(text.split())


def _count_map(values):
    return dict(sorted(collections.Counter(values).items(), key=lambda x: str(x[0])))


def _saved_failures(verdicts):
    out = []
    for iid, rows in (verdicts or {}).items():
        for row in rows or []:
            if row.get("verdict") == "fail":
                out.append({"id": iid, "reviewer": row.get("reviewer"),
                            "notes": row.get("notes")})
    return out


def compute_metrics(items, *, hard_flags=None, soft_flags=None, verdicts=None):
    """Return deterministic quality metrics for one run/unit."""
    hard_flags = hard_flags or {}
    soft_flags = soft_flags or {}
    all_text = "\n".join(
        s for item in items for s in (_english(item), _reference_text(item)) if s)
    dim_counts = collections.Counter(item.get("dimension") for item in items)
    present = [d for d in DIM_ORDER if dim_counts.get(d)]
    failures = _saved_failures(verdicts)
    return {
        "item_count": len(items),
        "dimension_counts": {d: dim_counts.get(d, 0) for d in DIM_ORDER},
        "dimension_coverage": present,
        "missing_dimensions": [d for d in DIM_ORDER if not dim_counts.get(d)],
        "largest_dimension_count": max(dim_counts.values(), default=0),
        "hard_gate_flagged_items": len(hard_flags),
        "hard_gate_problem_count": sum(len(v) for v in hard_flags.values()),
        "hard_gate_flags": hard_flags,
        "soft_padding_flagged_items": len(soft_flags),
        "soft_padding_flags": soft_flags,
        "item_text_words": sum(_word_count(_english(item)) for item in items),
        "leader_reference_words": sum(_word_count(_reference_text(item))
                                      for item in items),
        "leader_reference_count": sum(bool(item.get("leader_reference"))
                                      for item in items),
        "verse_tag_count": len(_VERSE.findall(all_text)),
        "doctrine_tag_count": len(_DOCTRINE.findall(all_text)),
        "difficulty_counts": _count_map(item.get("difficulty") for item in items),
        "difficulty_3_count": sum(item.get("difficulty") == 3 for item in items),
        "type_counts": _count_map(item.get("type") for item in items),
        "age_tier_counts": _count_map(item.get("age_tier") for item in items),
        # Verdicts are saved before revision, so name them precisely.
        "saved_review_failure_count": len(failures),
        "saved_review_failures": failures,
    }


def build_dimension_fit_prompt(items, brief=None):
    definitions = "\n".join(f"{d}: {dimensions.TEMPLATES[d]}" for d in DIM_ORDER)
    payload = []
    for item in items:
        lr = item.get("leader_reference") or {}
        payload.append({
            "id": item.get("id"),
            "assigned_dimension": item.get("dimension"),
            "type": item.get("type"),
            "text_en": _english(item),
            "leader_reference_kind": lr.get("kind"),
            "leader_reference_text_en": _reference_text(item),
        })
    return f"""You are an adversarial Bible-fluency DIMENSION-FIT evaluator.
Judge the dominant skill the LEARNER actually performs, not the topic, label, or
presence of dimension-related words. Use these canonical definitions:

{definitions}

Sharp boundaries that must be enforced:
- D1 identifies people, roles, relationships, or places; an action involving a
  person is not automatically D1.
- D2 requires order, movement, cause-to-effect, or argument flow; merely listing
  two facts, motives, or contrasts is not sequence.
- D3 asks the sense or use of the Bible's own word or repeated phrase.
- D4 exercises memorization, cued recall, or recognition of Scripture itself.
- D5 explicitly connects this passage to another passage or biblical pattern.
- D6 requires the LEARNER to formulate a question. A model-written why-question
  that the learner answers is D7, not D6.
- D7 explains meaning or why from textual evidence. Closed extraction of a
  directly stated reason may be D2/D4 rather than genuine interpretation.
- D8 requires a concrete, observable response, report, or prayer topic.
- Inspect the leader reference: a canned answer can expose a supposedly open
  D6-D8 item as a closed task.

Status meanings:
- accurate: the assigned dimension is clearly the dominant exercised skill.
- mixed: the assigned skill is genuinely exercised, but another dimension is
  equally or more prominent.
- misclassified: the assigned skill is not genuinely exercised.

Return STRICT JSON ONLY: one object per input item, in the same order:
[
  {{"id":"...", "status":"accurate|mixed|misclassified",
    "suggested_dimension":"D1"..."D8", "confidence":0.0,
    "reason":"one concrete sentence about the learner's actual task"}}
]
For accurate items, suggested_dimension repeats the assigned dimension. Never
omit an item and never add an item.

Theological brief (context only; do not evaluate theology here):
{brief or '(none)'}

Items:
{json.dumps(payload, ensure_ascii=False, indent=2)}"""


def _parse_fit(raw, items):
    match = _FENCE.search(raw)
    body = match.group(1) if match else raw
    start, end = body.find("["), body.rfind("]")
    if start < 0 or end < start:
        raise ValueError(f"dimension-fit reviewer returned no JSON array: {raw[:200]!r}")
    rows = json.loads(body[start:end + 1])
    expected = [item.get("id") for item in items]
    if not isinstance(rows, list) or [r.get("id") for r in rows] != expected:
        raise ValueError("dimension-fit result ids/order do not match input items")
    for row in rows:
        if row.get("status") not in FIT_STATUSES:
            raise ValueError(f"invalid dimension-fit status for {row.get('id')}")
        if row.get("suggested_dimension") not in DIM_ORDER:
            raise ValueError(f"invalid suggested dimension for {row.get('id')}")
        if not isinstance(row.get("reason"), str) or not row["reason"].strip():
            raise ValueError(f"missing dimension-fit reason for {row.get('id')}")
        confidence = row.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise ValueError(f"invalid confidence for {row.get('id')}")
    return rows


def evaluate_dimension_fit(items, *, brief=None, reviewer=_env_fit_reviewer, model=None):
    """Run one semantic fit review and return item results plus coverage summary."""
    rows = _parse_fit(reviewer(build_dimension_fit_prompt(items, brief), model=model), items)
    assigned = {item["id"]: item.get("dimension") for item in items}
    status_counts = collections.Counter(row["status"] for row in rows)
    suggested = collections.Counter(row["suggested_dimension"] for row in rows)
    supported = {assigned[row["id"]] for row in rows if row["status"] == "accurate"}
    questionable = ({assigned[row["id"]] for row in rows if row["status"] == "mixed"}
                    - supported)
    return {
        "status_counts": {s: status_counts.get(s, 0)
                          for s in ("accurate", "mixed", "misclassified")},
        "accurate_assigned_coverage": [d for d in DIM_ORDER if d in supported],
        "mixed_only_assigned_dimensions": [d for d in DIM_ORDER if d in questionable],
        "adjusted_dimension_counts": {d: suggested.get(d, 0) for d in DIM_ORDER},
        "adjusted_coverage": [d for d in DIM_ORDER if suggested.get(d)],
        "adjusted_missing_dimensions": [d for d in DIM_ORDER if not suggested.get(d)],
        "items": rows,
    }


def _gate_results(book, unit, items, dim_cap):
    allowed = compare_html._allowed(book, unit)
    if allowed is None:
        hard = gates.schema_check(items)
        for result in (gates.quote_check(book, items),
                       gates.section_reveal_check(items), gates.citation_check(items)):
            for iid, problems in result.items():
                hard.setdefault(iid, []).extend(problems)
    else:
        hard = gates.run_all(book, items, allowed)
    return hard, gates.dimension_cap_check(items, cap=dim_cap)


def evaluate(book, runs, *, units=None, base=None, dimension_fit=True,
             fit_backend="llm_core", fit_model="gemini-3.6-flash", dim_cap=3,
             reviewer=_env_fit_reviewer):
    """Evaluate selected runs and return a JSON-serializable report."""
    base = pathlib.Path(base) if base else compare_html.DEFAULT_BASE
    selected = set(units or [])
    report = {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "book": book,
        "requested_units": list(units or []),
        "dimension_fit_reviewer": {
            "enabled": bool(dimension_fit), "backend": fit_backend,
            "model": fit_model if dimension_fit else None,
        },
        "runs": {},
    }
    if dimension_fit:
        os.environ["SCRIPTURE_LOOM_LLM_BACKEND"] = fit_backend

    for run in runs:
        draft_dir, verdicts_dir, briefs_dir = compare_html._resolve_run(base / book, run)
        all_verdicts = compare_html._load_verdicts(verdicts_dir)
        files = sorted(pathlib.Path(draft_dir).glob("*.json"))
        if selected:
            files = [path for path in files if path.stem in selected]
        if selected - {path.stem for path in files}:
            missing = sorted(selected - {path.stem for path in files})
            raise FileNotFoundError(f"run {run} missing requested unit(s): {missing}")

        run_report = {"units": {}}
        totals = collections.Counter()
        for path in files:
            unit = path.stem
            items = json.loads(path.read_text(encoding="utf-8"))
            hard, soft = _gate_results(book, unit, items, dim_cap)
            metrics = compute_metrics(items, hard_flags=hard, soft_flags=soft,
                                      verdicts=all_verdicts.get(unit, {}))
            draft_models = sorted({((item.get("provenance") or {}).get("model"))
                                   for item in items
                                   if (item.get("provenance") or {}).get("model")})
            unit_report = {"metrics": metrics, "draft_models": draft_models}
            if dimension_fit:
                brief = compare_html._load_brief(unit, briefs_dir)
                unit_report["dimension_fit"] = evaluate_dimension_fit(
                    items, brief=brief, reviewer=reviewer, model=fit_model)
                unit_report["dimension_fit"]["reviewer_is_draft_model"] = \
                    fit_model in draft_models
                for status, n in unit_report["dimension_fit"]["status_counts"].items():
                    totals[f"fit_{status}"] += n
            run_report["units"][unit] = unit_report
            totals["units"] += 1
            totals["items"] += metrics["item_count"]
            totals["hard_gate_flagged_items"] += metrics["hard_gate_flagged_items"]
            totals["soft_padding_flagged_items"] += metrics["soft_padding_flagged_items"]
        run_report["aggregate"] = dict(totals)
        report["runs"][run] = run_report
    return report


def render_console(report):
    lines = []
    header = ("run unit items coverage maxdim hard soft words refs tags diff3 "
              "fit(a/m/x) adjusted-missing")
    lines.append(header)
    for run, run_data in report["runs"].items():
        for unit, data in run_data["units"].items():
            m = data["metrics"]
            fit = data.get("dimension_fit")
            if fit:
                sc = fit["status_counts"]
                fit_text = f"{sc['accurate']}/{sc['mixed']}/{sc['misclassified']}"
                missing = ",".join(fit["adjusted_missing_dimensions"]) or "-"
            else:
                fit_text, missing = "off", "?"
            tags = f"{m['verse_tag_count']}v/{m['doctrine_tag_count']}d"
            words = f"{m['item_text_words']}+{m['leader_reference_words']}"
            lines.append(
                f"{run} {unit} {m['item_count']} {len(m['dimension_coverage'])}/8 "
                f"{m['largest_dimension_count']} {m['hard_gate_flagged_items']} "
                f"{m['soft_padding_flagged_items']} {words} "
                f"{m['leader_reference_count']} {tags} {m['difficulty_3_count']} "
                f"{fit_text} {missing}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Evaluate content-build quality metrics and semantic D1-D8 fit")
    ap.add_argument("--book", required=True)
    ap.add_argument("--runs", required=True,
                    help="comma-separated run slugs, e.g. gemini-3.6-flash,opus")
    ap.add_argument("--units", nargs="*", help="optional unit ids; default all")
    ap.add_argument("--base", help="build root (default work/content_bank_build)")
    ap.add_argument("--out", help="JSON report path (default <base>/<book>/quality_eval.json)")
    ap.add_argument("--fit-backend", choices=("llm_core", "claude"),
                    default="llm_core")
    ap.add_argument("--fit-model", default="gemini-3.6-flash")
    ap.add_argument("--no-dimension-fit", action="store_true",
                    help="compute deterministic metrics only; make no LLM call")
    ap.add_argument("--dim-cap", type=int, default=gates.DEFAULT_DIM_CAP)
    args = ap.parse_args(argv)
    runs = [run.strip() for run in args.runs.split(",") if run.strip()]
    base = pathlib.Path(args.base) if args.base else compare_html.DEFAULT_BASE
    report = evaluate(args.book, runs, units=args.units, base=base,
                      dimension_fit=not args.no_dimension_fit,
                      fit_backend=args.fit_backend, fit_model=args.fit_model,
                      dim_cap=args.dim_cap)
    out = pathlib.Path(args.out) if args.out else base / args.book / "quality_eval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(render_console(report))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
