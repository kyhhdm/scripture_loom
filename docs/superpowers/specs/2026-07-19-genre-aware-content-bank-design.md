# Genre-aware content bank — two cheap changes

**Date:** 2026-07-19
**Status:** design, pending review
**Origin:** `docs/2026-07-19-genre-dimension-probe-findings.md`

## Background

A probe (Psalm 23, Philippians 2:1–11) tested how genre influences the content
bank. It killed the systematic idea (no new dimensions, no `genre` field, no
`genre → dimension-profile` table): D1/D2 are narrative-specific and go forced in
poetry/epistle, but D3–D8 carry the load and every passage stays authorable. Two
small, independent changes survived as worth building. They do **not** introduce a
genre concept into the data model; genre stays implicit in the passage.

- **Change 1 — availability-driven observation targets** (selector correctness).
- **Change 2 — genre-aware D3/D7 authoring guidance** (brief prose, no schema).
- **Change 3 — genre-general D3/D7 assessment language** (docs only).

A fourth question the probe raised — whether the member record should sub-label
*kinds* of D7 — is **decided against** here (derive-don't-store; see Non-goals); its
one real residual becomes Change 3.

Changes 1–2 are each scoped to one code site with tests; Change 3 is docs-only.
Together they are one implementation plan.

---

## Change 1 — availability-driven observation targets

### Problem

`prototype/selector.py: select_observation_targets(family, limit=3)` scores every
`(member, dimension)` pair over all eight `DIMENSIONS` using weakness × 10 +
staleness. It never receives the bank or the upcoming passage, so it cannot know
which dimensions that passage actually has published content for. On a passage with
no D2 content — e.g. a psalm, per the probe — it can hand the leader an observation
target of "watch this member on D2 (Event Sequence)" during a session that never
exercises D2. The target is unobservable.

This is the concrete failure the probe predicted, and the reason no genre system is
needed to fix it: the author already declines to draft unsupported dimensions (the
draft harness rule *"ONLY THE DIMENSIONS THIS PASSAGE GENUINELY SUPPORTS… Do not
pad"*), so *availability of published content* is already the correct signal.

The bug is already reachable in the shipped bank, not just in theory. Published
dimension coverage per Matthew pericope:

| Pericope | Published dimensions |
|---|---|
| MAT-009 Temptation (narrative) | D1 D2 D3 D4 D5 D6 D7 D8 |
| MAT-013 Sermon setup | D1 D2 D6 |
| MAT-014 Beatitudes (poetry) | **D2** D3 D4 D5 D6 D7 D8 — **no D1** |
| MAT-015 Salt & Light | D2 D3 D4 D5 D6 D7 D8 — **no D1** |

On a Beatitudes session (MAT-014) the current selector can still emit a **D1
(People & Places)** observation target — a dimension with zero content for that
passage. The fix stops exactly that.

### Design

Restrict observation-target candidate dimensions to those the upcoming passage has
published content for.

1. New helper in `selector.py`:

   ```python
   def available_dimensions(bank, passage_id):
       """Dimensions with >= 1 published item for this passage (any type)."""
       return {i["dimension"] for i in _published(bank, passage=passage_id)}
   ```

2. Change the signature:

   ```python
   def select_observation_targets(family, available_dims, limit=3):
   ```

   In the scoring loop, iterate `for dim in DIMENSIONS if dim in available_dims`
   (or intersect up front). Weakness/staleness scoring is otherwise unchanged.

3. `build_kit` computes and passes it:

   ```python
   available = available_dimensions(bank, passage["id"])
   targets = select_observation_targets(family, available)
   ```

### Behavior and edge cases

- A member's weakest dimension that this passage does not support is simply not
  offered this session. Its staleness keeps climbing, so it surfaces on a later
  passage that *does* support it. **No evidence or priority is lost** — it is
  deferred to a session where it can actually be observed.
- Fewer than `limit` available dimensions → fewer targets (limit is a max).
- Empty available set (passage has no published items) → no targets (`[]`).
- `select_discussion_questions` already filters to published items for the passage,
  so a preferred-but-absent target dimension already falls through there; no change
  needed. Change 1 is scoped strictly to observation targets, the one place that
  fabricates dimension coverage.

### Tests (`prototype/test_selector.py`)

- **New:** a passage missing a dimension never yields an observation target on that
  dimension, even when it is a member's weakest. Build a small bank fixture whose
  next passage publishes items for, say, D1/D3/D7 only; assert no target has a
  dimension outside that set.
- **New (over-suppression guard):** a member weak in an *available* dimension still
  gets a target on it — filtering must not drop supported weak dimensions.
- **Regression (resolved):** `test_targets_include_libertys_weak_event_sequence`
  asserts a D2 target. The fixture's next passage is MAT-014 (Beatitudes), which
  publishes four D2 items, so D2 is available and the test passes unchanged under
  the fix. No edit needed. (Confirmed: `available_dimensions(bank, "MAT-014")`
  includes D2 but not D1.)
- **New (concrete):** on MAT-014, no observation target has dimension D1 — the
  Beatitudes publish no D1 content. This is the shipped-bank instance of the bug and
  makes a good direct assertion.

---

## Change 2 — genre-aware D3/D7 authoring guidance

### Problem

The probe found that each non-narrative genre has a load-bearing reading move with
no native dimension, silently absorbed by D3/D7:

- poetry → figurative/metaphor structure and metaphor shifts (Ps 23: shepherd → host);
- epistle → argument-connective tracing (*therefore / if-then / but*).

`content_bank/author/dimensions.py: TEMPLATES` gives D3/D7 a single genre-generic
description for every passage. It does not cue the drafter toward these moves. There
is deliberately no `genre` field to switch on — and genre is **sub-pericope**
(Philippians 2 is exhortation in v1–4 and a hymn in v6–11), so any per-pericope
genre tag would mislabel half that passage. The guidance therefore must be authored
per pericope against the actual verses, which is exactly what a brief is.

### Design

Add an optional fifth part to the Stage-1 brief, and point the Stage-2 draft prompt
at it. No schema change, no genre field, no per-genre code map.

1. `build_brief_prompt.py: _SHAPE` — add a fifth part after Cross-references:

   > **Reading moves (per dimension — especially D3/D7).** One or two sentences
   > naming this passage's genre-specific emphases for Vocabulary and
   > Interpretation, and any shift within the passage. Examples — poetry: "D7 =
   > image → referent; note the metaphor shift at v5"; epistle: "D7 = trace the
   > *therefore*; D3 on the argument's key terms." For a straightforward narrative
   > passage where D3/D7 are already well served, write "standard" or omit.

   Keep the ~250-word budget realistic: raise the hard max to ~330 to fit the extra
   sentence(s), or state the note is excluded from the four-part word count.

2. `build_draft_prompt.py` — where `dimensions.TEMPLATES` is rendered, append to the
   D3 and D7 lines a pointer:
   `"→ consult the brief's *Reading moves* note for this passage's genre-specific emphasis (if present)."`
   Generic template stays; the drafter is routed from generic to the authored
   specific. "(if present)" degrades gracefully for briefs without the section.

### Why the brief, not code

The brief author (human/Claude, Stage 1) reads the actual verses, so a mixed-genre
pericope like Philippians 2 gets an accurate note ("v1–4 exhortation: trace the
*therefore*; v6–11 hymn: sequence + memory") that no per-pericope genre tag could
produce. This is faithful to the probe's core result: the passage is the genre
signal; keep genre out of the data model.

### Tests

- `build_brief_prompt` output contains the new **Reading moves** instruction.
- `build_draft_prompt` output D3 and D7 lines contain the *Reading moves* pointer.

### Out of scope

Backfilling the four existing Matthew briefs (mat-009/013/014/015) with a Reading-
moves note. They are narrative, where D3/D7 are already well served; add the note
when those pericopes are next revised. The `(if present)` pointer handles their
absence.

---

## Change 3 — genre-general D3/D7 assessment language (docs only)

### Problem

The probe asked whether the longitudinal record should distinguish *kinds* of D7
(narrative-meaning vs. argument-tracing vs. figurative-reading). It should **not**
store that (see the decision under Non-goals). But investigating it surfaced a real,
separate defect: the D7 and D3 *assessment standard* is narrative-shaped. D7's top
progression rung in `docs/design-kit_generator.md` is *"explains the passage within
the book's argument"* — coherent for an epistle, awkward for a psalm. A leader
marking △/✓ on D7 for Psalm 23 is judging figurative-reading against a standard
written for narrative meaning.

This matters because the selector's weakness signal (`weak_dimensions`, counting △/?
per dimension) is only as trustworthy as the marks feeding it. An unfair standard
produces misleading weakness, which then mis-biases review and observation targets.
Change 3 is the leader-facing mirror of Change 2: that change makes D3/D7 *authoring*
guidance genre-aware; this makes D3/D7 *assessment* guidance genre-aware.

### Design

Docs only — no code, no schema. In `docs/design-kit_generator.md`, revise the D3 and
D7 entries (the "Progression" and evidence lines) so the standard reads fairly across
genres. Two acceptable shapes:

- make the ladder language genre-general (e.g. D7 top rung: "explains the passage
  within its larger context — the book's argument, the psalm's movement, the
  proverb's contrast"); or
- keep the narrative ladder and add a one-line genre gloss per non-narrative genre.

Prefer the genre-general phrasing; it keeps one ladder while removing the narrative
assumption. Leave D1/D2 as-is — the probe established they are legitimately
narrative-specific and simply go unused on non-narrative passages (Change 1 already
prevents them being assessed where absent).

### Tests

None (prose in a design doc). Verification is editorial review that each revised D3/D7
rung reads fairly for narrative, poetry, and epistle.

### Scope note

Small and docs-only; rides in the same implementation plan as Changes 1–2 but has no
code dependency on them.

---

## Non-goals (explicit)

- No new fluency dimension; D1–D8 unchanged.
- No `genre` field on pericopes or items; no genre vocabulary in `schema.py`.
- No `genre → dimension-profile` table; the probe killed it (genre is sub-pericope).
- **No D7/D3 sub-labels in the evidence schema** (decided, not deferred).
  Distinguishing narrative-meaning / argument-tracing / figurative-reading is
  handled by *derive-don't-store*: every evidence record already carries its session's
  `passage`, so genre context is a derived attribute of the passage and any
  genre-stratified D7 view can be computed at read time if ever needed. Storing a
  per-mark sub-label would burden the reflect phase (the leader is not a data-entry
  clerk), fragment already-thin per-genre evidence, and multiply the schema against
  the eight-universal-dimensions design. Revisit **only if** cross-genre
  interpretation *reporting* becomes a product goal **and** reading diets go
  genre-mixed enough that per-passage derivation is insufficient — neither holds now.
  The real residual of that question (an unfair, narrative-shaped assessment standard)
  is addressed by Change 3, not by sub-labels.

## Testing summary

- `cd prototype && python3 -m unittest test_selector -v`
- `python3 -m unittest discover -s content_bank/tests -v`

Both suites green, including the new selector tests and the two author-prompt string
assertions.
