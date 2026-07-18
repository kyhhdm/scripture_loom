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
