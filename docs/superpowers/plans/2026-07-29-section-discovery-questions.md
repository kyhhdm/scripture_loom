# Section Discovery Questions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert section-level `throughline` and `thread` items from statements into discovery questions whose traced result is revealed via a `leader_reference`.

**Architecture:** The item `text` becomes a discovery-question stem; the statement we ship today moves into a `leader_reference` whose kind is dictated by the item's dimension (D3→`answer_key`, D7→`leader_note`). A new HARD gate enforces the pairing. No schema change (the shape is already permitted); the change is in the drafting prompt, one new gate, and the review-page flag surface.

**Tech Stack:** Python 3 stdlib, `unittest`. Run tests via `uv run python -m unittest`.

## Global Constraints

- **No change to `content_bank/lib/schema.py`.** It already permits a `leader_reference` on `throughline`/`thread`; the only ban is `memory_verse` (`schema.py:51-52`). A regression test guards this (Task 2).
- **Reveal kind is fixed by dimension:** `throughline` (always D7) → `leader_note`; `thread` D3 → `answer_key` (may carry `verse`); `thread` D7 → `leader_note`. This mirrors the validator's existing `answer_key`=closed / `leader_note`=open rule (`schema.py:56,60`).
- **Both types convert; forward-only.** No migration of existing statement-form items. No auto-derivation from the existing free-standing "arc questions" — those remain unchanged.
- **`thread_span_check` and the citation/quote gates are untouched.**
- `text` is the reader-first field (the stem); `refs` stay on `thread` only (`schema.py:97`); exactly one `throughline` per section.

---

## File Structure

- `content_bank/author/gates.py` — add `section_reveal_check`; wire it into `run_all`.
- `content_bank/author/build_section_draft_prompt.py` — `_SHAPE` + `_OUTPUT_SCHEMA`: emit question stems + dimension-appropriate `leader_reference`.
- `content_bank/author/compare_html.py` — merge `section_reveal_check` flags into the review page (rendering of the reveal itself already works via the type-agnostic `_leader_ref`).
- `content_bank/tests/test_gates.py` — gate behaviour tests.
- `content_bank/tests/test_schema.py` — regression: throughline/thread with `leader_reference` validates.
- `content_bank/tests/test_section_prompt.py` — prompt-shape tests.

---

### Task 1: `section_reveal_check` gate + wire into HARD tier

**Files:**
- Modify: `content_bank/author/gates.py` (add function after `thread_span_check` at line 426; extend `run_all` tuple at lines 450-452)
- Test: `content_bank/tests/test_gates.py`

**Interfaces:**
- Produces: `section_reveal_check(items) -> {item_id: [problem_str, ...]}` — same `{id: [problems]}` shape as the other gates. Only inspects `throughline`/`thread` items; needs no `book`/`allowed`.
- Consumes: nothing new.

- [ ] **Step 1: Write the failing test**

Add to `content_bank/tests/test_gates.py`:

```python
class TestSectionRevealCheck(unittest.TestCase):
    def _tl(self, **over):
        it = {"id": "PHP-S1-throughline", "section": "PHP-S1", "dimension": "D7",
              "type": "throughline", "age_tier": "all", "difficulty": 2,
              "review_status": "draft", "text": {"en": "Where is this movement driving?"},
              "leader_reference": {"kind": "leader_note", "text": {"en": "the spine"}},
              "version": 1}
        it.update(over)
        return it

    def _thread(self, **over):
        it = {"id": "PHP-S1-thread-x", "section": "PHP-S1", "dimension": "D3",
              "type": "thread", "age_tier": "all", "difficulty": 2,
              "review_status": "draft", "text": {"en": "Trace 'joy' — what does it reveal?"},
              "refs": ["PHP.1.4", "PHP.4.4"],
              "leader_reference": {"kind": "answer_key", "text": {"en": "joy recurs"},
                                   "verse": {"en": "Philippians 4:4"}},
              "version": 1}
        it.update(over)
        return it

    def test_correct_pairing_passes(self):
        self.assertEqual(gates.section_reveal_check([self._tl(), self._thread()]), {})

    def test_missing_reveal_flagged(self):
        bad = self._tl()
        del bad["leader_reference"]
        self.assertIn("PHP-S1-throughline", gates.section_reveal_check([bad]))

    def test_wrong_kind_for_d7_flagged(self):
        # D7 must be leader_note; answer_key is wrong.
        bad = self._tl(leader_reference={"kind": "answer_key", "text": {"en": "x"}})
        self.assertIn("PHP-S1-throughline", gates.section_reveal_check([bad]))

    def test_wrong_kind_for_d3_thread_flagged(self):
        # D3 must be answer_key; leader_note is wrong.
        bad = self._thread(leader_reference={"kind": "leader_note", "text": {"en": "x"}})
        self.assertIn("PHP-S1-thread-x", gates.section_reveal_check([bad]))

    def test_d7_thread_uses_leader_note(self):
        ok = self._thread(dimension="D7",
                          leader_reference={"kind": "leader_note", "text": {"en": "x"}})
        del ok["refs"]  # refs presence is thread_span's concern, not this gate's
        ok["refs"] = ["PHP.1.6", "PHP.2.5"]
        self.assertEqual(gates.section_reveal_check([ok]), {})

    def test_non_section_types_ignored(self):
        q = {"id": "PHP-S1-q-1", "type": "question", "dimension": "D5",
             "text": {"en": "?"}}  # no leader_reference here -> must NOT be flagged
        self.assertEqual(gates.section_reveal_check([q]), {})

    def test_run_all_includes_reveal_gate(self):
        bad = self._tl()
        del bad["leader_reference"]
        merged = gates.run_all("PHP", [bad], gates.section_allowed("PHP", "PHP-S1"))
        self.assertIn("PHP-S1-throughline", merged)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_gates.TestSectionRevealCheck -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'section_reveal_check'`.

- [ ] **Step 3: Add the gate**

In `content_bank/author/gates.py`, after `thread_span_check` (line 426), add:

```python
_REVEAL_KIND_FOR_DIM = {"D3": "answer_key", "D7": "leader_note"}


def section_reveal_check(items):
    """HARD: every section-level `throughline`/`thread` is a discovery question and
    MUST carry a leader_reference reveal whose kind matches its dimension
    (D3 -> answer_key, D7 -> leader_note). Missing reveal or mismatched kind is a
    defect. Non-section types are untouched (their reveal rules live elsewhere)."""
    flags = {}
    for it in items:
        if it.get("type") not in ("throughline", "thread"):
            continue
        want = _REVEAL_KIND_FOR_DIM.get(it.get("dimension"))
        lr = it.get("leader_reference")
        if not lr:
            flags[it["id"]] = [f"section item missing its leader_reference reveal "
                               f"(expected kind '{want}')"]
        elif lr.get("kind") != want:
            flags[it["id"]] = [f"reveal kind '{lr.get('kind')}' does not match "
                               f"dimension {it.get('dimension')} (expected '{want}')"]
    return flags
```

- [ ] **Step 4: Wire into `run_all`**

In `content_bank/author/gates.py`, change the `run_all` gate tuple (lines 450-452) to add `section_reveal_check(items)`:

```python
    for gate in (quote_check(book, items), schema_check(items),
                 refs_in_range(items, allowed), thread_span_check(items, allowed),
                 section_reveal_check(items), citation_check(items)):
```

Also update the `run_all` docstring line 446 to mention `+ section-reveal`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m unittest content_bank.tests.test_gates -v`
Expected: PASS (new class + existing tests green).

- [ ] **Step 6: Commit**

```bash
git add content_bank/author/gates.py content_bank/tests/test_gates.py
git commit -m "feat(gates): section_reveal_check — throughline/thread must carry a dimension-matched reveal"
```

---

### Task 2: Schema regression — reveal-bearing section items validate

**Files:**
- Test: `content_bank/tests/test_schema.py` (no production change — this guards the Global Constraint that `schema.py` already permits the shape)

**Interfaces:**
- Consumes: `schema.validate_item(item) -> [error_str, ...]` (empty list = valid); `valid_item(**over)` helper at `test_schema.py:9`.

- [ ] **Step 1: Write the test**

Add to `content_bank/tests/test_schema.py`:

```python
class TestSectionItemReveal(unittest.TestCase):
    def _prov(self):
        return {"reviewed_by": "kyhhdm", "reviewed_date": "2026-07-29",
                "guardrail": "WCF-1"}

    def test_throughline_with_leader_note_validates(self):
        it = valid_item(id="php-s1-throughline", type="throughline", dimension="D7",
                        review_status="draft")
        it.pop("passage", None)
        it["section"] = "PHP-S1"
        it["leader_reference"] = {"kind": "leader_note",
                                  "text": {"en": "the spine"}, "provenance": self._prov()}
        it["provenance"] = {"drafted_by": "hand", **self._prov()}
        self.assertEqual(schema.validate_item(it), [])

    def test_d3_thread_with_answer_key_and_verse_validates(self):
        it = valid_item(id="php-s1-thread-joy", type="thread", dimension="D3",
                        review_status="draft")
        it.pop("passage", None)
        it["section"] = "PHP-S1"
        it["refs"] = ["PHP.1.4", "PHP.4.4"]
        it["leader_reference"] = {"kind": "answer_key", "text": {"en": "joy recurs"},
                                  "verse": {"en": "Philippians 4:4"},
                                  "provenance": self._prov()}
        it["provenance"] = {"drafted_by": "hand", **self._prov()}
        self.assertEqual(schema.validate_item(it), [])
```

- [ ] **Step 2: Run — expect PASS immediately**

Run: `uv run python -m unittest content_bank.tests.test_schema.TestSectionItemReveal -v`
Expected: PASS (no production code needed; schema already permits it). If it FAILS, the failure text tells you which invariant the spec's "no schema change" assumption got wrong — stop and report before editing `schema.py`.

- [ ] **Step 3: Commit**

```bash
git add content_bank/tests/test_schema.py
git commit -m "test(schema): guard that reveal-bearing throughline/thread items validate"
```

---

### Task 3: Drafting prompt emits discovery stems + reveals

**Files:**
- Modify: `content_bank/author/build_section_draft_prompt.py` (`_SHAPE` lines 17-24; `_OUTPUT_SCHEMA` lines 55-58 and line 68)
- Test: `content_bank/tests/test_section_prompt.py`

**Interfaces:**
- Consumes: `build_section_draft_prompt.build(section_id, book, brief="") -> str`.
- Produces: no signature change; only prompt text changes.

- [ ] **Step 1: Write the failing tests**

Add to `content_bank/tests/test_section_prompt.py`:

```python
    def test_throughline_and_thread_carry_leader_reference_in_json(self):
        text = bsd.build("PHP-S1", "PHP")
        # The throughline JSON example must now include a leader_note reveal...
        self.assertIn('"type":"throughline"', text)
        tl = text.split('"type":"throughline"', 1)[1].split("}\n", 1)[0]
        self.assertIn("leader_reference", tl)
        self.assertIn("leader_note", tl)
        # ...and the old "need NO leader_reference" instruction must be gone.
        self.assertNotIn("need NO leader_reference", text)

    def test_prompt_frames_throughline_and_thread_as_questions(self):
        text = bsd.build("PHP-S1", "PHP").lower()
        # Discovery framing: the stem is a question leading to a reveal.
        self.assertIn("discovery question", text)
        self.assertIn("reveal", text)

    def test_reveal_kind_rule_stated(self):
        text = bsd.build("PHP-S1", "PHP")
        # D3 -> answer_key, D7 -> leader_note must be spelled out for section items.
        self.assertIn("D3", text)
        self.assertIn("answer_key", text)
        self.assertIn("leader_note", text)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m unittest content_bank.tests.test_section_prompt -v`
Expected: the three new tests FAIL (`need NO leader_reference` still present; throughline example has no `leader_reference`).

- [ ] **Step 3: Rewrite `_SHAPE` (lines 17-27)**

Replace the THROUGHLINE and THREADS paragraphs in `_SHAPE` with:

```python
**THROUGHLINE (exactly one, dimension D7).** A discovery QUESTION (not a
statement) that leads the reader to this section's spine — what the whole section
is driving at, in the text's own terms. Attach the spine itself as a leader-only
`leader_reference` (kind "leader_note"): the one- or two-sentence arc the reader
checks against after answering. The stem must be answerable FROM the text and must
not embed its own answer. This is what the zoom-out session prints.

**THREADS (zero or more, dimension D7 or D3).** For a word, phrase, or motif that
RECURS across two or more of the section's pericopes and carries the section's
argument: a discovery QUESTION that names the motif and asks what its recurrence
reveals, its member verse `refs` (e.g. MAT.1.22, MAT.2.15), and a leader-only
`leader_reference` holding the traced result (what the recurrence teaches). The
reveal `kind` follows the dimension: D3 (tracked key word) -> "answer_key" (with
the verse); D7 (interpretive movement) -> "leader_note". A thread may extend
beyond this section — anchor it here if this section is its payoff.
```

(Leave the QUESTIONS paragraph at lines 26-27 unchanged — the free-standing arc questions are unaffected.)

- [ ] **Step 4: Rewrite the `_OUTPUT_SCHEMA` throughline/thread shapes (lines 55-59) and line 68**

Replace lines 55-59 with:

```python
- EXACTLY ONE throughline — a D7 discovery question carrying its spine as a leader_note reveal:
  {"id":"<sid>-throughline","section":"<SID>","dimension":"D7","type":"throughline","age_tier":"all","difficulty":2,"review_status":"draft","text":{"en":"<question stem leading to the spine>"},"leader_reference":{"kind":"leader_note","text":{"en":"<the one/two-sentence arc, in the text's own terms>"}},"version":1}
- ZERO OR MORE threads (only if the motif genuinely RECURS across 2+ pericopes) — a discovery question carrying the traced result as its reveal:
  {"id":"<sid>-thread-<slug>","section":"<SID>","dimension":"D7"|"D3","type":"thread","age_tier":"all","difficulty":2,"review_status":"draft","text":{"en":"<question naming the motif + asking what its recurrence reveals>"},"refs":["<BOOK>.C.V","..."],"leader_reference":{"kind":"leader_note"|"answer_key","text":{"en":"<name + what the recurrence teaches>"}},"version":1}
  (refs = >=2 member verses where the motif recurs; a D3 thread's reveal kind is "answer_key" and adds "verse":{"en":"..."}, a D7 thread's is "leader_note")
```

Replace line 68 (`throughline and thread items need NO leader_reference.`) with:

```python
  Every throughline and thread MUST carry a leader_reference reveal whose kind
  matches its dimension: D3 -> "answer_key" (with "verse"), D7 -> "leader_note".
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m unittest content_bank.tests.test_section_prompt -v`
Expected: PASS (new + existing tests green — the existing `test_prompt_inlines_leader_reference_for_questions` still holds).

- [ ] **Step 6: Commit**

```bash
git add content_bank/author/build_section_draft_prompt.py content_bank/tests/test_section_prompt.py
git commit -m "feat(section-prompt): throughline/thread as discovery questions with dimension-matched reveal"
```

---

### Task 4: Surface `section_reveal_check` on the review page

**Files:**
- Modify: `content_bank/author/compare_html.py` (add a `section_reveal_check` merge in the per-unit gate loop, ~lines 108-113)
- Test: `content_bank/tests/test_gates.py` is sufficient for the gate; add a focused compare_html test only if a suitable test module exists (see Step 1).

**Interfaces:**
- Consumes: `gates.section_reveal_check(items)`; the existing `_merge(...)` helper and per-unit loop in `compare_html.py`.
- Produces: reveal violations appear in each card's `gate_problems` (rendering of the reveal text itself already works via the type-agnostic `_leader_ref`, `compare_html.py:119-133`).

- [ ] **Step 1: Check for an existing compare_html test module**

Run: `ls content_bank/tests/ | grep -i compare`
- If a module exists, add a test asserting a throughline missing its `leader_reference` shows up in that unit's flags via `build_model` / the flag path.
- If none exists, do NOT scaffold a new harness for one assertion — Task 1's `test_run_all_includes_reveal_gate` already proves the gate fires; this task is the one-line wiring so the review page calls it. Note the absence in the task report.

- [ ] **Step 2: Add the merge**

In `content_bank/author/compare_html.py`, `section_reveal_check` does not depend on the passage range, so it must run even for units whose range is unavailable. Add it in its own pass BEFORE the range-dependent loop (before line 108 `for unit, items in unit_items.items():`):

```python
    for unit, items in unit_items.items():
        _merge(gates.section_reveal_check(items))
```

Leave the existing range/thread loop unchanged.

- [ ] **Step 3: Run the gate + any compare_html tests**

Run: `uv run python -m unittest content_bank.tests.test_gates -v`
And, if a compare_html module exists, run it too.
Expected: PASS.

- [ ] **Step 4: Regenerate a review page to eyeball (manual, optional)**

If Jonah `work/` artifacts are present, rebuild the review page and confirm section cards render their reveal and that any deliberately unpaired item shows the flag. This is a visual check, not a committed artifact.

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/compare_html.py content_bank/tests/
git commit -m "feat(review): surface section_reveal_check flags on the comparison page"
```

---

## Final steps

- [ ] Run the full content-bank suite: `uv run python -m unittest discover -s content_bank/tests -v` — expect green.
- [ ] Use superpowers:finishing-a-development-branch to complete `feature/section-discovery-questions`.

## Self-Review

- **Spec coverage:** prompt change (Task 3), `section_reveal_check` gate + HARD wiring (Task 1), no-schema-change guard (Task 2), review rendering/flag surface (Task 4), forward-only + arc-questions-unchanged (Global Constraints). All spec sections mapped.
- **Placeholder scan:** none — every code step carries real code and exact paths.
- **Type consistency:** gate returns `{id: [str]}` matching sibling gates and `run_all`'s merge; `section_reveal_check(items)` (no `book`/`allowed`) is called consistently in `run_all` and `compare_html`; reveal-kind map `{D3: answer_key, D7: leader_note}` used identically in gate, prompt, and tests.
