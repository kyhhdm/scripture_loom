# Content-bank prototype content: generate, judge, tune

- **Date:** 2026-07-18
- **Depends on:** the content-bank *infrastructure* (`content_bank/`, PR #1) and the
  corpus (`corpus/`). Both are treated as fixed dependencies here.
- **Status:** design approved; ready for an implementation plan.

## Goal

Generate the first real, harness-produced content bank for the kit-generator
prototype's passages, judge its quality with independent adversarial review, and
feed recurring defects back into the authoring machinery. **The content is the
test case; tuning the machinery is the durable outcome.**

This is the "author a real slice on top of the infrastructure" cycle named as a
follow-up in `docs/sessions/2026-07-18-content-bank-infrastructure.md`, scoped
down to exactly what the prototype exercises.

## Scope

**In scope** — regenerate content for the prototype's reading-sequence pericopes,
replacing the 25 hand-migrated seed items:

- `MAT-009` The Temptation of Jesus (4:1-11)
- `MAT-013` The Sermon on the Mount — setup (5:1-2)
- `MAT-014` The Beatitudes (5:3-12)
- `MAT-015` Salt and Light (5:13-16)

**Out of scope** (explicit, so the plan does not drift):

- Chinese text. English-only this cycle; a `zh` pass and a distinct
  zh-conformity review are a later cycle (the design already flags
  `review_checklist.py` as English-centric).
- The `vocab_list` and `key_facts` item types. They exist in the schema but the
  prototype selector does not render them.
- Any other Matthew pericope. 149 of the 153 stay empty.
- Changing the corpus, the store schema/vocabularies (`schema.py`), the gate
  (`content.py`), or the selector logic (`selector.py`).

## Locked decisions

1. **Content + tune the machinery.** Effort lands on producing good content *and*
   improving `author/` from what the content teaches us.
2. **Regenerate all, replace seed.** The hand-migrated items are discarded; the
   harness output becomes the store. (No head-to-head merge.)
3. **Adversarial reviewer agents** are the quality signal — independent of the
   drafter, one lens per risk axis, prompted to *break* each item. Substance is
   judged, never keyword-linted (preserves the infrastructure invariant that the
   software proves an item was *reviewed*, not that it is *sound*).
4. **English-only.**
5. **MAT-013 joins the reading sequence** → `MAT-009 → MAT-013 → MAT-014 →
   MAT-015`. This gives the Beatitudes their "crowds / mountain / disciples"
   People-&-Places (D1) setup a real, *answerable-from-its-own-text* home.
6. **`reviewed` + confirmation digest.** Adversarial pass advances items to
   `review_status: "reviewed"`; a human confirms before anything is stamped
   `"published"`. Honors "AI proposes, the leader confirms."

## The quality rubric

A single written standard, derived from the design invariants
(`docs/core_principles.md`, `CLAUDE.md`), that **both** the adversarial reviewers
and `author/review_checklist.py` score against. Seven axes:

1. **Confessional conformity (WCF-1).** Affirms — and never hedges on —
   Scripture's inspiration, infallibility, inerrancy, sufficiency, clarity.
   Scripture interprets Scripture (WCF 1.9); no private novelty.
2. **Accuracy & answerability.** Every factual claim is correct against the
   passage and the corpus lampposts; names, places, sequence, and quotations
   match. **New, sharpened rule:** the item must be *answerable from this
   pericope's own text* — a question whose answer lives only in an adjacent
   pericope is a defect, not a cross-reference. (D5 "Connections" is the sole
   exception and must name where it reaches.)
3. **Evidence, never judgment.** Prompts elicit observable behavior; they never
   ask for or imply assessments of faith, character, or spiritual state.
4. **Age fitness.** Language and difficulty match the item's `age_tier`;
   activities are doable on paper with ordinary materials.
5. **Dimension fit.** The item genuinely exercises its tagged dimension (a D2
   item is about sequence, not vocabulary wearing a D2 label).
6. **Worship, not academy.** Serves fluency and the heart, not academic trivia;
   nothing that belongs to the denied during-session category (live scoring,
   gamification, etc.).
7. **Pedagogical strength.** A genuinely good prompt: open where it should be
   open, not leading, not trivially yes/no unless deliberately a warm-up.

**Coverage principle (falls out of MAT-013):** cover every dimension the passage
*genuinely supports*, at the tiers the selector needs — no more. Forcing a
dimension a thin text cannot carry (e.g. D7 interpretation on the 2-verse 5:1-2
setup) violates axis 1's "meaning from the text, not speculation." **Under-covering
a thin passage is correct, not a gap.** Target per rich pericope: questions across
the supported dimensions at mixed tiers/difficulties (~8-10), one child-or-youth
activity + one `pre_reader` variant, pre-reading quests at child/youth/adult, one
`memory_verse`, one `narration_prompt`.

## Workflow (per pericope)

```
build_draft_prompt.py ──▶ drafter ──▶ draft items
                                          │
                          ┌───────────────┘
                          ▼
        adversarial reviewers (one lens per rubric axis)
                          │  verdicts + defects
                          ▼
                    triage each defect
                    ├── fix the item ──────────────┐
                    └── fix the machinery           │
                         (recurring / systemic)     │
                          │                          │
              apply machinery fix, regenerate/repair │
                          └───────────► re-review ◀──┘
                                          │ clean
                                          ▼
                         review_status: "reviewed" (+ provenance)
```

After all four pericopes are clean → **confirmation digest** → human approval →
stamp `"published"` → write `store/mat.json`.

**Triage rule.** A defect is a *machinery* fix (not just an item fix) when it
recurs across items or pericopes, or when it traces to a missing instruction the
drafter could not have known — a gap in the drafting prompt, the per-dimension
guidance, or the checklist. One-off content mistakes are item fixes. Every
machinery change is recorded with the defect that motivated it.

## Components changed

- **New — the rubric artifact.** The seven axes above, in a form the reviewer
  agents are handed and `review_checklist.py` mirrors. Location:
  `content_bank/author/rubric.py` (a `build()` returning the text, matching the
  existing `review_checklist.py` / `dimensions.py` shape), so it is single-sourced
  and importable by both the checklist and the drafting pack.
- **`author/dimensions.py`** — expand each one-line template into drafting
  guidance rich enough to prevent the recurring dimension-fit and answerability
  defects the review surfaces. Meaning still sourced from
  `docs/design-kit_generator.md` Part 1.
- **`author/build_draft_prompt.py`** — fold in what the review teaches: the
  answerable-from-this-pericope rule, coverage-per-supported-dimension guidance,
  per-type expectations, tier/difficulty calibration, an explicit
  evidence-not-judgment constraint. Keep it offline, stdlib-only, no API.
- **`author/review_checklist.py`** — realign to the seven rubric axes (adds
  dimension-fit, answerability, pedagogical-strength; today it has conformity /
  accuracy / age-fitness / evidence).
- **`content_bank/store/mat.json`** — regenerated: seed replaced by
  harness-produced, adversarially-reviewed items for the four pericopes.
- **`content_bank/PROVENANCE.md`** — record this authoring cycle.
- **`prototype/family.json`** — `reading_sequence` gains `MAT-013`.

Not changed: `schema.py`, `content.py`, `validate.py`, `corpus_bridge.py`,
`prototype_bank.py`, `selector.py`, the corpus.

## Provenance model

- Drafted items: `provenance.drafted_by = "claude"`.
- After adversarial pass: `review_status = "reviewed"`,
  `provenance.reviewed_by` records the AI adversarial review, `guardrail = "WCF-1"`,
  `reviewed_date` set. (`validate_item` already requires `reviewed_by`,
  `reviewed_date`, `guardrail ∈ {WCF-1}` once status ≠ draft.)
- After human confirmation: `review_status = "published"`;
  `provenance.confirmed_by = "kyhhdm"` (human of record).

## Verification

- `content_bank` suite, `prototype` suite, `corpus` suite all green.
- `validate_store("MAT")` passes (referential integrity, id uniqueness, bilingual
  counts) on the regenerated store.
- The gate holds: `get_content(mode="product")` serves only `published`; any item
  left `reviewed`/`draft` is provably excluded.
- `generate_kit.py` runs end-to-end against the new store and produces a coherent
  kit.
- **Demo-passage check (flagged, resolved at verification):** adding MAT-013 makes
  it the *next* passage, so the default demo kit would feature the thin 5:1-2
  setup rather than the flagship Beatitudes. Resolve during verification —
  preferred: mark MAT-013 as a studied session in `family.json` so the demo kit
  remains MAT-014, while the sequence still teaches the setup first for real
  families. Decide against the generated output, not in the abstract.

## Deliverables

1. Regenerated, adversarially-reviewed `store/mat.json` (four pericopes).
2. Tuned authoring harness (`dimensions.py`, `build_draft_prompt.py`,
   `review_checklist.py`) + new `rubric.py`.
3. Updated `family.json`, `PROVENANCE.md`.
4. A quality/tuning writeup: the defects found, the machinery changes each
   motivated, and the residual known limitations.
5. All suites green; kit verified end-to-end.
