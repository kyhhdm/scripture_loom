# Content Bank Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the content-bank infrastructure — a gated, bilingual content store above the corpus, its validation, an offline authoring harness, and migration of the prototype's toy content onto it.

**Architecture:** A new top-level `content_bank/` package (sibling of `corpus/` and `prototype/`). `content_bank/lib` holds the schema/vocabularies, the single gated read path `get_content` (product mode serves published-only), a store validator, a thin corpus bridge, and a prototype adapter. `content_bank/author` holds offline prompt-pack and review-checklist scripts. Content is stored one JSON file per book, keyed on the corpus's stable pericope IDs. The prototype's selector/generator is repointed to the store and its toy JSON deleted.

**Tech Stack:** Python 3 standard library only. `unittest` for tests. Diff-able normalized JSON. No network at read or validate time.

## Global Constraints

- Python 3 standard library only — no third-party packages, no network at read/validate time. (Copied verbatim from the spec.)
- Diff-able normalized JSON, consistent with the corpus canon store.
- The content bank reads from the corpus and never duplicates corpus-owned data (pericope boundaries, book names).
- Controlled vocabularies live in exactly one place: `content_bank/lib/schema.py`.
- Product mode (`get_content(..., mode="product")`) serves only `review_status == "published"` items — the content gate. This is a hard, tested boundary.
- Publish invariant: any item with `review_status != "draft"` must carry `provenance.reviewed_by`, `provenance.reviewed_date`, and `provenance.guardrail == "WCF-1"`.
- Bilingual model: one logical item owns one `id`; language-specific strings live in `text: {en, zh}` (and optionally `category: {en, zh}`); at least one language key required.
- Corpus pericope IDs are the passage keys (e.g. `MAT-014`). Book code is uppercase (`MAT`); the corpus pericope file is lowercase (`corpus/canon/structure/pericopes/mat.json`).
- Test command: `python3 -m unittest discover -s content_bank/tests -v`. Prototype: `cd prototype && python3 -m unittest test_selector -v`.

## File Structure

```
content_bank/
  __init__.py                  (empty; makes content_bank a package)
  lib/
    __init__.py                (empty)
    schema.py                  vocabularies + validate_item()          [Task 1]
    content.py                 load_book_store(), get_content()         [Task 2]
    corpus_bridge.py           pericope/book/WCF/passage access to corpus [Task 3]
    validate.py                validate_store()                         [Task 4]
    prototype_bank.py          display_ref(), load_bank() adapter        [Task 6]
  author/
    __init__.py                (empty)
    dimensions.py              D1..D8 templates (encoded once)          [Task 7]
    build_draft_prompt.py      per-pericope prompt pack -> stdout/file  [Task 7]
    review_checklist.py        draft->reviewed->published checklist     [Task 7]
  store/
    matthew.json               migrated content, corpus-keyed           [Task 5]
  tests/
    test_schema.py             [Task 1]
    test_content.py            [Task 2]
    test_corpus_bridge.py      [Task 3]
    test_validate.py           [Task 4]
    test_store_matthew.py      [Task 5]
    test_prototype_bank.py     [Task 6]
    test_author.py             [Task 7]
  README.md                    [Task 8]
  PROVENANCE.md                [Task 5]
```

Prototype files modified: `prototype/generate_kit.py`, `prototype/test_selector.py`, `prototype/family.json`, `prototype/sample_output.md`; `prototype/content_bank.json` deleted. [Task 6]

### Passage mapping (prototype pericope → corpus pericope ID)

Resolved by inspecting `corpus/canon/structure/pericopes/mat.json`:

| Prototype items | Verse content | Corpus pericope |
|---|---|---|
| `mt4-*` (4 items) | Matthew 4:1–11, Temptation | **MAT-009** (`MAT.4.1-11`) |
| `mt5a-q-mountain`, `mt5a-quest-who-listens` (2 items) | Matthew 5:1–2, the crowds/mountain setup | **MAT-013** (`MAT.5.1-2`) |
| all other `mt5a-*` (15 items, incl. 1 draft) | Matthew 5:3–12, Beatitudes | **MAT-014** (`MAT.5.3-12`) |
| `mt5b-*` (4 items) | Matthew 5:13–16, Salt and Light | **MAT-015** (`MAT.5.13-16`) |

MAT-013 exists and correctly homes the two setup items, but is **not** placed in the prototype family's reading sequence, so the prototype's linear 3-passage demo (MAT-009 → MAT-014 → MAT-015) is preserved. Item IDs are kept unchanged so `family.json`'s `used_item_ids` and evidence references still resolve.

---

### Task 1: Schema and item validation

**Files:**
- Create: `content_bank/__init__.py` (empty)
- Create: `content_bank/lib/__init__.py` (empty)
- Create: `content_bank/lib/schema.py`
- Test: `content_bank/tests/test_schema.py`

**Interfaces:**
- Produces:
  - `DIMENSIONS: set[str]` (`{"D1".."D8"}`), `TYPES: set[str]`, `AGE_TIERS: set[str]`, `REVIEW_STATUSES: set[str]`, `LANGS: set[str]` (`{"en","zh"}`), `GUARDRAILS: set[str]` (`{"WCF-1"}`), `DIFFICULTIES: set[int]` (`{1,2,3}`)
  - `validate_item(item: dict) -> list[str]` — returns a list of human-readable error strings (empty list = valid). **Structural only**; does not check corpus referential integrity or ID uniqueness (those are store-level, Task 4).

- [ ] **Step 1: Write the failing test**

Create `content_bank/tests/test_schema.py`:

```python
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.lib import schema


def valid_item(**over):
    item = {
        "id": "mt5a-q-blessed",
        "passage": "MAT-014",
        "dimension": "D7",
        "type": "question",
        "age_tier": "youth",
        "difficulty": 2,
        "review_status": "published",
        "text": {"en": "Who does Jesus call blessed?"},
        "provenance": {"drafted_by": "hand", "reviewed_by": "kyhhdm",
                       "reviewed_date": "2026-07-18", "guardrail": "WCF-1"},
        "version": 1,
    }
    item.update(over)
    return item


class TestValidateItem(unittest.TestCase):
    def test_valid_item_has_no_errors(self):
        self.assertEqual(schema.validate_item(valid_item()), [])

    def test_bad_dimension_rejected(self):
        errs = schema.validate_item(valid_item(dimension="D9"))
        self.assertTrue(any("dimension" in e for e in errs))

    def test_bad_type_rejected(self):
        self.assertTrue(schema.validate_item(valid_item(type="poem")))

    def test_bad_age_tier_rejected(self):
        self.assertTrue(schema.validate_item(valid_item(age_tier="toddler")))

    def test_difficulty_out_of_range_rejected(self):
        self.assertTrue(schema.validate_item(valid_item(difficulty=4)))

    def test_text_must_have_a_language(self):
        self.assertTrue(schema.validate_item(valid_item(text={})))

    def test_text_language_must_be_non_empty(self):
        self.assertTrue(schema.validate_item(valid_item(text={"en": "  "})))

    def test_unknown_language_key_rejected(self):
        self.assertTrue(schema.validate_item(valid_item(text={"fr": "x"})))

    def test_category_only_allowed_on_quests(self):
        errs = schema.validate_item(valid_item(category={"en": "x"}))
        self.assertTrue(any("category" in e for e in errs))

    def test_category_allowed_on_pre_reading_quest(self):
        item = valid_item(type="pre_reading_quest", category={"en": "Listen for a repeat."})
        self.assertEqual(schema.validate_item(item), [])

    def test_draft_needs_no_provenance(self):
        item = valid_item(review_status="draft")
        del item["provenance"]
        self.assertEqual(schema.validate_item(item), [])

    def test_published_requires_review_provenance(self):
        item = valid_item()
        del item["provenance"]
        self.assertTrue(schema.validate_item(item))

    def test_published_requires_wcf_guardrail(self):
        item = valid_item()
        item["provenance"]["guardrail"] = "none"
        self.assertTrue(schema.validate_item(item))

    def test_missing_required_field_rejected(self):
        item = valid_item()
        del item["dimension"]
        self.assertTrue(schema.validate_item(item))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest content_bank.tests.test_schema -v` (from repo root)
Expected: FAIL — `ModuleNotFoundError: No module named 'content_bank'` (package not created yet).

- [ ] **Step 3: Write minimal implementation**

Create empty `content_bank/__init__.py` and `content_bank/lib/__init__.py`. Create `content_bank/lib/schema.py`:

```python
"""ContentItem controlled vocabularies and structural validation.

Single source of truth for the content-bank vocabularies. Structural checks
only; referential integrity (passage resolves to a corpus pericope) and ID
uniqueness are store-level concerns (see validate.py).
"""

DIMENSIONS = {f"D{i}" for i in range(1, 9)}
TYPES = {"question", "activity", "vocab_list", "memory_verse",
         "key_facts", "narration_prompt", "pre_reading_quest"}
AGE_TIERS = {"pre_reader", "child", "youth", "adult", "all"}
REVIEW_STATUSES = {"draft", "reviewed", "published"}
LANGS = {"en", "zh"}
GUARDRAILS = {"WCF-1"}
DIFFICULTIES = {1, 2, 3}

_REQUIRED = ("id", "passage", "dimension", "type", "age_tier",
             "difficulty", "review_status", "text", "version")


def _check_text(field, value, errors):
    if not isinstance(value, dict) or not value:
        errors.append(f"{field}: must be a non-empty language map")
        return
    for lang, s in value.items():
        if lang not in LANGS:
            errors.append(f"{field}: unknown language '{lang}'")
        if not isinstance(s, str) or not s.strip():
            errors.append(f"{field}: language '{lang}' text is empty")


def validate_item(item):
    """Return a list of error strings; empty means the item is structurally valid."""
    errors = []
    for field in _REQUIRED:
        if field not in item:
            errors.append(f"missing required field: {field}")
    if errors:
        return errors

    if item["dimension"] not in DIMENSIONS:
        errors.append(f"dimension: invalid '{item['dimension']}'")
    if item["type"] not in TYPES:
        errors.append(f"type: invalid '{item['type']}'")
    if item["age_tier"] not in AGE_TIERS:
        errors.append(f"age_tier: invalid '{item['age_tier']}'")
    if item["review_status"] not in REVIEW_STATUSES:
        errors.append(f"review_status: invalid '{item['review_status']}'")
    if item["difficulty"] not in DIFFICULTIES:
        errors.append(f"difficulty: must be one of {sorted(DIFFICULTIES)}")

    _check_text("text", item["text"], errors)

    if "category" in item:
        if item["type"] != "pre_reading_quest":
            errors.append("category: only allowed on pre_reading_quest items")
        else:
            _check_text("category", item["category"], errors)

    if item["review_status"] != "draft":
        prov = item.get("provenance") or {}
        if not prov.get("reviewed_by"):
            errors.append("provenance.reviewed_by: required once not draft")
        if not prov.get("reviewed_date"):
            errors.append("provenance.reviewed_date: required once not draft")
        if prov.get("guardrail") not in GUARDRAILS:
            errors.append("provenance.guardrail: must be 'WCF-1' once not draft")

    return errors
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest content_bank.tests.test_schema -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add content_bank/__init__.py content_bank/lib/__init__.py content_bank/lib/schema.py content_bank/tests/test_schema.py
git commit -m "content_bank: schema vocabularies and item validation"
```

---

### Task 2: The read path and content gate (`get_content`)

**Files:**
- Create: `content_bank/lib/content.py`
- Test: `content_bank/tests/test_content.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (reads store JSON directly).
- Produces:
  - `load_book_store(book: str, store_dir: pathlib.Path | None = None) -> dict` — loads `<store_dir>/<book_lower>.json`; default `store_dir` is `content_bank/store`.
  - `get_content(book, *, pericope=None, dimension=None, age_tier=None, lang="en", mode="product", store_dir=None) -> list[dict]` — returns full item dicts, filtered. Product mode returns only `review_status == "published"`. `age_tier` filter matches the requested tier plus `"all"`. Items lacking `lang` in their `text` map are excluded.

- [ ] **Step 1: Write the failing test**

Create `content_bank/tests/test_content.py`:

```python
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.lib import content


def item(**over):
    base = {
        "id": "x", "passage": "MAT-014", "dimension": "D7", "type": "question",
        "age_tier": "all", "difficulty": 1, "review_status": "published",
        "text": {"en": "hi"}, "version": 1,
    }
    base.update(over)
    return base


class TestGetContent(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        store = {"book": "MAT", "items": [
            item(id="pub", review_status="published"),
            item(id="draft", review_status="draft"),
            item(id="reviewed", review_status="reviewed"),
            item(id="youth", age_tier="youth"),
            item(id="p13", passage="MAT-013"),
            item(id="zhonly", text={"zh": "你好"}),
        ]}
        (self.dir / "matthew.json").write_text(json.dumps(store), encoding="utf-8")

    def ids(self, **kw):
        return {i["id"] for i in content.get_content("MAT", store_dir=self.dir, **kw)}

    def test_product_mode_serves_only_published(self):
        got = self.ids()
        self.assertIn("pub", got)
        self.assertNotIn("draft", got)
        self.assertNotIn("reviewed", got)

    def test_author_mode_serves_all_statuses(self):
        got = self.ids(mode="author")
        self.assertIn("draft", got)
        self.assertIn("reviewed", got)

    def test_pericope_filter(self):
        self.assertEqual(self.ids(pericope="MAT-013"), {"p13"})

    def test_age_tier_filter_includes_all(self):
        got = self.ids(age_tier="youth")
        self.assertIn("youth", got)   # tier match
        self.assertIn("pub", got)     # age_tier="all" always matches

    def test_missing_language_excluded(self):
        self.assertNotIn("zhonly", self.ids(lang="en"))
        self.assertIn("zhonly", self.ids(lang="zh"))

    def test_dimension_filter(self):
        self.assertEqual(self.ids(dimension="D1"), set())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest content_bank.tests.test_content -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'content_bank.lib.content'`.

- [ ] **Step 3: Write minimal implementation**

Create `content_bank/lib/content.py`:

```python
"""The single gated read path for content-bank items.

Product mode is the content gate: only review_status == "published" items are
served. Author mode returns every status and is used only by authoring tools.
"""
import json
import pathlib

_STORE_DIR = pathlib.Path(__file__).resolve().parents[1] / "store"


def _store_path(book, store_dir):
    base = pathlib.Path(store_dir) if store_dir is not None else _STORE_DIR
    return base / f"{book.lower()}.json"


def load_book_store(book, store_dir=None):
    with open(_store_path(book, store_dir), encoding="utf-8") as f:
        return json.load(f)


def get_content(book, *, pericope=None, dimension=None, age_tier=None,
                lang="en", mode="product", store_dir=None):
    items = load_book_store(book, store_dir).get("items", [])
    out = []
    for it in items:
        if mode == "product" and it.get("review_status") != "published":
            continue
        if pericope is not None and it.get("passage") != pericope:
            continue
        if dimension is not None and it.get("dimension") != dimension:
            continue
        if age_tier is not None and it.get("age_tier") not in (age_tier, "all"):
            continue
        if lang is not None and lang not in (it.get("text") or {}):
            continue
        out.append(it)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest content_bank.tests.test_content -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add content_bank/lib/content.py content_bank/tests/test_content.py
git commit -m "content_bank: gated read path get_content (published-only in product mode)"
```

---

### Task 3: Corpus bridge

**Files:**
- Create: `content_bank/lib/corpus_bridge.py`
- Test: `content_bank/tests/test_corpus_bridge.py`

**Interfaces:**
- Consumes: nothing from earlier tasks; reads corpus JSON directly and lazily imports `corpus/lib/passage.py` for passage text.
- Produces:
  - `pericopes(book: str) -> list[dict]` — the corpus pericope records for a book (each has `id`, `range`, `title_en`, `title_zh`).
  - `pericope_ids(book: str) -> set[str]`
  - `book_name(book: str, lang: str = "en") -> str`
  - `wcf_chapter1_text() -> str` — WCF chapter 1, sections joined as `"1.<n> <text>"` lines.
  - `passage_text(range_str: str, version: str = "BSB") -> str` — verse lines joined, via the corpus license gate.

- [ ] **Step 1: Write the failing test**

Create `content_bank/tests/test_corpus_bridge.py`:

```python
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.lib import corpus_bridge as cb


class TestCorpusBridge(unittest.TestCase):
    def test_pericope_ids_include_known_matthew_ids(self):
        ids = cb.pericope_ids("MAT")
        self.assertIn("MAT-009", ids)
        self.assertIn("MAT-014", ids)
        self.assertIn("MAT-015", ids)

    def test_pericope_records_have_ranges(self):
        by_id = {p["id"]: p for p in cb.pericopes("MAT")}
        self.assertEqual(by_id["MAT-014"]["range"], "MAT.5.3-12")

    def test_book_name_en_and_zh(self):
        self.assertEqual(cb.book_name("MAT", "en"), "Matthew")
        self.assertTrue(cb.book_name("MAT", "zh"))  # non-empty Chinese name

    def test_wcf_chapter1_mentions_scripture(self):
        text = cb.wcf_chapter1_text()
        self.assertIn("1.1", text)
        self.assertIn("Holy Scripture", text) if "Holy Scripture" in text else self.assertTrue(text)

    def test_passage_text_returns_verses(self):
        text = cb.passage_text("MAT.5.13-16", version="BSB")
        self.assertIn("salt", text.lower())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest content_bank.tests.test_corpus_bridge -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

Create `content_bank/lib/corpus_bridge.py`:

```python
"""Read-only access to corpus assets the content bank depends on.

Pericope, book, and WCF data are read directly from the corpus JSON canon.
Passage text goes through the corpus license gate (corpus/lib/passage.py),
imported lazily so importing this module never requires the corpus on sys.path.
"""
import json
import pathlib

_REPO = pathlib.Path(__file__).resolve().parents[2]
_CORPUS = _REPO / "corpus"


def _load(rel):
    with open(_CORPUS / rel, encoding="utf-8") as f:
        return json.load(f)


def pericopes(book):
    data = _load(f"canon/structure/pericopes/{book.lower()}.json")
    return data["pericopes"] if isinstance(data, dict) and "pericopes" in data else data


def pericope_ids(book):
    return {p["id"] for p in pericopes(book)}


def book_name(book, lang="en"):
    books = _load("canon/structure/books.json")
    key = "name_zh" if lang == "zh" else "name_en"
    return books[book][key]


def wcf_chapter1_text():
    wcf = _load("canon/lampposts/wcf.json")
    ch1 = next(c for c in wcf["chapters"] if c["n"] == 1)
    lines = [f"Chapter 1: {ch1['title']}"]
    for s in ch1["sections"]:
        lines.append(f"1.{s['n']} {s['text']}")
    return "\n".join(lines)


def passage_text(range_str, version="BSB"):
    import sys
    sys.path.insert(0, str(_CORPUS))
    from lib import passage  # corpus/lib/passage.py
    p = passage.get_passage(version, range_str, mode="product")
    return "\n".join(f"{ref}  {text}" for ref, text in p.verses.items())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest content_bank.tests.test_corpus_bridge -v`
Expected: PASS. (If `test_passage_text` fails because BSB lacks that range, fall back to `version="WEB"` in the test and in downstream callers — both are public-domain displayable.)

- [ ] **Step 5: Commit**

```bash
git add content_bank/lib/corpus_bridge.py content_bank/tests/test_corpus_bridge.py
git commit -m "content_bank: corpus bridge (pericopes, book names, WCF ch.1, passage text)"
```

---

### Task 4: Store validator (referential integrity, uniqueness, coverage)

**Files:**
- Create: `content_bank/lib/validate.py`
- Test: `content_bank/tests/test_validate.py`

**Interfaces:**
- Consumes: `schema.validate_item` (Task 1), `content.load_book_store` (Task 2), `corpus_bridge.pericope_ids` (Task 3).
- Produces:
  - `validate_store(book, store_dir=None) -> dict` with keys:
    - `errors: list[str]` — per-item schema errors, duplicate IDs, and dangling `passage` references.
    - `counts: dict` — `{"items", "published", "draft", "reviewed", "by_lang": {"en", "zh"}, "missing_zh", "missing_en"}`.

- [ ] **Step 1: Write the failing test**

Create `content_bank/tests/test_validate.py`:

```python
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.lib import validate


def item(**over):
    base = {
        "id": "a", "passage": "MAT-014", "dimension": "D7", "type": "question",
        "age_tier": "all", "difficulty": 1, "review_status": "draft",
        "text": {"en": "hi"}, "version": 1,
    }
    base.update(over)
    return base


class TestValidateStore(unittest.TestCase):
    def _write(self, items):
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "matthew.json").write_text(
            json.dumps({"book": "MAT", "items": items}), encoding="utf-8")
        return d

    def test_clean_store_has_no_errors(self):
        d = self._write([item(id="a"), item(id="b", passage="MAT-015")])
        self.assertEqual(validate.validate_store("MAT", store_dir=d)["errors"], [])

    def test_dangling_passage_is_error(self):
        d = self._write([item(id="a", passage="MAT-999")])
        errs = validate.validate_store("MAT", store_dir=d)["errors"]
        self.assertTrue(any("MAT-999" in e for e in errs))

    def test_duplicate_id_is_error(self):
        d = self._write([item(id="dup"), item(id="dup", passage="MAT-015")])
        errs = validate.validate_store("MAT", store_dir=d)["errors"]
        self.assertTrue(any("dup" in e for e in errs))

    def test_schema_error_surfaced(self):
        d = self._write([item(id="a", dimension="D9")])
        self.assertTrue(validate.validate_store("MAT", store_dir=d)["errors"])

    def test_counts_and_bilingual_coverage(self):
        d = self._write([
            item(id="a", text={"en": "x"}),
            item(id="b", text={"en": "x", "zh": "y"}, passage="MAT-015"),
        ])
        counts = validate.validate_store("MAT", store_dir=d)["counts"]
        self.assertEqual(counts["items"], 2)
        self.assertEqual(counts["by_lang"]["zh"], 1)
        self.assertEqual(counts["missing_zh"], 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest content_bank.tests.test_validate -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

Create `content_bank/lib/validate.py`:

```python
"""Store-level validation: schema, ID uniqueness, corpus referential integrity,
and bilingual coverage counts."""
from . import schema, content, corpus_bridge


def validate_store(book, store_dir=None):
    items = content.load_book_store(book, store_dir).get("items", [])
    valid_ids = corpus_bridge.pericope_ids(book)
    errors = []
    seen = set()

    for it in items:
        iid = it.get("id", "<no-id>")
        for e in schema.validate_item(it):
            errors.append(f"{iid}: {e}")
        if iid in seen:
            errors.append(f"{iid}: duplicate id")
        seen.add(iid)
        if it.get("passage") not in valid_ids:
            errors.append(f"{iid}: passage '{it.get('passage')}' is not a {book} pericope")

    counts = {
        "items": len(items),
        "published": sum(1 for i in items if i.get("review_status") == "published"),
        "draft": sum(1 for i in items if i.get("review_status") == "draft"),
        "reviewed": sum(1 for i in items if i.get("review_status") == "reviewed"),
        "by_lang": {
            "en": sum(1 for i in items if "en" in (i.get("text") or {})),
            "zh": sum(1 for i in items if "zh" in (i.get("text") or {})),
        },
    }
    counts["missing_zh"] = counts["items"] - counts["by_lang"]["zh"]
    counts["missing_en"] = counts["items"] - counts["by_lang"]["en"]
    return {"errors": errors, "counts": counts}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest content_bank.tests.test_validate -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add content_bank/lib/validate.py content_bank/tests/test_validate.py
git commit -m "content_bank: store validator (referential integrity + coverage counts)"
```

---

### Task 5: Migrate prototype content into the store

**Files:**
- Create: `content_bank/store/matthew.json`
- Create: `content_bank/PROVENANCE.md`
- Test: `content_bank/tests/test_store_matthew.py`

**Interfaces:**
- Consumes: `validate.validate_store` (Task 4).
- Produces: `content_bank/store/matthew.json` — the migrated content, corpus-keyed, `body` → `text.en`, one seeded `zh` string.

**Migration rules** (apply to every item in `prototype/content_bank.json`):
- Keep the item `id` unchanged.
- Replace `passage` per the mapping table in the File Structure section (mt4-* → MAT-009; `mt5a-q-mountain` and `mt5a-quest-who-listens` → MAT-013; other mt5a-* → MAT-014; mt5b-* → MAT-015).
- Rename `body` (string) → `text: {"en": <body>}`. For quests, rename `category` (string) → `category: {"en": <category>}`.
- On `mt5a-mv-peacemakers` only, add a `zh` translation to `text` to exercise the bilingual path: `"zh": "“使人和睦的人有福了，因为他们必称为神的儿子。”—马太福音 5:9"`.
- Add `"version": 1` to every item.
- For every non-`draft` item, add `"provenance": {"drafted_by": "hand", "reviewed_by": "kyhhdm", "reviewed_date": "2026-07-18", "guardrail": "WCF-1"}`. (The prototype content was human-authored and is treated as reviewed.) Leave the single `draft` item (`mt5a-q-draft-kingdom`) without provenance.
- Do **not** carry over the prototype's `pericopes` array — pericope metadata now comes from the corpus.

- [ ] **Step 1: Write the failing test**

Create `content_bank/tests/test_store_matthew.py`:

```python
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.lib import validate, content


class TestMatthewStore(unittest.TestCase):
    def test_store_is_valid(self):
        result = validate.validate_store("MAT")
        self.assertEqual(result["errors"], [])

    def test_expected_counts(self):
        counts = validate.validate_store("MAT")["counts"]
        self.assertEqual(counts["items"], 25)
        self.assertEqual(counts["published"], 24)
        self.assertEqual(counts["draft"], 1)
        self.assertEqual(counts["by_lang"]["zh"], 1)   # one seeded translation
        self.assertEqual(counts["missing_zh"], 24)

    def test_beatitudes_split(self):
        p13 = {i["id"] for i in content.get_content("MAT", pericope="MAT-013", mode="author")}
        self.assertEqual(p13, {"mt5a-q-mountain", "mt5a-quest-who-listens"})

    def test_draft_hidden_in_product_mode(self):
        ids = {i["id"] for i in content.get_content("MAT", mode="product", lang="en")}
        self.assertNotIn("mt5a-q-draft-kingdom", ids)

    def test_seeded_translation_present(self):
        zh = content.get_content("MAT", pericope="MAT-014", lang="zh")
        self.assertIn("mt5a-mv-peacemakers", {i["id"] for i in zh})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest content_bank.tests.test_store_matthew -v`
Expected: FAIL — `FileNotFoundError` (no `store/matthew.json`).

- [ ] **Step 3: Build the store file and provenance**

Create `content_bank/store/matthew.json` by transcribing all 25 items from `prototype/content_bank.json` under the migration rules above. The full item list and their target passages (from the mapping table):

- MAT-009: `mt4-q-who-tempted` (D1), `mt4-q-how-answered` (D4), `mt4-q-order` (D2), `mt4-q-which-book` (D3)
- MAT-013: `mt5a-q-mountain` (D2), `mt5a-quest-who-listens` (D1, pre_reading_quest, has category)
- MAT-014: `mt5a-q-repeats` (D3), `mt5a-q-who-blessed` (D7), `mt5a-q-hardest` (D6), `mt5a-q-remember` (D4), `mt5a-q-ot-echo` (D5), `mt5a-q-draft-kingdom` (D7, **draft, no provenance**), `mt5a-act-match` (D4), `mt5a-act-match-young` (D4), `mt5a-act-strips` (D2), `mt5a-quest-tally` (D3, has category), `mt5a-quest-kind-of-list` (D7, has category), `mt5a-quest-ot-hunt` (D5, has category), `mt5a-quest-they-you` (D7, has category), `mt5a-mv-peacemakers` (D4, **+zh**), `mt5a-narr` (D7)
- MAT-015: `mt5b-q-salt` (D3), `mt5b-q-light-why` (D7), `mt5b-quest-count-images` (D3, has category), `mt5b-mv-light` (D4)

Example of the first migrated item (follow this exact shape for all 25):

```json
{
  "book": "MAT",
  "items": [
    {
      "id": "mt4-q-who-tempted",
      "passage": "MAT-009",
      "dimension": "D1",
      "type": "question",
      "age_tier": "all",
      "difficulty": 1,
      "review_status": "published",
      "text": { "en": "Who was tempted in the wilderness, and by whom?" },
      "provenance": { "drafted_by": "hand", "reviewed_by": "kyhhdm", "reviewed_date": "2026-07-18", "guardrail": "WCF-1" },
      "version": 1
    }
  ]
}
```

Example draft item (no provenance):

```json
{
  "id": "mt5a-q-draft-kingdom",
  "passage": "MAT-014",
  "dimension": "D7",
  "type": "question",
  "age_tier": "adult",
  "difficulty": 3,
  "review_status": "draft",
  "text": { "en": "DRAFT — not yet reviewed against the confessional standard." },
  "version": 1
}
```

Example quest with bilingual category rename:

```json
{
  "id": "mt5a-quest-tally",
  "passage": "MAT-014",
  "dimension": "D3",
  "type": "pre_reading_quest",
  "age_tier": "child",
  "difficulty": 1,
  "review_status": "published",
  "text": { "en": "🔍 Listen for a word Jesus says again and again at the start of his sentences. Every time you hear it, make a tally mark. How many did you count?" },
  "category": { "en": "Listen for something that repeats." },
  "provenance": { "drafted_by": "hand", "reviewed_by": "kyhhdm", "reviewed_date": "2026-07-18", "guardrail": "WCF-1" },
  "version": 1
}
```

The `mt5a-mv-peacemakers` item's `text` gets both languages:

```json
"text": {
  "en": "\"Blessed are the peacemakers, for they shall be called children of God.\" — Matthew 5:9",
  "zh": "“使人和睦的人有福了，因为他们必称为神的儿子。”—马太福音 5:9"
}
```

Create `content_bank/PROVENANCE.md`:

```markdown
# Content bank provenance

## Seed content (2026-07-18)

The initial `store/matthew.json` items were migrated from the kit-generator
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest content_bank.tests.test_store_matthew -v`
Expected: PASS. If `test_expected_counts` fails, recount the transcribed items against the mapping table (25 total: 4 + 2 + 15 + 4).

- [ ] **Step 5: Commit**

```bash
git add content_bank/store/matthew.json content_bank/PROVENANCE.md content_bank/tests/test_store_matthew.py
git commit -m "content_bank: migrate prototype content to corpus-keyed store"
```

---

### Task 6: Prototype adapter (`display_ref`, `load_bank`)

**Files:**
- Create: `content_bank/lib/prototype_bank.py`
- Test: `content_bank/tests/test_prototype_bank.py`

**Interfaces:**
- Consumes: `content.get_content` (Task 2), `corpus_bridge.pericopes` / `book_name` (Task 3).
- Produces:
  - `display_ref(range_str: str, lang: str = "en") -> str` — e.g. `("MAT.5.3-12","en") -> "Matthew 5:3–12"`, `("MAT.5.1-2","en") -> "Matthew 5:1–2"`, `("MAT.4.1-11","en") -> "Matthew 4:1–11"`. Uses an en dash (`–`) between verses.
  - `load_bank(book: str, lang: str = "en", store_dir=None) -> dict` — returns the legacy bank shape the prototype selector expects: `{"pericopes": [{"id","ref","title"}...], "items": [{... "body", "category"?, "passage", "dimension", "type", "age_tier", "difficulty", "review_status", "id"}...]}`. `pericopes` includes every corpus pericope for the book (id, `display_ref` as `ref`, `title_en`/`title_zh` as `title`). `items` are the product-mode items for `lang`, with `text[lang]` flattened to `body` and `category[lang]` flattened to `category`.

- [ ] **Step 1: Write the failing test**

Create `content_bank/tests/test_prototype_bank.py`:

```python
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.lib import prototype_bank as pb


class TestDisplayRef(unittest.TestCase):
    def test_multi_verse(self):
        self.assertEqual(pb.display_ref("MAT.5.3-12", "en"), "Matthew 5:3–12")

    def test_two_verse(self):
        self.assertEqual(pb.display_ref("MAT.5.1-2", "en"), "Matthew 5:1–2")

    def test_cross_chapter_style_range(self):
        self.assertEqual(pb.display_ref("MAT.4.1-11", "en"), "Matthew 4:1–11")


class TestLoadBank(unittest.TestCase):
    def setUp(self):
        self.bank = pb.load_bank("MAT", lang="en")

    def test_pericopes_include_corpus_ids_with_display_refs(self):
        by_id = {p["id"]: p for p in self.bank["pericopes"]}
        self.assertEqual(by_id["MAT-014"]["ref"], "Matthew 5:3–12")
        self.assertEqual(by_id["MAT-014"]["title"], "The Beatitudes")

    def test_items_are_product_mode_with_flattened_body(self):
        ids = {i["id"] for i in self.bank["items"]}
        self.assertIn("mt5a-q-who-blessed", ids)
        self.assertNotIn("mt5a-q-draft-kingdom", ids)  # draft gated out
        item = next(i for i in self.bank["items"] if i["id"] == "mt5a-q-who-blessed")
        self.assertIsInstance(item["body"], str)
        self.assertNotIn("text", item)

    def test_quest_category_flattened(self):
        q = next(i for i in self.bank["items"] if i["id"] == "mt5a-quest-tally")
        self.assertIsInstance(q["category"], str)

    def test_zh_bank_uses_translation(self):
        zh = pb.load_bank("MAT", lang="zh")
        mv = next(i for i in zh["items"] if i["id"] == "mt5a-mv-peacemakers")
        self.assertIn("马太福音", mv["body"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest content_bank.tests.test_prototype_bank -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

Create `content_bank/lib/prototype_bank.py`:

```python
"""Adapter producing the legacy 'bank' dict shape the kit-generator prototype
consumes, sourced from the gated store and corpus pericope metadata.

Keeps the prototype selector logic unchanged: text[lang] is flattened to 'body'
and category[lang] to 'category' for the requested language.
"""
from . import content, corpus_bridge


def display_ref(range_str, lang="en"):
    # range_str like "MAT.5.3-12" or "MAT.5.1" (single verse)
    book_code, chapter, verses = range_str.split(".", 2)
    name = corpus_bridge.book_name(book_code, lang)
    if "-" in verses:
        v1, v2 = verses.split("-", 1)
        span = f"{v1}–{v2}"  # en dash
    else:
        span = verses
    return f"{name} {chapter}:{span}"


def load_bank(book, lang="en", store_dir=None):
    pericopes = [
        {
            "id": p["id"],
            "ref": display_ref(p["range"], lang),
            "title": p.get("title_zh") if lang == "zh" and p.get("title_zh") else p["title_en"],
        }
        for p in corpus_bridge.pericopes(book)
    ]
    items = []
    for it in content.get_content(book, lang=lang, mode="product", store_dir=store_dir):
        flat = {k: v for k, v in it.items() if k not in ("text", "category")}
        flat["body"] = it["text"][lang]
        if "category" in it and lang in it["category"]:
            flat["category"] = it["category"][lang]
        items.append(flat)
    return {"pericopes": pericopes, "items": items}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest content_bank.tests.test_prototype_bank -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add content_bank/lib/prototype_bank.py content_bank/tests/test_prototype_bank.py
git commit -m "content_bank: prototype bank adapter (display_ref, load_bank)"
```

---

### Task 7: Authoring harness (prompt pack + review checklist)

**Files:**
- Create: `content_bank/author/__init__.py` (empty)
- Create: `content_bank/author/dimensions.py`
- Create: `content_bank/author/build_draft_prompt.py`
- Create: `content_bank/author/review_checklist.py`
- Test: `content_bank/tests/test_author.py`

**Interfaces:**
- Consumes: `corpus_bridge.pericopes` / `wcf_chapter1_text` / `passage_text` / `book_name` (Task 3), `schema` vocabularies (Task 1).
- Produces:
  - `dimensions.TEMPLATES: dict[str, str]` — `"D1".."D8"` → one-line template description.
  - `build_draft_prompt.build(pericope_id: str, book: str = "MAT") -> str` — the assembled prompt-pack markdown.
  - `review_checklist.build(guardrail: str = "WCF-1") -> str` — the review checklist markdown.
  - Both scripts are runnable: `python3 -m content_bank.author.build_draft_prompt MAT-014` prints the pack; `--out PATH` writes it. `python3 -m content_bank.author.review_checklist` prints the checklist.

- [ ] **Step 1: Write the failing test**

Create `content_bank/tests/test_author.py`:

```python
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.author import build_draft_prompt, review_checklist, dimensions


class TestBuildDraftPrompt(unittest.TestCase):
    def setUp(self):
        self.prompt = build_draft_prompt.build("MAT-014", book="MAT")

    def test_includes_passage_reference_and_text(self):
        self.assertIn("MAT-014", self.prompt)
        self.assertIn("Beatitudes", self.prompt)
        self.assertIn("blessed", self.prompt.lower())  # passage text present

    def test_includes_westminster_guardrail(self):
        self.assertIn("Westminster", self.prompt)
        self.assertIn("1.1", self.prompt)  # WCF chapter 1 sections

    def test_includes_all_dimension_templates(self):
        for d in dimensions.TEMPLATES:
            self.assertIn(d, self.prompt)

    def test_includes_schema_vocabularies(self):
        self.assertIn("pre_reading_quest", self.prompt)  # a type
        self.assertIn("review_status", self.prompt)


class TestReviewChecklist(unittest.TestCase):
    def test_checklist_covers_conformity_accuracy_age_fit(self):
        text = review_checklist.build().lower()
        self.assertIn("westminster", text)
        self.assertIn("accura", text)
        self.assertIn("age", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest content_bank.tests.test_author -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

Create `content_bank/author/__init__.py` (empty). Create `content_bank/author/dimensions.py`:

```python
"""The eight fluency dimensions, encoded once for the drafting prompt.
Source of truth for meaning remains docs/design-kit_generator.md Part 1."""

TEMPLATES = {
    "D1": "People & Places — who the people are and where events happen.",
    "D2": "Event Sequence — the order and flow of events.",
    "D3": "Vocabulary — the Bible's own key terms and repeated phrases.",
    "D4": "Memory — memory verses, key phrases, passage recall.",
    "D5": "Connections — links to other passages and larger patterns.",
    "D6": "Questions — the learner's own question-asking, prompted here.",
    "D7": "Interpretation — what the text says, then why.",
    "D8": "Application — bringing the passage into life, observably.",
}
```

Create `content_bank/author/build_draft_prompt.py`:

```python
"""Assemble an offline drafting prompt pack for one pericope.

No network, no API call: this prints a self-contained prompt a human (or Claude)
runs by hand to produce draft ContentItems, which content_bank.lib.validate then
checks before they enter the store.
"""
import argparse

from ..lib import corpus_bridge, schema
from . import dimensions

_SCHEMA_BLOCK = """Each item MUST be a JSON object with these fields:
  id             globally unique, stable, kebab-case
  passage        the pericope id below
  dimension      one of: {dimensions}
  type           one of: {types}
  age_tier       one of: {tiers}
  difficulty     one of: 1, 2, 3
  review_status  "draft"   (all newly drafted items start as draft)
  text           {{ "en": "...", "zh": "..." }}  (>= 1 language; en required for now)
  category       {{ "en": "..." }}  (ONLY for pre_reading_quest items)
  version        1
Do not add provenance; the human reviewer stamps it at publish time."""


def build(pericope_id, book="MAT"):
    peris = {p["id"]: p for p in corpus_bridge.pericopes(book)}
    if pericope_id not in peris:
        raise ValueError(f"{pericope_id} is not a {book} pericope")
    p = peris[pericope_id]
    name = corpus_bridge.book_name(book, "en")
    parts = []
    parts.append(f"# Drafting pack — {pericope_id}: {p['title_en']}\n")
    parts.append(f"Passage: {name} ({p['range']})\n")
    parts.append("## The passage (public-domain text)\n")
    parts.append(corpus_bridge.passage_text(p["range"]) + "\n")
    parts.append("## Confessional guardrail (a hard constraint on every item)\n")
    parts.append("Draft WITHIN the Westminster Confession of Faith. Content that "
                 "hedges on Scripture's reliability, inspiration, or sufficiency "
                 "fails review.\n")
    parts.append(corpus_bridge.wcf_chapter1_text() + "\n")
    parts.append("## Fluency dimensions to cover\n")
    for d, desc in dimensions.TEMPLATES.items():
        parts.append(f"- {d}: {desc}")
    parts.append("")
    parts.append("## Output schema\n")
    parts.append(_SCHEMA_BLOCK.format(
        dimensions=", ".join(sorted(schema.DIMENSIONS)),
        types=", ".join(sorted(schema.TYPES)),
        tiers=", ".join(sorted(schema.AGE_TIERS))))
    parts.append("")
    parts.append("Return a JSON array of draft items for this pericope.")
    return "\n".join(parts)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("pericope_id")
    ap.add_argument("--book", default="MAT")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    text = build(args.pericope_id, args.book)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        print(text)


if __name__ == "__main__":
    main()
```

Create `content_bank/author/review_checklist.py`:

```python
"""Print the draft -> reviewed -> published review checklist a human fills in."""
import argparse

_CHECKLIST = """# Content review checklist ({guardrail})

Advance an item draft -> reviewed -> published only when every box is checked.

## Confessional conformity (Westminster Confession, Chapter 1)
- [ ] Affirms, and does not hedge on, Scripture's inspiration, infallibility,
      inerrancy, sufficiency, and clarity.
- [ ] Treats Scripture as interpreting Scripture (WCF 1.9); no private novelty.
- [ ] Draws meaning from the text, not from speculation.

## Accuracy
- [ ] Every factual claim is correct against the passage and the corpus lampposts.
- [ ] Names, places, sequence, and quotations match the text.

## Age fitness
- [ ] Language and difficulty match the item's age_tier.
- [ ] Activities are doable on paper with the stated materials.

## Evidence, never judgment
- [ ] Prompts elicit observable behavior, never assessments of faith or character.

On pass, stamp provenance:
  reviewed_by, reviewed_date, guardrail={guardrail}, and set review_status.
"""


def build(guardrail="WCF-1"):
    return _CHECKLIST.format(guardrail=guardrail)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--guardrail", default="WCF-1")
    args = ap.parse_args(argv)
    print(build(args.guardrail))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest content_bank.tests.test_author -v`
Expected: PASS. Also spot-check the script: `python3 -m content_bank.author.build_draft_prompt MAT-014 | head -30`.

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/ content_bank/tests/test_author.py
git commit -m "content_bank: offline authoring harness (draft prompt pack + review checklist)"
```

---

### Task 8: Rewire the prototype and finish

**Files:**
- Modify: `prototype/generate_kit.py`
- Modify: `prototype/test_selector.py`
- Modify: `prototype/family.json`
- Regenerate: `prototype/sample_output.md`
- Delete: `prototype/content_bank.json`
- Create: `content_bank/README.md`

**Interfaces:**
- Consumes: `prototype_bank.load_bank` (Task 6).

- [ ] **Step 1: Update the prototype fixtures and test IDs (write the failing test first)**

Edit `prototype/family.json`: change `reading_sequence` and the session `passage` to corpus IDs. Set:

```json
"reading_sequence": ["MAT-009", "MAT-014", "MAT-015"],
```
and in the single session (`"date": "2026-07-12"`) change `"passage": "mt-4-1-11"` to `"passage": "MAT-009"`. Leave `used_item_ids` (`mt4-q-who-tempted`, `mt4-q-how-answered`) unchanged — item ids did not change.

Edit `prototype/test_selector.py`:
- Replace `load()` so the bank comes from the adapter instead of the deleted JSON:

```python
import sys
sys.path.insert(0, str(HERE.parent))          # repo root, for content_bank
from content_bank.lib import prototype_bank


def load():
    bank = prototype_bank.load_bank("MAT", lang="en")
    family = json.loads((HERE / "family.json").read_text())
    return bank, family
```
- Update the hard-coded pericope IDs in assertions:
  - `test_next_passage_follows_reading_sequence`: expect `"MAT-014"` (after the studied MAT-009, the next in sequence).
  - `test_after_studying_beatitudes_next_is_salt_and_light`: append a session with `"passage": "MAT-014"`; expect `"MAT-015"`.
  - `test_review_questions_come_from_studied_passages_only`: expect each `q["passage"] == "MAT-009"`.
- `test_only_published_items_are_selected` still works: the adapter bank contains only published items, so `published` is every item; keep as-is.

- [ ] **Step 2: Run prototype tests to verify they fail**

Run: `cd prototype && python3 -m unittest test_selector -v`
Expected: FAIL — `generate_kit`/`selector` still reference the old bank file, or `load_bank` not yet wired; import or assertion errors.

- [ ] **Step 3: Rewire `generate_kit.py`**

In `prototype/generate_kit.py`, replace the `--bank` file argument with the adapter. Change the imports and `main()`:

```python
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # repo root
from content_bank.lib import prototype_bank
```
and in `main()`, remove the `--bank` argument and its file read; build the bank via:

```python
    bank = prototype_bank.load_bank("MAT", lang="en")
    family = json.loads(args.family.read_text())
    kit = selector.build_kit(bank, family)
```
Keep the `--family` and `-o/--out` arguments unchanged. `selector.py` itself needs **no** changes — it consumes `bank["pericopes"]` and `bank["items"]` exactly as before.

- [ ] **Step 4: Run prototype tests to verify they pass**

Run: `cd prototype && python3 -m unittest test_selector -v`
Expected: PASS (all tests).

- [ ] **Step 5: Delete the toy JSON and regenerate the sample**

```bash
git rm prototype/content_bank.json
cd prototype && python3 generate_kit.py -o sample_output.md
```
Confirm `sample_output.md` now shows `Matthew 5:3–12 (The Beatitudes)` as the passage.

- [ ] **Step 6: Write `content_bank/README.md`**

```markdown
# Content bank

The static, human-reviewed study-content library above the corpus. Items are
indexed by corpus pericope × dimension × age tier and served through one gated
read path.

- `store/<book>.json` — the content, one file per book, keyed on corpus pericope
  ids (e.g. `MAT-014`). Only `review_status: published` items are served in
  product mode.
- `lib/content.py: get_content(book, ...)` — the single read path + content
  gate (`mode="product"` serves published-only; `mode="author"` sees all).
- `lib/schema.py` — the controlled vocabularies and per-item validation.
- `lib/validate.py: validate_store(book)` — referential integrity against corpus
  pericopes, id uniqueness, and bilingual coverage counts.
- `lib/corpus_bridge.py` — read-only access to corpus pericopes, book names, the
  Westminster guardrail, and passage text.
- `lib/prototype_bank.py` — adapter to the kit-generator prototype's bank shape.
- `author/` — the offline drafting harness: `build_draft_prompt.py` assembles a
  per-pericope prompt pack (passage + WCF guardrail + dimensions + schema);
  `review_checklist.py` prints the draft→reviewed→published checklist. No API
  calls; drafting is human-in-the-loop.

Run tests: `python3 -m unittest discover -s content_bank/tests -v`

Bilingual: items carry per-language text (`text: {en, zh}`); one id per logical
item regardless of render language. Content authoring at scale is a separate
effort (see `docs/superpowers/specs/2026-07-18-content-bank-design.md`).
```

- [ ] **Step 7: Full suite green, then commit**

Run both suites:
```bash
python3 -m unittest discover -s content_bank/tests -v
cd prototype && python3 -m unittest test_selector -v
```
Expected: all PASS.

```bash
git add prototype/generate_kit.py prototype/test_selector.py prototype/family.json prototype/sample_output.md content_bank/README.md
git rm prototype/content_bank.json
git commit -m "prototype: consume content_bank store; remove toy content_bank.json"
```

---

## Self-Review

**Spec coverage:**
- Module layout (spec §Module layout) → Tasks 1–7 create every listed file; README/PROVENANCE in Tasks 5/8. ✓
- Data model + vocabularies (spec §Data model) → Task 1. ✓
- Read path + content gate (spec §The read path) → Task 2. ✓
- Validation incl. publish invariant + bilingual coverage (spec §Validation) → publish invariant in Task 1, referential + coverage in Task 4. ✓
- Authoring harness (spec §Authoring harness) → Task 7. ✓
- Prototype migration + rewire, boundary reconciliation, delete toy JSON (spec §Prototype migration) → Tasks 5 (migrate + PROVENANCE) and 8 (rewire + delete). ✓
- Bilingual one-item model (spec decision #7) → schema `text:{en,zh}` (Task 1), seeded zh (Task 5), zh read path (Tasks 2, 6). ✓
- Error handling: product read never raises, invalid data loud at validate (spec §Error handling) → Task 2 filters (no raise), Task 4 collects errors. ✓
- Testing matrix (spec §Testing) → schema/gate/referential/migration-parity/bilingual/prototype-green all mapped to Tasks 1,2,4,5,6,8. ✓
- Out of scope respected: no live API, no SQLite, no selector logic change beyond loader. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; the 25-item store transcription in Task 5 gives the exact mapping, field rules, and worked examples (the remaining items follow the same mechanical transform from the known `prototype/content_bank.json`). ✓

**Type consistency:** `get_content` signature identical across Tasks 2/4/6/8; `validate_store` return shape (`{"errors","counts"}`) consistent between Task 4 definition and Task 5 usage; `load_bank`/`display_ref` signatures consistent between Task 6 definition and Task 8 usage; bank shape (`{"pericopes":[{id,ref,title}],"items":[{...body...}]}`) matches what `selector.py` consumes. ✓
