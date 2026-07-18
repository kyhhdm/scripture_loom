# Content bank provenance

## Prototype content — generated cycle (2026-07-18/19)

The seed items below were **replaced**. `store/mat.json` now holds **62 items**
across the prototype's four reading-sequence pericopes — `MAT-009` (Temptation,
20), `MAT-013` (Sermon-on-the-Mount setup, 8), `MAT-014` (Beatitudes, 18),
`MAT-015` (Salt & Light, 16) — produced by the two-stage authoring harness and
adversarially reviewed.

**How each item was produced (per pericope):**

1. **Theological brief (Stage 1).** `build_brief_prompt.py` assembled a
   distillation pack — passage (BSB, gated) + full WCF ch.1 + JFB/MHC commentary +
   top cross-references + WCF/WLC/WSC statements selected by proof-text
   reverse-lookup. A ~250-word brief was distilled, **fidelity-reviewed** (faithful
   to the lampposts, no private novelty, passage-emphasis primary), and committed
   to `author/briefs/mat-009,013,014,015.md`. These briefs are the theological
   base and part of provenance.
2. **Items (Stage 2).** `build_draft_prompt.py` assembled a passage-first pack
   (foregrounded passage + the committed brief + a compact WCF-1 guardrail); items
   were drafted, structurally validated (`schema.validate_item`), and scored by
   **two independent adversarial reviewers** on the seven-axis rubric, then
   repaired until clean.

**Provenance stamps:** `drafted_by: claude`, `reviewed_by: claude-adversarial`,
`reviewed_date: 2026-07-18`, `guardrail: WCF-1`, `brief: <brief path>`, and after
the human confirmation gate `confirmed_by: kyhhdm` (human of record) with
`review_status: published`.

**English-only this cycle** (`text: {en}`); `zh` and a distinct zh-conformity
review are a later cycle.

## Leader references — augmentation cycle (2026-07-19)

The 62 published items were augmented with an optional **leader-only**
`leader_reference` (issue #2). 57 references were authored across the four
pericopes: **39 answer keys** (closed dimensions D1–D5 — expected response +
verse) and **18 leader notes** (open dimensions D6–D8 — where the text leads and
common misreadings, kept open). Every `question` and `pre_reading_quest` is
covered; `activity`/`narration_prompt` items carry a reference only where it aids
facilitation; `memory_verse` items carry none. The reference is leader-only data;
keeping it off any printed page is the heart-prep-gate feature's concern, not this
cycle's.

**How each reference was produced (per pericope):**

1. **Drafting.** `build_reference_prompt.py` assembled a pack — the foregrounded
   passage + the committed brief (`author/briefs/<pericope>.md`, the same
   theological base as the item cycle) + the eligible items tagged by kind + the
   reference criteria. Each reference is a per-question distillation of that brief,
   not a new content source.
2. **Adversarial accuracy review.** An independent reviewer tried to break each
   reference against the passage as ground truth: answer keys correct,
   answerable-from-this-passage, and cited-verse-actually-contains-the-answer;
   leader notes kept open (no canned answer). D5 connection answers must name their
   cross-reference. 0 defects on the first pass.
3. **Doctrinal-balance re-sweep.** A defect the owner surfaced — the MAT-009 D3
   "It is written" answer key read flatly as though Jesus lacked authority over
   Scripture — drove a **machinery fix**: a "reduce confusion, doctrinally
   balanced" principle added to the single-sourced `rubric.reference_criteria()`
   (inherited by the drafter pack, the adversarial reviewers, and the human
   checklist). Re-sweeping all 57 under the new lens flagged 2 items
   (`mt4-d3-it-is-written-q`, `mt4-d7-why-scripture-q`); both were sharpened to
   affirm Christ as Scripture's divine Author (WCF-1) while keeping the point.
4. **Human confirmation gate.** kyhhdm reviewed the full digest and approved all
   57 before any reference entered the store.

**Provenance stamps (on `leader_reference.provenance`):** `drafted_by: claude`,
`reviewed_by: claude-adversarial`, `reviewed_date: 2026-07-19`,
`guardrail: WCF-1`, `confirmed_by: kyhhdm`. The item's own `review_status`
(`published`) and provenance are untouched.

**English-only this cycle** (`text: {en}`, `verse: {en}`); a `zh` reference pass
is a later cycle.

The quality defects the review caught and the machinery changes each drove are
recorded in `docs/superpowers/notes/2026-07-18-content-tuning-log.md`; a
human-readable per-pericope review of the published set is at
`docs/superpowers/notes/2026-07-18-mat-content-review.md`.

## Seed content (2026-07-18) — superseded

*(Historical: the 25 hand-migrated seed items described below were replaced by the
generated cycle above. Retained for provenance history.)*

The initial `store/mat.json` items were migrated from the kit-generator
prototype's hand-authored `prototype/content_bank.json` (25 items across three
prototype pericopes). Content is human-authored; `provenance.drafted_by` is
`hand` and each published item is recorded as reviewed against `WCF-1`
(Westminster Confession, Chapter 1).

### Boundary reconciliation (prototype refs → corpus pericope IDs)

The prototype's `mt-5-1-12` ("The Beatitudes", Matthew 5:1–12) does not exist as
a single corpus pericope: the corpus (seeded from BSB section headings) splits it
into `MAT-013` (5:1–2, "The Sermon on the Mount") and `MAT-014` (5:3–12, "The
Beatitudes"). Items were mapped to the pericope whose range actually covers their
content:

- `mt5a-q-mountain` and `mt5a-quest-who-listens` concern the crowds/mountain
  setup (5:1–2) → **MAT-013**.
- All other `mt5a-*` items concern the Beatitudes proper (5:3–12) → **MAT-014**.
- `mt4-*` → **MAT-009** (5:1–2... no: Matthew 4:1–11, exact match).
- `mt5b-*` → **MAT-015** (Matthew 5:13–16, exact match).

No pericope was invented. `MAT-013` is a real corpus pericope; it is simply not
placed in the sample family's reading sequence, so the prototype's linear
three-passage demo is preserved.

### Bilingual

Only English text was migrated. One item (`mt5a-mv-peacemakers`) carries a
seeded Chinese (`zh`) translation to exercise the bilingual read path. The
remaining `zh` translations are a documented, test-pinned gap (`missing_zh`),
to be authored later.
