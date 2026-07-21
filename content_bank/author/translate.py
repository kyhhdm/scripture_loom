"""LLM-backed Chinese translation of content items with strict CUV alignment.

Translate → parse structured JSON → merge zh (never touching en or structured
fields). Gating (cuv_quote_check + glossary_check) with repair, a back-
translation doctrinal-review lens, and the promote step live here too. The
tool proposes; only promote() writes the store.
"""
import copy
import json
import re

from . import build_translate_prompt, gates, glossary as _glossary, quote_detect
from .llm import llm

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json(text):
    m = _FENCE.search(text)
    body = m.group(1) if m else text
    s, e = body.find("{"), body.rfind("}")
    if s != -1 and e > s:
        return json.loads(body[s:e + 1])
    raise ValueError(f"no JSON in translation output: {text[:200]!r}")


def _applicable_glossary(item, glossary):
    en = " ".join(s for l, s in gates._lang_strings(item) if l == "en")
    out = []
    for e in glossary:
        if re.search(r"\b" + re.escape(e["en_term"]) + r"\b", en, re.IGNORECASE):
            out.append(e)
    return out


def _merge_zh(item, resp):
    out = copy.deepcopy(item)
    if isinstance(resp.get("text"), dict) and "zh" in resp["text"]:
        out.setdefault("text", {})["zh"] = resp["text"]["zh"]
    lr = resp.get("leader_reference")
    if isinstance(lr, dict) and isinstance(out.get("leader_reference"), dict):
        if isinstance(lr.get("text"), dict) and "zh" in lr["text"]:
            out["leader_reference"].setdefault("text", {})["zh"] = lr["text"]["zh"]
        if isinstance(lr.get("verse"), dict) and "zh" in lr["verse"] \
                and isinstance(out["leader_reference"].get("verse"), dict):
            out["leader_reference"]["verse"]["zh"] = lr["verse"]["zh"]
    return out


def translate_item(item, book, *, glossary=None, model=None):
    glossary = _glossary.load_glossary() if glossary is None else glossary
    detected = quote_detect.detect_quotes(item, book)
    applicable = _applicable_glossary(item, glossary)
    prompt = build_translate_prompt.build(item, book, detected=detected,
                                          glossary_entries=applicable)
    resp = _extract_json(llm(prompt, model))
    return {"item": _merge_zh(item, resp),
            "terms": resp.get("terms", []),
            "uncertain": resp.get("uncertain", []),
            "cuv_refs": sorted({d["ref"] for d in detected})}
