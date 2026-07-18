"""Print the draft -> reviewed -> published review checklist a human fills in.
Mirrors the seven-axis rubric (author/rubric.py)."""
import argparse

from . import rubric

_HEAD = """# Content review checklist ({guardrail})

Advance an item draft -> reviewed -> published only when every box is checked.
Judged against the seven-axis rubric:

"""

_BOXES = """
## Confessional conformity ({guardrail}: Westminster Confession, Chapter 1)
- [ ] Affirms, and does not hedge on, Scripture's inspiration, infallibility,
      inerrancy, sufficiency, and clarity.
- [ ] Scripture interprets Scripture (WCF 1.9); meaning from the text.

## Accuracy & answerability
- [ ] Every factual claim is correct against the passage and the brief.
- [ ] Names, places, sequence, and quotations match the text.
- [ ] Answerable from THIS pericope's verses (D5 may name a brief cross-reference).

## Evidence, never judgment
- [ ] Elicits observable behavior; never assesses faith, character, or state.

## Age fitness
- [ ] Language and difficulty match age_tier; activities doable on paper.

## Dimension fit
- [ ] Genuinely exercises its tagged fluency dimension.

## Worship, not academy
- [ ] Serves fluency and the heart; nothing during-session.

## Pedagogical strength
- [ ] A good prompt: open where it should be, not leading, not trivially yes/no.

## Leader references (leader-only; never printed)
- [ ] Answer keys (D1-D5): expected response correct and grounded in the passage
      + brief; the cited verse actually contains it.
- [ ] Leader notes (D6-D8): keep the question open; no canned answer, not leading.
- [ ] No reference on a memory_verse item.

On pass, stamp provenance:
  reviewed_by, reviewed_date, guardrail={guardrail}, and set review_status.
"""


def build(guardrail="WCF-1"):
    return _HEAD + rubric.build() + rubric.reference_criteria() + _BOXES.format(guardrail=guardrail)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--guardrail", default="WCF-1")
    args = ap.parse_args(argv)
    print(build(args.guardrail))


if __name__ == "__main__":
    main()
