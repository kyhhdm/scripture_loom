"""Compose a session kit from the selector's output and print it as markdown.

Usage:  python3 generate_kit.py [-o kit.md]
"""
import argparse
import json
import pathlib
import sys

import selector

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # repo root
from content_bank.lib import prototype_bank

HEART_PREPARATION = """\
> **Before you plan anything** — you are about to lead worship, not deliver a
> lesson. God will speak to your family in his Word; your preparation serves
> that, it cannot produce it.
>
> **First:** read {ref} once, slowly, as a hearer — not yet as a teacher.
> **Then pray** — for yourself, and for each member by name.
> Only then, review the plan below.\
"""

SESSION_ORDER = ("opening prayer → opening recall → first reading (cold) → "
                 "silent observation → hand out quests → second reading → narration → "
                 "question round → vocabulary → connection round → memory verse → "
                 "exit cards → closing prayer")


def compose(kit, names):
    out = []
    add = out.append

    if kit.get("kind") == "zoom_out":
        add(f"# Zoom-out Session — {kit['section']}")
        add(f"\n*Consolidation for {kit['family']}. No new passage this session.*\n")
        add("\n## Put the story in order\n")
        add("Shuffle these cards, then place them back in reading order:\n")
        for c in kit["sequence_cards"]:
            add(f"- {c['title']}  ({c['ref']})")
        add("\n*Leader's reference (correct order):* "
            + " → ".join(c["title"] for c in kit["sequence_cards"]))
        if kit["memory_recall"]:
            add("\n\n## Memory verses from this section\n")
            for m in kit["memory_recall"]:
                add(f"- {m['body']}")
        add(f"\n\n## Throughline\n\n{kit['throughline_prompt']}\n")
        add("\n---\n")
        for r in kit["roles"]:
            add(f"- **{r['role']}** — {r['member']}")
        return "\n".join(out)

    p = kit["passage"]
    add(f"# Session Kit — {p['ref']} ({p['title']})")
    add(f"\n*Generated for {kit['family']} from the content bank and member records.*\n")

    add("\n## Page 1 — Leader Guide\n")
    add(HEART_PREPARATION.format(ref=p["ref"]))
    add(f"\n**Session order:** {SESSION_ORDER}\n")

    add("\n### Opening recall (spaced review)\n")
    for q in kit["review_questions"]:
        add(f"- {q['body']}  `[{q['dimension']} {selector.DIMENSIONS[q['dimension']]}]`")
    for line in kit["personalized_lines"]:
        add(f"\n> *{line}*")

    if kit.get("arc_recap"):
        r = kit["arc_recap"]
        trail = " → ".join(r["studied"]) if r["studied"] else "(beginning this section)"
        add(f"\n> **The story so far — {r['section']} ({r['position']}):** {trail}\n")

    add("\n\n### Listen for — this session's observation targets\n")
    for i, t in enumerate(kit["observation_targets"], 1):
        add(f"{i}. **{names[t['member']]}** — {selector.DIMENSIONS[t['dimension']]}"
            f"  `[{t['dimension']}]`")
    add("\n*Watch for these only. Everything else is a bonus.*\n")

    add("\n### Key questions — after the second reading\n")
    for i, q in enumerate(kit["discussion_questions"], 1):
        add(f"{i}. {q['body']}  `[{q['dimension']}]`")

    if kit["narration_prompt"]:
        add(f"\n**Narration:** {kit['narration_prompt']['body']}\n")

    add("\n### Roles this session\n")
    for r in kit["roles"]:
        add(f"- {r['role']}: **{r['member']}**")

    if kit["memory_verse"]:
        add(f"\n### Memory verse\n\n> {kit['memory_verse']['body']}\n")

    add("\n## Page 2 — Quest slips (before the second reading)\n")
    for q in kit["quests"]:
        who = names[q["member"]] + (" *(leader — quest doubles as modeling)*" if q["leader"] else "")
        if q["text"] is None:
            add(f"**{who}** — stage {q['stage']}: *no prompt needed; asks unprompted.*\n")
        else:
            add(f"**{who}** — stage {q['stage']}:\n\n> {q['text']}\n")

    add("\n## Page 3 — Recall activity\n")
    if kit["activity"]:
        add(f"> {kit['activity']['body']}\n")
    if kit["activity_young"]:
        add(f"\n**Younger variant:**\n\n> {kit['activity_young']['body']}\n")

    add("\n## Page 4 — Leader observation grid\n")
    add("| Member | Q | A | R | C | U | P |\n|---|---|---|---|---|---|---|")
    for member_id, name in names.items():
        if not any(q["member"] == member_id and q["leader"] for q in kit["quests"]):
            add(f"| {name} | | | | | | |")
    add("\n`✓ clear  △ partial  ? follow up  ★ notable  ° unprompted`\n")
    reminders = " · ".join(
        f"{names[t['member']]}: {selector.DIMENSIONS[t['dimension']]}"
        for t in kit["observation_targets"])
    add(f"> *Three things only — {reminders}. Mark, don't write.*\n")

    add("\n---\n*Selected item ids (mark used after the session): "
        + ", ".join(f"`{i}`" for i in kit["selected_item_ids"]) + "*")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", default=HERE / "family.json", type=pathlib.Path)
    parser.add_argument("-o", "--out", type=pathlib.Path)
    args = parser.parse_args()

    bank = prototype_bank.load_bank("MAT", lang="en")
    sections = prototype_bank.load_sections("MAT", lang="en")
    family = json.loads(args.family.read_text())
    kit = selector.build_kit(bank, family, sections)
    names = {m["id"]: m["name"] for m in family["members"]}
    text = compose(kit, names)
    if args.out:
        args.out.write_text(text)
        print(f"Wrote {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
