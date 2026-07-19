# Arc Artifact (v2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a section-scoped tier of authored arc content — throughlines, cross-pericope threads, and arc questions — to the content bank, consumed by the zoom-out session, degrading to the shipped MVP behavior when no arc content exists.

**Architecture:** Four additive changes, all reusing existing machinery. (1) `ContentItem` gains a `section` scope (`passage` xor `section`) plus `throughline`/`thread` types and a `refs` list — pure `schema.py` validation. (2) Store validation resolves `section` ids and thread `refs`, enforces one throughline per section. (3) A section-scope authoring brief builder mirrors the pericope brief. (4) `build_zoom_out_kit` pulls published section-scoped content and the renderer prints it, falling back to the MVP's derived throughline when absent.

**Tech Stack:** Python 3 standard library only. JSON. `unittest`.

## Global Constraints

- **Python 3 standard library only.**
- **`passage` xor `section`** — a `ContentItem` carries exactly one. Never a multi-pericope `passage` (preserves probe D-B).
- **`dimensions.py` is NOT modified** — the D2 authoring reshape is retired as YAGNI; arc content is D7/D3/D5 which the rules already permit.
- **No new dimension (no D9), no new evidence field.** Arc content is scored via the MVP's `kind`-based derive-don't-store.
- **Back-compatible** — existing passage-scoped items validate unchanged; a zoom-out with no authored arc content is byte-for-byte the MVP zoom-out.
- **WCF-1** — arc content reuses the existing `leader_reference` + provenance pipeline (`answer_key` on closed dims, `leader_note` on open).
- **Section-id shape** `^[A-Z0-9]{3}-S\d+$` (e.g. `MAT-S1`); **verse-ref shape** `^[A-Z0-9]{3}\.\d+\.\d+$` (e.g. `MAT.1.22`).
- **No real store content is committed in this plan** — selector/validation tests use fixtures. Authoring reviewed MAT-S1 content into `store/mat.json` is separate WCF-1 authoring work.

**Spec:** `docs/superpowers/specs/2026-07-19-arc-artifact-v2-design.md`.

**Test commands:**
- Content bank: `python3 -m unittest discover -s content_bank/tests -v`
- Selector: `cd prototype && python3 -m unittest test_selector -v`
- Corpus: `python3 -m unittest discover -s corpus/tests -v`

---

### Task 1: Schema — `section` scope, new types, `refs`

**Files:**
- Modify: `content_bank/lib/schema.py`
- Test: `content_bank/tests/test_schema.py`

**Interfaces:**
- Produces: `schema.validate_item(item)` now accepts `section`-scoped items and the `throughline`/`thread` types. `TYPES` gains `throughline`, `thread`. New module constants `SECTION_ONLY_TYPES`, `SECTION_RE`, `REF_RE`.

- [ ] **Step 1: Write the failing tests.**

Add to `content_bank/tests/test_schema.py` (a valid section item helper + the new cases):

```python
def _throughline(**over):
    item = {
        "id": "mat-s1-tl", "section": "MAT-S1", "type": "throughline",
        "dimension": "D7", "age_tier": "all", "difficulty": 2,
        "review_status": "draft", "text": {"en": "x"}, "version": 1,
    }
    item.update(over)
    return item


class TestSectionScope(unittest.TestCase):
    def test_valid_throughline(self):
        self.assertEqual(schema.validate_item(_throughline()), [])

    def test_passage_and_section_mutually_exclusive(self):
        self.assertTrue(any("exactly one" in e
                            for e in schema.validate_item(_throughline(passage="MAT-001"))))

    def test_neither_passage_nor_section(self):
        item = _throughline()
        del item["section"]
        self.assertTrue(any("exactly one" in e for e in schema.validate_item(item)))

    def test_throughline_must_be_d7(self):
        self.assertTrue(any("D7" in e for e in schema.validate_item(_throughline(dimension="D6"))))

    def test_thread_requires_refs(self):
        item = _throughline(id="t", type="thread", dimension="D7")
        errs = schema.validate_item(item)
        self.assertTrue(any("refs" in e for e in errs))

    def test_thread_valid_with_refs(self):
        item = _throughline(id="t", type="thread", dimension="D7",
                            refs=["MAT.1.22", "MAT.2.15"])
        self.assertEqual(schema.validate_item(item), [])

    def test_thread_malformed_ref(self):
        item = _throughline(id="t", type="thread", dimension="D7", refs=["Matt 1"])
        self.assertTrue(any("malformed ref" in e for e in schema.validate_item(item)))

    def test_refs_forbidden_on_non_thread(self):
        self.assertTrue(any("refs" in e for e in schema.validate_item(_throughline(refs=["MAT.1.1"]))))

    def test_existing_passage_item_still_valid(self):
        item = {"id": "q1", "passage": "MAT-009", "dimension": "D1", "type": "question",
                "age_tier": "all", "difficulty": 1, "review_status": "draft",
                "text": {"en": "x"}, "version": 1}
        self.assertEqual(schema.validate_item(item), [])
```

- [ ] **Step 2: Run to verify failure.**

Run: `python3 -m unittest content_bank.tests.test_schema.TestSectionScope -v`
Expected: FAIL — section items rejected (`type: invalid 'throughline'`, `missing required field: passage`).

- [ ] **Step 3: Implement schema changes.**

In `content_bank/lib/schema.py`, add `import re` at the top, extend the constants, drop `passage` from `_REQUIRED`, and add `_check_scope`:

```python
import re
```

```python
TYPES = {"question", "activity", "vocab_list", "memory_verse",
         "key_facts", "narration_prompt", "pre_reading_quest",
         "throughline", "thread"}
```

```python
SECTION_ONLY_TYPES = {"throughline", "thread"}
SECTION_RE = re.compile(r"^[A-Z0-9]{3}-S\d+$")
REF_RE = re.compile(r"^[A-Z0-9]{3}\.\d+\.\d+$")
```

```python
_REQUIRED = ("id", "dimension", "type", "age_tier",
             "difficulty", "review_status", "text", "version")
```

Add the helper:

```python
def _check_scope(item, errors):
    has_p, has_s = "passage" in item, "section" in item
    if has_p == has_s:
        errors.append("scope: exactly one of 'passage' / 'section' is required")
    if has_s and not SECTION_RE.match(str(item.get("section"))):
        errors.append(f"section: malformed id '{item.get('section')}'")
    t = item.get("type")
    if t in SECTION_ONLY_TYPES and not has_s:
        errors.append(f"{t}: must be section-scoped (needs 'section')")
    if t == "thread":
        refs = item.get("refs")
        if not isinstance(refs, list) or not refs:
            errors.append("thread: 'refs' must be a non-empty list")
        else:
            for r in refs:
                if not isinstance(r, str) or not REF_RE.match(r):
                    errors.append(f"refs: malformed ref '{r}'")
    elif "refs" in item:
        errors.append("refs: only allowed on 'thread' items")
    if t == "throughline" and item.get("dimension") != "D7":
        errors.append("throughline: dimension must be D7")
    if t == "thread" and item.get("dimension") not in ("D3", "D7"):
        errors.append("thread: dimension must be D3 or D7")
```

Call it in `validate_item` — after the `difficulty` check and before `_check_text`:

```python
    _check_scope(item, errors)
```

- [ ] **Step 4: Run tests to verify pass + no regressions.**

Run: `python3 -m unittest content_bank.tests.test_schema -v` → PASS (new + existing).
If any pre-existing test asserted the error string `missing required field: passage`, update it: passage is no longer unconditionally required — a passage-less, section-less item now yields the `scope: exactly one…` error instead. Re-run the whole content_bank suite: `python3 -m unittest discover -s content_bank/tests` → OK.

- [ ] **Step 5: Commit.**

```bash
git add content_bank/lib/schema.py content_bank/tests/test_schema.py
git commit -m "schema: section scope, throughline/thread types, thread refs"
```

---

### Task 2: Store validation — section resolution, refs-in-book, one throughline per section

**Files:**
- Modify: `content_bank/lib/corpus_bridge.py` (add `section_ids`)
- Modify: `content_bank/lib/validate.py`
- Test: `content_bank/tests/test_validate.py`

**Interfaces:**
- Consumes: `schema.validate_item` (Task 1).
- Produces: `corpus_bridge.section_ids(book) -> set[str]`. `validate_store` now guards the `passage` referential check to passage-scoped items and adds section/refs/throughline-count checks.

- [ ] **Step 1: Add `corpus_bridge.section_ids`.**

Append to `content_bank/lib/corpus_bridge.py`:

```python
def section_ids(book):
    """Section ids declared in the corpus section map, or empty if none."""
    try:
        from corpus.lib import sections as _sections
        return {s["id"] for s in _sections.load(book)["sections"]}
    except FileNotFoundError:
        return set()
```

- [ ] **Step 2: Write the failing validation tests.**

Add to `content_bank/tests/test_validate.py` (follow the file's existing fixture-store pattern — a temp `store_dir` with a `<book>.json`; if the suite already has a helper to write a store, reuse it):

```python
class TestSectionValidation(unittest.TestCase):
    def _store(self, tmpdir, items):
        import json, pathlib
        p = pathlib.Path(tmpdir) / "mat.json"
        p.write_text(json.dumps({"items": items}), encoding="utf-8")
        return tmpdir

    def _tl(self, **over):
        item = {"id": "tl1", "section": "MAT-S1", "type": "throughline",
                "dimension": "D7", "age_tier": "all", "difficulty": 2,
                "review_status": "published", "text": {"en": "x"}, "version": 1,
                "provenance": {"reviewed_by": "a", "reviewed_date": "2026-07-19", "guardrail": "WCF-1"}}
        item.update(over)
        return item

    def test_valid_section_item_passes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self._store(d, [self._tl()])
            self.assertEqual(validate.validate_store("MAT", store_dir=d)["errors"], [])

    def test_unresolved_section_reported(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self._store(d, [self._tl(section="MAT-S99")])
            errs = validate.validate_store("MAT", store_dir=d)["errors"]
            self.assertTrue(any("is not a MAT section" in e for e in errs))

    def test_thread_ref_outside_book_reported(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self._store(d, [self._tl(id="t", type="thread", dimension="D7", refs=["PHP.1.7"])])
            errs = validate.validate_store("MAT", store_dir=d)["errors"]
            self.assertTrue(any("outside book MAT" in e for e in errs))

    def test_two_published_throughlines_reported(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self._store(d, [self._tl(id="a"), self._tl(id="b")])
            errs = validate.validate_store("MAT", store_dir=d)["errors"]
            self.assertTrue(any("throughline" in e and "MAT-S1" in e for e in errs))
```

- [ ] **Step 3: Run to verify failure.**

Run: `python3 -m unittest content_bank.tests.test_validate.TestSectionValidation -v`
Expected: FAIL — `validate_store` currently flags the section item's absent `passage` as "not a MAT pericope" and has no section/refs/throughline checks.

- [ ] **Step 4: Implement validation.**

In `content_bank/lib/validate.py`, inside `validate_store`, add the section-id set and replace/extend the per-item checks:

```python
    valid_ids = corpus_bridge.pericope_ids(book)
    valid_sections = corpus_bridge.section_ids(book)
```

Change the passage check to guard on scope, and add section + refs checks (inside the `for it in items:` loop, replacing the existing unconditional passage check):

```python
        p = it.get("passage")
        if p is not None and p not in valid_ids:
            errors.append(f"{iid}: passage '{p}' is not a {book} pericope")
        s = it.get("section")
        if s is not None and s not in valid_sections:
            errors.append(f"{iid}: section '{s}' is not a {book} section")
        if it.get("type") == "thread":
            for r in it.get("refs", []):
                if isinstance(r, str) and r.split(".", 1)[0] != book:
                    errors.append(f"{iid}: ref '{r}' outside book {book}")
```

After the loop (before building `counts`), add the one-throughline-per-section check:

```python
    published_tl = {}
    for it in items:
        if it.get("type") == "throughline" and it.get("review_status") == "published":
            sec = it.get("section")
            published_tl[sec] = published_tl.get(sec, 0) + 1
    for sec, n in published_tl.items():
        if n > 1:
            errors.append(f"section {sec}: {n} published throughlines (max 1)")
```

- [ ] **Step 5: Run tests to verify pass + no regressions.**

Run: `python3 -m unittest content_bank.tests.test_validate -v` → PASS.
Run the full suite `python3 -m unittest discover -s content_bank/tests` → OK (the real `store/mat.json` is all passage-scoped, so the guarded passage check is unchanged for it).

- [ ] **Step 6: Commit.**

```bash
git add content_bank/lib/corpus_bridge.py content_bank/lib/validate.py content_bank/tests/test_validate.py
git commit -m "content_bank: store validation for section-scoped items (section/refs/throughline)"
```

---

### Task 3: Section-scope authoring brief

**Files:**
- Create: `content_bank/author/build_section_brief_prompt.py`
- Test: `content_bank/tests/test_author.py`

**Interfaces:**
- Consumes: `corpus.lib.sections.load(book)`, `corpus_bridge.pericopes(book)`, `corpus_bridge.passage_text(range)`, `corpus_bridge.wcf_chapter1_text()`.
- Produces: `build_section_brief_prompt.build(section_id, book="MAT") -> str`.

- [ ] **Step 1: Write the failing test.**

Add to `content_bank/tests/test_author.py`:

```python
class TestSectionBrief(unittest.TestCase):
    def test_section_brief_renders_span_and_asks_for_arc_content(self):
        from content_bank.author import build_section_brief_prompt
        text = build_section_brief_prompt.build("MAT-S1", "MAT")
        self.assertIn("Prologue: The Infancy", text)
        self.assertIn("The Genealogy of Jesus", text)      # a pericope title in the span
        self.assertIn("The Return to Nazareth", text)       # the last pericope in MAT-S1
        for token in ("THROUGHLINE", "THREAD", "refs", "QUESTION"):
            self.assertIn(token, text)

    def test_section_brief_rejects_unknown_section(self):
        from content_bank.author import build_section_brief_prompt
        with self.assertRaises(ValueError):
            build_section_brief_prompt.build("MAT-S99", "MAT")
```

- [ ] **Step 2: Run to verify failure.**

Run: `python3 -m unittest content_bank.tests.test_author.TestSectionBrief -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the builder.**

Create `content_bank/author/build_section_brief_prompt.py`:

```python
"""Assemble the Stage-1 distillation pack for one SECTION (book-arc content).

Offline: prints a self-contained pack a human/Claude runs by hand to produce the
section's authored arc content — one throughline, named cross-pericope threads,
and arc questions — under the WCF-1 guardrail, reviewed before publish."""
import argparse

from corpus.lib import sections as _sections
from ..lib import corpus_bridge

_SHAPE = """## Produce the SECTION ARC CONTENT

Under WCF ch.1 (inspired, sufficient, Scripture-interprets-Scripture), and only
from what the text above states, draft:

**THROUGHLINE (exactly one, dimension D7).** One or two sentences: what this whole
section is about, in the text's own terms. This is what the zoom-out session prints.

**THREADS (zero or more, dimension D7 or D3).** A word, phrase, or motif that RECURS
across two or more of the section's pericopes and carries the section's argument.
For each: a name, its member verse `refs` (e.g. MAT.1.22, MAT.2.15), and a one- or
two-sentence interpretive note (what the recurrence teaches). A thread may extend
beyond this section — anchor it here if this section is its payoff.

**QUESTIONS (2-4, dimension D5/D6/D7).** Cross-pericope discussion questions for the
zoom-out — answerable only across the section, not from one pericope.

SAFEGUARD — add no doctrine the text does not state; keep to observable meaning."""


def build(section_id, book="MAT"):
    secs = {s["id"]: s for s in _sections.load(book)["sections"]}
    if section_id not in secs:
        raise ValueError(f"{section_id} is not a {book} section")
    sec = secs[section_id]
    peris = corpus_bridge.pericopes(book)
    ids = [p["id"] for p in peris]
    i, j = ids.index(sec["first_pericope"]), ids.index(sec["last_pericope"])
    span = peris[i:j + 1]

    parts = [f"# Section brief pack — {section_id}: {sec['title_en']}\n",
             f"Spans {sec['first_pericope']}..{sec['last_pericope']} "
             f"({len(span)} pericopes)\n",
             "## The section's pericopes (public-domain text) — the SUBJECT\n"]
    for p in span:
        parts.append(f"### {p['id']} — {p['title_en']} ({p['range']})\n"
                     f"{corpus_bridge.passage_text(p['range'])}\n")
    parts.append("## WCF Chapter 1 — the method guardrail (full)\n"
                 + corpus_bridge.wcf_chapter1_text() + "\n")
    parts.append(_SHAPE)
    return "\n".join(parts)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("section_id")
    ap.add_argument("--book", default="MAT")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    text = build(args.section_id, args.book)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        print(text)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify pass.**

Run: `python3 -m unittest content_bank.tests.test_author.TestSectionBrief -v` → PASS.
Run the full content_bank suite → OK.

- [ ] **Step 5: Commit.**

```bash
git add content_bank/author/build_section_brief_prompt.py content_bank/tests/test_author.py
git commit -m "author: section-scope brief builder for arc content"
```

---

### Task 4: Selector — zoom-out consumes authored arc content

**Files:**
- Modify: `prototype/selector.py` (`_published_section`; `build_zoom_out_kit`)
- Modify: `prototype/generate_kit.py` (render authored throughline/threads/questions)
- Test: `prototype/test_selector.py`

**Interfaces:**
- Consumes: bank items that may carry `section` (flattened by `prototype_bank.load_bank`, which keeps every non-`text`/`category` field including `section`, `refs`, `leader_reference`, and adds `body`).
- Produces: `build_zoom_out_kit` adds `throughline_item` (or None), `threads` (list), `section_questions` (list); `_published_section(bank, section, type_=None)`.

- [ ] **Step 1: Write the failing tests.**

Add to `prototype/test_selector.py`:

```python
def _section_item(id, type, dim, **over):
    item = {"id": id, "section": "MAT-S1", "type": type, "dimension": dim,
            "age_tier": "all", "difficulty": 2, "review_status": "published",
            "body": id + " text"}
    item.update(over)
    return item


class TestZoomOutArcContent(unittest.TestCase):
    def _completed_s1(self, bank, family):
        order = [p["id"] for p in bank["pericopes"]]
        family["reading_sequence"] = order
        family["sessions"] = [{"date": "d", "passage": pid, "evidence": []}
                              for pid in order[:6]]
        return family

    def test_authored_content_appears_in_zoom_out(self):
        bank, family = load()
        bank = {**bank, "items": bank["items"] + [
            _section_item("tl", "throughline", "D7"),
            _section_item("th", "thread", "D7", refs=["MAT.1.22", "MAT.2.15"]),
            _section_item("q", "question", "D7"),
        ]}
        self._completed_s1(bank, family)
        kit = selector.build_zoom_out_kit(bank, family, SECTIONS, SECTIONS[0])
        self.assertEqual(kit["throughline_item"]["id"], "tl")
        self.assertEqual([t["id"] for t in kit["threads"]], ["th"])
        self.assertEqual([q["id"] for q in kit["section_questions"]], ["q"])

    def test_no_authored_content_degrades_to_mvp(self):
        bank, family = load()
        self._completed_s1(bank, family)
        kit = selector.build_zoom_out_kit(bank, family, SECTIONS, SECTIONS[0])
        self.assertIsNone(kit["throughline_item"])
        self.assertEqual(kit["threads"], [])
        self.assertEqual(kit["section_questions"], [])
        self.assertIn("throughline_prompt", kit)   # MVP generic prompt still present
```

- [ ] **Step 2: Run to verify failure.**

Run: `cd prototype && python3 -m unittest test_selector.TestZoomOutArcContent -v`
Expected: FAIL — `KeyError: 'throughline_item'` (build_zoom_out_kit does not add these keys yet).

- [ ] **Step 3: Implement.**

In `prototype/selector.py`, add the helper (near `_published`):

```python
def _published_section(bank, section_id, type_=None):
    for item in bank["items"]:
        if item.get("review_status") != "published":
            continue
        if item.get("section") != section_id:
            continue
        if type_ and item.get("type") != type_:
            continue
        yield item
```

In `build_zoom_out_kit`, before the `return`, compute and attach the authored content, and extend `selected_item_ids`:

```python
    sid = section["id"]
    throughline_item = next(iter(_published_section(bank, sid, "throughline")), None)
    threads = list(_published_section(bank, sid, "thread"))
    section_questions = list(_published_section(bank, sid, "question"))
```

Then add these keys to the returned dict:

```python
        "throughline_item": throughline_item,
        "threads": threads,
        "section_questions": section_questions,
```

and change `selected_item_ids` to include them:

```python
        "selected_item_ids": [i["id"] for i in memory_recall]
        + ([throughline_item["id"]] if throughline_item else [])
        + [t["id"] for t in threads] + [q["id"] for q in section_questions],
```

- [ ] **Step 4: Render authored content in `generate_kit.py`.**

In `prototype/generate_kit.py`, in the zoom-out branch of `compose`, replace the single throughline line
`add(f"\n\n## Throughline\n\n{kit['throughline_prompt']}\n")`
with:

```python
        add("\n\n## Throughline\n")
        if kit.get("throughline_item"):
            add(kit["throughline_item"]["body"])
            lr = kit["throughline_item"].get("leader_reference")
            if lr:
                add(f"\n> *Leader:* {lr['text']['en']}")
        else:
            add(kit["throughline_prompt"])
        if kit.get("threads"):
            add("\n\n## Threads across the section\n")
            for t in kit["threads"]:
                refs = ", ".join(t.get("refs", []))
                add(f"- {t['body']}  (see {refs})")
                lr = t.get("leader_reference")
                if lr:
                    add(f"  \n  > *Leader:* {lr['text']['en']}")
        if kit.get("section_questions"):
            add("\n\n## Section questions\n")
            for q in kit["section_questions"]:
                add(f"- {q['body']}  `[{q['dimension']}]`")
```

- [ ] **Step 5: Run all suites + smoke render.**

Run:
- `cd prototype && python3 -m unittest test_selector -v` → OK (new tests + all pre-existing, incl. the MVP zoom-out test which now also sees the three new keys but asserts only its own).
- `python3 -m unittest discover -s content_bank/tests` → OK.
- `python3 -m unittest discover -s corpus/tests` → OK.
- Smoke: `cd prototype && python3 generate_kit.py -o /tmp/kit.md` → exit 0 (real store has no section content, so the zoom-out path, if reached, prints the generic prompt; a normal kit is unaffected).

- [ ] **Step 6: Commit.**

```bash
git add prototype/selector.py prototype/generate_kit.py prototype/test_selector.py
git commit -m "selector: zoom-out consumes authored throughline/threads/section questions"
```

---

## Self-Review (author's check against the spec)

- **Spec coverage:** §Data model (`section` scope, `throughline`/`thread`, `refs`) → Task 1. §Validation & store (section resolution, refs-in-book, one throughline/section) → Task 2. §Authoring pipeline (section-scope brief) → Task 3. §Selector/zoom-out integration (authored throughline replaces generic, anchored threads, section questions, degrade-to-derived) → Task 4. §Non-goals (dimensions.py untouched, no D9, no new evidence field, back-compat) → Global Constraints + the degrade-to-MVP test (Task 4 Step 1).
- **Placeholder scan:** none — every step carries complete code and concrete assertions.
- **Type/signature consistency:** `section` scope, `SECTION_RE`/`REF_RE`, and the `throughline`/`thread` types defined in Task 1 are used identically in Tasks 2 (validation) and 4 (selector). `_published_section(bank, section_id, type_)` in Task 4 mirrors the existing `_published` signature. Thread `refs` shape `MAT.1.22` is identical across schema (Task 1), store validation (Task 2), the brief (Task 3), and the selector fixture (Task 4).
- **Back-compat is explicitly tested:** `test_existing_passage_item_still_valid` (Task 1), the real-store regression (Task 2 Step 5), and `test_no_authored_content_degrades_to_mvp` (Task 4).
- **Note:** no real store content is authored here (that is separate WCF-1 work); the plan proves the machinery with fixtures.
