# Citation Tags + Two-Mode Hard Gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the authoring LLM declare its Scripture and doctrine citations as inline `<verse>`/`<doctrine>` tags, and add a deterministic gate that *verifies* each declaration (quote-mode vs BSB/CUV, basis-mode vs the Westminster canon lampposts) instead of rediscovering quotes.

**Architecture:** A pure tag parser/stripper (`citation_tags`) and a standards resolver (`standards`) in `content_bank/lib/`. A new `citation_check` gate in `content_bank/author/gates.py` composes them plus the existing `quote_detect` recall net, and is registered in `run_all` (English build) and `translate.zh_gate_flags` (translation). The two prompt builders instruct the model to emit/preserve tags. Reader-facing renderers strip tags via `citation_tags.strip_tags`. Tagged strings are the stored source of truth.

**Tech Stack:** Python 3.12, stdlib only (`re`, `json`, `copy`); in-repo `corpus_bridge`, `quote_detect`; `unittest`.

## Global Constraints

- Canonical corpus ref format only: `PHP.1.6` / `PHP.1.1-11` — never human format.
- Scripture versions: `BSB` for `en`, `CUV` for `zh` (per `gates._EN_VERSION`/`_ZH_VERSION`).
- Standards refs: `WCF` → `"C.S"` (chapter.section); `WLC`/`WSC` → `"Q<n>"`.
- Verify, never trust: a tag is a model *claim*; the gate still checks it. Fail-closed on malformed markup.
- The LLM authors tags; scripts only verify. `<doctrine>` tags are authored in English and carried through translation — translation never mints new ones.
- Network-free, offline, deterministic. All tests mock `llm` and read only committed corpus JSON.
- New third-party deps are not needed; do not add any.
- Tests run under `uv`: `uv run python -m unittest discover -s content_bank/tests -v` (and `prototype`).

---

### Task 1: `citation_tags` — parser + stripper

**Files:**
- Create: `content_bank/lib/citation_tags.py`
- Test: `content_bank/tests/test_citation_tags.py`

**Interfaces:**
- Produces:
  - `Verse = namedtuple("Verse", "ref text")`
  - `Doctrine = namedtuple("Doctrine", "std ref text")`
  - `strip_tags(s: str) -> str` — removes every `<verse>/<doctrine>` open/close tag, keeps inner text; passes non-strings through unchanged.
  - `parse(s: str) -> tuple[list[Verse], list[Doctrine], bool]` — returns `(verses, doctrines, malformed)`. `malformed` is True when tag markers exist that did not parse as well-formed elements.

- [ ] **Step 1: Write the failing test**

```python
# content_bank/tests/test_citation_tags.py
import unittest
from content_bank.lib import citation_tags as ct


class TestStrip(unittest.TestCase):
    def test_strips_verse_keeps_inner(self):
        s = 'He said <verse ref="PHP.1.6">a good work in you</verse> here.'
        self.assertEqual(ct.strip_tags(s), "He said a good work in you here.")

    def test_strips_doctrine_keeps_inner(self):
        s = 'Rests on <doctrine std="WCF" ref="1.4">God its author</doctrine>.'
        self.assertEqual(ct.strip_tags(s), "Rests on God its author.")

    def test_untagged_unchanged_and_nonstring_passthrough(self):
        self.assertEqual(ct.strip_tags("plain text"), "plain text")
        self.assertIsNone(ct.strip_tags(None))


class TestParse(unittest.TestCase):
    def test_parses_verse_and_doctrine(self):
        s = ('<verse ref="PHP.1.1">servants of Christ Jesus</verse> and '
             '<doctrine std="WSC" ref="Q1">to glorify God</doctrine>')
        verses, doctrines, malformed = ct.parse(s)
        self.assertFalse(malformed)
        self.assertEqual(verses, [ct.Verse("PHP.1.1", "servants of Christ Jesus")])
        self.assertEqual(doctrines, [ct.Doctrine("WSC", "Q1", "to glorify God")])

    def test_clean_text_not_malformed(self):
        self.assertEqual(ct.parse("no tags at all"), ([], [], False))

    def test_missing_close_is_malformed(self):
        v, d, malformed = ct.parse('<verse ref="PHP.1.1">servants')
        self.assertTrue(malformed)

    def test_missing_ref_attr_is_malformed(self):
        v, d, malformed = ct.parse('<verse>servants of Christ Jesus</verse>')
        self.assertTrue(malformed)

    def test_doctrine_missing_std_is_malformed(self):
        v, d, malformed = ct.parse('<doctrine ref="1.4">x</doctrine>')
        self.assertTrue(malformed)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_citation_tags -v`
Expected: FAIL — `ModuleNotFoundError: content_bank.lib.citation_tags`.

- [ ] **Step 3: Write minimal implementation**

```python
# content_bank/lib/citation_tags.py
"""Inline citation tags emitted by the authoring LLM.

Two elements live inside content text fields:
  <verse ref="PHP.1.6">verbatim Scripture</verse>
  <doctrine std="WCF" ref="1.4">paraphrase of the doctrine</doctrine>

This module parses and strips them. Pure/stdlib; shared by the deterministic
gate (verification) and the reader-facing renderers (strip on display).
"""
import re
from collections import namedtuple

Verse = namedtuple("Verse", "ref text")
Doctrine = namedtuple("Doctrine", "std ref text")

_VERSE_RE = re.compile(r'<verse\s+ref="([^"]*)"\s*>(.*?)</verse>', re.DOTALL)
_DOCTRINE_RE = re.compile(
    r'<doctrine\s+std="([^"]*)"\s+ref="([^"]*)"\s*>(.*?)</doctrine>', re.DOTALL)
_ANY_TAG_RE = re.compile(r'</?(?:verse|doctrine)\b[^>]*>')
_V_OPEN, _V_CLOSE = re.compile(r'<verse\b'), re.compile(r'</verse\b')
_D_OPEN, _D_CLOSE = re.compile(r'<doctrine\b'), re.compile(r'</doctrine\b')


def strip_tags(s):
    """Remove every <verse>/<doctrine> open/close tag, keeping inner text."""
    if not isinstance(s, str):
        return s
    return _ANY_TAG_RE.sub("", s)


def parse(s):
    """Return (verses, doctrines, malformed).

    `malformed` is True when the string holds tag markers that did not parse
    as well-formed elements (missing/extra attribute, unbalanced) — the gate
    treats that as fail-closed.
    """
    if not isinstance(s, str):
        return [], [], False
    verses = [Verse(m.group(1), m.group(2)) for m in _VERSE_RE.finditer(s)]
    doctrines = [Doctrine(m.group(1), m.group(2), m.group(3))
                 for m in _DOCTRINE_RE.finditer(s)]
    malformed = (
        len(_V_OPEN.findall(s)) != len(verses)
        or len(_V_CLOSE.findall(s)) != len(verses)
        or len(_D_OPEN.findall(s)) != len(doctrines)
        or len(_D_CLOSE.findall(s)) != len(doctrines))
    return verses, doctrines, malformed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_citation_tags -v`
Expected: PASS (all cases).

- [ ] **Step 5: Commit**

```bash
git add content_bank/lib/citation_tags.py content_bank/tests/test_citation_tags.py
git commit -m "feat(citation): inline <verse>/<doctrine> tag parser + stripper"
```

---

### Task 2: `standards` — Westminster citation resolver

**Files:**
- Create: `content_bank/lib/standards.py`
- Test: `content_bank/tests/test_standards.py`

**Interfaces:**
- Consumes: `corpus_bridge._load(rel)` (reads `corpus/canon/lampposts/{wcf,wlc,wsc}.json`).
- Produces: `resolve(std: str, ref: str) -> str | None` — the section text (WCF) or answer (WLC/WSC) if the citation exists, else `None`. Unknown `std`, malformed `ref`, or out-of-range number → `None`.

Canon shapes (verified): `wcf.json` → `{"chapters": [{"n": int, "sections": [{"n": int, "text": str}]}]}`; `wlc.json`/`wsc.json` → `{"questions": [{"n": int, "q": str, "a": str}]}`.

- [ ] **Step 1: Write the failing test**

```python
# content_bank/tests/test_standards.py
import unittest
from content_bank.lib import standards


class TestResolve(unittest.TestCase):
    def test_wcf_section_resolves(self):
        text = standards.resolve("WCF", "1.4")
        self.assertIsInstance(text, str)
        self.assertIn("authority", text.lower())

    def test_wcf_out_of_range_is_none(self):
        self.assertIsNone(standards.resolve("WCF", "1.99"))
        self.assertIsNone(standards.resolve("WCF", "99.1"))

    def test_wcf_bad_ref_shape_is_none(self):
        self.assertIsNone(standards.resolve("WCF", "Q1"))
        self.assertIsNone(standards.resolve("WCF", "1"))

    def test_wsc_and_wlc_question_resolves(self):
        self.assertIn("glorify", standards.resolve("WSC", "Q1").lower())
        self.assertIsInstance(standards.resolve("WLC", "Q1"), str)

    def test_question_out_of_range_is_none(self):
        self.assertIsNone(standards.resolve("WSC", "Q9999"))
        self.assertIsNone(standards.resolve("WSC", "1.4"))

    def test_unknown_standard_is_none(self):
        self.assertIsNone(standards.resolve("XYZ", "1.1"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_standards -v`
Expected: FAIL — `ModuleNotFoundError: content_bank.lib.standards`.

- [ ] **Step 3: Write minimal implementation**

```python
# content_bank/lib/standards.py
"""Resolve a Westminster Standards citation against the committed canon
lampposts. WCF ref is "chapter.section"; WLC/WSC ref is "Q<number>".
Returns the cited text if it exists, else None. Network-free."""
import re

from . import corpus_bridge

_FILES = {"WCF": "canon/lampposts/wcf.json",
          "WLC": "canon/lampposts/wlc.json",
          "WSC": "canon/lampposts/wsc.json"}
_WCF_RE = re.compile(r"^(\d+)\.(\d+)$")
_Q_RE = re.compile(r"^Q(\d+)$")


def resolve(std, ref):
    if std not in _FILES:
        return None
    data = corpus_bridge._load(_FILES[std])
    if std == "WCF":
        m = _WCF_RE.match(ref or "")
        if not m:
            return None
        c, sec = int(m.group(1)), int(m.group(2))
        ch = next((x for x in data["chapters"] if x["n"] == c), None)
        if ch is None:
            return None
        s = next((x for x in ch["sections"] if x["n"] == sec), None)
        return s["text"] if s else None
    m = _Q_RE.match(ref or "")
    if not m:
        return None
    n = int(m.group(1))
    q = next((x for x in data["questions"] if x["n"] == n), None)
    return q["a"] if q else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_standards -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add content_bank/lib/standards.py content_bank/tests/test_standards.py
git commit -m "feat(standards): resolve WCF/WLC/WSC citations vs canon lampposts"
```

---

### Task 3: `citation_check` gate + registration in `run_all`

**Files:**
- Modify: `content_bank/author/gates.py`
- Test: `content_bank/tests/test_citation_check.py`

**Interfaces:**
- Consumes: `citation_tags.parse`, `standards.resolve`, `corpus_bridge.passage_text`, `quote_detect.detect_quotes` (lazy import to avoid the `gates`↔`quote_detect` cycle), and the existing `_lang_strings`, `_norm`, `_EN_VERSION`, `_ZH_VERSION`.
- Produces: `citation_check(items, *, langs=None) -> {id: [flags]}`. `langs` filters which language strings are checked (`None` = all). Flag strings are prefixed `citation.malformed` / `citation.verse_mismatch` / `citation.basis_unresolved` / `citation.untagged_quote`. `run_all` includes `citation_check(items)`.

**Verified ground-truth values used in tests:**
- `BSB PHP.1.1` = `"Paul and Timothy, servants of Christ Jesus, To all the saints in Christ Jesus at Philippi, together with the overseers and deacons:"`
- `CUV PHP.1.1` contains `基督耶稣的仆人`.
- `WCF 1.4`, `WSC Q1` resolve; `WCF 1.99` does not.

- [ ] **Step 1: Write the failing test**

```python
# content_bank/tests/test_citation_check.py
import unittest
from content_bank.author import gates

_BSB_PHP_1_1 = ("Paul and Timothy, servants of Christ Jesus, To all the saints "
                "in Christ Jesus at Philippi, together with the overseers and deacons:")


def _item(text_en, itype="question", iid="PHP-001-D1-01", **extra):
    it = {"id": iid, "passage": "PHP.1.1-11", "dimension": "D1", "type": itype,
          "text": {"en": text_en}}
    it.update(extra)
    return it


class TestVerseMode(unittest.TestCase):
    def test_correct_subverse_quote_passes_by_containment(self):
        it = _item('Who are the <verse ref="PHP.1.1">servants of Christ Jesus</verse>?')
        self.assertEqual(gates.citation_check([it]), {})

    def test_altered_quote_flagged(self):
        it = _item('The <verse ref="PHP.1.1">servants of Jesus Christ</verse>.')
        flags = gates.citation_check([it])["PHP-001-D1-01"]
        self.assertTrue(any("verse_mismatch" in f for f in flags))

    def test_memory_verse_requires_full_equality(self):
        # a sub-verse phrase is NOT the whole verse -> equality fails
        it = _item('<verse ref="PHP.1.1">servants of Christ Jesus</verse>',
                   itype="memory_verse")
        flags = gates.citation_check([it])["PHP-001-D1-01"]
        self.assertTrue(any("verse_mismatch" in f for f in flags))

    def test_memory_verse_full_verse_equality_passes(self):
        it = _item(f'<verse ref="PHP.1.1">{_BSB_PHP_1_1}</verse>',
                   itype="memory_verse")
        self.assertEqual(gates.citation_check([it]), {})

    def test_bad_ref_grammar_flagged_malformed(self):
        it = _item('<verse ref="Philippians 1:1">servants of Christ Jesus</verse>')
        flags = gates.citation_check([it])["PHP-001-D1-01"]
        self.assertTrue(any("malformed" in f for f in flags))

    def test_unbalanced_tag_flagged_malformed(self):
        it = _item('<verse ref="PHP.1.1">servants of Christ Jesus')
        flags = gates.citation_check([it])["PHP-001-D1-01"]
        self.assertTrue(any("malformed" in f for f in flags))


class TestBasisMode(unittest.TestCase):
    def test_resolvable_doctrine_passes(self):
        it = _item('Rests on <doctrine std="WCF" ref="1.4">God its author</doctrine>.')
        self.assertEqual(gates.citation_check([it]), {})

    def test_unresolvable_doctrine_flagged(self):
        it = _item('Rests on <doctrine std="WCF" ref="1.99">nonsense</doctrine>.')
        flags = gates.citation_check([it])["PHP-001-D1-01"]
        self.assertTrue(any("basis_unresolved" in f for f in flags))

    def test_unknown_standard_flagged(self):
        it = _item('Rests on <doctrine std="XYZ" ref="1.1">nope</doctrine>.')
        flags = gates.citation_check([it])["PHP-001-D1-01"]
        self.assertTrue(any("basis_unresolved" in f for f in flags))


class TestRecallNetAndLangs(unittest.TestCase):
    def test_untagged_verbatim_quote_flagged(self):
        # a 4+ word BSB span left untagged -> recall net flags it
        it = _item("The phrase servants of Christ Jesus appears here.")
        flags = gates.citation_check([it])["PHP-001-D1-01"]
        self.assertTrue(any("untagged_quote" in f for f in flags))

    def test_same_quote_when_tagged_not_flagged(self):
        it = _item('The phrase <verse ref="PHP.1.1">servants of Christ Jesus</verse> here.')
        self.assertEqual(gates.citation_check([it]), {})

    def test_zh_verse_verified_against_cuv(self):
        it = _item("q", iid="PHP-001-D1-02")
        it["text"]["zh"] = '谁是<verse ref="PHP.1.1">基督耶稣的仆人</verse>？'
        self.assertEqual(gates.citation_check([it]), {})

    def test_langs_filter_skips_en_recall_net(self):
        it = _item("servants of Christ Jesus appears untagged in english")
        it["text"]["zh"] = "干净的中文没有标签"
        # zh-only: en recall net is skipped, so no flags
        self.assertEqual(gates.citation_check([it], langs={"zh"}), {})


class TestRunAllIncludesCitation(unittest.TestCase):
    def test_run_all_surfaces_verse_mismatch(self):
        it = _item('<verse ref="PHP.1.1">servants of Jesus Christ</verse>',
                   itype="memory_verse")
        allowed = [("PHP", 1, 1, 11)]
        merged = gates.run_all("PHP", [it], allowed)
        self.assertIn("PHP-001-D1-01", merged)
        self.assertTrue(any("verse_mismatch" in f for f in merged["PHP-001-D1-01"]))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_citation_check -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'citation_check'`.

- [ ] **Step 3: Write minimal implementation**

Add the import near the top of `gates.py` (with the existing `from ..lib import corpus_bridge, schema`):

```python
from ..lib import corpus_bridge, schema, citation_tags, standards
```

Add `copy` to the stdlib imports at the top (`import copy`).

Add these functions to `gates.py` (place them after `schema_check`, before the `_REF_TOKEN` block):

```python
_VERSE_REF_RE = re.compile(r"^[A-Z0-9]{3}\.\d+\.\d+(?:-(?:\d+\.)?\d+)?$")


def _passage_plain(ref, version):
    """Verse text for `ref` with the leading 'MARKER  ' stripped from each line."""
    raw = corpus_bridge.passage_text(ref, version=version)
    out = []
    for line in raw.splitlines():
        parts = line.split("  ", 1)
        out.append(parts[1] if len(parts) == 2 else line)
    return " ".join(out)


def _verse_problem(ref, inner, version, item_type):
    """Return a flag string if the tagged verse fails, else None."""
    if not _VERSE_REF_RE.match(ref):
        return f"citation.malformed: bad verse ref '{ref}'"
    try:
        hay = _norm(_passage_plain(ref, version))
    except Exception:
        return f"citation.verse_mismatch: '{ref}' does not resolve in {version}"
    core = _norm(inner)
    if not core:
        return f"citation.verse_mismatch: '{ref}' has empty quote"
    ok = (core == hay) if item_type == "memory_verse" else (core in hay)
    if not ok:
        return (f"citation.verse_mismatch: '{ref}' inner text does not match "
                f"{version}")
    return None


def _untagged_quote_flags(item, langs):
    """EN recall net: verbatim BSB spans left outside a <verse> tag."""
    if langs is not None and "en" not in langs:
        return []
    from . import quote_detect  # lazy: quote_detect imports gates
    covered = []
    stripped = copy.deepcopy(item)
    for m in (stripped.get("text"), (stripped.get("leader_reference") or {}).get("text"),
              (stripped.get("leader_reference") or {}).get("verse")):
        if isinstance(m, dict) and isinstance(m.get("en"), str):
            verses, _, _ = citation_tags.parse(m["en"])
            covered.extend(_norm(v.text) for v in verses)
            m["en"] = citation_tags.strip_tags(m["en"])
    out = []
    for hit in quote_detect.detect_quotes(stripped, None):
        q = _norm(hit["quote"])
        if any(q in c or c in q for c in covered):
            continue
        out.append(f"citation.untagged_quote: '{hit['quote']}' ({hit['ref']}) "
                   f"not wrapped in a <verse> tag")
    return out


def citation_check(items, *, langs=None):
    """Verify declared citations. quote-mode: <verse> inner text is verbatim in
    the corpus version for its language (equality for memory_verse, containment
    otherwise). basis-mode: <doctrine> ref resolves in WCF/WLC/WSC. Fail-closed
    on malformed markup. quote_detect recall net flags untagged verbatim spans."""
    flags = {}
    for it in items:
        problems = []
        itype = it.get("type")
        for lang, s in _lang_strings(it):
            if langs is not None and lang not in langs:
                continue
            verses, doctrines, malformed = citation_tags.parse(s)
            if malformed:
                problems.append("citation.malformed: unbalanced or malformed "
                                "<verse>/<doctrine> markup")
            version = _ZH_VERSION if lang == "zh" else _EN_VERSION
            for v in verses:
                p = _verse_problem(v.ref, v.text, version, itype)
                if p:
                    problems.append(p)
            for d in doctrines:
                if standards.resolve(d.std, d.ref) is None:
                    problems.append(f"citation.basis_unresolved: {d.std} {d.ref}")
        problems.extend(_untagged_quote_flags(it, langs))
        if problems:
            flags[it["id"]] = problems
    return flags
```

Register it in `run_all` — change the gate tuple:

```python
def run_all(book, items, allowed):
    """The HARD gate tier: quote + schema + ref-range + thread-span + citation.
    Any flag here is a defect the repair loop must clear or the unit fails. Soft
    anti-padding (dimension_cap_check) is deliberately NOT included."""
    merged = {}
    for gate in (quote_check(book, items), schema_check(items),
                 refs_in_range(items, allowed), thread_span_check(items, allowed),
                 citation_check(items)):
        for k, v in gate.items():
            merged.setdefault(k, []).extend(v)
    return merged
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_citation_check -v`
Expected: PASS.

Then confirm no regression in the existing gate tests:
Run: `uv run python -m unittest content_bank.tests.test_gates -v`
Expected: PASS (if a `test_gates.py` exists; otherwise skip).

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/gates.py content_bank/tests/test_citation_check.py
git commit -m "feat(gates): citation_check two-mode gate + recall net; wire into run_all"
```

---

### Task 4: translation verifies zh citation tags

**Files:**
- Modify: `content_bank/author/translate.py:67` (`zh_gate_flags`)
- Test: `content_bank/tests/test_translate.py` (add a case)

**Interfaces:**
- Consumes: `gates.citation_check([item], langs={"zh"})`.
- Produces: `zh_gate_flags` now also returns `citation.*` flags for the `zh` string, so `translate_with_gates`' existing repair loop fixes bad zh tags. `_merge_zh` already carries tags (they are part of the zh string) — no change needed there.

- [ ] **Step 1: Write the failing test**

Add to `content_bank/tests/test_translate.py`:

```python
class TestZhCitationGate(unittest.TestCase):
    def _item(self):
        return {"id": "PHP-001-D1-01", "passage": "PHP.1.1-11", "dimension": "D1",
                "type": "question", "text": {"en": "servants of Christ Jesus?"}}

    def test_bad_zh_verse_tag_is_gate_flagged(self):
        # zh <verse> whose inner text is NOT the CUV wording -> flagged
        bad = ('{"text": {"zh": "谁是<verse ref=\\"PHP.1.1\\">错误的经文</verse>？"}, '
               '"terms": [], "uncertain": []}')
        with mock.patch.object(translate, "llm", side_effect=[bad, bad, bad]):
            out = translate.translate_with_gates(self._item(), "PHP", glossary=[],
                                                 max_repair=2)
        self.assertFalse(out["gate_ok"])
        self.assertTrue(any("citation" in f for f in out["gate_flags"]))

    def test_good_zh_verse_tag_passes(self):
        good = ('{"text": {"zh": "谁是<verse ref=\\"PHP.1.1\\">基督耶稣的仆人</verse>？"}, '
                '"terms": [], "uncertain": []}')
        with mock.patch.object(translate, "llm", return_value=good):
            out = translate.translate_with_gates(self._item(), "PHP", glossary=[])
        self.assertTrue(out["gate_ok"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_translate.TestZhCitationGate -v`
Expected: FAIL — `test_bad_zh_verse_tag_is_gate_flagged` fails because `zh_gate_flags` does not yet run `citation_check` (gate_ok is True).

- [ ] **Step 3: Write minimal implementation**

Edit `zh_gate_flags` in `content_bank/author/translate.py`:

```python
def zh_gate_flags(item, glossary):
    flags = []
    for gate in (gates.cuv_quote_check([item]),
                 gates.glossary_check([item], glossary),
                 gates.citation_check([item], langs={"zh"})):
        flags.extend(gate.get(item["id"], []))
    return flags
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_translate -v`
Expected: PASS (new cases + all existing translate tests).

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/translate.py content_bank/tests/test_translate.py
git commit -m "feat(translate): verify zh <verse> tags against CUV in the repair loop"
```

---

### Task 5: prompt builders emit / preserve tags

**Files:**
- Modify: `content_bank/author/build_draft_prompt.py` (add a tagging block; include it in `build`)
- Modify: `content_bank/author/build_translate_prompt.py` (add a preserve-tags rule)
- Test: `content_bank/tests/test_draft_prompt.py` (new or existing), `content_bank/tests/test_translate_prompt.py`

**Interfaces:**
- Produces: both prompts contain the literal element names `<verse ref=` and `<doctrine std=` and the tagging instructions. No signature changes.

- [ ] **Step 1: Write the failing test**

Add to `content_bank/tests/test_translate_prompt.py` (`TestTranslatePrompt`):

```python
    def test_prompt_instructs_tag_preservation(self):
        p = btp.build(self._item(), "PHP", detected=[], glossary_entries=[])
        self.assertIn("<verse ref=", p)
        self.assertIn("<doctrine std=", p)
```

Create `content_bank/tests/test_draft_prompt.py`:

```python
import unittest
from content_bank.author import build_draft_prompt as bdp


class TestDraftPromptTagging(unittest.TestCase):
    def test_tagging_block_present(self):
        # PHP-001 has a committed brief; build the real draft pack.
        p = bdp.build("PHP-001", book="PHP")
        self.assertIn("<verse ref=", p)
        self.assertIn("<doctrine std=", p)
        self.assertIn("PHP.1.6", p)  # canonical ref-format example


if __name__ == "__main__":
    unittest.main()
```

(`content_bank/author/briefs/php-001.md` is committed, so `bdp.build("PHP-001", book="PHP")` builds without a `brief=` override.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_draft_prompt content_bank.tests.test_translate_prompt -v`
Expected: FAIL — the tag instructions are absent.

- [ ] **Step 3: Write minimal implementation**

In `build_draft_prompt.py`, add the block constant after `_WCF1_GUARDRAIL`:

```python
_TAGGING_BLOCK = """## Citation tagging (hard requirement)

Declare every citation inline so the gate can verify it:
- Quoted Scripture: wrap the verbatim words in
  `<verse ref="PHP.1.6">...</verse>` — `ref` in canonical corpus format
  (`BOOK.CHAPTER.VERSE`, e.g. `PHP.1.6`, or a range `PHP.1.1-11`). The inner
  text MUST be the exact BSB wording (a `memory_verse` must tag the WHOLE verse).
- A claim resting on the Westminster Standards: wrap the paraphrase in
  `<doctrine std="WCF" ref="1.4">...</doctrine>` — `std` is WCF/WLC/WSC; `ref`
  is chapter.section for WCF (`1.4`) or `Q<n>` for WLC/WSC (`Q1`). The inner
  text is your paraphrase, not a quote.
- Tag by function: tag marked quotations down to a 4-word floor; do NOT tag
  incidental single-word overlap with the passage. Leave non-quoted prose
  untagged."""
```

Insert it into the `parts` list in `build`, right after the confessional guardrail:

```python
             "## Confessional guardrail\n",
             _WCF1_GUARDRAIL + "\n",
             "## Citation tagging\n",
             _TAGGING_BLOCK + "\n",
             "## Dimensions to cover\n"]
```

In `build_translate_prompt.py`, add rule 8 to `_RULES` (renumber nothing else; insert before the `## Output` line):

```python
8. PRESERVE every <verse>/<doctrine> tag from the English. Translate the text
   INSIDE a <verse> tag to the verbatim CUV wording for that ref (widen to the
   smallest containing CUV span if needed); translate the paraphrase inside a
   <doctrine> tag but copy its std/ref unchanged. Never invent a new tag.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_draft_prompt content_bank.tests.test_translate_prompt -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/build_draft_prompt.py content_bank/author/build_translate_prompt.py content_bank/tests/test_draft_prompt.py content_bank/tests/test_translate_prompt.py
git commit -m "feat(prompts): instruct <verse>/<doctrine> tagging (draft) and preservation (translate)"
```

---

### Task 6: strip tags at every reader-facing surface

**Files:**
- Modify: `content_bank/lib/prototype_bank.py:22` (`load_bank` — the kit's single text source)
- Modify: `content_bank/author/translate_compare_html.py` (`_leader_ref`, `build_page`)
- Modify: `content_bank/author/compare_html.py` (`_card`, `_leader_ref`)
- Test: extend `content_bank/tests/test_prototype_bank.py` (add `TestLoadBankStripsTags`) and `content_bank/tests/test_translate_compare_html.py`

**Interfaces:**
- Consumes: `citation_tags.strip_tags`.
- Produces: no signature changes; every reader-facing string is tag-free.

- [ ] **Step 1: Write the failing test**

Add to `content_bank/tests/test_prototype_bank.py` (the file already imports
`from content_bank.lib import prototype_bank as pb`; add `json`, `tempfile`,
and `pathlib` — `pathlib` is already imported). Product mode surfaces only
`review_status == "published"` items (`content.get_content`), so the fixture
MUST be published:

```python
import json
import tempfile


class TestLoadBankStripsTags(unittest.TestCase):
    def _store_dir(self, item):
        d = tempfile.mkdtemp()
        (pathlib.Path(d) / "php.json").write_text(
            json.dumps({"book": "PHP", "items": [item]}), encoding="utf-8")
        return d

    def test_body_and_leader_ref_stripped(self):
        item = {"id": "PHP-001-D1-01", "passage": "PHP.1.1-11", "dimension": "D1",
                "type": "question", "review_status": "published", "version": 1,
                "age_tier": "all", "difficulty": 1,
                "text": {"en": 'Who are the <verse ref="PHP.1.1">servants of Christ '
                               'Jesus</verse>?'},
                "leader_reference": {"kind": "answer_key",
                                     "text": {"en": 'Rests on <doctrine std="WCF" '
                                              'ref="1.4">God its author</doctrine>.'},
                                     "verse": {"en": "Philippians 1:1"}}}
        bank = pb.load_bank("PHP", lang="en", store_dir=self._store_dir(item))
        it = bank["items"][0]
        self.assertNotIn("<verse", it["body"])
        self.assertEqual(it["body"], "Who are the servants of Christ Jesus?")
        self.assertNotIn("<doctrine", it["leader_reference"]["text"]["en"])
```

Add to `content_bank/tests/test_translate_compare_html.py` (`TestTranslateComparePage`):

```python
    def test_tags_stripped_from_display(self):
        root = tempfile.mkdtemp()
        d = pathlib.Path(root) / "PHP" / "runs" / "opus" / "translations" / "deepseek-v4-flash"
        d.mkdir(parents=True)
        p = _proposal("PHP-001-D1-01",
                      '谁是<verse ref="PHP.1.1">基督耶稣的仆人</verse>？')
        p["en"] = 'the <verse ref="PHP.1.1">servants of Christ Jesus</verse>'
        (d / "PHP-001-D1-01.json").write_text(json.dumps(p), encoding="utf-8")
        page = tch.build_page("PHP", "opus", ["deepseek-v4-flash"], root=root)
        row = page["rows"][0]
        self.assertNotIn("<verse", row["en"])
        self.assertNotIn("<verse", row["cells"]["deepseek-v4-flash"]["zh"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_prototype_bank content_bank.tests.test_translate_compare_html -v`
Expected: FAIL — tags still present in `body`/`en`/`zh`.

- [ ] **Step 3: Write minimal implementation**

`content_bank/lib/prototype_bank.py` — import and strip in `load_bank`:

```python
import copy

from . import content, corpus_bridge, citation_tags
```

```python
    for it in content.get_content(book, lang=lang, mode="product", store_dir=store_dir):
        flat = {k: v for k, v in it.items() if k not in ("text", "category")}
        flat["body"] = citation_tags.strip_tags(it["text"][lang])
        lr = flat.get("leader_reference")
        if isinstance(lr, dict):
            lr = copy.deepcopy(lr)
            for key in ("text", "verse"):
                m = lr.get(key)
                if isinstance(m, dict) and isinstance(m.get(lang), str):
                    m[lang] = citation_tags.strip_tags(m[lang])
            flat["leader_reference"] = lr
        if "category" in it and lang in it["category"]:
            flat["category"] = it["category"][lang]
        items.append(flat)
```

`content_bank/author/translate_compare_html.py` — add `from ..lib import corpus_bridge, citation_tags` and strip at the collection points:

In `_leader_ref`, strip the returned text/verse:

```python
    text = citation_tags.strip_tags((lr.get("text") or {}).get(lang, ""))
    verse = citation_tags.strip_tags((lr.get("verse") or {}).get(lang, ""))
    return label, text, verse
```

In `build_page`, strip `en`, the zh cell text, and category:

```python
        rows.append({"id": iid, "en": citation_tags.strip_tags(first.get("en", "")),
                     ...})
```
and in the cell dict:
```python
            cells[t] = {"zh": citation_tags.strip_tags((p["item"].get("text") or {}).get("zh", "")),
                        ...}
```

`content_bank/author/compare_html.py` — add `from ..lib import citation_tags` (check the existing import line) and strip in `_leader_ref` and `_card` where `text_en` values are read:

```python
        "text_en": citation_tags.strip_tags((lr.get("text") or {}).get("en")),
```
```python
        "text_en": citation_tags.strip_tags((item.get("text") or {}).get("en")) or "(no en text)",
```

(`strip_tags(None)` returns `None`, so the `or "(no en text)"` fallback still works.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_prototype_bank content_bank.tests.test_translate_compare_html -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add content_bank/lib/prototype_bank.py content_bank/author/translate_compare_html.py content_bank/author/compare_html.py content_bank/tests/test_prototype_bank.py content_bank/tests/test_translate_compare_html.py
git commit -m "feat(render): strip <verse>/<doctrine> tags at reader-facing surfaces"
```

---

## Final verification

- [ ] Run the full content-bank suite: `uv run python -m unittest discover -s content_bank/tests -v` — all green.
- [ ] Run the prototype suite: `cd prototype && uv run python -m unittest test_selector -v` — all green.
- [ ] Sanity: `uv run python -m unittest discover -s corpus/tests -v` — unaffected, still green.
