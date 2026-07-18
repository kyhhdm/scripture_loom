# Content-bank leader references: fact answers + open-question notes

- **Date:** 2026-07-19
- **Issue:** #2 — "Content bank: leader references (fact answers + open-question notes)"
- **Depends on:** the completed content cycle (two-stage authoring harness + 62
  published items, merged via #1) and the corpus. Both are fixed dependencies here.
- **Status:** design approved; ready for an implementation plan.

## Goal

Give each content-bank item an optional **leader-only** reference, typed by the
kind of question it poses:

- **Closed / factual items** (D1, D2, D3, D4, and D5's "which text") gain a concise
  **answer key** — the expected response plus the verse it comes from.
- **Open / formative items** (D6, D7, D8) gain a **leader note** — where the text
  leads and the common misreadings to watch, explicitly told to *keep it open*,
  never a canned answer.

This issue authors the **reference data only**. It is deliberately orthogonal to
the *access mechanism*: how a leader is allowed to reach the reference (the
heart-prep gate, the attempt-submit UX, print suppression) is the separate gate
issue's concern (see "Out of scope" and the follow-up section of
`docs/superpowers/specs/2026-07-18-content-bank-prototype-content-design.md`).

## Principles (from the issue)

- **Grounded in the briefs.** A reference is a per-question distillation of the
  same lampposts (brief + commentary + cross-refs) already wired into the completed
  cycle — not a new content source. Stage 1's committed briefs
  (`author/briefs/<pericope>.md`) are the theological base.
- **A wrong answer key is worse than none.** References pass the same adversarial
  accuracy review as items (answers correct & text-grounded; notes must not close
  an open question), then a human-confirmation gate. "AI proposes, the leader
  confirms" holds for references exactly as it does for items.
- **English-only** this cycle (matches current content).
- **Leader-only data.** The reference is item *data*. Whether or where it is
  rendered or withheld — and keeping it off any printed page — is the gate issue's
  concern, not this one.

## Scope

**In scope:**

- `lib/schema.py` + `lib/validate.py`: an optional `leader_reference` field with
  structural validation.
- `author/build_reference_prompt.py`: an authoring pack that drafts the typed
  reference for each eligible item from the item + its brief + the passage.
- Reference-review criteria in `author/review_checklist.py` and `author/rubric.py`
  so the adversarial accuracy pass has an explicit written standard.
- An augmentation pass over the existing **62 published items** (MAT-009/013/014/015):
  draft references → adversarial review → human-confirmation digest → commit into
  `store/mat.json`.
- Tests and `PROVENANCE.md`.

**Out of scope** (explicit, so the plan does not drift):

- The heart-prep gate, attempt-submit UX, and the reveal flow. Product-flow,
  belongs in `docs/unplug_assitant.md` and the gate issue.
- Print suppression / kit-generator changes. The reference is leader-only data; the
  gate issue owns keeping it off printed pages. This cycle does not touch
  `prototype_bank.py`, `selector.py`, or `generate_kit.py`.
- Chinese references. English-only this cycle; a `zh` reference pass is a later
  cycle, matching the English-only state of current content.
- Changing the store gate (`content.py`), the selector, or the corpus.
- References on new pericopes or new items — this augments the existing 62 only.

## Locked decisions

1. **One typed object.** The reference is a single optional `leader_reference`
   object on the item, self-typed by a `kind` field. Not two parallel fields, and
   not separate linked store items.
2. **Enforce the kind↔dimension mapping structurally.** `validate.py` rejects an
   `answer_key` on an open dimension and a `leader_note` on a closed dimension.
   This is a structural category check, not a substance judgment — it does not
   violate the infrastructure invariant that the software proves an item was
   *reviewed*, not that it is *sound*.
3. **Coverage.** `question` and `pre_reading_quest` items always get a typed
   reference; `activity` and `narration_prompt` items get an optional
   `leader_note` where it aids facilitation; `memory_verse` items get none (their
   answer is the printed verse itself).
4. **The reference has its own gate.** The reference carries its own provenance and
   is only committed to the store after human confirmation. The item's
   `review_status` stays `published` throughout and its own provenance is untouched.

## The `leader_reference` field

Optional object on any item:

```json
"leader_reference": {
  "kind": "answer_key",
  "text": { "en": "The Spirit led Jesus; the devil tempted him." },
  "verse": { "en": "Matthew 4:1" },
  "provenance": {
    "drafted_by": "claude",
    "reviewed_by": "claude-adversarial",
    "reviewed_date": "2026-07-19",
    "guardrail": "WCF-1",
    "confirmed_by": "kyhhdm"
  }
}
```

- **`kind`** — required; one of `answer_key`, `leader_note`.
- **`text`** — required; a non-empty language map, same shape and rules as the
  item's `text` (validated by the existing `_check_text`).
  - For an **answer key**: the expected response, concise.
  - For a **leader note**: where the text leads and misreadings to flag, with the
    explicit stance *keep this open — never a canned answer*.
- **`verse`** — optional; a non-empty language map holding a human-readable
  reference string (e.g. `"Matthew 4:1"`). Allowed **only** on `answer_key`. It is
  leader-facing display text, consistent with how `text` works — deliberately not a
  structured corpus ref.
- **`provenance`** — required once the reference is present in the committed store.
  Mirrors item provenance: `drafted_by`, `reviewed_by`, `reviewed_date`, `guardrail`.
  `confirmed_by` records the human of record.

### Kind ↔ dimension mapping

- **Closed dimensions** `{D1, D2, D3, D4, D5}` → `answer_key`. (D5 "Connections"
  answers with *which text* it reaches — still a closed, checkable answer.)
- **Open dimensions** `{D6, D7, D8}` → `leader_note`.

A `pre_reading_quest` is typed by whichever dimension it carries: a fact-noticing
quest (tagged D1–D4/D5) gets an `answer_key`; a quest that asks the listener to
wonder or notice a *why* (tagged D6/D7) gets a `leader_note`. The dimension rule
handles this without a special case.

## Schema changes (`lib/schema.py`)

Add:

```python
REFERENCE_KINDS = {"answer_key", "leader_note"}
CLOSED_DIMENSIONS = {"D1", "D2", "D3", "D4", "D5"}
OPEN_DIMENSIONS = {"D6", "D7", "D8"}
```

In `validate_item`, when `leader_reference` is present, check (structural only):

- `leader_reference` is a dict.
- `kind` ∈ `REFERENCE_KINDS`.
- `text` is a non-empty language map (`_check_text("leader_reference.text", ...)`).
- **Mapping:** `answer_key` requires `dimension ∈ CLOSED_DIMENSIONS`;
  `leader_note` requires `dimension ∈ OPEN_DIMENSIONS`.
- `verse`, if present: `kind == "answer_key"` and a non-empty language map.
  A `verse` on a `leader_note` is an error.
- `type != "memory_verse"` — a reference on a memory verse is an error.
- Provenance-once-present, mirroring the item rule (`review_status != "draft"`):
  `provenance.reviewed_by`, `provenance.reviewed_date`, and
  `provenance.guardrail == "WCF-1"` are required. `confirmed_by` is **not**
  validate-enforced — exactly like items today, it is the human gate applied by the
  confirmation digest before commit, recorded in provenance.

No change to the required-fields list, to `content.py`, or to the item lifecycle.
`leader_reference` is purely additive and optional.

## Store validation (`lib/validate.py`)

`validate_store` gains a `references` block in its `counts`:

```python
"references": {
    "total": <count of items with leader_reference>,
    "answer_key": <count>,
    "leader_note": <count>,
    "missing_reference": <eligible items (question|pre_reading_quest) lacking one>,
}
```

No new referential-integrity rules; per-item structural checks already run through
`schema.validate_item`. The count surfaces eligibility gaps for the digest.

## Authoring machinery (`author/`)

### `build_reference_prompt.py` (new)

Mirrors `build_draft_prompt.py`. Offline, stdlib-only, no API. For one pericope:

- Loads the pericope's **committed items** from the store (`content.load_book_store`),
  the pericope's **committed brief** (`author/briefs/<pericope>.md`), and the
  **foregrounded passage** (`corpus_bridge.passage_text`).
- Emits, per **eligible** item (see Coverage), an instruction to draft a typed
  reference:
  - Closed dim → an `answer_key`: the concise expected response + the verse.
    Correct and answerable from the passage/brief.
  - Open dim → a `leader_note`: where the text leads and misreadings to flag, with
    the explicit rule **"keep this open — never a canned answer; do not supply a
    model answer the leader would read out."**
- Carries the same grounding discipline as drafting: the reference is distilled
  from the passage + brief, adds no private novelty, and stays within the WCF-1
  guardrail.
- Output schema: a JSON array of `{ item_id, leader_reference }` objects for the
  reviewer/committer to merge back onto the items.

### Reference-review criteria

Single-sourced so the adversarial reviewers and the checklist share one standard:

- `rubric.py`: add a short `REFERENCE_AXES` note and a `reference_criteria()` (or
  equivalent) returning the reference standard: **answer keys** correct and
  text-grounded against passage + brief; **leader notes** must not close the open
  question (no canned answer, no leading toward one reading the text does not
  compel).
- `review_checklist.py`: add a `## Leader references` section mirroring those
  criteria as check boxes, so the human confirmation step has an explicit gate.

## Augmentation pass (the content work)

Per pericope (MAT-009, MAT-013, MAT-014, MAT-015), following the established
cycle-1 human-in-loop pattern:

1. **Draft.** Build the reference pack; the drafter (claude) produces references
   for all eligible items in the pericope, grounded in that pericope's brief.
2. **Adversarial review.** An independent reviewer pass checks each reference
   against the reference criteria — answer keys correct & text-grounded; notes kept
   open. Defects are repaired; recurring defects that trace to the prompt are fixed
   in `build_reference_prompt.py` (same triage rule as cycle 1: recurring or
   missing-instruction → machinery fix; one-off → content fix). On a clean pass,
   stamp `reviewed_by = "claude-adversarial"`, `reviewed_date`, `guardrail = "WCF-1"`.
3. **Human-confirmation digest.** After all four pericopes' references are clean,
   present a digest to the human of record. **This is a real checkpoint: no
   reference is written into `store/mat.json` before approval.** On approval, stamp
   `confirmed_by = "kyhhdm"` and merge each `leader_reference` onto its item.

Items remain `review_status: "published"` throughout; item-level provenance is not
touched. Coverage per the locked decision: all `question` (38) + `pre_reading_quest`
(8) get a typed reference; `activity`/`narration_prompt` get an optional
`leader_note` where it aids facilitation; `memory_verse` gets none.

## Provenance model (references)

- Drafted references: `leader_reference.provenance.drafted_by = "claude"`.
- After adversarial pass: `reviewed_by = "claude-adversarial"`, `reviewed_date`,
  `guardrail = "WCF-1"` (validate requires these once a reference is committed).
- After human confirmation: `confirmed_by = "kyhhdm"` — the gate before commit.

`PROVENANCE.md` records this reference-authoring cycle: the briefs each reference
was distilled from, and any machinery changes the review surfaced.

## Components changed

- **`lib/schema.py`** — `REFERENCE_KINDS`, `CLOSED_DIMENSIONS`, `OPEN_DIMENSIONS`;
  `leader_reference` validation in `validate_item`.
- **`lib/validate.py`** — `references` counts in `validate_store`.
- **New `author/build_reference_prompt.py`** — the Stage-2-analogous reference pack.
- **`author/rubric.py`** — reference criteria, single-sourced.
- **`author/review_checklist.py`** — a leader-references checklist section.
- **`store/mat.json`** — regenerated with confirmed `leader_reference` fields on
  eligible items.
- **`PROVENANCE.md`** — record the reference cycle.

**Not changed:** `lib/content.py` (the gate), `lib/prototype_bank.py`,
`lib/corpus_bridge.py`, `author/build_brief_prompt.py`, `author/build_draft_prompt.py`,
`author/dimensions.py`, `author/briefs/*`, the corpus, the prototype selector, and
`prototype/family.json`.

## Verification

- `content_bank`, `prototype`, and `corpus` suites all green.
- `validate_store("MAT")` passes on the augmented store; `references.missing_reference`
  is zero for the eligible set (every question and pre_reading_quest carries a
  reference), and every committed reference validates (kind↔dimension, verse rules,
  provenance).
- The product gate is oblivious to the new field: `get_content(mode="product")`
  serves the same `published` items it did before; `leader_reference` rides along as
  data and changes nothing the gate decides.
- `generate_kit.py` still runs end-to-end and produces a coherent kit. (Confirming
  the reference never reaches print is the **gate issue's** verification, not this
  one; here we only confirm we did not break kit generation.)

## Deliverables

1. `leader_reference` schema + validation with tests.
2. `build_reference_prompt.py` + reference-review criteria in `rubric.py` /
   `review_checklist.py`, with tests.
3. Augmented, adversarially-reviewed, human-confirmed `store/mat.json` — references
   on all eligible published items.
4. Updated `PROVENANCE.md`.
5. All suites green; store validates; kit still generates.

## Testing

- `tests/test_schema.py`: a valid `answer_key` and a valid `leader_note`;
  kind↔dimension rejection both directions; `verse` rejected on a `leader_note`;
  reference rejected on a `memory_verse`; provenance required once a reference is
  present; bad `kind` rejected.
- `tests/test_validate.py`: `references` counts (total, by kind, `missing_reference`).
- `tests/test_author.py`: `build_reference_prompt` emits a pack covering the
  pericope's eligible items and carries the keep-open instruction for open
  dimensions.
- `tests/test_store_matthew.py`: committed references validate and satisfy the
  eligibility rule (questions + quests covered; memory verses have none).
