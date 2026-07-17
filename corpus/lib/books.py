"""Load the canonical 66-book table (canon/structure/books.json)."""
import json
from pathlib import Path

CANON_ROOT = Path(__file__).resolve().parents[1] / "canon"


def load(root=None):
    root = Path(root) if root else CANON_ROOT
    with open(root / "structure" / "books.json", encoding="utf-8") as f:
        return json.load(f)


def _order():
    b = load()
    return sorted(b, key=lambda code: b[code]["n"])


BOOK_ORDER = _order()
