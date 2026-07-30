"""LLM-backed Chinese translation of content items with strict CUV alignment.

Translate → parse structured JSON → merge zh (never touching en or structured
fields). Gating (cuv_quote_check + glossary_check) with repair, a back-
translation doctrinal-review lens, and the promote step live here too. The
tool proposes; only promote() writes the store.
"""
import copy
import json
import re

from . import build_translate_prompt, gates, glossary as _glossary, quote_detect, store_writer
from .llm import llm
from ..lib import content, corpus_bridge

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
    cat = resp.get("category")
    if isinstance(cat, dict) and "zh" in cat and isinstance(out.get("category"), dict):
        out["category"]["zh"] = cat["zh"]
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
                 gates.glossary_check([item], glossary),
                 gates.citation_check([item], langs={"zh"})):
        flags.extend(gate.get(item["id"], []))
    return flags


_CITATION_HINT = (
    "\n\n## Fixing citation.* flags\n"
    "A Scripture quote in the zh must be the verbatim CUV wording wrapped in "
    "「…」 AND kept inside its <verse> tag: <verse ref=\"PHP.1.6\">「…CUV…」</verse>. "
    "'untagged_quote' means you emitted a bare 「…」 without the <verse> tag — wrap "
    "it in the <verse ref=...> from the English. 'verse_mismatch' means the CUV "
    "wording inside the tag is wrong — use the exact CUV text. Keep std/ref "
    "unchanged on <doctrine> tags.")


def _repair_prompt(item, flags):
    hint = _CITATION_HINT if any("citation" in f for f in flags) else ""
    return ("Your Chinese translation has these problems — fix ONLY them, keeping "
            "everything else identical, and return the SAME strict JSON shape:\n"
            + "\n".join(f"- {f}" for f in flags)
            + hint
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


_FIX_PROMPT_HEAD = (
    "A back-translation drift review found a DOCTRINAL divergence between this "
    "Chinese translation and the original English / Westminster frame. Propose a "
    "revised zh that RESOLVES the drift, under these hard rules:\n"
    "- Every Scripture quote must stay a verbatim CUV span in 「…」 inside its "
    "<verse ...> tag; keep every <verse>/<doctrine> tag and its ref/std unchanged.\n"
    "- Change ONLY what the drift note requires; keep everything else identical.\n"
    "- If the drift exists ONLY because the CUV itself renders the wording this way, "
    "you CANNOT fix it without leaving the CUV. In that case DO NOT change the text: "
    "return changed=false and explain.")


def _fix_prompt(item, notes):
    return (_FIX_PROMPT_HEAD
            + "\n\n## Drift note\n" + (notes or "")
            + "\n\n## Current item (with its zh)\n"
            + json.dumps(item, ensure_ascii=False, indent=2)
            + '\n\nReturn STRICT JSON ONLY: {"changed": true|false, "reason": "...", '
              '"text": {"zh": ...}, "leader_reference": {...}, "terms": [...], '
              '"uncertain": [...]}.')


def suggest_drift_fix(item, book, drift, *, glossary=None, model=None,
                      drift_model=None):
    """Given a drift-flagged translated item, ask the model for a CUV-safe revision.

    Returns a suggested_fix dict (see plan), or None when ``drift`` did not fire.
    The original ``item`` is never mutated; on a declined fix it is returned as-is.
    The revision is proposed by ``model``; the re-drift check uses ``drift_model``
    when given (else ``model``), so a stronger reviewer can vet the fix.
    """
    if not drift.get("drift"):
        return None
    glossary = _glossary.load_glossary() if glossary is None else glossary
    resp = _extract_json(llm(_fix_prompt(item, drift.get("notes", "")), model))
    rationale = resp.get("reason", "")
    if not resp.get("changed"):
        flags = zh_gate_flags(item, glossary)
        return {"changed": False, "rationale": rationale, "item": item,
                "gate_ok": not flags, "gate_flags": flags, "drift": drift}
    revised = _merge_zh(item, resp)
    flags = zh_gate_flags(revised, glossary)
    new_drift = back_translate_review(revised, model=drift_model or model)
    return {"changed": True, "rationale": rationale, "item": revised,
            "gate_ok": not flags, "gate_flags": flags, "drift": new_drift,
            "terms": resp.get("terms", []), "uncertain": resp.get("uncertain", [])}


def _merge_zh_into_store_item(store_item, proposal_item):
    """Copy ONLY zh text values from the proposal onto the store item."""
    out = copy.deepcopy(store_item)
    p_text = (proposal_item.get("text") or {})
    if "zh" in p_text:
        out.setdefault("text", {})["zh"] = p_text["zh"]
    p_lr = proposal_item.get("leader_reference") or {}
    o_lr = out.get("leader_reference")
    if isinstance(o_lr, dict):
        if "zh" in (p_lr.get("text") or {}):
            o_lr.setdefault("text", {})["zh"] = p_lr["text"]["zh"]
        if isinstance(o_lr.get("verse"), dict) and "zh" in (p_lr.get("verse") or {}):
            o_lr["verse"]["zh"] = p_lr["verse"]["zh"]
    if isinstance(out.get("category"), dict) and "zh" in (proposal_item.get("category") or {}):
        out["category"]["zh"] = proposal_item["category"]["zh"]
    return out


def promote(book, proposals, accepted_ids, *, store_dir=None):
    accepted = set(accepted_ids)
    store = content.load_book_store(book, store_dir)
    by_id = {it["id"]: it for it in store["items"]}
    to_write, promoted = [], []
    for p in proposals:
        if p["id"] not in accepted:
            continue
        if p["id"] not in by_id:
            raise KeyError(f"{p['id']} not in {book} store")
        to_write.append(_merge_zh_into_store_item(by_id[p["id"]], p["item"]))
        promoted.append(p["id"])
    if to_write:
        store_writer.upsert_items(book, to_write, store_dir)
    return promoted
