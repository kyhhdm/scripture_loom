"""Store-level validation: schema, ID uniqueness, corpus referential integrity,
and bilingual coverage counts."""
from . import schema, content, corpus_bridge


def validate_store(book, store_dir=None):
    items = content.load_book_store(book, store_dir).get("items", [])
    valid_ids = corpus_bridge.pericope_ids(book)
    errors = []
    seen = set()

    for it in items:
        iid = it.get("id", "<no-id>")
        for e in schema.validate_item(it):
            errors.append(f"{iid}: {e}")
        if iid in seen:
            errors.append(f"{iid}: duplicate id")
        seen.add(iid)
        if it.get("passage") not in valid_ids:
            errors.append(f"{iid}: passage '{it.get('passage')}' is not a {book} pericope")

    counts = {
        "items": len(items),
        "published": sum(1 for i in items if i.get("review_status") == "published"),
        "draft": sum(1 for i in items if i.get("review_status") == "draft"),
        "reviewed": sum(1 for i in items if i.get("review_status") == "reviewed"),
        "by_lang": {
            "en": sum(1 for i in items if "en" in (i.get("text") or {})),
            "zh": sum(1 for i in items if "zh" in (i.get("text") or {})),
        },
    }
    counts["missing_zh"] = counts["items"] - counts["by_lang"]["zh"]
    counts["missing_en"] = counts["items"] - counts["by_lang"]["en"]
    return {"errors": errors, "counts": counts}
