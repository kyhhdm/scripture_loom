"""Assemble the Stage-1 distillation pack for one SECTION (book-arc content).

Offline: prints a self-contained pack a human/Claude runs by hand to produce the
section's authored arc content — one throughline, named cross-pericope threads,
and arc questions — under the WCF-1 guardrail, reviewed before publish."""
import argparse

from corpus.lib import sections as _sections
from ..lib import corpus_bridge

_SHAPE = """## Produce the SECTION ARC CONTENT

Under WCF ch.1 (inspired, sufficient, Scripture-interprets-Scripture), and only
from what the text above states, draft:

**THROUGHLINE (exactly one, dimension D7).** One or two sentences: what this whole
section is about, in the text's own terms. This is what the zoom-out session prints.

**THREADS (zero or more, dimension D7 or D3).** A word, phrase, or motif that RECURS
across two or more of the section's pericopes and carries the section's argument.
For each: a name, its member verse `refs` (e.g. MAT.1.22, MAT.2.15), and a one- or
two-sentence interpretive note (what the recurrence teaches). A thread may extend
beyond this section — anchor it here if this section is its payoff.

**QUESTIONS (2-4, dimension D5/D6/D7).** Cross-pericope discussion questions for the
zoom-out — answerable only across the section, not from one pericope.

SAFEGUARD — add no doctrine the text does not state; keep to observable meaning."""


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
             f"({len(span)} pericopes)\n",
             "## The section's pericopes (public-domain text) — the SUBJECT\n"]
    for p in span:
        parts.append(f"### {p['id']} — {p['title_en']} ({p['range']})\n"
                     f"{corpus_bridge.passage_text(p['range'])}\n")
    parts.append("## WCF Chapter 1 — the method guardrail (full)\n"
                 + corpus_bridge.wcf_chapter1_text() + "\n")
    parts.append(_SHAPE)
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
