"""Assemble the translation prompt for one content item.

Given the English item, the BSB quotes detected in it (each with the CUV text
for the same ref), the applicable glossary terms, and the English WCF-1 frame,
produce a prompt that renders the item into simplified Chinese with every
Scripture excerpt as verbatim CUV wording in 「…」, mandated glossary terms, and
doctrinal fidelity — returning structured JSON with the zh fields plus a terms
report and an uncertainty list.
"""
import json

from ..lib import corpus_bridge

_RULES = """## Rules
1. Translate the prose into natural simplified Chinese.
2. Every Scripture excerpt MUST be the verbatim CUV wording for its verse,
   wrapped in corner brackets 「…」. Use the CUV text given below — do NOT
   translate the English quote yourself.
3. If an English phrase has no contiguous CUV span, WIDEN to the smallest
   contiguous CUV span that contains it (a clause or the whole verse). Never
   invent a non-CUV rendering.
4. Use the MANDATED glossary rendering for every listed theological term; do
   not substitute a synonym.
5. Preserve every doctrinal claim exactly (see the Westminster frame): do not
   soften, strengthen, reinterpret, evangelize, or add/remove content. State
   observable behavior, never judgment.
6. Do NOT change any structured field (id, dimension, type, refs). Translate
   only text values.
7. If you are unsure of a term's correct Chinese rendering, LIST it in
   "uncertain" — never fabricate a confident wrong term.

## Output — STRICT JSON ONLY, no prose:
{"text": {"zh": "..."},
 "leader_reference": {"text": {"zh": "..."}, "verse": {"zh": "..."}},
 "category": {"zh": "..."},
 "terms": [{"en": "<term>", "zh": "<rendering used>"}],
 "uncertain": ["<anything you were unsure of>"]}
Omit "leader_reference" if the item has none; omit "verse" if the reference has
none; omit "category" if the item has none (only pre-reading items carry one)."""


def _aligned_scripture(detected):
    if not detected:
        return "(no Scripture excerpts detected in this item)"
    seen, blocks = set(), []
    for d in detected:
        ref = d["ref"]
        if ref in seen:
            continue
        seen.add(ref)
        bsb = corpus_bridge.passage_text(ref, version="BSB")
        cuv = corpus_bridge.passage_text(ref, version="CUV")
        blocks.append(f"### {ref}\nBSB: {bsb}\nCUV: {cuv}")
    return "\n".join(blocks)


def _glossary_block(entries):
    if not entries:
        return "(no mandated terms apply)"
    return "\n".join(f"- {e['en_term']} → {e['zh_term']}" for e in entries)


def build(item, book, *, detected, glossary_entries):
    return (
        "You are translating human-reviewed Bible-study content into simplified "
        "Chinese for Mainland families who read the Chinese Union Version (CUV).\n\n"
        "## English item (JSON)\n"
        f"{json.dumps(item, ensure_ascii=False, indent=2)}\n\n"
        "## Scripture excerpts — use the CUV wording verbatim\n"
        f"{_aligned_scripture(detected)}\n\n"
        "## Mandated theological terms (glossary)\n"
        f"{_glossary_block(glossary_entries)}\n\n"
        "## Westminster frame (doctrinal fidelity guardrail)\n"
        f"{corpus_bridge.wcf_chapter1_text()}\n\n"
        f"{_RULES}")
