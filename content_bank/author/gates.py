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
