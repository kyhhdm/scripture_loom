# CUV-Alignment Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the network-free foundation for Chinese BSB→CUV alignment: a content-based BSB quote detector, a language-aware quote gate (en→BSB, zh→CUV), a CUV-alignment gate, and a curated theological glossary with a compliance gate.

**Architecture:** Pure functions over the corpus (BSB + `cuv-simp` canon) and a curated `glossary.json`. No LLM calls. This is Plan 1 of 2 for the spec `docs/superpowers/specs/2026-07-21-cuv-alignment-translation-design.md`; Plan 2 (the `translate_cli` tool, prompt, back-translation review, review/promote UI) stands on these gates. Part A of the spec (fetch the ZH Standards reference) is already done — the term reference is in `work/glossary_build/standards_zh/term_extraction.md`.

**Tech Stack:** Python 3, `uv`, stdlib + in-repo packages (`content_bank.lib.corpus_bridge`, `content_bank.lib.schema`, `corpus.lib.passage`), `unittest`.

## Global Constraints

- Run everything under `uv` (`uv run …`). Tests: `uv run python -m unittest …`.
- **Network-free**: every task's code and tests read only committed corpus JSON; no HTTP, no model calls.
- **Bilingual schema is fixed**: `text`/`leader_reference.text`/`leader_reference.verse` are `{en, zh}` maps; `LANGS = {"en", "zh"}` (`content_bank/lib/schema.py`).
- **Versions**: English Scripture = `BSB` (`corpus/canon/bibles/bsb.json`); Chinese = `CUV` simplified (`corpus/canon/bibles/cuv-simp.json`). Access via `corpus.lib.passage.get_passage` / `corpus_bridge.passage_text`.
- **CUV excerpt delimiter in `zh` text = corner brackets `「…」`** (the machine-readable handle the CUV gate checks).
- **Licensing guard**: the copyrighted Ligonier ZH Standards live only in the gitignored `work/glossary_build/standards_zh/`. The shipped `glossary.json` carries **term-level vocabulary only** (word / short standard phrase), never verbatim Standards passages. No task writes Standards text under `corpus/` or `content_bank/` beyond single-term renderings.
- Follow existing test placement: new tests go in `content_bank/tests/test_*.py`.

---

### Task 1: Content-based BSB quote detector

Detects Scripture quotes by matching an item's English against the BSB of its own passage + any structured refs it cites — independent of quotation marks. Each hit carries its source ref (the CUV-mapping key for Plan 2).

**Files:**
- Create: `content_bank/author/quote_detect.py`
- Test: `content_bank/tests/test_quote_detect.py`

**Interfaces:**
- Consumes: `content_bank.lib.corpus_bridge.passage_text(range_str, version="BSB")`; `content_bank.author.gates._norm`, `gates._stated_refs`.
- Produces: `detect_quotes(item: dict, book: str) -> list[dict]`, each `{"quote": str, "ref": str}` where `ref` is the range/token whose BSB text contains the span. `DETECT_MIN_WORDS = 4`.

- [ ] **Step 1: Write the failing test**

```python
# content_bank/tests/test_quote_detect.py
import unittest
from content_bank.author import quote_detect


def _item(text_en=None, lr_text_en=None, passage="PHP.1.1-11"):
    it = {"id": "T-1", "passage": passage,
          "text": {"en": text_en or ""}}
    if lr_text_en is not None:
        it["leader_reference"] = {"kind": "answer_key",
                                  "text": {"en": lr_text_en}}
    return it


class TestDetectQuotes(unittest.TestCase):
    def test_detects_verbatim_bsb_span_without_quote_marks(self):
        # BSB PHP.1.1 contains "servants of Christ Jesus" — no quote marks used.
        it = _item(lr_text_en="They are the servants of Christ Jesus by title.")
        hits = quote_detect.detect_quotes(it, "PHP")
        quotes = [h["quote"].lower() for h in hits]
        self.assertTrue(any("servants of christ jesus" in q for q in quotes))
        self.assertTrue(all(h["ref"] for h in hits))

    def test_ignores_short_coincidental_runs(self):
        it = _item(text_en="Who is this and that here?")
        self.assertEqual(quote_detect.detect_quotes(it, "PHP"), [])

    def test_empty_when_no_passage(self):
        it = {"id": "T-2", "text": {"en": "servants of Christ Jesus"}}
        self.assertEqual(quote_detect.detect_quotes(it, "PHP"), [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_quote_detect -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'content_bank.author.quote_detect'`.

- [ ] **Step 3: Write minimal implementation**

```python
# content_bank/author/quote_detect.py
"""Content-based BSB quote detection.

Finds maximal spans of an item's English text that appear verbatim in the BSB
of the item's own passage + any structured ref it cites — independent of
quotation marks. Each hit carries the ref whose text matched (the CUV-mapping
key). Network-free; reads only committed corpus JSON.
"""
from ..lib import corpus_bridge
from . import gates

DETECT_MIN_WORDS = 4


def _detect_ranges(item):
    ranges = []
    if item.get("passage"):
        ranges.append(item["passage"])
    for tok in gates._stated_refs(item):
        if tok not in ranges:
            ranges.append(tok)
    return ranges


def _english_strings(item):
    out = []
    t = item.get("text") or {}
    if isinstance(t.get("en"), str):
        out.append(t["en"])
    ref = item.get("leader_reference") or {}
    for key in ("text", "verse"):
        m = ref.get(key) or {}
        if isinstance(m.get("en"), str):
            out.append(m["en"])
    return out


def _haystacks(item):
    hays = []
    for r in _detect_ranges(item):
        try:
            text = corpus_bridge.passage_text(r, version="BSB")
        except Exception:
            continue
        hays.append((r, gates._norm(text)))
    return hays


def detect_quotes(item, book):
    hays = _haystacks(item)
    found = []
    for s in _english_strings(item):
        words = s.split()
        n = len(words)
        i = 0
        while i < n:
            best_j, best_ref = i, None
            j = i + 1
            while j <= n:
                phrase = gates._norm(" ".join(words[i:j]))
                match = next((ref for ref, h in hays if phrase and phrase in h), None)
                if match is None:
                    break
                best_j, best_ref = j, match
                j += 1
            if best_j - i >= DETECT_MIN_WORDS:
                found.append({"quote": " ".join(words[i:best_j]), "ref": best_ref})
                i = best_j
            else:
                i += 1
    return found
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_quote_detect -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/quote_detect.py content_bank/tests/test_quote_detect.py
git commit -m "feat(translate): content-based BSB quote detector"
```

---

### Task 2: Language-aware `quote_check` + single-quote fix

`quote_check` currently checks **every** language value against BSB and counts length with `.split()`. Once `zh` is populated, that mis-checks Chinese against BSB and mis-counts Han. Make it route `en`→BSB / `zh`→CUV, add `「…」` + Han-char handling for `zh`, and catch word-boundary single quotes on the `en` side.

**Files:**
- Modify: `content_bank/author/gates.py`
- Test: `content_bank/tests/test_gates_lang.py`

**Interfaces:**
- Consumes: `corpus/canon/bibles/{bsb,cuv-simp}.json`.
- Produces: `quote_check(book, items)` (unchanged signature; now bilingual); new module constants `MIN_HAN = 4`; helpers `_version_text(version)`, `_zh_quoted_spans(s)`, `_han_len(s)`, `_lang_strings(item)`, `_quote_misses_for_lang(item, lang)`. `_book_text` retained (delegates to `_version_text("BSB")`).

- [ ] **Step 1: Write the failing test**

```python
# content_bank/tests/test_gates_lang.py
import unittest
from content_bank.author import gates


class TestLangAwareQuoteCheck(unittest.TestCase):
    def _item(self, en=None, zh=None):
        text = {}
        if en is not None:
            text["en"] = en
        if zh is not None:
            text["zh"] = zh
        return {"id": "T-1", "passage": "PHP.1.1-11", "text": text}

    def test_zh_verbatim_cuv_span_passes(self):
        # CUV PHP.1.1 contains 基督耶稣的仆人.
        it = self._item(zh="他们是「基督耶稣的仆人」。")
        self.assertNotIn("T-1", gates.quote_check("PHP", [it]))

    def test_zh_non_cuv_span_fails(self):
        it = self._item(zh="他们是「基督耶稣的好朋友」。")
        self.assertIn("T-1", gates.quote_check("PHP", [it]))

    def test_zh_span_not_checked_against_bsb(self):
        # A real CUV span must not be flagged just because it isn't in BSB.
        it = self._item(zh="「基督耶稣的仆人」")
        self.assertNotIn("T-1", gates.quote_check("PHP", [it]))

    def test_en_double_quote_still_works(self):
        good = self._item(en='He calls them "servants of Christ Jesus" here.')
        bad = self._item(en='He calls them "friends of Rome forever" here.')
        self.assertNotIn("T-1", gates.quote_check("PHP", [good]))
        self.assertIn("T-1", gates.quote_check("PHP", [bad]))

    def test_en_single_quote_detected_apostrophe_ignored(self):
        # Single-quoted BSB phrase should be checked; Paul's apostrophe must not
        # create a spurious span.
        bad = self._item(en="They are 'friends of Rome forever' in Paul's words.")
        self.assertIn("T-1", gates.quote_check("PHP", [bad]))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_gates_lang -v`
Expected: FAIL — `test_zh_non_cuv_span_fails` and single-quote tests fail (zh spans currently checked vs BSB / single quotes not matched).

- [ ] **Step 3: Write minimal implementation**

In `content_bank/author/gates.py`, add constants and helpers after `MIN_WORDS = 3`:

```python
MIN_HAN = 4
_EN_VERSION, _ZH_VERSION = "BSB", "CUV"
_VERSION_FILE = {"BSB": "bsb.json", "CUV": "cuv-simp.json"}
_HAYSTACK_CACHE = {}


def _version_text(version):
    if version not in _HAYSTACK_CACHE:
        path = _ROOT / "corpus" / "canon" / "bibles" / _VERSION_FILE[version]
        data = json.loads(path.read_text(encoding="utf-8"))
        parts = []
        for bk in data["books"].values():
            for ch in bk.values():
                for verse in ch.values():
                    if isinstance(verse, str):
                        parts.append(verse)
        _HAYSTACK_CACHE[version] = _norm(" ".join(parts))
    return _HAYSTACK_CACHE[version]


def _zh_quoted_spans(s):
    return (re.findall(r"「([^」]{2,300})」", s)
            + re.findall(r'"([^"]{2,300})"', s)
            + re.findall(r"“([^”]{2,300})”", s))


def _han_len(s):
    return len(re.findall(r"[一-鿿]", s))


def _lang_strings(item):
    ref = item.get("leader_reference") or {}
    for m in (item.get("text"), ref.get("text"), ref.get("verse")):
        if isinstance(m, dict):
            for lang, s in m.items():
                if isinstance(s, str):
                    yield lang, s


def _quote_misses_for_lang(item, lang):
    version = _ZH_VERSION if lang == "zh" else _EN_VERSION
    hay = _version_text(version)
    misses = []
    for l, s in _lang_strings(item):
        if l != lang:
            continue
        spans = _zh_quoted_spans(s) if lang == "zh" else _quoted_spans(s)
        for span in spans:
            core = span.strip(" \t\n,.;:!?\"'—-…")
            if lang == "zh":
                if _han_len(core) < MIN_HAN:
                    continue
            elif len(core.split()) < MIN_WORDS:
                continue
            if _norm(core) not in hay:
                misses.append(span)
    return misses
```

Replace `_quoted_spans` (add word-boundary single quotes) and `_book_text`, and rewrite `quote_check`:

```python
def _quoted_spans(s):
    return (re.findall(r'"([^"]{3,300})"', s)
            + re.findall(r"“([^”]{3,300})”", s)
            + re.findall(r"(?<!\w)'([^']{3,300})'(?!\w)", s))


def _book_text(_book):
    return _version_text("BSB")


def quote_check(book, items):
    flags = {}
    for it in items:
        misses = _quote_misses_for_lang(it, "en") + _quote_misses_for_lang(it, "zh")
        if misses:
            flags[it["id"]] = misses
    return flags
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m unittest content_bank.tests.test_gates_lang -v`
Expected: PASS (5 tests).
Run the existing suite to confirm no regression: `uv run python -m unittest discover -s content_bank/tests -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/gates.py content_bank/tests/test_gates_lang.py
git commit -m "feat(gates): language-aware quote_check (en->BSB, zh->CUV) + single-quote fix"
```

---

### Task 3: `cuv_quote_check` (zh-only gate for the translation pipeline)

The zh-only entry point Plan 2's pipeline calls after translating — every `「…」` span in a `zh` field must be verbatim CUV.

**Files:**
- Modify: `content_bank/author/gates.py`
- Test: `content_bank/tests/test_gates_lang.py` (add to existing file)

**Interfaces:**
- Consumes: `_quote_misses_for_lang` (Task 2).
- Produces: `cuv_quote_check(items) -> {item_id: [misses]}`.

- [ ] **Step 1: Write the failing test**

Append to `content_bank/tests/test_gates_lang.py`:

```python
class TestCuvQuoteCheck(unittest.TestCase):
    def _item(self, zh):
        return {"id": "Z-1", "passage": "PHP.1.1-11", "text": {"zh": zh}}

    def test_verbatim_cuv_passes(self):
        self.assertEqual(gates.cuv_quote_check([self._item("「基督耶稣的仆人」")]), {})

    def test_altered_cuv_fails(self):
        self.assertIn("Z-1", gates.cuv_quote_check([self._item("「基督耶稣的门徒」")]))

    def test_ignores_en_only_item(self):
        it = {"id": "Z-2", "passage": "PHP.1.1-11",
              "text": {"en": '"nonexistent phrase here now"'}}
        self.assertEqual(gates.cuv_quote_check([it]), {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_gates_lang.TestCuvQuoteCheck -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'cuv_quote_check'`.

- [ ] **Step 3: Write minimal implementation**

Add to `content_bank/author/gates.py`:

```python
def cuv_quote_check(items):
    flags = {}
    for it in items:
        misses = _quote_misses_for_lang(it, "zh")
        if misses:
            flags[it["id"]] = misses
    return flags
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_gates_lang.TestCuvQuoteCheck -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/gates.py content_bank/tests/test_gates_lang.py
git commit -m "feat(gates): cuv_quote_check zh-only entry point"
```

---

### Task 4: Curated theological glossary + loader/validator

The glossary asset: mandated Chinese renderings for theological head-terms, each traceable to CUV and/or the Standards. Seeded from the extraction reference (`work/glossary_build/standards_zh/term_extraction.md`) plus core CUV biblical terms. Term-level only (licensing guard). Full expansion is a follow-on data task; this seeds it and provides the loader/validator the gate needs.

**Files:**
- Create: `content_bank/author/glossary.json`
- Create: `content_bank/author/glossary.py`
- Test: `content_bank/tests/test_glossary.py`

**Interfaces:**
- Produces: `load_glossary(path=None) -> list[dict]`; `validate_glossary(entries) -> list[str]`. Entry schema: `{"en_term": str, "zh_term": str, "sources": [str, ...], "avoid": [str, ...], "note": str}` (`avoid`/`note` optional).

- [ ] **Step 1: Write the failing test**

```python
# content_bank/tests/test_glossary.py
import unittest
from content_bank.author import glossary


class TestGlossary(unittest.TestCase):
    def test_loads_and_validates(self):
        entries = glossary.load_glossary()
        self.assertTrue(entries)
        self.assertEqual(glossary.validate_glossary(entries), [])

    def test_entries_have_required_fields_and_a_source(self):
        for e in glossary.load_glossary():
            self.assertTrue(e.get("en_term"))
            self.assertTrue(e.get("zh_term"))
            self.assertTrue(e.get("sources"), f"{e['en_term']} needs a source")

    def test_validate_flags_missing_source(self):
        bad = [{"en_term": "grace", "zh_term": "恩典", "sources": []}]
        self.assertTrue(glossary.validate_glossary(bad))

    def test_known_terms_present(self):
        by_en = {e["en_term"]: e for e in glossary.load_glossary()}
        self.assertEqual(by_en["justification"]["zh_term"], "称义")
        self.assertEqual(by_en["saints"]["zh_term"], "圣徒")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_glossary -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'content_bank.author.glossary'`.

- [ ] **Step 3: Write the glossary data and loader**

Create `content_bank/author/glossary.json` (seed — doctrinal terms from the extraction, biblical terms from CUV; `sources` cite `CUV:<ref>` and/or `WCF/WSC/WLC.<n>`):

```json
[
  {"en_term": "justification", "zh_term": "称义", "sources": ["WSC.33", "WCF.11"], "avoid": ["合理化"]},
  {"en_term": "sanctification", "zh_term": "成圣", "sources": ["WSC.35", "WCF.13"]},
  {"en_term": "adoption", "zh_term": "得儿子的名分", "sources": ["WSC.34", "WLC.74"]},
  {"en_term": "regeneration", "zh_term": "重生", "sources": ["WSC.95"]},
  {"en_term": "repentance", "zh_term": "悔改", "sources": ["WSC.87", "WCF.15"]},
  {"en_term": "redemption", "zh_term": "救赎", "sources": ["WSC.21", "WCF.8"]},
  {"en_term": "predestination", "zh_term": "预定", "sources": ["WCF.3"]},
  {"en_term": "election", "zh_term": "拣选", "sources": ["WCF.3"]},
  {"en_term": "mediator", "zh_term": "中保", "sources": ["WSC.23", "WCF.8"]},
  {"en_term": "covenant of grace", "zh_term": "恩典之约", "sources": ["WCF.7", "WLC.30"]},
  {"en_term": "providence", "zh_term": "护理", "sources": ["WSC.11"]},
  {"en_term": "infallible", "zh_term": "无谬", "sources": ["WCF.1"], "avoid": ["可靠"]},
  {"en_term": "inerrant", "zh_term": "真确", "sources": ["WCF.1"]},
  {"en_term": "inspiration", "zh_term": "默示", "sources": ["WCF.1"]},
  {"en_term": "Scripture", "zh_term": "圣经", "sources": ["WSC.2", "CUV:2TI.3.16"]},
  {"en_term": "grace", "zh_term": "恩典", "sources": ["CUV:JHN.1.16", "WSC.20"]},
  {"en_term": "saints", "zh_term": "圣徒", "sources": ["CUV:PHP.1.1"]},
  {"en_term": "overseers", "zh_term": "监督", "sources": ["CUV:PHP.1.1"]},
  {"en_term": "deacons", "zh_term": "执事", "sources": ["CUV:PHP.1.1"]},
  {"en_term": "faith", "zh_term": "信心", "sources": ["WSC.86", "CUV:HEB.11.1"]}
]
```

Create `content_bank/author/glossary.py`:

```python
"""Mandated theological term glossary: English head-term -> Chinese rendering,
each traceable to CUV (biblical terms) and/or the Westminster Standards
(doctrinal terms). Term-level vocabulary only — see the licensing guard in
docs/superpowers/specs/2026-07-21-cuv-alignment-translation-design.md.
"""
import json
import pathlib

_DEFAULT = pathlib.Path(__file__).with_name("glossary.json")


def load_glossary(path=None):
    p = pathlib.Path(path) if path else _DEFAULT
    return json.loads(p.read_text(encoding="utf-8"))


def validate_glossary(entries):
    errors = []
    seen = set()
    for e in entries:
        term = e.get("en_term")
        if not term:
            errors.append("entry missing en_term")
            continue
        if not e.get("zh_term"):
            errors.append(f"{term}: missing zh_term")
        if not e.get("sources"):
            errors.append(f"{term}: needs at least one source")
        if term.lower() in seen:
            errors.append(f"{term}: duplicate en_term")
        seen.add(term.lower())
    return errors
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m unittest content_bank.tests.test_glossary -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/glossary.json content_bank/author/glossary.py content_bank/tests/test_glossary.py
git commit -m "feat(translate): curated theological glossary + loader/validator"
```

---

### Task 5: `glossary_check` gate

Deterministic doctrinal-vocabulary gate: when an item's English contains a glossary head-term and the item has `zh`, require the mandated `zh_term` in the Chinese and flag any `avoid` (known-wrong) rendering.

**Files:**
- Modify: `content_bank/author/gates.py`
- Test: `content_bank/tests/test_glossary_check.py`

**Interfaces:**
- Consumes: `glossary.load_glossary()` (Task 4); `_lang_strings` (Task 2).
- Produces: `glossary_check(items, glossary=None) -> {item_id: [problems]}`. `glossary=None` loads the default.

- [ ] **Step 1: Write the failing test**

```python
# content_bank/tests/test_glossary_check.py
import unittest
from content_bank.author import gates

GLOSS = [{"en_term": "justification", "zh_term": "称义",
          "sources": ["WSC.33"], "avoid": ["合理化"]}]


def _item(en, zh=None):
    text = {"en": en}
    if zh is not None:
        text["zh"] = zh
    return {"id": "G-1", "passage": "PHP.1.1-11", "text": text}


class TestGlossaryCheck(unittest.TestCase):
    def test_mandated_term_present_passes(self):
        it = _item("A question about justification.", "关于称义的问题。")
        self.assertEqual(gates.glossary_check([it], GLOSS), {})

    def test_missing_mandated_term_flags(self):
        it = _item("A question about justification.", "关于成义的问题。")
        self.assertIn("G-1", gates.glossary_check([it], GLOSS))

    def test_forbidden_rendering_flags(self):
        it = _item("A question about justification.", "关于合理化的问题。")
        self.assertIn("G-1", gates.glossary_check([it], GLOSS))

    def test_en_only_item_skipped(self):
        it = _item("A question about justification.")  # no zh yet
        self.assertEqual(gates.glossary_check([it], GLOSS), {})

    def test_term_absent_from_english_skipped(self):
        it = _item("A question about people and places.", "关于人物的问题。")
        self.assertEqual(gates.glossary_check([it], GLOSS), {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_glossary_check -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'glossary_check'`.

- [ ] **Step 3: Write minimal implementation**

Add to `content_bank/author/gates.py` (import at top: `from . import glossary as _glossary`):

```python
import re as _re_word


def _has_en_term(text_en, term):
    return _re_word.search(r"\b" + _re_word.escape(term) + r"\b",
                           text_en, _re_word.IGNORECASE) is not None


def glossary_check(items, glossary=None):
    entries = glossary if glossary is not None else _glossary.load_glossary()
    flags = {}
    for it in items:
        en_text = " ".join(s for l, s in _lang_strings(it) if l == "en")
        zh_text = " ".join(s for l, s in _lang_strings(it) if l == "zh")
        if not zh_text:
            continue  # nothing translated yet
        problems = []
        for e in entries:
            if not _has_en_term(en_text, e["en_term"]):
                continue
            if e["zh_term"] not in zh_text:
                problems.append(f"'{e['en_term']}' -> expected '{e['zh_term']}' "
                                f"(source {', '.join(e.get('sources', []))})")
            for wrong in e.get("avoid", []):
                if wrong in zh_text:
                    problems.append(f"'{e['en_term']}' uses forbidden '{wrong}'")
        if problems:
            flags[it["id"]] = problems
    return flags
```

Note: put the `from . import glossary as _glossary` import with the other top-of-file imports; the `import re` already present covers regex — reuse it instead of `_re_word` if preferred (the plan uses a distinct alias only to avoid touching the existing `re` usage; `re` is fine).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m unittest content_bank.tests.test_glossary_check -v`
Expected: PASS (5 tests).
Full suite: `uv run python -m unittest discover -s content_bank/tests -v` — all PASS.

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/gates.py content_bank/tests/test_glossary_check.py
git commit -m "feat(gates): glossary_check doctrinal-vocabulary gate"
```

---

### Task 6: Glossary-coverage report

Answers "do we need more terms?" empirically: scan a book's content for theological terms that appear but have **no** glossary entry. Uses a maintained `theological_lexicon.json` (the recognizer — a superset of candidate theological vocabulary, broader than the glossary) so the report can surface *unknown* gaps, not just track known terms.

**Files:**
- Create: `content_bank/author/theological_lexicon.json`
- Create: `content_bank/author/glossary_coverage.py`
- Test: `content_bank/tests/test_glossary_coverage.py`

**Interfaces:**
- Consumes: `glossary.load_glossary()` (Task 4); `gates._lang_strings` (Task 2).
- Produces: `load_lexicon(path=None) -> list[str]`; `coverage_report(items, glossary=None, lexicon=None) -> dict` with keys `covered` (lexicon terms present in content that HAVE a glossary entry, sorted) and `uncovered` (present but NOT in glossary, sorted).

- [ ] **Step 1: Write the failing test**

```python
# content_bank/tests/test_glossary_coverage.py
import unittest
from content_bank.author import glossary_coverage as gc

LEXICON = ["justification", "propitiation", "covenant of grace"]
GLOSS = [{"en_term": "justification", "zh_term": "称义", "sources": ["WSC.33"]}]


def _item(en):
    return {"id": "C-1", "passage": "PHP.1.1-11", "text": {"en": en}}


class TestCoverageReport(unittest.TestCase):
    def test_flags_uncovered_term_present_in_content(self):
        items = [_item("A note on justification and propitiation.")]
        rep = gc.coverage_report(items, glossary=GLOSS, lexicon=LEXICON)
        self.assertIn("justification", rep["covered"])
        self.assertIn("propitiation", rep["uncovered"])
        self.assertNotIn("covenant of grace", rep["uncovered"])  # absent from text

    def test_multiword_term_matched(self):
        items = [_item("This is the covenant of grace in view.")]
        rep = gc.coverage_report(items, glossary=GLOSS, lexicon=LEXICON)
        self.assertIn("covenant of grace", rep["uncovered"])

    def test_defaults_load(self):
        rep = gc.coverage_report([_item("nothing theological here")])
        self.assertEqual(rep["covered"], [])
        self.assertEqual(rep["uncovered"], [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_glossary_coverage -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'content_bank.author.glossary_coverage'`.

- [ ] **Step 3: Write the lexicon and the report**

Create `content_bank/author/theological_lexicon.json` (recognizer superset: the doctrinal spine + the high-weight additions + core biblical terms; grows as content is triaged):

```json
["God", "Scripture", "revelation", "inspiration", "infallible", "inerrant",
 "authority", "canon", "Trinity", "decree", "predestination", "election",
 "providence", "creation", "covenant", "covenant of works", "covenant of grace",
 "mediator", "Christ", "incarnation", "redemption", "atonement", "propitiation",
 "satisfaction", "merit", "imputation", "justification", "adoption",
 "regeneration", "sanctification", "faith", "repentance", "effectual calling",
 "union with Christ", "glorification", "perseverance", "assurance",
 "means of grace", "common grace", "sin", "original sin", "total depravity",
 "fall", "guilt", "conscience", "free will", "image of God", "holiness",
 "righteousness", "salvation", "eternal life", "law", "moral law",
 "commandment", "worship", "Sabbath", "prayer", "church", "communion of saints",
 "sacrament", "baptism", "Lord's Supper", "saints", "grace", "overseers",
 "deacons", "gospel", "fellowship", "joy", "humility", "contentment"]
```

Create `content_bank/author/glossary_coverage.py`:

```python
"""Glossary-coverage report: which theological terms appear in a book's content
but have no mandated glossary rendering. Deterministic; network-free. The
lexicon is the recognizer (candidate theological vocabulary, broader than the
glossary) so genuinely-missing terms surface, not just tracked ones.
"""
import json
import pathlib
import re

from . import glossary as _glossary
from . import gates

_LEXICON = pathlib.Path(__file__).with_name("theological_lexicon.json")


def load_lexicon(path=None):
    p = pathlib.Path(path) if path else _LEXICON
    return json.loads(p.read_text(encoding="utf-8"))


def _en_text(items):
    return " ".join(s for it in items
                    for l, s in gates._lang_strings(it) if l == "en")


def _present(term, text):
    return re.search(r"\b" + re.escape(term) + r"\b", text, re.IGNORECASE) is not None


def coverage_report(items, glossary=None, lexicon=None):
    entries = glossary if glossary is not None else _glossary.load_glossary()
    terms = lexicon if lexicon is not None else load_lexicon()
    glossed = {e["en_term"].lower() for e in entries}
    text = _en_text(items)
    covered, uncovered = [], []
    for term in terms:
        if not _present(term, text):
            continue
        (covered if term.lower() in glossed else uncovered).append(term)
    return {"covered": sorted(covered), "uncovered": sorted(uncovered)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_glossary_coverage -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/theological_lexicon.json content_bank/author/glossary_coverage.py content_bank/tests/test_glossary_coverage.py
git commit -m "feat(translate): glossary-coverage report (empirical gap finder)"
```

---

## Self-Review

**Spec coverage (against `2026-07-21-cuv-alignment-translation-design.md`):**
- Content-based BSB detection (passage + cited refs, ≥4 words) → Task 1. ✅
- `quote_check` language-aware (en→BSB, zh→CUV) + single-quote fix + Han-char length → Task 2. ✅
- `cuv_quote_check` (verbatim `「…」` CUV) → Task 3. ✅
- Glossary derived from CUV + Standards, term-level, traceable sources, precedence-curated → Task 4 (seed asset; full curation is the noted follow-on data task). ✅
- `glossary_check` (mandated present, forbidden absent) → Task 5. ✅
- Glossary-coverage report (empirical "do we need more terms?" gap finder) → Task 6. ✅
- Licensing guard (no shipped Standards text; term-level only) → Global Constraints + Task 4 seed uses only single-term renderings. ✅
- **Deferred to Plan 2 (LLM-integrated):** `translate_cli`, translation prompt, back-translation review lens, proposal emission, `compare_html` en▸zh▸CUV extension, confirm→promote. Not in this plan by design.
- **Deferred (data/aid):** an automated CUV-term extraction helper to grow the glossary; the widen-don't-backtranslate fallback lives in the Plan 2 prompt, but Task 3's gate already enforces its invariant (contiguous CUV substring or fail).

**Placeholder scan:** none — every step has runnable code and exact commands.

**Type consistency:** `detect_quotes -> [{"quote","ref"}]`; gate functions return `{id: [str]}` matching the existing `gates.py` contract; `load_glossary`/`validate_glossary`/`glossary_check`/`coverage_report` signatures consistent across Tasks 4–6. `_lang_strings`, `_version_text`, `_quote_misses_for_lang` defined in Task 2 and reused in Tasks 3, 5 & 6. ✅
