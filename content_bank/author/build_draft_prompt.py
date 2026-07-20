"""Assemble the Stage-2 drafting pack for one pericope.

Passage-first: the pericope's verses are the subject; the theological base is the
committed brief (author/briefs/<pericope>.md, produced by Stage 1). The full
lampposts are NOT here — only a compact WCF-1 guardrail. Offline, no API."""
import argparse
import pathlib

from ..lib import corpus_bridge, schema
from . import dimensions, rubric

_BRIEFS = pathlib.Path(__file__).parent / "briefs"

_WCF1_GUARDRAIL = """Draft WITHIN the Westminster Confession's doctrine of Scripture
(WCF ch.1): God-inspired, infallible, inerrant, sufficient, clear; Scripture
interprets Scripture. Hedging on this fails review. (Full chapter and this
passage's doctrinal anchors are distilled in the brief above.)"""

_RULES_BLOCK = """## How to draft (hard rules)

- ANSWERABLE FROM THIS PASSAGE: every item except a D5 (Connections) item must be
  answerable from the verses above alone. D5 may reach only a cross-reference
  named in the brief, and must name it.
- ONLY THE DIMENSIONS THIS PASSAGE GENUINELY SUPPORTS: a short setup passage may
  support D1/D2/D6 and not D7/D8 — that's correct, not a gap. Do not pad.
- EVIDENCE, NEVER JUDGMENT: prompts elicit observable behavior; never assess
  faith, character, or spiritual state.
- STAY ON THE PASSAGE: the brief is your base; items are about the PASSAGE.
- TIERS: spread across age_tiers (pre_reader/child/youth/adult/all), 1-3."""

_TYPE_BLOCK = """## What each type should be

Use ONLY these five types this cycle — not vocab_list or key_facts (the prototype
selector does not render them):
- question: one clear question; tag the dimension it exercises.
- activity: doable on paper with ordinary materials; add a pre_reader variant
  when the passage allows.
- pre_reading_quest: "listen for X" prompt with a short `category` label, at
  child/youth/adult tiers. Its "listen-for" form is fact-noticing — tag it
  D1/D2/D3/D4. Only tag it D5/D6/D7 if the prompt itself asks the listener to
  hunt for a connection, form a question, or notice a *why* (not just spot a fact).
- memory_verse: one or two verses from THIS passage, verbatim, with reference.
- narration_prompt: "retell in your own words" for the passage as a whole."""

_SCHEMA_BLOCK = """Each item MUST be a JSON object with these fields:
  id, passage (pericope id), dimension ({dimensions}),
  type ({types}), age_tier ({tiers}), difficulty (1|2|3),
  review_status "draft", text {{ "en": "..." }}, version 1,
  category {{ "en": "..." }} ONLY for pre_reading_quest,
  leader_reference {{ ... }} per the "Leader references" section above
  (on every item EXCEPT memory_verse)."""

_REFERENCE_BLOCK = """## Leader references (leader-only; author them inline)

Author a leader-only `leader_reference` on every item EXCEPT `memory_verse` (a
memory_verse item gets NO leader_reference — the printed verse is the answer).
CLOSED dimensions (D1-D5) -> kind "answer_key"; OPEN dimensions (D6-D8) -> kind
"leader_note". Shape:

  "leader_reference": {
    "kind": "answer_key" | "leader_note",
    "text": { "en": "..." },
    "verse": { "en": "Philippians 1:6" },      // answer_key ONLY; omit for notes
    "provenance": { "reviewed_by": "claude-draft",
                    "reviewed_date": "2026-07-20", "guardrail": "WCF-1" }
  }

- answer_key (D1-D5): the concise, correct expected response plus the verse it comes
  from, grounded in THIS passage + the brief. A wrong answer key is worse than none.
- leader_note (D6-D8): point where the text leads and flag common misreadings, but
  KEEP THE QUESTION OPEN — never a canned answer read aloud, never leading beyond the
  text.
- The `provenance` above is a draft stub (the human reviewer overwrites it on
  confirmation); keep `guardrail` exactly "WCF-1"."""

_READING_MOVES_PTR = (" -> consult the brief's *Reading moves* note for this "
                      "passage's genre-specific emphasis (if present).")


def _load_brief(pericope_id):
    f = _BRIEFS / f"{pericope_id.lower()}.md"
    if not f.exists():
        raise FileNotFoundError(
            f"No brief for {pericope_id}; run Stage 1 (build_brief_prompt) and "
            f"commit {f} first.")
    return f.read_text(encoding="utf-8")


def build(pericope_id, book="MAT", brief=None):
    if brief is None:
        brief = _load_brief(pericope_id)
    peris = {p["id"]: p for p in corpus_bridge.pericopes(book)}
    if pericope_id not in peris:
        raise ValueError(f"{pericope_id} is not a {book} pericope")
    p = peris[pericope_id]
    name = corpus_bridge.book_name(book, "en")
    parts = [f"# Draft pack — {pericope_id}: {p['title_en']}\n",
             f"Passage: {name} ({p['range']})\n",
             "## THE PASSAGE — your SUBJECT\n",
             corpus_bridge.passage_text(p["range"]) + "\n",
             "## Theological base (brief — consult, do not draft about)\n",
             brief + "\n",
             "## Confessional guardrail\n",
             _WCF1_GUARDRAIL + "\n",
             "## Dimensions to cover\n"]
    for d, desc in dimensions.TEMPLATES.items():
        line = f"- {d}: {desc}"
        if d in ("D3", "D7"):
            line += _READING_MOVES_PTR
        parts.append(line)
    parts.append("")
    parts.append(_RULES_BLOCK)
    parts.append("")
    parts.append(_TYPE_BLOCK)
    parts.append("")
    parts.append("## Quality rubric (all seven axes)\n")
    parts.append(rubric.build())
    parts.append("")
    parts.append(_REFERENCE_BLOCK)
    parts.append("")
    parts.append("## Leader-reference review criteria\n")
    parts.append(rubric.reference_criteria())
    parts.append("")
    parts.append("## Output schema\n")
    parts.append(_SCHEMA_BLOCK.format(
        dimensions=", ".join(sorted(schema.DIMENSIONS)),
        types=", ".join(sorted(schema.TYPES)),
        tiers=", ".join(sorted(schema.AGE_TIERS))))
    parts.append("")
    parts.append("Return a JSON array of draft items.")
    return "\n".join(parts)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("pericope_id")
    ap.add_argument("--book", default="MAT")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    text = build(args.pericope_id, args.book)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        print(text)


if __name__ == "__main__":
    main()
