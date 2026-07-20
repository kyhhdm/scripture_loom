"""Deterministic content gates for the standalone builder (issue #16).

Pure functions, each returning ``{item_id: [problems]}`` (empty dict = clean):
- quote_check : quoted spans must be verbatim BSB (whole-Bible haystack)
- schema_check: content_bank.lib.schema.validate_item, keyed by id
- refs_in_range: stated verse references must fall in the unit's range

Committed replacement for the untracked work/content_bank_build/quote_check.py.
Stdlib + in-repo packages only; offline.
"""
import json
import pathlib
import re

from ..lib import corpus_bridge, schema

_ROOT = pathlib.Path(__file__).resolve().parents[2]
MIN_WORDS = 3


def _norm(s):
    s = re.sub(r"[\"'“”‘’]", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def _book_text(_book):
    # Haystack = the WHOLE BSB, so legitimate cross-reference quotes validate.
    bsb = _ROOT / "corpus" / "canon" / "bibles" / "bsb.json"
    data = json.loads(bsb.read_text(encoding="utf-8"))
    parts = []
    for bk in data["books"].values():
        for ch in bk.values():
            for verse in ch.values():
                if isinstance(verse, str):
                    parts.append(verse)
    return _norm(" ".join(parts))


def _quoted_spans(s):
    return re.findall(r'"([^"]{3,300})"', s) + re.findall(r"“([^”]{3,300})”", s)


def _item_strings(item):
    out = list((item.get("text") or {}).values())
    ref = item.get("leader_reference") or {}
    out += list((ref.get("text") or {}).values())
    out += list((ref.get("verse") or {}).values())
    return out


def quote_check(book, items):
    hay = _book_text(book)
    flags = {}
    for it in items:
        misses = []
        for s in _item_strings(it):
            for span in _quoted_spans(s):
                core = span.strip(" \t\n,.;:!?\"'—-…")
                if len(core.split()) < MIN_WORDS:
                    continue
                if _norm(core) not in hay:
                    misses.append(span)
        if misses:
            flags[it["id"]] = misses
    return flags


def schema_check(items):
    flags = {}
    for it in items:
        errs = schema.validate_item(it)
        if errs:
            flags[it["id"]] = errs
    return flags


_REF_TOKEN = re.compile(r"\b[A-Z0-9]{3}\.\d+\.\d+\b")


def _parsed(range_str):
    return corpus_bridge._parse_range(range_str)


def pericope_allowed(book, pericope_id):
    peris = {p["id"]: p for p in corpus_bridge.pericopes(book)}
    if pericope_id not in peris:
        raise ValueError(f"{pericope_id} is not a {book} pericope")
    return [_parsed(peris[pericope_id]["range"])]


def section_allowed(book, section_id):
    from corpus.lib import sections as _sections
    secs = {s["id"]: s for s in _sections.load(book)["sections"]}
    if section_id not in secs:
        raise ValueError(f"{section_id} is not a {book} section")
    sec = secs[section_id]
    peris = corpus_bridge.pericopes(book)
    ids = [p["id"] for p in peris]
    i, j = ids.index(sec["first_pericope"]), ids.index(sec["last_pericope"])
    return [_parsed(p["range"]) for p in peris[i:j + 1]]


def _in_any(book, chapter, verse, allowed):
    return any(b == book and c == chapter and lo <= verse <= hi
               for (b, c, lo, hi) in allowed)


def _stated_refs(item):
    blob = json.dumps(item, ensure_ascii=False)
    tokens = set(_REF_TOKEN.findall(blob))
    tokens.update(item.get("refs") or [])
    return sorted(tokens)


def refs_in_range(items, allowed):
    flags = {}
    for it in items:
        # D5 (Connections) pericope items legitimately cross-reference.
        if "passage" in it and it.get("dimension") == "D5":
            continue
        bad = []
        for ref in _stated_refs(it):
            try:
                b, c, lo, hi = _parsed(ref)
            except (ValueError, AttributeError):
                continue
            if not _in_any(b, c, lo, allowed) or not _in_any(b, c, hi, allowed):
                bad.append(ref)
        if bad:
            flags[it["id"]] = bad
    return flags


def run_all(book, items, allowed):
    merged = {}
    for gate in (quote_check(book, items), schema_check(items),
                 refs_in_range(items, allowed)):
        for k, v in gate.items():
            merged.setdefault(k, []).extend(v)
    return merged
