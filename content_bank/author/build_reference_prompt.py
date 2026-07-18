"""Assemble the reference-authoring pack for one pericope.

For each eligible committed item (question + pre_reading_quest always; activity +
narration_prompt where it aids facilitation), instruct the drafter to produce a
typed leader-only reference grounded in the passage + the committed brief. Closed
dimensions get an answer_key (expected response + verse); open dimensions get a
leader_note that keeps the question open. Offline, stdlib-only, no API."""
import argparse
import pathlib

from ..lib import content, corpus_bridge, schema
from . import rubric

_BRIEFS = pathlib.Path(__file__).parent / "briefs"

_ALWAYS = {"question", "pre_reading_quest"}
_OPTIONAL = {"activity", "narration_prompt"}

_RULES = """## How to write each reference (hard rules)

- LEADER-ONLY: this text never prints on the kit. It prepares the leader to lead
  from memory; it is formation, not a crutch.
- GROUNDED: distill the passage + the brief above; add no private novelty; stay
  within the WCF-1 doctrine of Scripture.
- CLOSED dimensions (D1-D5) -> an ANSWER KEY: the concise expected response plus
  the verse it comes from. It must be correct and answerable from THIS passage.
  A wrong answer key is worse than none.
- OPEN dimensions (D6-D8) -> a LEADER NOTE: point where the text leads and flag
  common misreadings, but KEEP IT OPEN -- never a canned answer the leader would
  read out, never leading toward a reading the text does not compel.
- REDUCE CONFUSION, DON'T TRADE IT: a reference shines light and removes a
  confusion -- it must not create a new one. In guarding one truth, do not word it
  so that, read flatly, it denies another the church confesses (e.g. Jesus
  submitting to Scripture must not imply he lacks authority over it -- he is its
  divine Author). Keep the doctrinal ground balanced.
- question + pre_reading_quest ALWAYS get a reference. activity + narration_prompt
  get a reference only where it genuinely aids facilitation; otherwise omit it.
- memory_verse items get NO reference (the answer is the printed verse)."""

_SCHEMA = """## Output schema

Return a JSON array of objects, one per item you write a reference for:
  { "item_id": "<the item id>",
    "leader_reference": {
      "kind": "answer_key" | "leader_note",
      "text": { "en": "..." },
      "verse": { "en": "Matthew 4:1" }    // answer_key ONLY; omit for notes
    } }
answer_key only on D1-D5 items; leader_note only on D6-D8 items. Return only the
JSON array."""


def _load_brief(pericope_id):
    f = _BRIEFS / f"{pericope_id.lower()}.md"
    if not f.exists():
        raise FileNotFoundError(
            f"No brief for {pericope_id}; commit {f} first.")
    return f.read_text(encoding="utf-8")


def _eligible(item):
    return item.get("type") in _ALWAYS or item.get("type") in _OPTIONAL


def build(pericope_id, book="MAT", brief=None, store_dir=None):
    if brief is None:
        brief = _load_brief(pericope_id)
    peris = {p["id"]: p for p in corpus_bridge.pericopes(book)}
    if pericope_id not in peris:
        raise ValueError(f"{pericope_id} is not a {book} pericope")
    p = peris[pericope_id]
    items = [i for i in content.load_book_store(book, store_dir).get("items", [])
             if i.get("passage") == pericope_id and _eligible(i)]
    name = corpus_bridge.book_name(book, "en")

    parts = [f"# Reference pack -- {pericope_id}: {p['title_en']}\n",
             f"Passage: {name} ({p['range']})\n",
             "## THE PASSAGE -- ground every reference here\n",
             corpus_bridge.passage_text(p["range"]) + "\n",
             "## Theological base (brief)\n",
             brief + "\n",
             _RULES, "",
             "## Items needing a reference\n"]
    for i in items:
        d = i["dimension"]
        kind = "answer_key" if d in schema.CLOSED_DIMENSIONS else "leader_note"
        opt = "  (optional)" if i["type"] in _OPTIONAL else ""
        parts.append(f"- {i['id']} [{d} / {i['type']} / {kind}]{opt}: "
                     f"{i['text'].get('en', '')}")
    parts.append("")
    parts.append("## Reference review criteria\n")
    parts.append(rubric.reference_criteria())
    parts.append("")
    parts.append(_SCHEMA)
    return "\n".join(parts)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("pericope_id")
    ap.add_argument("--book", default="MAT")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    text = build(args.pericope_id, args.book)
    if args.out:
        pathlib.Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
