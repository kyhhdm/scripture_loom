"""Store-level validation: schema, ID uniqueness, corpus referential integrity,
and bilingual coverage counts."""
from . import schema, content, corpus_bridge


def validate_store(book, store_dir=None):
    items = content.load_book_store(book, store_dir).get("items", [])
    valid_ids = corpus_bridge.pericope_ids(book)
    valid_sections = corpus_bridge.section_ids(book)
    errors = []
    seen = set()

    for it in items:
        iid = it.get("id", "<no-id>")
        for e in schema.validate_item(it):
            errors.append(f"{iid}: {e}")
        if iid in seen:
            errors.append(f"{iid}: duplicate id")
        seen.add(iid)
        p = it.get("passage")
        if p is not None and p not in valid_ids:
            errors.append(f"{iid}: passage '{p}' is not a {book} pericope")
        s = it.get("section")
        if s is not None and s not in valid_sections:
            errors.append(f"{iid}: section '{s}' is not a {book} section")
        if it.get("type") == "thread":
            for r in it.get("refs", []):
                if isinstance(r, str) and r.split(".", 1)[0] != book:
                    errors.append(f"{iid}: ref '{r}' outside book {book}")

    published_tl = {}
    for it in items:
        if it.get("type") == "throughline" and it.get("review_status") == "published":
            sec = it.get("section")
            published_tl[sec] = published_tl.get(sec, 0) + 1
    for sec, n in published_tl.items():
        if n > 1:
            errors.append(f"section {sec}: {n} published throughlines (max 1)")

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
    refs = [i["leader_reference"] for i in items if i.get("leader_reference")]
    counts["references"] = {
        "total": len(refs),
        "answer_key": sum(1 for r in refs if r.get("kind") == "answer_key"),
        "leader_note": sum(1 for r in refs if r.get("kind") == "leader_note"),
        "missing_reference": sum(
            1 for i in items
            if i.get("type") in ("question", "pre_reading_quest")
            and not i.get("leader_reference")),
    }
    counts["missing_zh"] = counts["items"] - counts["by_lang"]["zh"]
    counts["missing_en"] = counts["items"] - counts["by_lang"]["en"]
    return {"errors": errors, "counts": counts}
