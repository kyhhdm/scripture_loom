"""Assemble an offline drafting prompt pack for one pericope.

No network, no API call: this prints a self-contained prompt a human (or Claude)
runs by hand to produce draft ContentItems, which content_bank.lib.validate then
checks before they enter the store.
"""
import argparse

from ..lib import corpus_bridge, schema
from . import dimensions

_SCHEMA_BLOCK = """Each item MUST be a JSON object with these fields:
  id             globally unique, stable, kebab-case
  passage        the pericope id below
  dimension      one of: {dimensions}
  type           one of: {types}
  age_tier       one of: {tiers}
  difficulty     one of: 1, 2, 3
  review_status  "draft"   (all newly drafted items start as draft)
  text           {{ "en": "...", "zh": "..." }}  (>= 1 language; en required for now)
  category       {{ "en": "..." }}  (ONLY for pre_reading_quest items)
  version        1
Do not add provenance; the human reviewer stamps it at publish time."""


def build(pericope_id, book="MAT"):
    peris = {p["id"]: p for p in corpus_bridge.pericopes(book)}
    if pericope_id not in peris:
        raise ValueError(f"{pericope_id} is not a {book} pericope")
    p = peris[pericope_id]
    name = corpus_bridge.book_name(book, "en")
    parts = []
    parts.append(f"# Drafting pack — {pericope_id}: {p['title_en']}\n")
    parts.append(f"Passage: {name} ({p['range']})\n")
    parts.append("## The passage (public-domain text)\n")
    parts.append(corpus_bridge.passage_text(p["range"]) + "\n")
    parts.append("## Confessional guardrail (a hard constraint on every item)\n")
    parts.append("Draft WITHIN the Westminster Confession of Faith. Content that "
                 "hedges on Scripture's reliability, inspiration, or sufficiency "
                 "fails review.\n")
    parts.append(corpus_bridge.wcf_chapter1_text() + "\n")
    parts.append("## Fluency dimensions to cover\n")
    for d, desc in dimensions.TEMPLATES.items():
        parts.append(f"- {d}: {desc}")
    parts.append("")
    parts.append("## Output schema\n")
    parts.append(_SCHEMA_BLOCK.format(
        dimensions=", ".join(sorted(schema.DIMENSIONS)),
        types=", ".join(sorted(schema.TYPES)),
        tiers=", ".join(sorted(schema.AGE_TIERS))))
    parts.append("")
    parts.append("Return a JSON array of draft items for this pericope.")
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
