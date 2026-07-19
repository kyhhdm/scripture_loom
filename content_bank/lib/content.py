"""The single gated read path for content-bank items.

Product mode is the content gate: only review_status == "published" items are
served. Author mode returns every status and is used only by authoring tools.
"""
import json
import pathlib

_STORE_DIR = pathlib.Path(__file__).resolve().parents[1] / "store"


def store_path(book, store_dir=None):
    base = pathlib.Path(store_dir) if store_dir is not None else _STORE_DIR
    return base / f"{book.lower()}.json"


def _store_path(book, store_dir):
    return store_path(book, store_dir)


def load_book_store(book, store_dir=None):
    with open(_store_path(book, store_dir), encoding="utf-8") as f:
        return json.load(f)


def get_content(book, *, pericope=None, dimension=None, age_tier=None,
                lang="en", mode="product", store_dir=None):
    items = load_book_store(book, store_dir).get("items", [])
    out = []
    for it in items:
        if mode == "product" and it.get("review_status") != "published":
            continue
        if pericope is not None and it.get("passage") != pericope:
            continue
        if dimension is not None and it.get("dimension") != dimension:
            continue
        if age_tier is not None and it.get("age_tier") not in (age_tier, "all"):
            continue
        if lang is not None and lang not in (it.get("text") or {}):
            continue
        out.append(it)
    return out
