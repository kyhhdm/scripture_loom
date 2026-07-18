"""ContentItem controlled vocabularies and structural validation.

Single source of truth for the content-bank vocabularies. Structural checks
only; referential integrity (passage resolves to a corpus pericope) and ID
uniqueness are store-level concerns (see validate.py).
"""

DIMENSIONS = {f"D{i}" for i in range(1, 9)}
TYPES = {"question", "activity", "vocab_list", "memory_verse",
         "key_facts", "narration_prompt", "pre_reading_quest"}
AGE_TIERS = {"pre_reader", "child", "youth", "adult", "all"}
REVIEW_STATUSES = {"draft", "reviewed", "published"}
LANGS = {"en", "zh"}
GUARDRAILS = {"WCF-1"}
DIFFICULTIES = {1, 2, 3}

_REQUIRED = ("id", "passage", "dimension", "type", "age_tier",
             "difficulty", "review_status", "text", "version")


def _check_text(field, value, errors):
    if not isinstance(value, dict) or not value:
        errors.append(f"{field}: must be a non-empty language map")
        return
    for lang, s in value.items():
        if lang not in LANGS:
            errors.append(f"{field}: unknown language '{lang}'")
        if not isinstance(s, str) or not s.strip():
            errors.append(f"{field}: language '{lang}' text is empty")


def validate_item(item):
    """Return a list of error strings; empty means the item is structurally valid."""
    errors = []
    for field in _REQUIRED:
        if field not in item:
            errors.append(f"missing required field: {field}")
    if errors:
        return errors

    if item["dimension"] not in DIMENSIONS:
        errors.append(f"dimension: invalid '{item['dimension']}'")
    if item["type"] not in TYPES:
        errors.append(f"type: invalid '{item['type']}'")
    if item["age_tier"] not in AGE_TIERS:
        errors.append(f"age_tier: invalid '{item['age_tier']}'")
    if item["review_status"] not in REVIEW_STATUSES:
        errors.append(f"review_status: invalid '{item['review_status']}'")
    if item["difficulty"] not in DIFFICULTIES:
        errors.append(f"difficulty: must be one of {sorted(DIFFICULTIES)}")

    _check_text("text", item["text"], errors)

    if "category" in item:
        if item["type"] != "pre_reading_quest":
            errors.append("category: only allowed on pre_reading_quest items")
        else:
            _check_text("category", item["category"], errors)

    if item["review_status"] != "draft":
        prov = item.get("provenance") or {}
        if not prov.get("reviewed_by"):
            errors.append("provenance.reviewed_by: required once not draft")
        if not prov.get("reviewed_date"):
            errors.append("provenance.reviewed_date: required once not draft")
        if prov.get("guardrail") not in GUARDRAILS:
            errors.append("provenance.guardrail: must be 'WCF-1' once not draft")

    return errors
