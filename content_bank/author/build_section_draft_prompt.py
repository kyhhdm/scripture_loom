"""Assemble the Stage-2 draft prompt for one SECTION (book-arc content).

Given the section's arc brief (Stage 1, build_section_brief_prompt), produces the
section's authored arc content — one throughline, named cross-pericope threads, and
arc questions — under the WCF-1 guardrail, reviewed before publish. The section
analogue of build_draft_prompt."""
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

_OUTPUT_SCHEMA = """## Output — a JSON array of section-scoped ContentItems

Return ONLY a JSON array (no prose). Produce exactly one throughline, zero or more
threads, and 2-4 arc questions, using the section id <SID> (lower-case in ids) and
book <BOOK>:

- EXACTLY ONE throughline:
  {"id":"<sid>-throughline","section":"<SID>","dimension":"D7","type":"throughline","age_tier":"all","difficulty":2,"review_status":"draft","text":{"en":"..."},"version":1}
- ZERO OR MORE threads (only if the motif genuinely RECURS across 2+ pericopes):
  {"id":"<sid>-thread-<slug>","section":"<SID>","dimension":"D7"|"D3","type":"thread","age_tier":"all","difficulty":2,"review_status":"draft","text":{"en":"<name + what the recurrence teaches>"},"refs":["<BOOK>.C.V","..."],"version":1}
  (refs = >=2 member verses where the motif recurs)
- 2-4 arc QUESTIONS answerable only ACROSS the section:
  {"id":"<sid>-q-<slug>","section":"<SID>","dimension":"D5"|"D6"|"D7","type":"question","age_tier":"youth"|"adult"|"all","difficulty":2|3,"review_status":"draft","text":{"en":"..."},"version":1}
  Give D6/D7 a leader_note and D5 an answer_key, each with a leader_reference and
  provenance {"reviewed_by":"claude","reviewed_date":"2026-07-20","guardrail":"WCF-1"};
  throughline/thread need no leader_reference.

Keep exactly one throughline. Quoted words must be verbatim BSB."""


def build(section_id, book="MAT", brief=""):
    secs = {s["id"]: s for s in _sections.load(book)["sections"]}
    if section_id not in secs:
        raise ValueError(f"{section_id} is not a {book} section")
    sec = secs[section_id]
    peris = corpus_bridge.pericopes(book)
    ids = [p["id"] for p in peris]
    i, j = ids.index(sec["first_pericope"]), ids.index(sec["last_pericope"])
    span = peris[i:j + 1]

    parts = [f"# Section draft pack — {section_id}: {sec['title_en']}\n",
             f"Spans {sec['first_pericope']}..{sec['last_pericope']} "
             f"({len(span)} pericopes)\n",
             "## The section's pericopes (public-domain text) — the SUBJECT\n"]
    for p in span:
        parts.append(f"### {p['id']} — {p['title_en']} ({p['range']})\n"
                     f"{corpus_bridge.passage_text(p['range'])}\n")
    parts.append("## WCF Chapter 1 — the method guardrail (full)\n"
                 + corpus_bridge.wcf_chapter1_text() + "\n")
    if brief and brief.strip():
        parts.append("## Section arc brief (Stage 1) — the distilled spine to draft "
                     "FROM\n" + brief.strip() + "\n")
    parts.append(_SHAPE)
    parts.append("\n" + _OUTPUT_SCHEMA
                 .replace("<SID>", section_id)
                 .replace("<sid>", section_id.lower())
                 .replace("<BOOK>", book))
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
