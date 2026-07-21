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
from ..lib import corpus_bridge

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


def zh_gate_flags(item, glossary):
    flags = []
    for gate in (gates.cuv_quote_check([item]),
                 gates.glossary_check([item], glossary)):
        flags.extend(gate.get(item["id"], []))
    return flags


def _repair_prompt(item, flags):
    return ("Your Chinese translation has these problems — fix ONLY them, keeping "
            "everything else identical, and return the SAME strict JSON shape:\n"
            + "\n".join(f"- {f}" for f in flags)
            + "\n\n## Current item (with your zh)\n"
            + json.dumps(item, ensure_ascii=False, indent=2)
            + '\n\nReturn STRICT JSON ONLY: {"text": {"zh": ...}, '
              '"leader_reference": {...}, "terms": [...], "uncertain": [...]}.')


def translate_with_gates(item, book, *, glossary=None, model=None, max_repair=2):
    glossary = _glossary.load_glossary() if glossary is None else glossary
    out = translate_item(item, book, glossary=glossary, model=model)
    flags = zh_gate_flags(out["item"], glossary)
    rounds = 0
    while flags and rounds < max_repair:
        rounds += 1
        resp = _extract_json(llm(_repair_prompt(out["item"], flags), model))
        out["item"] = _merge_zh(out["item"], resp)
        if "terms" in resp:
            out["terms"] = resp["terms"]
        if "uncertain" in resp:
            out["uncertain"] = resp["uncertain"]
        flags = zh_gate_flags(out["item"], glossary)
    out["gate_ok"] = not flags
    out["gate_flags"] = flags
    return out


def back_translate_review(item, *, model=None):
    zh = " ".join(s for l, s in gates._lang_strings(item) if l == "zh")
    en = " ".join(s for l, s in gates._lang_strings(item) if l == "en")
    if not zh.strip():
        return {"drift": False, "notes": "no zh"}
    prompt = (
        "Back-translate the Chinese below into English, then compare its DOCTRINAL "
        "meaning to the original English and the Westminster frame. Flag any drift: "
        "softened/strengthened/added/removed doctrine, or judgment stated as fact.\n\n"
        f"## Original English\n{en}\n\n## Chinese to check\n{zh}\n\n"
        f"## Westminster frame\n{corpus_bridge.wcf_chapter1_text()}\n\n"
        'Return STRICT JSON ONLY: {"drift": true|false, "notes": "concrete"}.')
    v = _extract_json(llm(prompt, model))
    return {"drift": bool(v.get("drift")), "notes": v.get("notes", "")}
