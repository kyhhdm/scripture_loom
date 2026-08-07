"""Group envelope prompts: wrap the per-unit prompts, ask for one {"units":{...}} object.

Group mode batches a section + its pericopes into one LLM call per stage. Rather than
re-derive the tuned per-unit instructions (citation tags, item shapes, dimension rules,
rubric), each unit's exact existing prompt is embedded as a sub-pack and a wrapper
reframes every "Return a JSON array" as "place that array as this unit's value in the
single top-level object". Maximum fidelity; the only new text is the envelope framing.
"""
from . import (build_brief_prompt, build_section_brief_prompt,
               build_draft_prompt, build_section_draft_prompt)


def _unit_kind(unit_id):
    """A section id carries the ``-S`` marker (e.g. PHP-S2); a pericope does not."""
    return "section" if "-S" in unit_id else "pericope"


_BRIEF_HEADER = (
    "# GROUP BRIEF BATCH\n\n"
    "Below are {n} independent brief-writing tasks, one per unit. Complete ALL of "
    "them. Each task tells you to 'Produce the ... BRIEF'; do that for each, then "
    "return ONE JSON object and nothing else:\n"
    '  {{"units": {{"<UNIT_ID>": "<that unit\'s full brief markdown as a JSON '
    'string>", ...}}}}\n'
    "Use EXACTLY these unit ids as keys: {ids}. Do not merge, summarize across, or "
    "omit any unit.\n\n---\n")

_DRAFT_HEADER = (
    "# GROUP DRAFT BATCH\n\n"
    "Below are {n} independent drafting tasks, one per unit. Complete ALL of them. "
    "Each task ends by asking for a JSON array; in this batch you instead place that "
    "array as the unit's value in ONE top-level object, and return nothing else:\n"
    '  {{"units": {{"<UNIT_ID>": [ ...that unit\'s items... ], ...}}}}\n'
    "Use EXACTLY these unit ids as keys: {ids}. Each unit keeps its own schema (a "
    "section unit produces one throughline / threads / arc questions; a pericope "
    "unit produces its item types). Do not merge across units or omit any.\n\n---\n")


def _brief_subpack(unit_id, book):
    if _unit_kind(unit_id) == "section":
        return build_section_brief_prompt.build(unit_id, book)
    return build_brief_prompt.build(unit_id, book)


def _draft_subpack(unit_id, book, brief):
    if _unit_kind(unit_id) == "section":
        return build_section_draft_prompt.build(unit_id, book, brief)
    return build_draft_prompt.build(unit_id, book, brief)


def brief_envelope(unit_ids, book):
    head = _BRIEF_HEADER.format(n=len(unit_ids), ids=", ".join(unit_ids))
    blocks = [f"\n===== UNIT {u} =====\n{_brief_subpack(u, book)}" for u in unit_ids]
    return head + "\n".join(blocks)


def draft_envelope(unit_ids, book, briefs):
    head = _DRAFT_HEADER.format(n=len(unit_ids), ids=", ".join(unit_ids))
    blocks = [f"\n===== UNIT {u} =====\n{_draft_subpack(u, book, briefs[u])}"
              for u in unit_ids]
    return head + "\n".join(blocks)
