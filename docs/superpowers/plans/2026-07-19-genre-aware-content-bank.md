# Genre-aware Content Bank Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the content bank behave correctly across biblical genres without adding any genre concept to the data model — three small changes drawn from `docs/superpowers/specs/2026-07-19-genre-aware-content-bank-design.md`.

**Architecture:** (1) The kit selector stops offering observation targets on dimensions a passage has no published content for. (2) The offline authoring prompts gain a per-pericope "Reading moves" note that routes D3/D7 drafting toward the passage's genre-specific reading move. (3) The D7 progression language in the design doc is made genre-general so leader assessment marks are fair across genres. No new dimensions, no `genre` field, no schema change.

**Tech Stack:** Python 3 standard library only (no third-party packages). Tests via `unittest`.

## Global Constraints

- Python 3 standard library only — no third-party imports, no dependency manifest.
- No new fluency dimension; `D1`–`D8` unchanged.
- No `genre` field on pericopes or items; no genre vocabulary in `content_bank/lib/schema.py`.
- No `genre → dimension-profile` table; genre stays implicit in the passage.
- No D7/D3 sub-labels in the evidence schema (decided: derive-don't-store).
- Selector tests: `cd prototype && python3 -m unittest test_selector -v`
- Content-bank tests: `python3 -m unittest discover -s content_bank/tests -v`
- Commit message trailer on every commit: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

## File Structure

- `prototype/selector.py` — kit selector. Task 1 adds `available_dimensions()` and threads it into `select_observation_targets()` and `build_kit()`.
- `prototype/test_selector.py` — selector tests. Task 1 adds observation-target coverage.
- `content_bank/author/build_brief_prompt.py` — Stage-1 brief prompt. Task 2 adds the fifth "Reading moves" part to `_SHAPE`.
- `content_bank/author/build_draft_prompt.py` — Stage-2 draft prompt. Task 2 adds the D3/D7 pointer.
- `content_bank/tests/test_author.py` — author-prompt tests. Task 2 adds assertions.
- `docs/design-kit_generator.md` — the D1–D8 definitions. Task 3 revises the D7 progression line.

Task 1 and Task 2 touch disjoint files and can be implemented in either order. Task 3 is docs-only and independent of both.

---

### Task 1: Availability-driven observation targets

**Files:**
- Modify: `prototype/selector.py` (add helper after `_published` at lines 29-37; change `select_observation_targets` at lines 101-130; change `build_kit` at lines 232-234)
- Test: `prototype/test_selector.py` (add to `TestObservationTargets`, near line 109)

**Interfaces:**
- Produces: `available_dimensions(bank, passage_id) -> set[str]` — the set of dimension codes (e.g. `{"D2","D3",...}`) with at least one published item for `passage_id`.
- Produces: `select_observation_targets(family, available_dims, limit=3) -> list[dict]` — new required second positional arg `available_dims` (a set of dimension codes); return shape unchanged (`[{"member": ..., "dimension": ...}, ...]`).
- Consumes: existing `_published(bank, passage=None, type_=None)` generator and the module-level `DIMENSIONS` dict.

Background fact (verified against the shipped bank): the default `family.json` fixture's next passage is `MAT-014` (the Beatitudes), whose published dimensions are `{D2, D3, D4, D5, D6, D7, D8}` — **no D1**. Today the selector can still emit a D1 observation target there; this task stops that. The existing `test_targets_include_libertys_weak_event_sequence` asserts a `(liberty, D2)` target and keeps passing because `MAT-014` publishes D2 — it doubles as the over-suppression regression guard.

- [ ] **Step 1: Write the failing test**

Add to the `TestObservationTargets` class in `prototype/test_selector.py`:

```python
    def test_no_target_on_dimension_absent_from_passage(self):
        """The Beatitudes (MAT-014, the fixture's next passage) publish no D1
        content, so no member may be given a D1 observation target there."""
        bank, family = load()
        self.assertEqual(kit_passage_dims(bank, "MAT-014") & {"D1"}, set())  # precondition
        kit = selector.build_kit(bank, family)
        self.assertEqual(kit["passage"]["id"], "MAT-014")
        target_dims = {t["dimension"] for t in kit["observation_targets"]}
        self.assertNotIn("D1", target_dims)
```

Add this module-level helper near the top of `prototype/test_selector.py`, just after the `load()` function:

```python
def kit_passage_dims(bank, passage_id):
    return selector.available_dimensions(bank, passage_id)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd prototype && python3 -m unittest test_selector.TestObservationTargets.test_no_target_on_dimension_absent_from_passage -v`
Expected: FAIL with `AttributeError: module 'selector' has no attribute 'available_dimensions'`.

- [ ] **Step 3: Add the `available_dimensions` helper**

In `prototype/selector.py`, immediately after the `_published` function (after line 37), add:

```python
def available_dimensions(bank, passage_id):
    """Dimensions with >= 1 published item for this passage (any type)."""
    return {item["dimension"] for item in _published(bank, passage=passage_id)}
```

- [ ] **Step 4: Thread it into `select_observation_targets`**

In `prototype/selector.py`, change the signature (line 101) and the scoring loop (lines 115-120). Replace:

```python
def select_observation_targets(family, limit=3):
    """(member, dimension) pairs: weakness first, then staleness; never the leader;
    at most two targets per member."""
    members = [m for m in family["members"] if not m["leader"]]
    weakness, last_observed = {}, {}
    for idx, session in enumerate(family["sessions"]):
        for ev in session["evidence"]:
            key = (ev["member"], ev["dimension"])
            last_observed[key] = idx
            if ev["quality"] in WEAK or ev["code"] == "U":
                weakness[key] = weakness.get(key, 0) + 1

    n_sessions = len(family["sessions"])
    scored = []
    for m in members:
        for dim in DIMENSIONS:
            key = (m["id"], dim)
            staleness = n_sessions - 1 - last_observed.get(key, -1)
            score = weakness.get(key, 0) * 10 + staleness
            scored.append((-score, m["id"], dim))
```

with:

```python
def select_observation_targets(family, available_dims, limit=3):
    """(member, dimension) pairs: weakness first, then staleness; never the leader;
    at most two targets per member. Only dimensions in `available_dims` (those the
    upcoming passage publishes content for) are eligible."""
    members = [m for m in family["members"] if not m["leader"]]
    weakness, last_observed = {}, {}
    for idx, session in enumerate(family["sessions"]):
        for ev in session["evidence"]:
            key = (ev["member"], ev["dimension"])
            last_observed[key] = idx
            if ev["quality"] in WEAK or ev["code"] == "U":
                weakness[key] = weakness.get(key, 0) + 1

    n_sessions = len(family["sessions"])
    scored = []
    for m in members:
        for dim in DIMENSIONS:
            if dim not in available_dims:
                continue
            key = (m["id"], dim)
            staleness = n_sessions - 1 - last_observed.get(key, -1)
            score = weakness.get(key, 0) * 10 + staleness
            scored.append((-score, m["id"], dim))
```

The `targets`/`per_member` loop below it (lines 122-130) is unchanged.

- [ ] **Step 5: Pass available dimensions from `build_kit`**

In `prototype/selector.py`, in `build_kit` (lines 232-234), replace:

```python
def build_kit(bank, family):
    passage = next_passage(bank, family)
    targets = select_observation_targets(family)
```

with:

```python
def build_kit(bank, family):
    passage = next_passage(bank, family)
    available = available_dimensions(bank, passage["id"])
    targets = select_observation_targets(family, available)
```

- [ ] **Step 6: Run the new test and verify it passes**

Run: `cd prototype && python3 -m unittest test_selector.TestObservationTargets.test_no_target_on_dimension_absent_from_passage -v`
Expected: PASS.

- [ ] **Step 7: Run the whole selector suite (regression guard)**

Run: `cd prototype && python3 -m unittest test_selector -v`
Expected: all tests PASS, including `test_targets_include_libertys_weak_event_sequence` (D2 is available on MAT-014) and `test_at_most_three_targets`.

- [ ] **Step 8: Commit**

```bash
cd /media/pb/data/pjllc/scripture_loom
git add prototype/selector.py prototype/test_selector.py
git commit -m "$(printf 'selector: observation targets only on dimensions the passage publishes\n\nselect_observation_targets now takes the set of dimensions the upcoming\npassage has published content for and never offers a target outside it,\nso e.g. a D1 target is never assigned on the Beatitudes (no D1 content).\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 2: Genre-aware D3/D7 authoring guidance

**Files:**
- Modify: `content_bank/author/build_brief_prompt.py` (`_SHAPE` string, lines 10-42)
- Modify: `content_bank/author/build_draft_prompt.py` (add a module constant near the other `_*_BLOCK` constants; change the `TEMPLATES` render loop at lines 79-81)
- Test: `content_bank/tests/test_author.py` (extend the import at line 6; add an assertion to `TestBuildDraftPrompt`; add a new `TestBuildBriefPrompt` class)

**Interfaces:**
- Consumes: `build_brief_prompt.build(pericope_id, book="MAT") -> str` and `build_draft_prompt.build(pericope_id, book="MAT", brief=None) -> str` (existing signatures, unchanged).
- Produces: draft-prompt output where the D3 and D7 dimension lines each end with the exact substring `consult the brief's *Reading moves*`; brief-prompt output containing the substrings `Reading moves` and `five parts`.

- [ ] **Step 1: Write the failing tests**

In `content_bank/tests/test_author.py`, extend the import at line 6 to include `build_brief_prompt`:

```python
from content_bank.author import build_draft_prompt, review_checklist, dimensions, rubric, build_reference_prompt, build_brief_prompt
```

Add this test to the existing `TestBuildDraftPrompt` class:

```python
    def test_d3_d7_point_to_reading_moves(self):
        # The pointer appears exactly twice — once on D3, once on D7.
        self.assertEqual(self.prompt.count("consult the brief's *Reading moves*"), 2)
```

Add this new class after `TestBuildDraftPrompt`:

```python
class TestBuildBriefPrompt(unittest.TestCase):
    def setUp(self):
        self.prompt = build_brief_prompt.build("MAT-014", book="MAT")

    def test_asks_for_reading_moves_part(self):
        self.assertIn("Reading moves", self.prompt)

    def test_brief_now_has_five_parts(self):
        self.assertIn("five parts", self.prompt)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest content_bank.tests.test_author.TestBuildBriefPrompt content_bank.tests.test_author.TestBuildDraftPrompt.test_d3_d7_point_to_reading_moves -v`
Expected: FAIL — `test_asks_for_reading_moves_part` and `test_brief_now_has_five_parts` fail on missing substrings; `test_d3_d7_point_to_reading_moves` fails (`0 != 2`).

- [ ] **Step 3: Add the fifth "Reading moves" part to the brief prompt**

In `content_bank/author/build_brief_prompt.py`, in the `_SHAPE` string, change the count line (line 12) from:

```python
~250 words (hard max 300), in exactly these four parts:
```

to:

```python
~250 words (hard max 300, excluding the Reading-moves note below), in exactly these five parts:
```

Then, immediately after the Cross-references line (line 23):

```python
**Cross-references.** The vetted links above, each with a one-phrase note.
```

add:

```python
**Reading moves (per dimension — especially D3/D7).** One or two sentences naming
this passage's genre-specific emphases for Vocabulary (D3) and Interpretation (D7),
and any shift within the passage. Examples — poetry: "D7 = image -> referent; note
the metaphor shift at v5"; epistle: "D7 = trace the therefore; D3 on the argument's
key terms." For a straightforward narrative passage where D3/D7 are already well
served, write "standard" or omit. (Excluded from the word count above.)
```

- [ ] **Step 4: Add the D3/D7 pointer to the draft prompt**

In `content_bank/author/build_draft_prompt.py`, add this module constant alongside the other `_*_BLOCK` constants (e.g. after `_SCHEMA_BLOCK`, before `def _load_brief`):

```python
_READING_MOVES_PTR = (" -> consult the brief's *Reading moves* note for this "
                      "passage's genre-specific emphasis (if present).")
```

Then change the `TEMPLATES` render loop (lines 79-81) from:

```python
    for d, desc in dimensions.TEMPLATES.items():
        parts.append(f"- {d}: {desc}")
    parts.append("")
```

to:

```python
    for d, desc in dimensions.TEMPLATES.items():
        line = f"- {d}: {desc}"
        if d in ("D3", "D7"):
            line += _READING_MOVES_PTR
        parts.append(line)
    parts.append("")
```

- [ ] **Step 5: Run the new tests and verify they pass**

Run: `python3 -m unittest content_bank.tests.test_author.TestBuildBriefPrompt content_bank.tests.test_author.TestBuildDraftPrompt.test_d3_d7_point_to_reading_moves -v`
Expected: PASS (all three).

- [ ] **Step 6: Run the full content-bank suite (regression guard)**

Run: `python3 -m unittest discover -s content_bank/tests -v`
Expected: all PASS, including the pre-existing `test_all_dimension_templates_present` and `test_carries_the_brief`.

- [ ] **Step 7: Commit**

```bash
cd /media/pb/data/pjllc/scripture_loom
git add content_bank/author/build_brief_prompt.py content_bank/author/build_draft_prompt.py content_bank/tests/test_author.py
git commit -m "$(printf 'author: genre-aware D3/D7 guidance via a per-pericope Reading-moves note\n\nStage-1 brief gains an optional fifth part naming this passage genre-\nspecific D3/D7 emphases (poetry: image->referent; epistle: trace the\ntherefore); the Stage-2 draft prompt routes its D3/D7 lines to it. No\ngenre field, no schema change; mixed-genre pericopes handled because the\nnote is authored against the verses.\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 3: Genre-general D7 assessment language (docs only)

**Files:**
- Modify: `docs/design-kit_generator.md` (the D7 "Progression" line, currently line 108)

**Interfaces:** none (prose in a design doc; no code depends on it).

This task removes the narrative assumption from the D7 progression ladder so a leader marking △/✓ on a psalm or epistle judges against a fair standard. The D3 ladder ("notices and asks about words → gives own-words definitions → tracks a word's usage across books") is already genre-general and needs no change — the review step below confirms that.

- [ ] **Step 1: Revise the D7 progression rung**

In `docs/design-kit_generator.md`, in the `#### D7. Interpretation` section, replace the Progression line (line 108):

```markdown
- **Progression:** accurate observation of what is written → explains meaning within the passage → explains the passage within the book's argument.
```

with:

```markdown
- **Progression:** accurate observation of what is written → explains meaning within the passage → explains the passage within its larger context — the book's argument, the psalm's movement, or the proverb's contrast, according to the passage's kind.
```

- [ ] **Step 2: Editorial review across genres**

Read the revised D7 entry (Observable evidence, Question templates, Paper activities, Progression) and the D3 entry, and confirm each rung reads fairly for a narrative passage (Matthew 4), a poem (Psalm 23), and an epistle (Philippians 2). Specifically confirm the new D7 top rung is coherent for all three (book's argument = epistle; psalm's movement = poetry; proverb's contrast = wisdom) and that no other line in D3/D7 silently assumes narrative. If another narrative-only phrase is found, apply the same genre-general treatment inline.

Expected outcome: D3 unchanged (already genre-general); D7 progression reads fairly across all three genres.

- [ ] **Step 3: Commit**

```bash
cd /media/pb/data/pjllc/scripture_loom
git add docs/design-kit_generator.md
git commit -m "$(printf 'docs: make the D7 progression ladder genre-general\n\nThe top rung assumed narrative ("within the book argument"); it now reads\n"within its larger context — the book argument, the psalm movement, or\nthe proverb contrast, according to the passage kind" so leader\nassessment marks are fair across genres and the selector weakness signal\nstays trustworthy.\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Final verification

- [ ] **Run both suites green:**

```bash
cd /media/pb/data/pjllc/scripture_loom
( cd prototype && python3 -m unittest test_selector -v )
python3 -m unittest discover -s content_bank/tests -v
```

Expected: both suites pass with no failures or errors.

- [ ] **Confirm no scope leakage:** `git diff main --stat` shows only `prototype/selector.py`, `prototype/test_selector.py`, `content_bank/author/build_brief_prompt.py`, `content_bank/author/build_draft_prompt.py`, `content_bank/tests/test_author.py`, and `docs/design-kit_generator.md` changed (plus the earlier committed docs). No changes to `content_bank/lib/schema.py`, no `genre` field anywhere.
