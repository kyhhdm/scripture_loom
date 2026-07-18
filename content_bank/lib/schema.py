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

REFERENCE_KINDS = {"answer_key", "leader_note"}
CLOSED_DIMENSIONS = {"D1", "D2", "D3", "D4", "D5"}
OPEN_DIMENSIONS = {"D6", "D7", "D8"}

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


def _check_reference(item, errors):
    ref = item["leader_reference"]
    if not isinstance(ref, dict):
        errors.append("leader_reference: must be an object")
        return
    kind = ref.get("kind")
    if kind not in REFERENCE_KINDS:
        errors.append(f"leader_reference.kind: invalid '{kind}'")
    if item.get("type") == "memory_verse":
        errors.append("leader_reference: not allowed on memory_verse items")
    _check_text("leader_reference.text", ref.get("text"), errors)

    dim = item.get("dimension")
    if kind == "answer_key" and dim not in CLOSED_DIMENSIONS:
        errors.append(
            f"leader_reference: answer_key only on closed dimensions "
            f"{sorted(CLOSED_DIMENSIONS)}, not '{dim}'")
    if kind == "leader_note" and dim not in OPEN_DIMENSIONS:
        errors.append(
            f"leader_reference: leader_note only on open dimensions "
            f"{sorted(OPEN_DIMENSIONS)}, not '{dim}'")

    if "verse" in ref:
        if kind != "answer_key":
            errors.append("leader_reference.verse: only allowed on answer_key")
        else:
            _check_text("leader_reference.verse", ref.get("verse"), errors)

    prov = ref.get("provenance") or {}
    if not prov.get("reviewed_by"):
        errors.append("leader_reference.provenance.reviewed_by: required")
    if not prov.get("reviewed_date"):
        errors.append("leader_reference.provenance.reviewed_date: required")
    if prov.get("guardrail") not in GUARDRAILS:
        errors.append("leader_reference.provenance.guardrail: must be 'WCF-1'")


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

    if "leader_reference" in item:
        _check_reference(item, errors)

    return errors
