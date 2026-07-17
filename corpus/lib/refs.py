"""Canonical scripture references: MAT.5.1, ranges MAT.5.1-12 / MAT.5.1-MAT.6.4."""
import re
from . import books

_BOOKS = None
_REF = re.compile(r"^([1-3]?[A-Z]{2,3})\.(\d+)\.(\d+)$")


def _codes():
    global _BOOKS
    if _BOOKS is None:
        _BOOKS = set(books.load())
    return _BOOKS


def parse(ref):
    m = _REF.match(ref)
    if not m:
        raise ValueError(f"malformed ref: {ref!r}")
    book, ch, v = m.group(1), int(m.group(2)), int(m.group(3))
    if book not in _codes():
        raise ValueError(f"unknown book: {book!r}")
    if ch < 1 or v < 1:
        raise ValueError(f"chapter/verse must be >= 1: {ref!r}")
    return (book, ch, v)


def fmt(book, ch, v):
    return f"{book}.{ch}.{v}"


def parse_range(r):
    if "-" not in r:
        start = parse(r)
        return (start, start)
    left, right = r.split("-", 1)
    start = parse(left)
    if "." in right:                       # full form: MAT.5.1-MAT.6.4
        end = parse(right)
    else:                                  # short form: MAT.5.1-12
        end = (start[0], start[1], int(right))
    if end[0] != start[0]:
        raise ValueError(f"cross-book range not allowed: {r!r}")
    if (end[1], end[2]) < (start[1], start[2]):
        raise ValueError(f"backwards range: {r!r}")
    return (start, end)


def in_range(ref_tuple, range_tuple):
    (b1, c1, v1), (b2, c2, v2) = range_tuple
    book, ch, v = ref_tuple
    if book != b1:
        return False
    return (c1, v1) <= (ch, v) <= (c2, v2)
