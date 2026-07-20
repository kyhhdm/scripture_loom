"""Assemble the Stage-1 distillation pack for one SECTION (book-arc brief).

Offline: prints a self-contained pack a human/model runs to produce a compact arc
brief for the section — the spine that runs across its pericopes, recurring motifs
(candidate threads) with member refs, the cross-pericope connections, and doctrinal
anchors. The section analogue of build_brief_prompt; its output is drafted FROM by
build_section_draft_prompt (Stage 2)."""
import argparse

from corpus.lib import sections as _sections
from ..lib import corpus_bridge

_SHAPE = """## Produce the SECTION ARC BRIEF

~250 words (hard max 350), in exactly these four parts, drawn only from the passages
above and their commentary — NOT from outside knowledge:

**Arc spine (primary).** In the text's own terms, the single movement that runs
across these pericopes: how the section opens, turns, and lands. This governs the
section's throughline.
**Recurring motifs (candidate threads).** Words, phrases, or images that RECUR
across two or more of the section's pericopes and carry its argument. For each: the
motif, its member verse refs (e.g. PHP.1.5, PHP.4.15), and one phrase on what the
recurrence teaches. List only genuine cross-pericope recurrences; if there are none,
write "none".
**Cross-pericope connections.** How each pericope builds on the one before — the
joints between stations that the zoom-out questions can probe. Name the moves, not a
per-pericope summary.
**Doctrinal anchors.** Method: WCF ch.1 (inspired, sufficient, Scripture-interprets-
Scripture). Name only doctrine the section's own text bears; add none it does not
state.

SAFEGUARD — stay at the ARC level: motifs and moves that SPAN pericopes, not what a
single pericope already covers on its own (that is the pericope briefs' job). Quote
words verbatim from the passages. Add no doctrine the text does not state; keep to
observable meaning. End with a one-line note of anything set aside as off-arc."""


def build(section_id, book="MAT"):
    secs = {s["id"]: s for s in _sections.load(book)["sections"]}
    if section_id not in secs:
        raise ValueError(f"{section_id} is not a {book} section")
    sec = secs[section_id]
    peris = corpus_bridge.pericopes(book)
    ids = [p["id"] for p in peris]
    i, j = ids.index(sec["first_pericope"]), ids.index(sec["last_pericope"])
    span = peris[i:j + 1]

    parts = [f"# Section brief pack — {section_id}: {sec['title_en']}\n",
             f"Spans {sec['first_pericope']}..{sec['last_pericope']} "
             f"({len(span)} pericopes) — the stations of the arc:\n",
             "\n".join(f"- {p['id']} — {p['title_en']} ({p['range']})" for p in span)
             + "\n",
             "## The section's pericopes (public-domain text) — the SUBJECT\n"]
    for p in span:
        parts.append(f"### {p['id']} — {p['title_en']} ({p['range']})\n"
                     f"{corpus_bridge.passage_text(p['range'])}\n")
    parts.append("## WCF Chapter 1 — the method guardrail (full)\n"
                 + corpus_bridge.wcf_chapter1_text() + "\n")
    parts.append("## Cross-references across the span (Scripture interprets Scripture)"
                 " — aids for spotting recurrences\n")
    refs = []
    for p in span:
        refs.extend(corpus_bridge.crossrefs(p["range"]))
    parts.append("\n".join(f"- {r['from']} -> {r['to']} (weight {r.get('weight')})"
                           for r in refs) if refs else "(none)")
    parts.append("\n\n" + _SHAPE)
    return "\n".join(parts)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("section_id")
    ap.add_argument("--book", default="MAT")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    text = build(args.section_id, args.book)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        print(text)


if __name__ == "__main__":
    main()
