"""Adapter producing the legacy 'bank' dict shape the kit-generator prototype
consumes, sourced from the gated store and corpus pericope metadata.

Keeps the prototype selector logic unchanged: text[lang] is flattened to 'body'
and category[lang] to 'category' for the requested language.
"""
from . import content, corpus_bridge


def display_ref(range_str, lang="en"):
    # range_str like "MAT.5.3-12" or "MAT.5.1" (single verse)
    book_code, chapter, verses = range_str.split(".", 2)
    name = corpus_bridge.book_name(book_code, lang)
    if "-" in verses:
        v1, v2 = verses.split("-", 1)
        span = f"{v1}–{v2}"  # en dash
    else:
        span = verses
    return f"{name} {chapter}:{span}"


def load_bank(book, lang="en", store_dir=None):
    pericopes = [
        {
            "id": p["id"],
            "ref": display_ref(p["range"], lang),
            "title": p.get("title_zh") if lang == "zh" and p.get("title_zh") else p["title_en"],
        }
        for p in corpus_bridge.pericopes(book)
    ]
    items = []
    for it in content.get_content(book, lang=lang, mode="product", store_dir=store_dir):
        flat = {k: v for k, v in it.items() if k not in ("text", "category")}
        flat["body"] = it["text"][lang]
        if "category" in it and lang in it["category"]:
            flat["category"] = it["category"][lang]
        items.append(flat)
    return {"pericopes": pericopes, "items": items}
