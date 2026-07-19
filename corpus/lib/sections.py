"""Load and validate per-book section maps (canon/structure/sections/<book>.json).

A section map partitions a book's ordered pericopes into contiguous, named
movements drawn from the book's own structural markers. Additive to structure/;
never a per-pericope field.
"""
import json
import re
from pathlib import Path

CANON_ROOT = Path(__file__).resolve().parents[1] / "canon"

_MARKER_RE = re.compile(r"^[A-Z0-9]{3}\.\d+\.\d+$")
_REQUIRED = ("id", "title_en", "first_pericope", "last_pericope")


def load(book, root=None):
    root = Path(root) if root else CANON_ROOT
    with open(root / "structure" / "sections" / f"{book.lower()}.json", encoding="utf-8") as f:
        return json.load(f)


def _pericope_order(book, root):
    with open(root / "structure" / "pericopes" / f"{book.lower()}.json", encoding="utf-8") as f:
        return [p["id"] for p in json.load(f)["pericopes"]]


def validate_data(data, order):
    """Validate a parsed section map against an ordered list of pericope ids.
    Returns a list of error strings; empty means valid."""
    idx = {pid: i for i, pid in enumerate(order)}
    errors = []
    cursor = 0
    for s in data.get("sections", []):
        for field in _REQUIRED:
            if field not in s:
                errors.append(f"{s.get('id', '?')}: missing '{field}'")
        fi, li = idx.get(s.get("first_pericope")), idx.get(s.get("last_pericope"))
        if fi is None or li is None:
            errors.append(f"{s.get('id', '?')}: first/last pericope does not resolve")
            continue
        if fi > li:
            errors.append(f"{s.get('id', '?')}: first_pericope after last_pericope")
        if fi != cursor:
            expected = order[cursor] if cursor < len(order) else "<end>"
            errors.append(f"{s.get('id', '?')}: gap/overlap — expected first_pericope "
                          f"{expected}, got {s.get('first_pericope')}")
        cursor = li + 1
        mk = s.get("marker")
        if mk and not _MARKER_RE.match(mk):
            errors.append(f"{s.get('id', '?')}: malformed marker '{mk}'")
    if cursor != len(order):
        errors.append(f"sections do not cover all pericopes "
                      f"(covered {cursor} of {len(order)})")
    return errors


def validate(book, root=None):
    root = Path(root) if root else CANON_ROOT
    return validate_data(load(book, root), _pericope_order(book, root))
