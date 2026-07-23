"""Adapter producing the legacy 'bank' dict shape the kit-generator prototype
consumes, sourced from the gated store and corpus pericope metadata.

Keeps the prototype selector logic unchanged: text[lang] is flattened to 'body'
and category[lang] to 'category' for the requested language.
"""
import copy

from . import content, corpus_bridge, citation_tags


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
        flat["body"] = citation_tags.strip_tags(it["text"][lang])
        lr = flat.get("leader_reference")
        if isinstance(lr, dict):
            lr = copy.deepcopy(lr)
            for key in ("text", "verse"):
                m = lr.get(key)
                if isinstance(m, dict) and isinstance(m.get(lang), str):
                    m[lang] = citation_tags.strip_tags(m[lang])
            flat["leader_reference"] = lr
        if "category" in it and lang in it["category"]:
            flat["category"] = it["category"][lang]
        items.append(flat)
    return {"pericopes": pericopes, "items": items}


def load_sections(book, lang="en"):
    """Flattened section list for the selector: title[lang] -> 'title'."""
    from corpus.lib import sections as sections_lib
    out = []
    for s in sections_lib.load(book)["sections"]:
        title = s.get("title_zh") if lang == "zh" and s.get("title_zh") else s["title_en"]
        out.append({
            "id": s["id"], "title": title,
            "first_pericope": s["first_pericope"],
            "last_pericope": s["last_pericope"],
            "marker": s.get("marker"),
        })
    return out
