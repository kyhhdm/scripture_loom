"""Tiered-by-risk review digest for one build unit.

Closed dimensions (D1-D5) are batch-reviewed together; open dimensions
(D6-D8) and section-scoped types (throughline/thread) are reviewed item by
item. Renders Markdown for a human. Stdlib only, offline.
"""

BATCH_DIMENSIONS = {"D1", "D2", "D3", "D4", "D5"}
_ITEM_TYPES = {"throughline", "thread"}


def tier_of(item):
    if item.get("type") in _ITEM_TYPES:
        return "item"
    if item.get("dimension") not in BATCH_DIMENSIONS:
        return "item"
    return "batch"


def build_digest(unit_id, items, verdicts):
    return {
        "unit": unit_id,
        "batch": [it for it in items if tier_of(it) == "batch"],
        "item_tier": [it for it in items if tier_of(it) == "item"],
        "verdicts": verdicts,
    }


def _verdict_lines(item_id, verdicts):
    lines = []
    for v in verdicts.get(item_id, []):
        lines.append(f"  - {v['reviewer']}: {v['verdict']} — {v.get('notes', '')}")
    return lines


def _item_block(it, verdicts):
    scope = it.get("passage") or it.get("section")
    lines = [f"- **{it['id']}** [{it['dimension']}/{it['type']}/{it['age_tier']}] "
             f"({scope}): {it['text'].get('en', '')}"]
    lines.extend(_verdict_lines(it["id"], verdicts))
    return lines


def render_digest(digest):
    out = [f"# Review digest — {digest['unit']}", ""]
    out.append("## Batch review (D1-D5) — confirm/reject together, spot-edit")
    for it in digest["batch"]:
        out.extend(_item_block(it, digest["verdicts"]))
    out.append("")
    out.append("## Item-by-item review (D6-D8, throughline, thread) — confirm each")
    for it in digest["item_tier"]:
        out.extend(_item_block(it, digest["verdicts"]))
    return "\n".join(out) + "\n"
