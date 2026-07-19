"""Merge content items into store/<book>.json by id.

Existing ids are replaced in place (preserving order); new ids are appended.
The only committed-code path that writes the store. Stdlib only, offline.
"""
import json

from ..lib import content


def upsert_items(book, items, store_dir=None):
    path = content.store_path(book, store_dir)
    if path.exists():
        store = content.load_book_store(book, store_dir)
    else:
        store = {"book": book.upper(), "items": []}
    existing = store["items"]
    index = {it["id"]: i for i, it in enumerate(existing)}
    for it in items:
        if it["id"] in index:
            existing[index[it["id"]]] = it
        else:
            index[it["id"]] = len(existing)
            existing.append(it)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return store
