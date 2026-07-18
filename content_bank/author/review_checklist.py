"""Print the draft -> reviewed -> published review checklist a human fills in."""
import argparse

_CHECKLIST = """# Content review checklist ({guardrail})

Advance an item draft -> reviewed -> published only when every box is checked.

## Confessional conformity (Westminster Confession, Chapter 1)
- [ ] Affirms, and does not hedge on, Scripture's inspiration, infallibility,
      inerrancy, sufficiency, and clarity.
- [ ] Treats Scripture as interpreting Scripture (WCF 1.9); no private novelty.
- [ ] Draws meaning from the text, not from speculation.

## Accuracy
- [ ] Every factual claim is correct against the passage and the corpus lampposts.
- [ ] Names, places, sequence, and quotations match the text.

## Age fitness
- [ ] Language and difficulty match the item's age_tier.
- [ ] Activities are doable on paper with the stated materials.

## Evidence, never judgment
- [ ] Prompts elicit observable behavior, never assessments of faith or character.

On pass, stamp provenance:
  reviewed_by, reviewed_date, guardrail={guardrail}, and set review_status.
"""


def build(guardrail="WCF-1"):
    return _CHECKLIST.format(guardrail=guardrail)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--guardrail", default="WCF-1")
    args = ap.parse_args(argv)
    print(build(args.guardrail))


if __name__ == "__main__":
    main()
