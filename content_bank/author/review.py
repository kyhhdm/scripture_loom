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
from .llm import llm

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


def review(items, *, passage_text, brief, book, unit_id):
    out = []
    for name, lens, rubric_text in (
            ("r1", _R1, rubric.build()),
            ("r2", _R2, rubric.build() + "\n" + rubric.reference_criteria())):
        raw = llm(_reviewer_prompt(lens, rubric_text, items, passage_text, brief))
        out.append({"reviewer": name, "verdicts": _extract_json(raw)})
    return out


def _failed_ids(verdicts):
    ids = set()
    for v in verdicts:
        for iid, verdict in v.get("verdicts", {}).items():
            if verdict.get("verdict") == "fail":
                ids.add(iid)
    return ids


def revise(items, verdicts, *, passage_text, brief):
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
    raw = llm(prompt)
    return _extract_json(raw)
