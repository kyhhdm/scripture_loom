# Book-arc Layer (MVP) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give a family reading a book a "story so far" recap on every kit and a derived zoom-out consolidation session at each meaningful section boundary, scoring cross-pericope sequence comprehension under existing dimensions — no new dimension, no authored arc content, no change to pericope authoring.

**Architecture:** Three additive components. (1) A tiny per-book **section map** in the corpus (`structure/sections/`) with a loader + validator, mirroring `corpus/lib/books.py`. (2) A **recap micro-segment** — a pure-derived selector function added to every normal kit. (3) A **zoom-out session** — a `build_kit` branch that, at section completion, returns a derived consolidation kit instead of advancing to a new pericope. Evidence from zoom-out sessions files under existing dimensions; "arc scope" is derived from the session's `kind`, not stored (derive-don't-store).

**Tech Stack:** Python 3 standard library only. JSON corpus data. `unittest`.

## Global Constraints

- **Python 3 standard library only** — no third-party packages.
- **Section data is additive to `corpus/canon/structure/`** — a new `sections/` dir, never a field on a pericope. (Probe decision D-D.)
- **Derive-don't-store for arc scope** — the only new record fields are a session `kind` (`"normal"`|`"zoom_out"`, defaulting to `"normal"` when absent) and a `section` id on zoom-out sessions. **No new evidence field, no new dimension (no D9), no new dimension vocabulary.**
- **`content_bank/author/dimensions.py` is NOT modified** — the D2 "avoid sequence spanning other pericopes" rule stays; the arc sequence exercise is selector-generated, not authored.
- **Back-compatible** — `build_kit(bank, family)` (no `sections`) must keep working exactly as today; `sections` is an optional parameter defaulting to `None`. Sessions without `kind` are treated as `"normal"`.
- **Paper / Prepare only** — recap and zoom-out are printed onto the kit; nothing runs during the gathering (`docs/unplug_assitant.md` §16). The physical "put the cards in order" is done with paper cards by the family; the selector emits the cards and the reference order, it does **not** randomize.
- **WCF-1 safety** — section boundaries follow the book's own textual structural markers; the throughline prompt is open with no answer key (no fabricated interpretation).

**Spec:** `docs/superpowers/specs/2026-07-19-book-arc-layer-design.md`.

**Test commands:**
- Corpus: `python3 -m unittest discover -s corpus/tests -v`
- Content bank: `python3 -m unittest discover -s content_bank/tests -v`
- Selector: `cd prototype && python3 -m unittest test_selector -v`

---

### Task 1: Section map — data, loader, validator

**Files:**
- Create: `corpus/canon/structure/sections/mat.json`
- Create: `corpus/lib/sections.py`
- Create: `corpus/tests/test_sections.py`
- Read only: `corpus/lib/books.py` (loader pattern to mirror), `corpus/canon/structure/pericopes/mat.json` (the ordered pericope array validated against)

**Interfaces:**
- Produces: `corpus.lib.sections.load(book, root=None) -> dict` (the parsed file) and `corpus.lib.sections.validate(book, root=None) -> list[str]` (empty means valid). Section dicts have keys `id, title_en, title_zh, first_pericope, last_pericope, marker`.

- [ ] **Step 1: Write the Matthew section map.**

Create `corpus/canon/structure/sections/mat.json` (boundary ids resolved from the pericope ranges — a contiguous partition of all 153 pericopes):

```json
{
 "book": "MAT",
 "sections": [
  {"id": "MAT-S1", "title_en": "Prologue: The Infancy", "title_zh": "", "first_pericope": "MAT-001", "last_pericope": "MAT-006", "marker": null},
  {"id": "MAT-S2", "title_en": "Book One: The Sermon on the Mount", "title_zh": "", "first_pericope": "MAT-007", "last_pericope": "MAT-033", "marker": "MAT.7.28"},
  {"id": "MAT-S3", "title_en": "Book Two: The Mission Discourse", "title_zh": "", "first_pericope": "MAT-034", "last_pericope": "MAT-053", "marker": "MAT.11.1"},
  {"id": "MAT-S4", "title_en": "Book Three: The Parables of the Kingdom", "title_zh": "", "first_pericope": "MAT-054", "last_pericope": "MAT-077", "marker": "MAT.13.53"},
  {"id": "MAT-S5", "title_en": "Book Four: The Community Discourse", "title_zh": "", "first_pericope": "MAT-078", "last_pericope": "MAT-101", "marker": "MAT.19.1"},
  {"id": "MAT-S6", "title_en": "Book Five: The Olivet Discourse", "title_zh": "", "first_pericope": "MAT-102", "last_pericope": "MAT-130", "marker": "MAT.26.1"},
  {"id": "MAT-S7", "title_en": "Epilogue: Passion and Resurrection", "title_zh": "", "first_pericope": "MAT-131", "last_pericope": "MAT-153", "marker": null}
 ]
}
```

- [ ] **Step 2: Write the failing loader/validator test.**

Create `corpus/tests/test_sections.py`:

```python
import unittest
from corpus.lib import sections


class TestSections(unittest.TestCase):
    def test_load_returns_matthew_sections(self):
        data = sections.load("MAT")
        self.assertEqual(data["book"], "MAT")
        self.assertEqual(len(data["sections"]), 7)
        self.assertEqual(data["sections"][0]["id"], "MAT-S1")

    def test_matthew_partition_is_valid(self):
        self.assertEqual(sections.validate("MAT"), [])

    def test_gap_is_reported(self):
        # A partition that skips a pericope must error.
        bad = {"sections": [
            {"id": "S1", "title_en": "a", "first_pericope": "MAT-001", "last_pericope": "MAT-002", "marker": None},
            {"id": "S2", "title_en": "b", "first_pericope": "MAT-004", "last_pericope": "MAT-153", "marker": None},
        ]}
        errors = sections.validate_data(bad, ["MAT-%03d" % i for i in range(1, 154)])
        self.assertTrue(any("MAT-S" not in e and "gap" in e.lower() or "expected" in e.lower() for e in errors))

    def test_incomplete_cover_is_reported(self):
        bad = {"sections": [
            {"id": "S1", "title_en": "a", "first_pericope": "MAT-001", "last_pericope": "MAT-006", "marker": None},
        ]}
        errors = sections.validate_data(bad, ["MAT-%03d" % i for i in range(1, 154)])
        self.assertTrue(any("cover" in e.lower() for e in errors))
```

- [ ] **Step 3: Run the test to verify it fails.**

Run: `python3 -m unittest corpus.tests.test_sections -v`
Expected: FAIL / ERROR — `module 'corpus.lib.sections' has no attribute 'load'` (module does not exist yet).

- [ ] **Step 4: Implement the loader + validator.**

Create `corpus/lib/sections.py`:

```python
"""Load and validate per-book section maps (canon/structure/sections/<book>.json).

A section map partitions a book's ordered pericopes into contiguous, named
movements drawn from the book's own structural markers. Additive to structure/;
never a per-pericope field.
"""
import json
import re
from pathlib import Path

CANON_ROOT = Path(__file__).resolve().parents[1] / "canon"

_MARKER_RE = re.compile(r"^[A-Z0-9]{3}\.\d+\.\d+$")
_REQUIRED = ("id", "title_en", "first_pericope", "last_pericope")


def load(book, root=None):
    root = Path(root) if root else CANON_ROOT
    with open(root / "structure" / "sections" / f"{book.lower()}.json", encoding="utf-8") as f:
        return json.load(f)


def _pericope_order(book, root):
    with open(root / "structure" / "pericopes" / f"{book.lower()}.json", encoding="utf-8") as f:
        return [p["id"] for p in json.load(f)["pericopes"]]


def validate_data(data, order):
    """Validate a parsed section map against an ordered list of pericope ids.
    Returns a list of error strings; empty means valid."""
    idx = {pid: i for i, pid in enumerate(order)}
    errors = []
    cursor = 0
    for s in data.get("sections", []):
        for field in _REQUIRED:
            if field not in s:
                errors.append(f"{s.get('id', '?')}: missing '{field}'")
        fi, li = idx.get(s.get("first_pericope")), idx.get(s.get("last_pericope"))
        if fi is None or li is None:
            errors.append(f"{s.get('id', '?')}: first/last pericope does not resolve")
            continue
        if fi > li:
            errors.append(f"{s.get('id', '?')}: first_pericope after last_pericope")
        if fi != cursor:
            expected = order[cursor] if cursor < len(order) else "<end>"
            errors.append(f"{s.get('id', '?')}: gap/overlap — expected first_pericope "
                          f"{expected}, got {s.get('first_pericope')}")
        cursor = li + 1
        mk = s.get("marker")
        if mk and not _MARKER_RE.match(mk):
            errors.append(f"{s.get('id', '?')}: malformed marker '{mk}'")
    if cursor != len(order):
        errors.append(f"sections do not cover all pericopes "
                      f"(covered {cursor} of {len(order)})")
    return errors


def validate(book, root=None):
    root = Path(root) if root else CANON_ROOT
    return validate_data(load(book, root), _pericope_order(book, root))
```

- [ ] **Step 5: Run tests to verify they pass.**

Run: `python3 -m unittest corpus.tests.test_sections -v`
Expected: PASS (4 tests). Then run the whole corpus suite to confirm no regressions: `python3 -m unittest discover -s corpus/tests` → OK.

- [ ] **Step 6: Commit.**

```bash
git add corpus/canon/structure/sections/mat.json corpus/lib/sections.py corpus/tests/test_sections.py
git commit -m "corpus: per-book section map with partition validator (Matthew)"
```

---

### Task 2: Recap micro-segment (`arc_recap`)

**Files:**
- Modify: `prototype/selector.py` (add `_section_pericope_ids`, `_section_of`, `arc_recap`)
- Test: `prototype/test_selector.py`

**Interfaces:**
- Consumes: `bank["pericopes"]` (ordered, each `{id, ref, title}`); a `sections` list of flattened section dicts `{id, title, first_pericope, last_pericope, marker}`; `family["sessions"]`.
- Produces: `arc_recap(sections, bank, family) -> dict | None` = `{"section": str, "studied": [title, …], "position": "N of M"}`. Helpers `_section_pericope_ids(section, order) -> list[str]` and `_section_of(sections, bank, pericope_id) -> section | None`.

- [ ] **Step 1: Write the failing test.**

Add to `prototype/test_selector.py` (the flattened section shape uses `title`, matching the bank's flattened pericope `title`):

```python
SECTIONS = [
    {"id": "MAT-S1", "title": "Prologue: The Infancy",
     "first_pericope": "MAT-001", "last_pericope": "MAT-006", "marker": None},
    {"id": "MAT-S2", "title": "Book One: The Sermon on the Mount",
     "first_pericope": "MAT-007", "last_pericope": "MAT-033", "marker": "MAT.7.28"},
]


class TestArcRecap(unittest.TestCase):
    def test_recap_names_section_and_lists_studied_titles_in_order(self):
        bank, family = load()
        # Study the first two infancy pericopes; next_passage will be MAT-003.
        family["reading_sequence"] = [p["id"] for p in bank["pericopes"]]
        family["sessions"] = [
            {"date": "d", "passage": "MAT-001", "evidence": []},
            {"date": "d", "passage": "MAT-002", "evidence": []},
        ]
        recap = selector.arc_recap(SECTIONS, bank, family)
        self.assertEqual(recap["section"], "Prologue: The Infancy")
        self.assertEqual(recap["studied"],
                         ["The Genealogy of Jesus", "The Birth of Jesus"])
        self.assertEqual(recap["position"], "2 of 6")

    def test_recap_before_any_study_names_section_only(self):
        bank, family = load()
        family["reading_sequence"] = [p["id"] for p in bank["pericopes"]]
        family["sessions"] = []
        recap = selector.arc_recap(SECTIONS, bank, family)
        self.assertEqual(recap["section"], "Prologue: The Infancy")
        self.assertEqual(recap["studied"], [])
```

- [ ] **Step 2: Run it to verify it fails.**

Run: `cd prototype && python3 -m unittest test_selector.TestArcRecap -v`
Expected: FAIL — `module 'selector' has no attribute 'arc_recap'`.

- [ ] **Step 3: Implement the helpers and `arc_recap`.**

Add to `prototype/selector.py`:

```python
def _normal_sessions(family):
    return [s for s in family["sessions"] if s.get("kind", "normal") == "normal"]


def _section_pericope_ids(section, order):
    """Pericope ids in a section, in reading order (order = bank pericope ids)."""
    i, j = order.index(section["first_pericope"]), order.index(section["last_pericope"])
    return order[i:j + 1]


def _section_of(sections, bank, pericope_id):
    order = [p["id"] for p in bank["pericopes"]]
    for section in sections:
        if pericope_id in _section_pericope_ids(section, order):
            return section
    return None


def arc_recap(sections, bank, family):
    """'The story so far' within the current section: its title and the ordered
    titles of its pericopes the family has already studied. Pure derived."""
    passage = next_passage(bank, family)
    section = _section_of(sections, bank, passage["id"])
    if not section:
        return None
    order = [p["id"] for p in bank["pericopes"]]
    title_by = {p["id"]: p["title"] for p in bank["pericopes"]}
    section_ids = _section_pericope_ids(section, order)
    studied = {s["passage"] for s in _normal_sessions(family)}
    studied_ids = [pid for pid in section_ids if pid in studied]
    return {
        "section": section["title"],
        "studied": [title_by[pid] for pid in studied_ids],
        "position": f"{len(studied_ids)} of {len(section_ids)}",
    }
```

- [ ] **Step 4: Run tests to verify they pass.**

Run: `cd prototype && python3 -m unittest test_selector.TestArcRecap -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit.**

```bash
git add prototype/selector.py prototype/test_selector.py
git commit -m "selector: derived arc_recap (story-so-far) micro-segment"
```

---

### Task 3: Zoom-out trigger + normal-only passage advance

**Files:**
- Modify: `prototype/selector.py` (`due_zoom_out`; make `next_passage` count normal sessions only)
- Test: `prototype/test_selector.py`

**Interfaces:**
- Consumes: `sections`, `family["sessions"]` (sessions may carry `kind` and, when `kind=="zoom_out"`, `section`).
- Produces: `due_zoom_out(sections, family) -> section | None`. `next_passage` unchanged externally but now ignores zoom-out sessions when computing the studied set.

- [ ] **Step 1: Write the failing tests.**

Add to `prototype/test_selector.py`:

```python
class TestZoomOutTrigger(unittest.TestCase):
    def _study_through(self, bank, family, last_id):
        order = [p["id"] for p in bank["pericopes"]]
        family["reading_sequence"] = order
        upto = order[: order.index(last_id) + 1]
        family["sessions"] = [{"date": "d", "passage": pid, "evidence": []} for pid in upto]
        return family

    def test_fires_at_section_last_pericope(self):
        bank, family = load()
        self._study_through(bank, family, "MAT-006")  # end of MAT-S1
        section = selector.due_zoom_out(SECTIONS, family)
        self.assertIsNotNone(section)
        self.assertEqual(section["id"], "MAT-S1")

    def test_does_not_fire_mid_section(self):
        bank, family = load()
        self._study_through(bank, family, "MAT-004")  # inside MAT-S1
        self.assertIsNone(selector.due_zoom_out(SECTIONS, family))

    def test_does_not_fire_twice_for_same_section(self):
        bank, family = load()
        self._study_through(bank, family, "MAT-006")
        family["sessions"].append({"date": "d", "kind": "zoom_out", "section": "MAT-S1", "evidence": []})
        self.assertIsNone(selector.due_zoom_out(SECTIONS, family))

    def test_next_passage_ignores_zoom_out_sessions(self):
        bank, family = load()
        order = [p["id"] for p in bank["pericopes"]]
        family["reading_sequence"] = order
        family["sessions"] = [
            {"date": "d", "passage": "MAT-001", "evidence": []},
            {"date": "d", "kind": "zoom_out", "section": "MAT-S1", "evidence": []},
        ]
        # The zoom-out session must not count as "studied MAT-002"; next is MAT-002.
        self.assertEqual(selector.next_passage(bank, family)["id"], "MAT-002")
```

- [ ] **Step 2: Run to verify failure.**

Run: `cd prototype && python3 -m unittest test_selector.TestZoomOutTrigger -v`
Expected: FAIL — `module 'selector' has no attribute 'due_zoom_out'`.

- [ ] **Step 3: Implement.**

In `prototype/selector.py`, change `next_passage`'s studied line to use normal sessions only:

```python
def next_passage(bank, family):
    """Next unstudied pericope in the family's reading sequence."""
    studied = {s["passage"] for s in _normal_sessions(family)}
    for pid in family["reading_sequence"]:
        if pid not in studied:
            return next(p for p in bank["pericopes"] if p["id"] == pid)
    raise ValueError("Reading sequence exhausted — extend it.")
```

Add:

```python
def due_zoom_out(sections, family):
    """The Section to zoom out on, or None. Fires when the most-recently-studied
    pericope is a section's last_pericope and no zoom_out session exists for it."""
    normal = _normal_sessions(family)
    if not normal:
        return None
    last_pid = normal[-1]["passage"]
    zoomed = {s["section"] for s in family["sessions"] if s.get("kind") == "zoom_out"}
    for section in sections:
        if section["last_pericope"] == last_pid and section["id"] not in zoomed:
            return section
    return None
```

- [ ] **Step 4: Run tests to verify they pass.**

Run: `cd prototype && python3 -m unittest test_selector.TestZoomOutTrigger -v`
Expected: PASS (4 tests). Then `cd prototype && python3 -m unittest test_selector` → all still OK (next_passage change is back-compatible: sessions without `kind` count as normal).

- [ ] **Step 5: Commit.**

```bash
git add prototype/selector.py prototype/test_selector.py
git commit -m "selector: zoom-out trigger at section completion; passage advance ignores zoom-outs"
```

---

### Task 4: `build_zoom_out_kit` contents

**Files:**
- Modify: `prototype/selector.py` (`build_zoom_out_kit`)
- Test: `prototype/test_selector.py`

**Interfaces:**
- Consumes: `bank`, `family`, `sections`, a `section` dict.
- Produces: `build_zoom_out_kit(bank, family, sections, section) -> dict` with keys `family, kind("zoom_out"), section, section_id, sequence_cards, correct_order, memory_recall, throughline_prompt, roles, selected_item_ids`.

- [ ] **Step 1: Write the failing test.**

Add to `prototype/test_selector.py`:

```python
class TestZoomOutKit(unittest.TestCase):
    def test_zoom_out_kit_contents(self):
        bank, family = load()
        order = [p["id"] for p in bank["pericopes"]]
        family["reading_sequence"] = order
        family["sessions"] = [{"date": "d", "passage": pid, "evidence": []}
                              for pid in order[:6]]  # studied all of MAT-S1
        section = SECTIONS[0]
        kit = selector.build_zoom_out_kit(bank, family, SECTIONS, section)

        self.assertEqual(kit["kind"], "zoom_out")
        self.assertEqual(kit["section_id"], "MAT-S1")
        # sequence cards are exactly the section's pericopes, in reading order
        self.assertEqual([c["id"] for c in kit["sequence_cards"]],
                         ["MAT-001", "MAT-002", "MAT-003", "MAT-004", "MAT-005", "MAT-006"])
        self.assertEqual(kit["correct_order"],
                         ["MAT-001", "MAT-002", "MAT-003", "MAT-004", "MAT-005", "MAT-006"])
        # memory_recall only contains memory verses whose passage is a studied MAT-S1 pericope
        for item in kit["memory_recall"]:
            self.assertEqual(item["type"], "memory_verse")
            self.assertIn(item["passage"], set([c["id"] for c in kit["sequence_cards"]]))
        # open throughline prompt, no answer key
        self.assertIn("Prologue: The Infancy", kit["throughline_prompt"])
```

- [ ] **Step 2: Run to verify failure.**

Run: `cd prototype && python3 -m unittest test_selector.TestZoomOutKit -v`
Expected: FAIL — `module 'selector' has no attribute 'build_zoom_out_kit'`.

- [ ] **Step 3: Implement.**

Add to `prototype/selector.py`:

```python
def build_zoom_out_kit(bank, family, sections, section):
    """A derived consolidation session over a completed section. No new passage.
    The family physically shuffles the printed cards and reorders them; the kit
    carries the cards in reading order plus the correct order for the leader."""
    order = [p["id"] for p in bank["pericopes"]]
    by_id = {p["id"]: p for p in bank["pericopes"]}
    section_ids = _section_pericope_ids(section, order)
    studied = {s["passage"] for s in _normal_sessions(family)}

    cards = [{"id": pid, "title": by_id[pid]["title"], "ref": by_id[pid]["ref"]}
             for pid in section_ids]
    memory_recall = [i for i in _published(bank, type_="memory_verse")
                     if i["passage"] in section_ids and i["passage"] in studied]

    return {
        "family": family["name"],
        "kind": "zoom_out",
        "section": section["title"],
        "section_id": section["id"],
        "sequence_cards": cards,
        "correct_order": [c["id"] for c in cards],
        "memory_recall": memory_recall,
        "throughline_prompt": f"In one sentence, what was “{section['title']}” about?",
        "roles": assign_roles(family),
        "selected_item_ids": [i["id"] for i in memory_recall],
    }
```

- [ ] **Step 4: Run tests to verify they pass.**

Run: `cd prototype && python3 -m unittest test_selector.TestZoomOutKit -v`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add prototype/selector.py prototype/test_selector.py
git commit -m "selector: build_zoom_out_kit (derived sequence/memory/throughline consolidation)"
```

---

### Task 5: Integration — `build_kit` branch, section bridge, renderer

**Files:**
- Modify: `prototype/selector.py` (`build_kit` gains optional `sections`, branches, adds `arc_recap`)
- Modify: `content_bank/lib/prototype_bank.py` (`load_sections`)
- Modify: `prototype/generate_kit.py` (load + pass sections; render `arc_recap`; render zoom-out kit)
- Test: `prototype/test_selector.py`; `content_bank/tests/test_prototype_bank.py`

**Interfaces:**
- Consumes: everything from Tasks 1–4.
- Produces: `build_kit(bank, family, sections=None) -> dict` — a zoom-out kit when one is due, else the normal kit now carrying `"arc_recap"` (only when `sections` is provided). `prototype_bank.load_sections(book, lang="en") -> list[dict]` (flattened `{id, title, first_pericope, last_pericope, marker}`).

- [ ] **Step 1: Write the failing tests.**

Add to `prototype/test_selector.py`:

```python
class TestBuildKitIntegration(unittest.TestCase):
    def test_normal_kit_includes_arc_recap_when_sections_given(self):
        bank, family = load()  # family has studied MAT-009, MAT-013; next is MAT-014
        kit = selector.build_kit(bank, family, SECTIONS)
        self.assertIn("arc_recap", kit)
        self.assertIsNotNone(kit["arc_recap"])
        self.assertNotEqual(kit.get("kind"), "zoom_out")

    def test_zoom_out_replaces_session_at_boundary(self):
        bank, family = load()
        order = [p["id"] for p in bank["pericopes"]]
        family["reading_sequence"] = order
        family["sessions"] = [{"date": "d", "passage": pid, "evidence": []}
                              for pid in order[:6]]  # completed MAT-S1
        kit = selector.build_kit(bank, family, SECTIONS)
        self.assertEqual(kit["kind"], "zoom_out")
        self.assertEqual(kit["section_id"], "MAT-S1")
        self.assertNotIn("passage", kit)  # no new pericope advanced

    def test_back_compat_without_sections(self):
        bank, family = load()
        kit = selector.build_kit(bank, family)  # no sections arg
        self.assertEqual(kit["passage"]["id"], "MAT-014")
        self.assertNotIn("arc_recap", kit)
```

Add to `content_bank/tests/test_prototype_bank.py`:

```python
    def test_load_sections_flattens_titles(self):
        from content_bank.lib import prototype_bank
        secs = prototype_bank.load_sections("MAT", lang="en")
        self.assertEqual(len(secs), 7)
        self.assertEqual(secs[0]["id"], "MAT-S1")
        self.assertEqual(secs[0]["title"], "Prologue: The Infancy")
        self.assertEqual(secs[0]["first_pericope"], "MAT-001")
```

- [ ] **Step 2: Run to verify failure.**

Run: `cd prototype && python3 -m unittest test_selector.TestBuildKitIntegration -v` → FAIL (`build_kit()` takes 2 positional args / no `arc_recap`).
Run: `python3 -m unittest content_bank.tests.test_prototype_bank -v` → FAIL (`load_sections` missing).

- [ ] **Step 3: Implement the bridge.**

Add to `content_bank/lib/prototype_bank.py`:

```python
def load_sections(book, lang="en"):
    """Flattened section list for the selector: title[lang] -> 'title'."""
    from corpus.lib import sections as sections_lib
    out = []
    for s in sections_lib.load(book)["sections"]:
        title = s.get("title_zh") if lang == "zh" and s.get("title_zh") else s["title_en"]
        out.append({
            "id": s["id"], "title": title,
            "first_pericope": s["first_pericope"],
            "last_pericope": s["last_pericope"],
            "marker": s.get("marker"),
        })
    return out
```

- [ ] **Step 4: Implement the `build_kit` branch.**

In `prototype/selector.py`, change `build_kit`:

```python
def build_kit(bank, family, sections=None):
    if sections:
        section = due_zoom_out(sections, family)
        if section:
            return build_zoom_out_kit(bank, family, sections, section)

    passage = next_passage(bank, family)
    available = available_dimensions(bank, passage["id"])
    targets = select_observation_targets(family, available)
    review = select_review_questions(bank, family)
    discussion = select_discussion_questions(bank, family, passage["id"], targets)
    main_act, young_act = select_activity(bank, family, passage["id"])
    quests = select_quests(bank, family, passage["id"])
    verse = next(iter(_published(bank, passage=passage["id"], type_="memory_verse")), None)
    narration = next(iter(_published(bank, passage=passage["id"], type_="narration_prompt")), None)

    selected = [i["id"] for i in review + discussion]
    selected += [a["id"] for a in (main_act, young_act, verse, narration) if a]
    selected += [q["item_id"] for q in quests if q["item_id"]]

    kit = {
        "family": family["name"],
        "passage": passage,
        "review_questions": review,
        "observation_targets": targets,
        "discussion_questions": discussion,
        "activity": main_act,
        "activity_young": young_act,
        "quests": quests,
        "memory_verse": verse,
        "narration_prompt": narration,
        "personalized_lines": personalized_lines(family),
        "roles": assign_roles(family),
        "selected_item_ids": selected,
    }
    if sections:
        kit["arc_recap"] = arc_recap(sections, bank, family)
    return kit
```

- [ ] **Step 5: Wire the renderer.**

In `prototype/generate_kit.py`, load and pass sections, and render the two new surfaces. Change the build call (around line 106–108):

```python
    bank = prototype_bank.load_bank("MAT", lang="en")
    sections = prototype_bank.load_sections("MAT", lang="en")
    family = json.loads((HERE / "family.json").read_text())
    kit = selector.build_kit(bank, family, sections)
```

Add a zoom-out branch at the top of `compose` (after `out = []; add = out.append`):

```python
    if kit.get("kind") == "zoom_out":
        add(f"# Zoom-out Session — {kit['section']}")
        add(f"\n*Consolidation for {kit['family']}. No new passage this session.*\n")
        add("\n## Put the story in order\n")
        add("Shuffle these cards, then place them back in reading order:\n")
        for c in kit["sequence_cards"]:
            add(f"- {c['title']}  ({c['ref']})")
        add("\n*Leader's reference (correct order):* "
            + " → ".join(c["title"] for c in kit["sequence_cards"]))
        if kit["memory_recall"]:
            add("\n\n## Memory verses from this section\n")
            for m in kit["memory_recall"]:
                add(f"- {m['body']}")
        add(f"\n\n## Throughline\n\n{kit['throughline_prompt']}\n")
        add("\n---\n")
        for r in kit["roles"]:
            add(f"- **{r['role']}** — {r['member']}")
        return "\n".join(out)
```

And render the recap on the normal kit — after the "Opening recall" block, add:

```python
    if kit.get("arc_recap"):
        r = kit["arc_recap"]
        trail = " → ".join(r["studied"]) if r["studied"] else "(beginning this section)"
        add(f"\n> **The story so far — {r['section']} ({r['position']}):** {trail}\n")
```

- [ ] **Step 6: Run all suites to verify pass + no regressions.**

Run:
- `cd prototype && python3 -m unittest test_selector -v` → OK (all, including the three new integration tests and every pre-existing test).
- `python3 -m unittest discover -s content_bank/tests` → OK.
- `python3 -m unittest discover -s corpus/tests` → OK.
- Smoke-render: `cd prototype && python3 generate_kit.py -o /tmp/kit.md` → exits 0; `/tmp/kit.md` shows the "story so far" line.

- [ ] **Step 7: Commit.**

```bash
git add prototype/selector.py content_bank/lib/prototype_bank.py prototype/generate_kit.py prototype/test_selector.py content_bank/tests/test_prototype_bank.py
git commit -m "selector: wire arc layer into build_kit + kit renderer (recap + zoom-out)"
```

---

## Self-Review (author's check against the spec)

- **Spec coverage:** §1 section map → Task 1 (data + `sections.py` loader/validator). §2 recap micro-segment → Task 2 (`arc_recap`) + Task 5 Step 5 (render). §3 zoom-out (trigger, replace-session, derived contents) → Tasks 3 (`due_zoom_out`, no passage advance) + 4 (`build_zoom_out_kit`) + 5 (`build_kit` branch, render). §4 evidence/derive-don't-store → session `kind`/`section` fields used in Tasks 3–4; no new evidence field or dimension anywhere. §5 non-goals → Global Constraints (no `dimensions.py` edit, no D9, back-compat, additive data).
- **Placeholder scan:** none — `mat.json` ids are fully resolved (contiguous partition of all 153 pericopes); every code and test step carries complete code.
- **Type/signature consistency:** `arc_recap(sections, bank, family)`, `due_zoom_out(sections, family)`, `build_zoom_out_kit(bank, family, sections, section)`, `build_kit(bank, family, sections=None)`, `load_sections(book, lang)` are used identically across their defining task, the integration task, and the renderer. Flattened section shape (`title`, not `title_en`) is consistent between `load_sections` (Task 5) and the `SECTIONS` test fixture (Tasks 2–5). Section dicts from the corpus (`title_en/title_zh`) are only ever consumed by `load_sections`, which flattens them.
- **TDD note:** every task is failing-test → run-red → implement → run-green → commit. Back-compat is explicitly tested (Task 5 `test_back_compat_without_sections`).
