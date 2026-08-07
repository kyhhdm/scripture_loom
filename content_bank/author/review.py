"""Optional adversarial review + revise step for the standalone builder (#16).

Two complementary reviewer lenses (r1 accuracy/WCF-1/answerability; r2
evidence-not-judgment/age/dimension/pedagogy/leader-references), single-sourced
against author/rubric.py, then one revise pass over only the failed items. Never
bypasses the deterministic gates (the caller re-gates afterward). Items stay
review_status "draft"; this sharpens the draft, it does not confer human review.
"""
import json
import re

from . import rubric
from .llm import llm, route_from_env
from .telemetry import record_call

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

_R1 = ("ADVERSARIAL review, lens r1 (accuracy, WCF-1 conformity, answerability). "
       "Hunt for faults: wrong facts/verse refs, quotes not verbatim BSB, keys not "
       "grounded, non-D5 items not answerable from THIS passage, imported doctrine "
       "the passage does not bear, hedging on WCF-1.")
_R2 = ("ADVERSARIAL review, lens r2 (evidence-not-judgment, age fitness, dimension "
       "fit, pedagogy, leader-reference correctness). Hunt for faults: prompts that "
       "assess faith/character/spiritual state; language mismatched to age_tier; "
       "item not exercising its tagged dimension; answer_key on D6-D8 or leader_note "
       "on D1-D5 or any leader_reference on a memory_verse; leading/trivial prompts.")


def _extract_json(text):
    m = _FENCE.search(text)
    body = m.group(1) if m else text
    for op, cl in (("{", "}"), ("[", "]")):
        s, e = body.find(op), body.rfind(cl)
        if s != -1 and e > s:
            try:
                return json.loads(body[s:e + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"no JSON in reviewer output: {text[:200]!r}")


def _reviewer_prompt(lens, rubric_text, items, passage_text, brief):
    return (f"{lens}\n\n## Rubric\n{rubric_text}\n\n## Passage\n{passage_text}\n\n"
            f"## Brief\n{brief}\n\n## Draft items (JSON)\n"
            f"{json.dumps(items, ensure_ascii=False)}\n\n"
            "Return STRICT JSON ONLY: an object mapping item id -> "
            '{"verdict":"pass"|"fail","notes":"concrete"}. No prose.')


def review(items, *, passage_text, brief, book, unit_id, r1_route=None,
           r2_route=None, sink=None, experiment=None, kind=None):
    r1_route = r1_route or route_from_env()
    r2_route = r2_route or route_from_env()
    out = []
    for name, lens, rubric_text, route in (
            ("r1", _R1, rubric.build(), r1_route),
            ("r2", _R2, rubric.build() + "\n" + rubric.reference_criteria(), r2_route)):
        prompt = _reviewer_prompt(lens, rubric_text, items, passage_text, brief)
        res = llm(prompt, route)
        record_call(sink, experiment=experiment, stage=f"review_{name}",
                    unit_id=unit_id, kind=kind, attempt=1, route=route,
                    prompt=prompt, result=res)
        out.append({"reviewer": name, "verdicts": _extract_json(res.text)})
    return out


def _failed_ids(verdicts):
    ids = set()
    for v in verdicts:
        for iid, verdict in v.get("verdicts", {}).items():
            if verdict.get("verdict") == "fail":
                ids.add(iid)
    return ids


def revise(items, verdicts, *, passage_text, brief, route=None, sink=None,
           experiment=None, unit_id=None, kind=None):
    route = route or route_from_env()
    failed = _failed_ids(verdicts)
    if not failed:
        return items
    prompt = (
        "Revise ONLY the flagged items to address each reviewer note precisely "
        "(fix fact/quote; retag dimension and switch answer_key<->leader_note to "
        "match; reframe judgment->observable behavior; make answerable/grounded). "
        "Leave passing items byte-identical. If an item cannot be made both accurate "
        "and gate-clean, DROP it.\n\n"
        f"## Passage\n{passage_text}\n\n## Brief\n{brief}\n\n"
        f"## Reviewer verdicts (JSON)\n{json.dumps(verdicts, ensure_ascii=False)}\n\n"
        f"## Current items (JSON)\n{json.dumps(items, ensure_ascii=False)}\n\n"
        "Return ONLY the full corrected JSON array.")
    res = llm(prompt, route)
    record_call(sink, experiment=experiment, stage="revise", unit_id=unit_id,
                kind=kind, attempt=1, route=route, prompt=prompt, result=res)
    return _extract_json(res.text)


# --- Group-batched review/revise (one call per lens over a whole section-group) -----
# Same two independent lenses and the same targeted revise, but batched: the envelope
# maps each unit id to its own verdicts / revised items. Single-unit review/revise
# above are untouched.

def failed_units(group_verdicts):
    """The unit ids that have at least one ``fail`` verdict from either lens."""
    out = set()
    for r in group_verdicts:
        for unit, vmap in r.get("verdicts_by_unit", {}).items():
            if any(v.get("verdict") == "fail" for v in vmap.values()):
                out.add(unit)
    return out


def _unit_block(unit_id, ctx, items):
    return (f"===== UNIT {unit_id} =====\n## Passage\n{ctx['passage_text']}\n\n"
            f"## Brief\n{ctx['brief']}\n\n## Draft items (JSON)\n"
            f"{json.dumps(items, ensure_ascii=False)}")


def _group_reviewer_prompt(lens, rubric_text, items_by_unit, ctx_by_unit):
    blocks = [_unit_block(u, ctx_by_unit[u], items)
              for u, items in items_by_unit.items()]
    return (f"{lens}\n\n## Rubric\n{rubric_text}\n\n" + "\n\n".join(blocks) +
            "\n\nReturn STRICT JSON ONLY mapping each unit id to its item verdicts:\n"
            '{"units": {"<UNIT_ID>": {"<item_id>": {"verdict":"pass"|"fail",'
            '"notes":"concrete"}}}}. No prose.')


def review_group(items_by_unit, *, ctx_by_unit, book, r1_route=None, r2_route=None,
                 sink=None, experiment=None, section_id=None):
    """Two batched lens calls over a group. Returns
    ``[{"reviewer": name, "verdicts_by_unit": {unit: {item_id: verdict}}}, ...]``."""
    r1_route = r1_route or route_from_env()
    r2_route = r2_route or route_from_env()
    out = []
    for name, lens, rubric_text, route in (
            ("r1", _R1, rubric.build(), r1_route),
            ("r2", _R2, rubric.build() + "\n" + rubric.reference_criteria(), r2_route)):
        prompt = _group_reviewer_prompt(lens, rubric_text, items_by_unit, ctx_by_unit)
        res = llm(prompt, route)
        record_call(sink, experiment=experiment, stage=f"review_{name}",
                    unit_id=section_id, kind="group", attempt=1, route=route,
                    prompt=prompt, result=res)
        obj = _extract_json(res.text)
        out.append({"reviewer": name,
                    "verdicts_by_unit": obj.get("units", obj)})
    return out


def revise_group(items_by_unit, group_verdicts, *, ctx_by_unit, route=None, sink=None,
                 experiment=None, section_id=None):
    """Revise only the units with a failed item, batched into one call. Passing units
    are returned unchanged (byte-identical)."""
    route = route or route_from_env()
    failed = failed_units(group_verdicts)
    if not failed:
        return dict(items_by_unit)
    ordered = [u for u in items_by_unit if u in failed]
    sub_verdicts = [
        {"reviewer": r["reviewer"],
         "verdicts_by_unit": {u: r.get("verdicts_by_unit", {}).get(u, {})
                              for u in ordered}}
        for r in group_verdicts]
    blocks = [_unit_block(u, ctx_by_unit[u], items_by_unit[u]) for u in ordered]
    prompt = (
        "Revise ONLY the flagged items to address each reviewer note precisely "
        "(fix fact/quote; retag dimension and switch answer_key<->leader_note; "
        "reframe judgment->observable behavior; make answerable/grounded). Leave "
        "passing items byte-identical; DROP an item that cannot be made both accurate "
        "and gate-clean.\n\n## Reviewer verdicts (JSON)\n"
        f"{json.dumps(sub_verdicts, ensure_ascii=False)}\n\n" + "\n\n".join(blocks) +
        '\n\nReturn ONLY {"units": {"<UNIT_ID>": [ ...corrected items... ]}} for the '
        "units above.")
    res = llm(prompt, route)
    record_call(sink, experiment=experiment, stage="revise", unit_id=section_id,
                kind="group", attempt=1, route=route, prompt=prompt, result=res)
    revised = _extract_json(res.text)
    revised = revised.get("units", revised)
    out = dict(items_by_unit)
    out.update({u: revised[u] for u in ordered if u in revised})
    return out
