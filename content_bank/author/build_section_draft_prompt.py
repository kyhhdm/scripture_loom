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

**THROUGHLINE (exactly one, dimension D7).** A discovery QUESTION (not a
statement) that leads the reader to this section's spine — what the whole section
is driving at, in the text's own terms. Attach the spine itself as a leader-only
`leader_reference` (kind "leader_note"): the one- or two-sentence arc the reader
checks against after answering. The stem must be answerable FROM the text and must
not embed its own answer. This is what the zoom-out session prints.

**THREADS (zero or more, dimension D7 or D3).** For a word, phrase, or motif that
RECURS across two or more of the section's pericopes and carries the section's
argument: a discovery QUESTION that names the motif and asks what its recurrence
reveals, its member verse `refs` (e.g. MAT.1.22, MAT.2.15), and a leader-only
`leader_reference` holding the traced result (what the recurrence teaches). The
reveal `kind` follows the dimension: D3 (tracked key word) -> "answer_key" (with
the verse); D7 (interpretive movement) -> "leader_note". A thread may extend
beyond this section — anchor it here if this section is its payoff.

**QUESTIONS (2-4, dimension D5/D6/D7).** Cross-pericope discussion questions for the
zoom-out — answerable only across the section, not from one pericope.

SAFEGUARD — add no doctrine the text does not state; keep to observable meaning."""

_TAGGING_BLOCK = """## Citation tagging (hard requirement)

Every verbatim Scripture quote MUST be wrapped inline so the gate can verify it:
- `<verse ref="PHP.1.6">exact BSB words</verse>` — `ref` in canonical corpus
  format (`BOOK.CHAPTER.VERSE`, e.g. `PHP.1.6`, or a range `PHP.1.1-11`); the
  inner text is the exact BSB wording.
- A THREAD note typically strings several short quotes drawn from DIFFERENT
  verses across the section — wrap EACH quoted span in its OWN `<verse>` with
  its own `ref` (the same verses you list in the item's `refs`). Do not leave
  any quoted phrase untagged.
- A claim resting on the Westminster Standards: wrap the paraphrase in
  `<doctrine std="WCF" ref="1.4">your paraphrase</doctrine>` — `std` is
  WCF/WLC/WSC; `ref` is chapter.section for WCF (`1.4`) or `Q<n>` for WLC/WSC
  (`Q1`). The inner text is your paraphrase, not a quote.
- Tag marked quotations down to a 4-word floor; do NOT tag incidental
  single-word overlap. Keep every tag well-formed — a matching close tag and
  only the attributes shown — malformed markup fails the gate."""

_OUTPUT_SCHEMA = """## Output — a JSON array of section-scoped ContentItems

Return ONLY a JSON array (no prose). Produce exactly one throughline, zero or more
threads, and 2-4 arc questions, using the section id <SID> (lower-case in ids) and
book <BOOK>:

- EXACTLY ONE throughline — a D7 discovery question carrying its spine as a leader_note reveal:
  {"id":"<sid>-throughline","section":"<SID>","dimension":"D7","type":"throughline","age_tier":"all","difficulty":2,"review_status":"draft","text":{"en":"<question stem leading to the spine>"},"leader_reference":{"kind":"leader_note","text":{"en":"<the one/two-sentence arc, in the text's own terms>"}},"version":1}
- ZERO OR MORE threads (only if the motif genuinely RECURS across 2+ pericopes) — a discovery question carrying the traced result as its reveal:
  {"id":"<sid>-thread-<slug>","section":"<SID>","dimension":"D7"|"D3","type":"thread","age_tier":"all","difficulty":2,"review_status":"draft","text":{"en":"<question naming the motif + asking what its recurrence reveals>"},"refs":["<BOOK>.C.V","..."],"leader_reference":{"kind":"leader_note"|"answer_key","text":{"en":"<name + what the recurrence teaches>"}},"version":1}
  (refs = >=2 member verses where the motif recurs; a D3 thread's reveal kind is "answer_key" and adds "verse":{"en":"..."}, a D7 thread's is "leader_note")
- 2-4 arc QUESTIONS answerable only ACROSS the section. EVERY question MUST carry a
  leader-only `leader_reference`. `kind` is EXACTLY "answer_key" or "leader_note"
  (no other value): a D5 question -> "answer_key" (with the verse it comes from);
  a D6 or D7 question -> "leader_note" (no verse). Shapes:
  D5 (answer_key):
  {"id":"<sid>-q-<slug>","section":"<SID>","dimension":"D5","type":"question","age_tier":"youth"|"adult"|"all","difficulty":2|3,"review_status":"draft","text":{"en":"..."},"leader_reference":{"kind":"answer_key","text":{"en":"the concise correct answer, drawn across the section"},"verse":{"en":"Philippians 2:5-8"}},"version":1}
  D6/D7 (leader_note):
  {"id":"<sid>-q-<slug>","section":"<SID>","dimension":"D6"|"D7","type":"question","age_tier":"youth"|"adult"|"all","difficulty":2|3,"review_status":"draft","text":{"en":"..."},"leader_reference":{"kind":"leader_note","text":{"en":"point where the text leads; flag a common misreading; keep the question open"}},"version":1}
  Every throughline and thread MUST carry a leader_reference reveal whose kind
  matches its dimension: D3 -> "answer_key" (with "verse"), D7 -> "leader_note".

Keep exactly one throughline. Quoted words must be verbatim BSB, and every
quoted span must be wrapped per the Citation tagging section above."""


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
    parts.append("\n" + _TAGGING_BLOCK)
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
