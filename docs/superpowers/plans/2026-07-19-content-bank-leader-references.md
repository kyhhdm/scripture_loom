# Content-bank Leader References Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional, leader-only `leader_reference` field to content-bank items — a typed answer key (closed dimensions) or leader note (open dimensions) — with validation, an authoring pack, and a human-confirmed augmentation of the 62 published Matthew items.

**Architecture:** Purely additive. A single self-typed `leader_reference` object rides on each item; `schema.validate_item` gains structural checks; `validate_store` gains counts; a new `build_reference_prompt.py` mirrors `build_draft_prompt.py`; the reference criteria are single-sourced in `rubric.py`. The augmentation follows cycle-1's human-in-loop pattern (drafter = claude, `reviewed_by = "claude-adversarial"`, `confirmed_by = "kyhhdm"`), and no reference reaches `store/mat.json` before a human confirmation digest.

**Tech Stack:** Python 3 standard library only, no third-party packages. `unittest`.

## Global Constraints

- Python 3 standard library only — no third-party imports, no dependency manifest.
- Offline, no network, no API calls in any authoring code (deterministic packs).
- English-only this cycle — references carry `{"en": ...}` only.
- Do NOT change: `lib/content.py` (the gate), `lib/prototype_bank.py`, `lib/corpus_bridge.py`, `author/build_brief_prompt.py`, `author/build_draft_prompt.py`, `author/dimensions.py`, `author/briefs/*`, `prototype/*`, the corpus.
- Closed dimensions = `{D1, D2, D3, D4, D5}` → `answer_key`. Open dimensions = `{D6, D7, D8}` → `leader_note`. `memory_verse` items get no reference.
- Coverage: `question` + `pre_reading_quest` always get a reference; `activity` + `narration_prompt` get one only where it aids facilitation; `memory_verse` never.
- Provenance guardrail value is exactly `"WCF-1"` (the only member of `GUARDRAILS`).
- Run tests from repo root: `python3 -m unittest discover -s content_bank/tests -v`.
- Commit messages end with the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer.

---

### Task 1: `leader_reference` schema validation

**Files:**
- Modify: `content_bank/lib/schema.py`
- Test: `content_bank/tests/test_schema.py`

**Interfaces:**
- Consumes: existing `schema.validate_item(item) -> list[str]`, `_check_text(field, value, errors)`, `GUARDRAILS`, `DIMENSIONS`.
- Produces: module constants `REFERENCE_KINDS = {"answer_key", "leader_note"}`, `CLOSED_DIMENSIONS = {"D1","D2","D3","D4","D5"}`, `OPEN_DIMENSIONS = {"D6","D7","D8"}`; `validate_item` now validates an optional `item["leader_reference"]`.

- [ ] **Step 1: Write the failing tests**

Add to `content_bank/tests/test_schema.py` (the file already defines `valid_item(**over)`; append these methods inside `TestValidateItem`, and add a helper near the top of the class body):

```python
    def _ref(self, **over):
        ref = {
            "kind": "answer_key",
            "text": {"en": "The Spirit led Jesus; the devil tempted him."},
            "provenance": {"reviewed_by": "claude-adversarial",
                           "reviewed_date": "2026-07-19", "guardrail": "WCF-1"},
        }
        ref.update(over)
        return ref

    def test_valid_answer_key_reference(self):
        item = valid_item(dimension="D1", leader_reference=self._ref())
        self.assertEqual(schema.validate_item(item), [])

    def test_valid_leader_note_reference(self):
        note = self._ref(kind="leader_note",
                         text={"en": "Point where the text leads; keep it open."})
        item = valid_item(dimension="D7", leader_reference=note)
        self.assertEqual(schema.validate_item(item), [])

    def test_answer_key_rejected_on_open_dimension(self):
        item = valid_item(dimension="D7", leader_reference=self._ref())
        self.assertTrue(any("answer_key" in e for e in schema.validate_item(item)))

    def test_leader_note_rejected_on_closed_dimension(self):
        note = self._ref(kind="leader_note")
        item = valid_item(dimension="D2", leader_reference=note)
        self.assertTrue(any("leader_note" in e for e in schema.validate_item(item)))

    def test_bad_reference_kind_rejected(self):
        item = valid_item(dimension="D1", leader_reference=self._ref(kind="hint"))
        self.assertTrue(any("kind" in e for e in schema.validate_item(item)))

    def test_verse_rejected_on_leader_note(self):
        note = self._ref(kind="leader_note", verse={"en": "Matthew 5:7"})
        item = valid_item(dimension="D7", leader_reference=note)
        self.assertTrue(any("verse" in e for e in schema.validate_item(item)))

    def test_verse_allowed_on_answer_key(self):
        item = valid_item(dimension="D1",
                          leader_reference=self._ref(verse={"en": "Matthew 4:1"}))
        self.assertEqual(schema.validate_item(item), [])

    def test_reference_rejected_on_memory_verse(self):
        item = valid_item(type="memory_verse", dimension="D4",
                          leader_reference=self._ref(verse={"en": "Matthew 4:4"}))
        self.assertTrue(any("memory_verse" in e for e in schema.validate_item(item)))

    def test_reference_provenance_required(self):
        item = valid_item(dimension="D1",
                          leader_reference=self._ref(provenance={}))
        errs = schema.validate_item(item)
        self.assertTrue(any("leader_reference.provenance" in e for e in errs))

    def test_reference_text_must_be_lang_map(self):
        item = valid_item(dimension="D1", leader_reference=self._ref(text={}))
        self.assertTrue(any("leader_reference.text" in e for e in schema.validate_item(item)))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /media/pb/data/pjllc/scripture_loom && python3 -m unittest content_bank.tests.test_schema -v`
Expected: the 10 new tests FAIL (references not yet validated — valid refs pass trivially but the rejection tests fail because no errors are produced).

- [ ] **Step 3: Add the constants**

In `content_bank/lib/schema.py`, after the `DIFFICULTIES = {1, 2, 3}` line, add:

```python
REFERENCE_KINDS = {"answer_key", "leader_note"}
CLOSED_DIMENSIONS = {"D1", "D2", "D3", "D4", "D5"}
OPEN_DIMENSIONS = {"D6", "D7", "D8"}
```

- [ ] **Step 4: Add the reference checker**

In `content_bank/lib/schema.py`, add this function after `_check_text`:

```python
def _check_reference(item, errors):
    ref = item["leader_reference"]
    if not isinstance(ref, dict):
        errors.append("leader_reference: must be an object")
        return
    kind = ref.get("kind")
    if kind not in REFERENCE_KINDS:
        errors.append(f"leader_reference.kind: invalid '{kind}'")
    if item.get("type") == "memory_verse":
        errors.append("leader_reference: not allowed on memory_verse items")
    _check_text("leader_reference.text", ref.get("text"), errors)

    dim = item.get("dimension")
    if kind == "answer_key" and dim not in CLOSED_DIMENSIONS:
        errors.append(
            f"leader_reference: answer_key only on closed dimensions "
            f"{sorted(CLOSED_DIMENSIONS)}, not '{dim}'")
    if kind == "leader_note" and dim not in OPEN_DIMENSIONS:
        errors.append(
            f"leader_reference: leader_note only on open dimensions "
            f"{sorted(OPEN_DIMENSIONS)}, not '{dim}'")

    if "verse" in ref:
        if kind != "answer_key":
            errors.append("leader_reference.verse: only allowed on answer_key")
        else:
            _check_text("leader_reference.verse", ref.get("verse"), errors)

    prov = ref.get("provenance") or {}
    if not prov.get("reviewed_by"):
        errors.append("leader_reference.provenance.reviewed_by: required")
    if not prov.get("reviewed_date"):
        errors.append("leader_reference.provenance.reviewed_date: required")
    if prov.get("guardrail") not in GUARDRAILS:
        errors.append("leader_reference.provenance.guardrail: must be 'WCF-1'")
```

- [ ] **Step 5: Wire it into `validate_item`**

In `content_bank/lib/schema.py`, at the end of `validate_item`, immediately before `return errors`, add:

```python
    if "leader_reference" in item:
        _check_reference(item, errors)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /media/pb/data/pjllc/scripture_loom && python3 -m unittest content_bank.tests.test_schema -v`
Expected: PASS (all tests, new and existing).

- [ ] **Step 7: Commit**

```bash
cd /media/pb/data/pjllc/scripture_loom
git add content_bank/lib/schema.py content_bank/tests/test_schema.py
git commit -m "$(cat <<'EOF'
content_bank: leader_reference schema validation

Optional self-typed leader_reference: answer_key (closed dims D1-D5) or
leader_note (open dims D6-D8), verse only on answer_key, none on
memory_verse, provenance required when present.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `references` counts in `validate_store`

**Files:**
- Modify: `content_bank/lib/validate.py`
- Test: `content_bank/tests/test_validate.py`

**Interfaces:**
- Consumes: existing `validate.validate_store(book, store_dir=None) -> {"errors": [...], "counts": {...}}`.
- Produces: `counts["references"] = {"total", "answer_key", "leader_note", "missing_reference"}`.

- [ ] **Step 1: Write the failing test**

First inspect the existing test file to match its fixture style:
Run: `cd /media/pb/data/pjllc/scripture_loom && sed -n '1,60p' content_bank/tests/test_validate.py`

Add a test that builds a small in-memory store and checks the counts. Append to `content_bank/tests/test_validate.py` a new test class (uses a temp store dir so it does not depend on the real store):

```python
import json
import tempfile


class TestReferenceCounts(unittest.TestCase):
    def _write_store(self, items):
        d = tempfile.mkdtemp()
        with open(pathlib.Path(d) / "mat.json", "w", encoding="utf-8") as f:
            json.dump({"items": items}, f)
        return d

    def _item(self, iid, dim, typ, ref=None):
        it = {"id": iid, "passage": "MAT-014", "dimension": dim, "type": typ,
              "age_tier": "youth", "difficulty": 1, "review_status": "published",
              "text": {"en": "x"}, "version": 1,
              "provenance": {"drafted_by": "claude", "reviewed_by": "claude",
                             "reviewed_date": "2026-07-19", "guardrail": "WCF-1"}}
        if ref is not None:
            it["leader_reference"] = ref
        return it

    def test_reference_counts(self):
        ak = {"kind": "answer_key", "text": {"en": "a"},
              "provenance": {"reviewed_by": "claude", "reviewed_date": "2026-07-19",
                             "guardrail": "WCF-1"}}
        note = {"kind": "leader_note", "text": {"en": "n"},
                "provenance": {"reviewed_by": "claude", "reviewed_date": "2026-07-19",
                               "guardrail": "WCF-1"}}
        items = [
            self._item("q1", "D1", "question", ak),
            self._item("q2", "D7", "question", note),
            self._item("q3", "D2", "question"),            # eligible, missing
            self._item("a1", "D8", "activity"),            # not counted as missing
        ]
        d = self._write_store(items)
        counts = validate.validate_store("MAT", store_dir=d)["counts"]
        self.assertEqual(counts["references"]["total"], 2)
        self.assertEqual(counts["references"]["answer_key"], 1)
        self.assertEqual(counts["references"]["leader_note"], 1)
        self.assertEqual(counts["references"]["missing_reference"], 1)
```

Note: confirm `pathlib` and `unittest` are already imported at the top of the test file from Step 1's inspection; add `import pathlib` if absent.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /media/pb/data/pjllc/scripture_loom && python3 -m unittest content_bank.tests.test_validate.TestReferenceCounts -v`
Expected: FAIL with `KeyError: 'references'`.

- [ ] **Step 3: Add the counts**

In `content_bank/lib/validate.py`, inside `validate_store`, after the `counts = { ... }` dict literal is built and before `counts["missing_zh"] = ...`, add:

```python
    refs = [i["leader_reference"] for i in items if i.get("leader_reference")]
    counts["references"] = {
        "total": len(refs),
        "answer_key": sum(1 for r in refs if r.get("kind") == "answer_key"),
        "leader_note": sum(1 for r in refs if r.get("kind") == "leader_note"),
        "missing_reference": sum(
            1 for i in items
            if i.get("type") in ("question", "pre_reading_quest")
            and not i.get("leader_reference")),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /media/pb/data/pjllc/scripture_loom && python3 -m unittest content_bank.tests.test_validate.TestReferenceCounts -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /media/pb/data/pjllc/scripture_loom
git add content_bank/lib/validate.py content_bank/tests/test_validate.py
git commit -m "$(cat <<'EOF'
content_bank: reference counts in validate_store

total, by kind, and missing_reference (eligible question/quest items
lacking a leader_reference).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: reference-review criteria (single-sourced)

**Files:**
- Modify: `content_bank/author/rubric.py`
- Modify: `content_bank/author/review_checklist.py`
- Test: `content_bank/tests/test_author.py`

**Interfaces:**
- Consumes: existing `rubric.build() -> str`, `review_checklist.build(guardrail="WCF-1") -> str`.
- Produces: `rubric.reference_criteria() -> str`; `review_checklist.build()` output now contains a `## Leader references` section.

- [ ] **Step 1: Write the failing tests**

Add to `content_bank/tests/test_author.py` a new test class (the file already imports `review_checklist`; ensure `rubric` is importable — add `rubric` to the existing `from content_bank.author import ...` line):

```python
from content_bank.author import rubric  # add rubric to the existing import line


class TestReferenceCriteria(unittest.TestCase):
    def test_rubric_exposes_reference_criteria(self):
        text = rubric.reference_criteria()
        low = text.lower()
        self.assertIn("answer key", low)
        self.assertIn("keep", low)          # notes kept open
        self.assertIn("open", low)

    def test_checklist_has_reference_section(self):
        text = review_checklist.build()
        self.assertIn("Leader references", text)
        self.assertIn("keep", text.lower())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /media/pb/data/pjllc/scripture_loom && python3 -m unittest content_bank.tests.test_author.TestReferenceCriteria -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'reference_criteria'`.

- [ ] **Step 3: Add `reference_criteria` to `rubric.py`**

In `content_bank/author/rubric.py`, after the `_BODY = """..."""` block and before `def build():`, add:

```python
REFERENCE_AXES = (
    "Answer-key accuracy",
    "Note stays open",
)

_REFERENCE_BODY = """# Leader-reference review criteria

A leader reference is leader-only, judged separately from the item it rides on.

- Answer keys (closed dimensions D1-D5). The expected response is correct and
  grounded in THIS passage and the brief; the cited verse actually contains it.
  A wrong answer key is worse than none.
- Leader notes (open dimensions D6-D8). Point where the text leads and flag
  common misreadings, but keep the question open -- never a canned answer the
  leader would read out, never leading toward a reading the text does not compel.
"""
```

Then add this function after `build`:

```python
def reference_criteria():
    return _REFERENCE_BODY
```

- [ ] **Step 4: Add the checklist section**

In `content_bank/author/review_checklist.py`, in the `_BOXES` string, add this block immediately before the closing `On pass, stamp provenance:` lines:

```
## Leader references (leader-only; never printed)
- [ ] Answer keys (D1-D5): expected response correct and grounded in the passage
      + brief; the cited verse actually contains it.
- [ ] Leader notes (D6-D8): keep the question open; no canned answer, not leading.
- [ ] No reference on a memory_verse item.
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /media/pb/data/pjllc/scripture_loom && python3 -m unittest content_bank.tests.test_author.TestReferenceCriteria -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /media/pb/data/pjllc/scripture_loom
git add content_bank/author/rubric.py content_bank/author/review_checklist.py content_bank/tests/test_author.py
git commit -m "$(cat <<'EOF'
content_bank: single-sourced leader-reference review criteria

rubric.reference_criteria() + a Leader references checklist section:
answer keys correct & text-grounded; notes must stay open.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `build_reference_prompt.py` authoring pack

**Files:**
- Create: `content_bank/author/build_reference_prompt.py`
- Test: `content_bank/tests/test_author.py`

**Interfaces:**
- Consumes: `content.load_book_store(book, store_dir=None)`, `corpus_bridge.pericopes(book)`, `corpus_bridge.passage_text(range_str)`, `corpus_bridge.book_name(book, "en")`, `schema.CLOSED_DIMENSIONS`, `rubric.reference_criteria()`, briefs in `author/briefs/<pericope>.md`.
- Produces: `build_reference_prompt.build(pericope_id, book="MAT", brief=None, store_dir=None) -> str`; `main(argv=None)` CLI.

- [ ] **Step 1: Write the failing tests**

Add to `content_bank/tests/test_author.py`:

```python
from content_bank.author import build_reference_prompt  # add to imports


class TestBuildReferencePrompt(unittest.TestCase):
    def setUp(self):
        self.prompt = build_reference_prompt.build(
            "MAT-014", book="MAT",
            brief="**Passage's own emphasis.** Jesus pronounces blessing...\n")

    def test_foregrounds_passage_and_brief(self):
        low = self.prompt.lower()
        self.assertIn("blessed", low)               # passage present
        self.assertIn("pronounces blessing", self.prompt)   # brief injected

    def test_lists_eligible_items_with_kind(self):
        # MAT-014 has questions across closed and open dims; both kinds appear.
        self.assertIn("answer_key", self.prompt)
        self.assertIn("leader_note", self.prompt)

    def test_carries_keep_open_instruction(self):
        self.assertIn("keep it open", self.prompt.lower())

    def test_excludes_memory_verse_items(self):
        # Every listed item id belongs to a non-memory_verse item.
        from content_bank.lib import content
        mv_ids = {i["id"] for i in content.load_book_store("MAT")["items"]
                  if i["type"] == "memory_verse" and i["passage"] == "MAT-014"}
        for mid in mv_ids:
            self.assertNotIn(mid, self.prompt)

    def test_output_schema_present(self):
        self.assertIn("item_id", self.prompt)
        self.assertIn("leader_reference", self.prompt)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /media/pb/data/pjllc/scripture_loom && python3 -m unittest content_bank.tests.test_author.TestBuildReferencePrompt -v`
Expected: FAIL with `ImportError` / `ModuleNotFoundError` for `build_reference_prompt`.

- [ ] **Step 3: Create `build_reference_prompt.py`**

Create `content_bank/author/build_reference_prompt.py` with exactly:

```python
"""Assemble the reference-authoring pack for one pericope.

For each eligible committed item (question + pre_reading_quest always; activity +
narration_prompt where it aids facilitation), instruct the drafter to produce a
typed leader-only reference grounded in the passage + the committed brief. Closed
dimensions get an answer_key (expected response + verse); open dimensions get a
leader_note that keeps the question open. Offline, stdlib-only, no API."""
import argparse
import pathlib

from ..lib import content, corpus_bridge, schema
from . import rubric

_BRIEFS = pathlib.Path(__file__).parent / "briefs"

_ALWAYS = {"question", "pre_reading_quest"}
_OPTIONAL = {"activity", "narration_prompt"}

_RULES = """## How to write each reference (hard rules)

- LEADER-ONLY: this text never prints on the kit. It prepares the leader to lead
  from memory; it is formation, not a crutch.
- GROUNDED: distill the passage + the brief above; add no private novelty; stay
  within the WCF-1 doctrine of Scripture.
- CLOSED dimensions (D1-D5) -> an ANSWER KEY: the concise expected response plus
  the verse it comes from. It must be correct and answerable from THIS passage.
  A wrong answer key is worse than none.
- OPEN dimensions (D6-D8) -> a LEADER NOTE: point where the text leads and flag
  common misreadings, but KEEP IT OPEN -- never a canned answer the leader would
  read out, never leading toward a reading the text does not compel.
- question + pre_reading_quest ALWAYS get a reference. activity + narration_prompt
  get a reference only where it genuinely aids facilitation; otherwise omit it.
- memory_verse items get NO reference (the answer is the printed verse)."""

_SCHEMA = """## Output schema

Return a JSON array of objects, one per item you write a reference for:
  { "item_id": "<the item id>",
    "leader_reference": {
      "kind": "answer_key" | "leader_note",
      "text": { "en": "..." },
      "verse": { "en": "Matthew 4:1" }    // answer_key ONLY; omit for notes
    } }
answer_key only on D1-D5 items; leader_note only on D6-D8 items. Return only the
JSON array."""


def _load_brief(pericope_id):
    f = _BRIEFS / f"{pericope_id.lower()}.md"
    if not f.exists():
        raise FileNotFoundError(
            f"No brief for {pericope_id}; commit {f} first.")
    return f.read_text(encoding="utf-8")


def _eligible(item):
    return item.get("type") in _ALWAYS or item.get("type") in _OPTIONAL


def build(pericope_id, book="MAT", brief=None, store_dir=None):
    if brief is None:
        brief = _load_brief(pericope_id)
    peris = {p["id"]: p for p in corpus_bridge.pericopes(book)}
    if pericope_id not in peris:
        raise ValueError(f"{pericope_id} is not a {book} pericope")
    p = peris[pericope_id]
    items = [i for i in content.load_book_store(book, store_dir).get("items", [])
             if i.get("passage") == pericope_id and _eligible(i)]
    name = corpus_bridge.book_name(book, "en")

    parts = [f"# Reference pack -- {pericope_id}: {p['title_en']}\n",
             f"Passage: {name} ({p['range']})\n",
             "## THE PASSAGE -- ground every reference here\n",
             corpus_bridge.passage_text(p["range"]) + "\n",
             "## Theological base (brief)\n",
             brief + "\n",
             _RULES, "",
             "## Items needing a reference\n"]
    for i in items:
        d = i["dimension"]
        kind = "answer_key" if d in schema.CLOSED_DIMENSIONS else "leader_note"
        opt = "  (optional)" if i["type"] in _OPTIONAL else ""
        parts.append(f"- {i['id']} [{d} / {i['type']} / {kind}]{opt}: "
                     f"{i['text'].get('en', '')}")
    parts.append("")
    parts.append("## Reference review criteria\n")
    parts.append(rubric.reference_criteria())
    parts.append("")
    parts.append(_SCHEMA)
    return "\n".join(parts)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("pericope_id")
    ap.add_argument("--book", default="MAT")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    text = build(args.pericope_id, args.book)
    if args.out:
        pathlib.Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
```

Note on `test_carries_keep_open_instruction`: the `_RULES` block contains "KEEP IT OPEN" — the test lowercases before matching, so "keep it open" matches.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /media/pb/data/pjllc/scripture_loom && python3 -m unittest content_bank.tests.test_author.TestBuildReferencePrompt -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /media/pb/data/pjllc/scripture_loom
git add content_bank/author/build_reference_prompt.py content_bank/tests/test_author.py
git commit -m "$(cat <<'EOF'
content_bank: build_reference_prompt authoring pack

Per-pericope pack: foregrounds passage + brief, lists eligible items with
their reference kind (answer_key for D1-D5, leader_note for D6-D8),
carries the keep-open rule and review criteria. Offline, stdlib-only.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Augment the 62 published items (human-confirmed) + verify

This task produces content and passes a human gate. The code deliverables are the store tests and the store/PROVENANCE updates; the content is drafted and reviewed in-session, then written only after confirmation.

**Files:**
- Modify: `content_bank/store/mat.json` (add `leader_reference` to eligible items)
- Modify: `content_bank/PROVENANCE.md`
- Test: `content_bank/tests/test_store_matthew.py`

**Interfaces:**
- Consumes: `build_reference_prompt.build(...)`, `validate.validate_store("MAT")`, `content.load_book_store("MAT")`, `content.get_content("MAT", mode="product")`.
- Produces: augmented committed store; two new store tests.

- [ ] **Step 1: Write the failing store tests**

Add to `content_bank/tests/test_store_matthew.py` inside `TestMatthewStore`:

```python
    def test_references_validate_and_cover_eligible(self):
        result = validate.validate_store("MAT")
        self.assertEqual(result["errors"], [])                    # refs valid
        refs = result["counts"]["references"]
        self.assertEqual(refs["missing_reference"], 0)            # all q/quest covered
        self.assertGreater(refs["answer_key"], 0)
        self.assertGreater(refs["leader_note"], 0)

    def test_no_reference_on_memory_verse(self):
        store = content.load_book_store("MAT")
        for it in store["items"]:
            if it["type"] == "memory_verse":
                self.assertNotIn("leader_reference", it)

    def test_reference_kind_matches_dimension(self):
        from content_bank.lib import schema
        store = content.load_book_store("MAT")
        for it in store["items"]:
            ref = it.get("leader_reference")
            if not ref:
                continue
            if ref["kind"] == "answer_key":
                self.assertIn(it["dimension"], schema.CLOSED_DIMENSIONS)
            else:
                self.assertIn(it["dimension"], schema.OPEN_DIMENSIONS)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /media/pb/data/pjllc/scripture_loom && python3 -m unittest content_bank.tests.test_store_matthew -v`
Expected: `test_references_validate_and_cover_eligible` FAILS (`missing_reference` = 46; no references yet). The other two pass vacuously.

- [ ] **Step 3: Draft references per pericope**

For each pericope in `MAT-009, MAT-013, MAT-014, MAT-015`:

```bash
cd /media/pb/data/pjllc/scripture_loom
python3 -m content_bank.author.build_reference_prompt MAT-009 \
  --out "$SCRATCH/ref-pack-mat-009.md"
```
(Repeat for 013/014/015; `$SCRATCH` = the session scratchpad dir.)

Acting as the drafter, produce for each eligible item a `leader_reference` grounded in that pericope's brief + passage:
- Closed dim (D1-D5) → `answer_key`: concise expected response in `text.en`, plus `verse.en` (e.g. `"Matthew 4:1"`).
- Open dim (D6-D8) → `leader_note`: where the text leads + misreadings, kept open; no `verse`.
- `activity`/`narration_prompt`: include a `leader_note` (or `answer_key` per its dimension) only where it aids facilitation.
Write the drafts to `$SCRATCH/refs-<pericope>.json` as `[{item_id, leader_reference}, ...]`.

- [ ] **Step 4: Adversarial self-review of the drafts**

For each drafted reference, review against `rubric.reference_criteria()`:
- answer key: correct and grounded in THIS passage + brief; verse actually contains it; answerable from the pericope (D5 may name a cross-reference from the brief).
- leader note: does NOT close the open question; not leading; flags real misreadings.
Repair defects in the scratchpad JSON. If a defect recurs across items and traces to the pack, fix `build_reference_prompt.py` (record it for the writeup) and re-draft the affected items. Do NOT write anything into the store yet.

- [ ] **Step 5: Present the human-confirmation digest — STOP for approval**

Produce a digest (to the user) listing, per pericope, each item id, its kind, the reference `text`, and any `verse`. State clearly: nothing is written to the store until you approve. **Wait for the user's explicit approval.** If they request changes, revise the scratchpad drafts and re-present. Do not proceed to Step 6 without approval.

- [ ] **Step 6: Merge confirmed references into the store**

On approval, add each `leader_reference` to its item in `content_bank/store/mat.json`, stamping provenance:
```json
"provenance": {
  "drafted_by": "claude",
  "reviewed_by": "claude-adversarial",
  "reviewed_date": "2026-07-19",
  "guardrail": "WCF-1",
  "confirmed_by": "kyhhdm"
}
```
Do not touch any item's own top-level `provenance` or its `review_status` (stays `published`). Use a one-off merge helper written to `$SCRATCH` (reads `refs-<pericope>.json`, matches by `item_id`, injects `leader_reference` with the stamped provenance, writes `store/mat.json` back with `json.dump(..., ensure_ascii=False, indent=2)` and a trailing newline). Verify the diff touches only the intended items and adds only `leader_reference` keys.

- [ ] **Step 7: Run the store tests + full suite**

Run: `cd /media/pb/data/pjllc/scripture_loom && python3 -m unittest content_bank.tests.test_store_matthew -v`
Expected: PASS (`missing_reference` = 0; kinds match dimensions; memory verses clean).

Run the whole content_bank suite:
Run: `cd /media/pb/data/pjllc/scripture_loom && python3 -m unittest discover -s content_bank/tests -v`
Expected: PASS.

- [ ] **Step 8: Update PROVENANCE.md**

In `content_bank/PROVENANCE.md`, add a section recording the reference-authoring cycle: date 2026-07-19, the four pericopes augmented, that each reference was distilled from `author/briefs/<pericope>.md`, the adversarial review + human-confirmation gate (`confirmed_by = "kyhhdm"`), and any machinery change surfaced in Step 4. First read the file to match its heading style:
Run: `cd /media/pb/data/pjllc/scripture_loom && sed -n '1,40p' content_bank/PROVENANCE.md`

- [ ] **Step 9: Full verification (all three suites + gate)**

```bash
cd /media/pb/data/pjllc/scripture_loom
python3 -m unittest discover -s content_bank/tests -v
python3 -m unittest discover -s corpus/tests -v
(cd prototype && python3 -m unittest test_selector -v)
```
Expected: all green. Then confirm the gate is oblivious to the new field and the kit still generates:
```bash
python3 -c "from content_bank.lib import content; \
  pub = content.get_content('MAT', mode='product'); \
  print('published served:', len(pub)); \
  print('statuses:', {i['review_status'] for i in pub})"
```
Expected: same published count as before the change; statuses = `{'published'}`.
Locate and run the kit generator end-to-end (per `CLAUDE.md` it lives with the prototype/generator; find it first):
Run: `cd /media/pb/data/pjllc/scripture_loom && ls prototype && grep -rl "def.*kit" prototype | head`
Then run the generator command it exposes and confirm it produces a coherent kit without error. (References are leader-only data; confirming they stay off the printed page is the gate issue's verification, not this one — here we only confirm kit generation still works.)

- [ ] **Step 10: Commit**

```bash
cd /media/pb/data/pjllc/scripture_loom
git add content_bank/store/mat.json content_bank/tests/test_store_matthew.py content_bank/PROVENANCE.md
git commit -m "$(cat <<'EOF'
content_bank: leader references on the 62 published Matthew items

Human-confirmed augmentation: answer keys (D1-D5) and leader notes
(D6-D8) drafted from each pericope's brief, adversarially reviewed,
confirmed_by kyhhdm. Items stay published; item provenance untouched.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Notes for the implementer

- Run everything from the repo root `/media/pb/data/pjllc/scripture_loom` so the `content_bank` package imports resolve (tests also self-insert `parents[2]` on `sys.path`).
- Tasks 1–4 are pure machinery and fully test-driven; Task 5 is the content pass with a real human gate at Step 5 — do not write to the store before approval.
- The augmentation covers 46 eligible items (38 questions + 8 pre_reading_quests) plus any optional activity/narration references you judge helpful; the 3 memory verses get none.
