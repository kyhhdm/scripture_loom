# CUV Translation Tool Implementation Plan (Plan 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the standalone `translate_cli` that renders reviewed English content into Chinese with strict verbatim-CUV Scripture alignment and glossary-enforced doctrinal vocabulary, emitting a human-reviewable proposal that lands `zh` only via an explicit promote step.

**Architecture:** A prompt builder + an LLM-backed translate/gate/repair core + a back-translation doctrinal-review lens + a CLI that walks a store slice and emits proposals + a promote step. Stands on the Plan-1 foundation (`quote_detect`, `cuv_quote_check`, `glossary_check`, `glossary`). Reuses the existing LLM seam (`content_bank/author/llm.py`), JSON-extraction and repair-loop patterns (`review.py`, `build_cli.py`), and the store writer (`store_writer.py`). Spec: `docs/superpowers/specs/2026-07-21-cuv-alignment-translation-design.md` (Part C).

**Tech Stack:** Python 3, `uv`, stdlib + in-repo packages, `unittest` with the LLM seam mocked (no network in tests).

## Global Constraints

- Run everything under `uv`. Tests: `uv run python -m unittest …`.
- **Tests mock the LLM seam** — patch `content_bank.author.translate.llm` (and `translate_cli`'s use of it). No test performs a network/model call.
- **Bilingual schema fixed**: `text`/`leader_reference.text`/`leader_reference.verse` are `{en, zh}` maps. Translation ONLY adds/updates `zh` values; it never alters `en`, `id`, `dimension`, `type`, `passage`, `refs`, `review_status`, or `provenance`.
- **CUV excerpt delimiter in `zh` = corner brackets `「…」`** (what `cuv_quote_check` verifies).
- **Widen, never back-translate**: if a detected English quote has no contiguous CUV span, the prompt instructs widening to the smallest containing CUV span — never a free rendering.
- **Doctrinal fidelity**: preserve every doctrinal claim exactly; use mandated glossary renderings; surface uncertainty rather than guessing. Anchor = English WCF-1 (`corpus_bridge.wcf_chapter1_text()`), public domain.
- **The tool proposes; humans dispose.** `translate_cli` writes proposals to a working dir; it NEVER writes the store. Only the explicit `promote` step (given an accepted-id list) merges `zh` into the store.
- **Versions**: BSB (`corpus/canon/bibles/bsb.json`) and CUV (`cuv-simp.json`) via `corpus_bridge.passage_text(range, version)`.
- New tests live in `content_bank/tests/test_*.py`.

## File Structure

- Create `content_bank/author/build_translate_prompt.py` — assembles the translation prompt (Task 1).
- Create `content_bank/author/translate.py` — translate/parse/merge, gate+repair, back-translation review, promote (Tasks 2–4, 6).
- Create `content_bank/author/translate_cli.py` — the CLI: walk a slice, emit proposals (Task 5).
- Tests: `test_translate_prompt.py`, `test_translate.py`, `test_translate_review.py`, `test_translate_cli.py`, `test_translate_promote.py`.

**Deferred (a later plan):** the `compare_html` en▸zh▸CUV-source▸flagged-terms visual review page. Interim human review is over the emitted proposal JSON; the promote step already enforces the human gate via an explicit accept list.

---

### Task 1: Translation prompt builder

**Files:**
- Create: `content_bank/author/build_translate_prompt.py`
- Test: `content_bank/tests/test_translate_prompt.py`

**Interfaces:**
- Consumes: `content_bank.lib.corpus_bridge.passage_text(range, version)`, `corpus_bridge.wcf_chapter1_text()`.
- Produces: `build(item, book, *, detected, glossary_entries) -> str`. `detected` is the list of `{"quote","ref"}` from `quote_detect.detect_quotes`; `glossary_entries` is the applicable subset of glossary dicts.

- [ ] **Step 1: Write the failing test**

```python
# content_bank/tests/test_translate_prompt.py
import unittest
from content_bank.author import build_translate_prompt as btp


class TestTranslatePrompt(unittest.TestCase):
    def _item(self):
        return {"id": "PHP-001-D1-01", "passage": "PHP.1.1-11", "dimension": "D1",
                "type": "question",
                "text": {"en": "Who calls themselves servants of Christ Jesus?"},
                "leader_reference": {"kind": "answer_key",
                                     "text": {"en": "Paul and Timothy (v.1)."},
                                     "verse": {"en": "Philippians 1:1"}}}

    def test_prompt_includes_cuv_bsb_glossary_and_rules(self):
        detected = [{"quote": "servants of Christ Jesus", "ref": "PHP.1.1-11"}]
        gloss = [{"en_term": "saints", "zh_term": "圣徒", "sources": ["CUV:PHP.1.1"]}]
        p = btp.build(self._item(), "PHP", detected=detected, glossary_entries=gloss)
        # CUV text for the passage is embedded (基督耶稣的仆人 is CUV PHP.1.1)
        self.assertIn("基督耶稣的仆人", p)
        # BSB text for the detected quote's ref is embedded
        self.assertIn("servants of Christ Jesus", p)
        # mandated glossary term present
        self.assertIn("圣徒", p)
        # the delimiter + fidelity rules are stated
        self.assertIn("「", p)
        # WCF-1 doctrinal anchor present
        self.assertIn("Holy Scripture", p)
        # structured-output keys named
        for key in ('"text"', '"terms"', '"uncertain"'):
            self.assertIn(key, p)

    def test_no_glossary_no_quotes_still_builds(self):
        p = btp.build(self._item(), "PHP", detected=[], glossary_entries=[])
        self.assertIn('"text"', p)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_translate_prompt -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'content_bank.author.build_translate_prompt'`.

- [ ] **Step 3: Write minimal implementation**

```python
# content_bank/author/build_translate_prompt.py
"""Assemble the translation prompt for one content item.

Given the English item, the BSB quotes detected in it (each with the CUV text
for the same ref), the applicable glossary terms, and the English WCF-1 frame,
produce a prompt that renders the item into simplified Chinese with every
Scripture excerpt as verbatim CUV wording in 「…」, mandated glossary terms, and
doctrinal fidelity — returning structured JSON with the zh fields plus a terms
report and an uncertainty list.
"""
import json

from ..lib import corpus_bridge

_RULES = """## Rules
1. Translate the prose into natural simplified Chinese.
2. Every Scripture excerpt MUST be the verbatim CUV wording for its verse,
   wrapped in corner brackets 「…」. Use the CUV text given below — do NOT
   translate the English quote yourself.
3. If an English phrase has no contiguous CUV span, WIDEN to the smallest
   contiguous CUV span that contains it (a clause or the whole verse). Never
   invent a non-CUV rendering.
4. Use the MANDATED glossary rendering for every listed theological term; do
   not substitute a synonym.
5. Preserve every doctrinal claim exactly (see the Westminster frame): do not
   soften, strengthen, reinterpret, evangelize, or add/remove content. State
   observable behavior, never judgment.
6. Do NOT change any structured field (id, dimension, type, refs). Translate
   only text values.
7. If you are unsure of a term's correct Chinese rendering, LIST it in
   "uncertain" — never fabricate a confident wrong term.

## Output — STRICT JSON ONLY, no prose:
{"text": {"zh": "..."},
 "leader_reference": {"text": {"zh": "..."}, "verse": {"zh": "..."}},
 "terms": [{"en": "<term>", "zh": "<rendering used>"}],
 "uncertain": ["<anything you were unsure of>"]}
Omit "leader_reference" if the item has none; omit "verse" if the reference has none."""


def _aligned_scripture(detected):
    if not detected:
        return "(no Scripture excerpts detected in this item)"
    seen, blocks = set(), []
    for d in detected:
        ref = d["ref"]
        if ref in seen:
            continue
        seen.add(ref)
        bsb = corpus_bridge.passage_text(ref, version="BSB")
        cuv = corpus_bridge.passage_text(ref, version="CUV")
        blocks.append(f"### {ref}\nBSB: {bsb}\nCUV: {cuv}")
    return "\n".join(blocks)


def _glossary_block(entries):
    if not entries:
        return "(no mandated terms apply)"
    return "\n".join(f"- {e['en_term']} → {e['zh_term']}" for e in entries)


def build(item, book, *, detected, glossary_entries):
    return (
        "You are translating human-reviewed Bible-study content into simplified "
        "Chinese for Mainland families who read the Chinese Union Version (CUV).\n\n"
        "## English item (JSON)\n"
        f"{json.dumps(item, ensure_ascii=False, indent=2)}\n\n"
        "## Scripture excerpts — use the CUV wording verbatim\n"
        f"{_aligned_scripture(detected)}\n\n"
        "## Mandated theological terms (glossary)\n"
        f"{_glossary_block(glossary_entries)}\n\n"
        "## Westminster frame (doctrinal fidelity guardrail)\n"
        f"{corpus_bridge.wcf_chapter1_text()}\n\n"
        f"{_RULES}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_translate_prompt -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/build_translate_prompt.py content_bank/tests/test_translate_prompt.py
git commit -m "feat(translate): translation prompt builder (CUV-aligned, glossary, WCF-1)"
```

---

### Task 2: Core translate — call, parse, merge zh

**Files:**
- Create: `content_bank/author/translate.py`
- Test: `content_bank/tests/test_translate.py`

**Interfaces:**
- Consumes: `quote_detect.detect_quotes`, `glossary.load_glossary`, `build_translate_prompt.build`, `llm`, `gates._lang_strings`.
- Produces: `_applicable_glossary(item, glossary) -> list`; `_merge_zh(item, resp) -> dict` (deep copy, zh merged); `translate_item(item, book, *, glossary=None, model=None) -> dict` returning `{"item": <copy+zh>, "terms": [...], "uncertain": [...], "cuv_refs": [...]}`.

- [ ] **Step 1: Write the failing test**

```python
# content_bank/tests/test_translate.py
import unittest
from unittest import mock
from content_bank.author import translate

ITEM = {"id": "PHP-001-D1-01", "passage": "PHP.1.1-11", "dimension": "D1",
        "type": "question", "review_status": "reviewed",
        "text": {"en": "Who are the servants of Christ Jesus?"},
        "leader_reference": {"kind": "answer_key",
                             "text": {"en": "Paul and Timothy."},
                             "verse": {"en": "Philippians 1:1"}}}

LLM_JSON = ('{"text": {"zh": "谁是「基督耶稣的仆人」？"},'
            ' "leader_reference": {"text": {"zh": "保罗和提摩太。"},'
            ' "verse": {"zh": "腓立比书 1:1"}},'
            ' "terms": [{"en": "saints", "zh": "圣徒"}],'
            ' "uncertain": []}')


class TestTranslateItem(unittest.TestCase):
    def test_merges_zh_preserves_en_and_structured(self):
        with mock.patch.object(translate, "llm", return_value=LLM_JSON):
            out = translate.translate_item(ITEM, "PHP", glossary=[])
        item = out["item"]
        self.assertEqual(item["text"]["zh"], "谁是「基督耶稣的仆人」？")
        self.assertEqual(item["text"]["en"], ITEM["text"]["en"])  # unchanged
        self.assertEqual(item["leader_reference"]["text"]["zh"], "保罗和提摩太。")
        self.assertEqual(item["id"], ITEM["id"])                  # structured intact
        self.assertEqual(item["review_status"], "reviewed")
        self.assertEqual(out["terms"], [{"en": "saints", "zh": "圣徒"}])
        # original item object not mutated
        self.assertNotIn("zh", ITEM["text"])

    def test_applicable_glossary_filters_by_english(self):
        gloss = [{"en_term": "saints", "zh_term": "圣徒", "sources": ["x"]},
                 {"en_term": "predestination", "zh_term": "预定", "sources": ["y"]}]
        got = translate._applicable_glossary(ITEM, gloss)
        self.assertEqual([e["en_term"] for e in got], [])  # neither term in EN text

    def test_applicable_glossary_matches_present_term(self):
        item = {"id": "x", "text": {"en": "A question about justification."}}
        gloss = [{"en_term": "justification", "zh_term": "称义", "sources": ["z"]}]
        got = translate._applicable_glossary(item, gloss)
        self.assertEqual([e["en_term"] for e in got], ["justification"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_translate -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'content_bank.author.translate'`.

- [ ] **Step 3: Write minimal implementation**

```python
# content_bank/author/translate.py
"""LLM-backed Chinese translation of content items with strict CUV alignment.

Translate → parse structured JSON → merge zh (never touching en or structured
fields). Gating (cuv_quote_check + glossary_check) with repair, a back-
translation doctrinal-review lens, and the promote step live here too. The
tool proposes; only promote() writes the store.
"""
import copy
import json
import re

from . import build_translate_prompt, gates, glossary as _glossary, quote_detect
from .llm import llm

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json(text):
    m = _FENCE.search(text)
    body = m.group(1) if m else text
    s, e = body.find("{"), body.rfind("}")
    if s != -1 and e > s:
        return json.loads(body[s:e + 1])
    raise ValueError(f"no JSON in translation output: {text[:200]!r}")


def _applicable_glossary(item, glossary):
    en = " ".join(s for l, s in gates._lang_strings(item) if l == "en")
    out = []
    for e in glossary:
        if re.search(r"\b" + re.escape(e["en_term"]) + r"\b", en, re.IGNORECASE):
            out.append(e)
    return out


def _merge_zh(item, resp):
    out = copy.deepcopy(item)
    if isinstance(resp.get("text"), dict) and "zh" in resp["text"]:
        out.setdefault("text", {})["zh"] = resp["text"]["zh"]
    lr = resp.get("leader_reference")
    if isinstance(lr, dict) and isinstance(out.get("leader_reference"), dict):
        if isinstance(lr.get("text"), dict) and "zh" in lr["text"]:
            out["leader_reference"].setdefault("text", {})["zh"] = lr["text"]["zh"]
        if isinstance(lr.get("verse"), dict) and "zh" in lr["verse"] \
                and isinstance(out["leader_reference"].get("verse"), dict):
            out["leader_reference"]["verse"]["zh"] = lr["verse"]["zh"]
    return out


def translate_item(item, book, *, glossary=None, model=None):
    glossary = _glossary.load_glossary() if glossary is None else glossary
    detected = quote_detect.detect_quotes(item, book)
    applicable = _applicable_glossary(item, glossary)
    prompt = build_translate_prompt.build(item, book, detected=detected,
                                          glossary_entries=applicable)
    resp = _extract_json(llm(prompt, model))
    return {"item": _merge_zh(item, resp),
            "terms": resp.get("terms", []),
            "uncertain": resp.get("uncertain", []),
            "cuv_refs": sorted({d["ref"] for d in detected})}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_translate -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/translate.py content_bank/tests/test_translate.py
git commit -m "feat(translate): core translate_item (call, parse, merge zh)"
```

---

### Task 3: zh gate + repair loop

**Files:**
- Modify: `content_bank/author/translate.py`
- Test: `content_bank/tests/test_translate.py` (add class)

**Interfaces:**
- Consumes: `gates.cuv_quote_check`, `gates.glossary_check`, `_merge_zh`, `llm`.
- Produces: `zh_gate_flags(item, glossary) -> list[str]` (merged cuv + glossary problems for one item); `translate_with_gates(item, book, *, glossary=None, model=None, max_repair=2) -> dict` — the Task-2 proposal plus `"gate_ok": bool` and `"gate_flags": [...]`, after up to `max_repair` repair rounds.

- [ ] **Step 1: Write the failing test**

```python
# add to content_bank/tests/test_translate.py
GOOD = ('{"text": {"zh": "「基督耶稣的仆人」保罗和提摩太。"}, "terms": [], "uncertain": []}')
BAD = ('{"text": {"zh": "「基督耶稣的门徒」保罗和提摩太。"}, "terms": [], "uncertain": []}')


class TestTranslateWithGates(unittest.TestCase):
    def _item(self):
        return {"id": "PHP-001-D1-01", "passage": "PHP.1.1-11", "dimension": "D1",
                "type": "question", "text": {"en": "servants of Christ Jesus?"}}

    def test_clean_translation_passes_gate(self):
        with mock.patch.object(translate, "llm", return_value=GOOD):
            out = translate.translate_with_gates(self._item(), "PHP", glossary=[])
        self.assertTrue(out["gate_ok"])
        self.assertEqual(out["gate_flags"], [])

    def test_bad_span_repaired_on_second_round(self):
        # first call returns a non-CUV 「…」 span, repair returns a clean one
        with mock.patch.object(translate, "llm", side_effect=[BAD, GOOD]):
            out = translate.translate_with_gates(self._item(), "PHP", glossary=[],
                                                 max_repair=2)
        self.assertTrue(out["gate_ok"])

    def test_unrepaired_bad_span_reported_not_raised(self):
        with mock.patch.object(translate, "llm", side_effect=[BAD, BAD, BAD]):
            out = translate.translate_with_gates(self._item(), "PHP", glossary=[],
                                                 max_repair=2)
        self.assertFalse(out["gate_ok"])
        self.assertTrue(out["gate_flags"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_translate.TestTranslateWithGates -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'translate_with_gates'`.

- [ ] **Step 3: Write minimal implementation**

Add to `content_bank/author/translate.py`:

```python
def zh_gate_flags(item, glossary):
    flags = []
    for gate in (gates.cuv_quote_check([item]),
                 gates.glossary_check([item], glossary)):
        flags.extend(gate.get(item["id"], []))
    return flags


def _repair_prompt(item, flags):
    return ("Your Chinese translation has these problems — fix ONLY them, keeping "
            "everything else identical, and return the SAME strict JSON shape:\n"
            + "\n".join(f"- {f}" for f in flags)
            + "\n\n## Current item (with your zh)\n"
            + json.dumps(item, ensure_ascii=False, indent=2)
            + '\n\nReturn STRICT JSON ONLY: {"text": {"zh": ...}, '
              '"leader_reference": {...}, "terms": [...], "uncertain": [...]}.')


def translate_with_gates(item, book, *, glossary=None, model=None, max_repair=2):
    glossary = _glossary.load_glossary() if glossary is None else glossary
    out = translate_item(item, book, glossary=glossary, model=model)
    flags = zh_gate_flags(out["item"], glossary)
    rounds = 0
    while flags and rounds < max_repair:
        rounds += 1
        resp = _extract_json(llm(_repair_prompt(out["item"], flags), model))
        out["item"] = _merge_zh(out["item"], resp)
        if "terms" in resp:
            out["terms"] = resp["terms"]
        if "uncertain" in resp:
            out["uncertain"] = resp["uncertain"]
        flags = zh_gate_flags(out["item"], glossary)
    out["gate_ok"] = not flags
    out["gate_flags"] = flags
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_translate -v`
Expected: PASS (all — Task 2's 3 + these 3).

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/translate.py content_bank/tests/test_translate.py
git commit -m "feat(translate): zh gate (cuv + glossary) + repair loop"
```

---

### Task 4: Back-translation doctrinal-review lens

**Files:**
- Modify: `content_bank/author/translate.py`
- Test: `content_bank/tests/test_translate_review.py`

**Interfaces:**
- Consumes: `llm`, `_extract_json`, `corpus_bridge.wcf_chapter1_text`, `gates._lang_strings`.
- Produces: `back_translate_review(item, *, model=None) -> {"drift": bool, "notes": str}`. Compares the item's `zh` back to its `en` against WCF-1; returns drift verdict. If the item has no `zh`, returns `{"drift": False, "notes": "no zh"}`.

- [ ] **Step 1: Write the failing test**

```python
# content_bank/tests/test_translate_review.py
import unittest
from unittest import mock
from content_bank.author import translate

ITEM = {"id": "x", "text": {"en": "Scripture is infallible.",
                            "zh": "圣经是无谬的。"}}


class TestBackTranslateReview(unittest.TestCase):
    def test_parses_drift_verdict(self):
        with mock.patch.object(translate, "llm",
                               return_value='{"drift": true, "notes": "softened"}'):
            v = translate.back_translate_review(ITEM)
        self.assertTrue(v["drift"])
        self.assertIn("soften", v["notes"])

    def test_no_zh_short_circuits(self):
        v = translate.back_translate_review({"id": "y", "text": {"en": "hi"}})
        self.assertFalse(v["drift"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_translate_review -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'back_translate_review'`.

- [ ] **Step 3: Write minimal implementation**

Add to `content_bank/author/translate.py` (add `from ..lib import corpus_bridge` to the imports):

```python
def back_translate_review(item, *, model=None):
    zh = " ".join(s for l, s in gates._lang_strings(item) if l == "zh")
    en = " ".join(s for l, s in gates._lang_strings(item) if l == "en")
    if not zh.strip():
        return {"drift": False, "notes": "no zh"}
    prompt = (
        "Back-translate the Chinese below into English, then compare its DOCTRINAL "
        "meaning to the original English and the Westminster frame. Flag any drift: "
        "softened/strengthened/added/removed doctrine, or judgment stated as fact.\n\n"
        f"## Original English\n{en}\n\n## Chinese to check\n{zh}\n\n"
        f"## Westminster frame\n{corpus_bridge.wcf_chapter1_text()}\n\n"
        'Return STRICT JSON ONLY: {"drift": true|false, "notes": "concrete"}.')
    v = _extract_json(llm(prompt, model))
    return {"drift": bool(v.get("drift")), "notes": v.get("notes", "")}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_translate_review -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/translate.py content_bank/tests/test_translate_review.py
git commit -m "feat(translate): back-translation doctrinal-review lens"
```

---

### Task 5: `translate_cli` — walk a slice, emit proposals

**Files:**
- Create: `content_bank/author/translate_cli.py`
- Test: `content_bank/tests/test_translate_cli.py`

**Interfaces:**
- Consumes: `content.load_book_store`, `translate.translate_with_gates`, `translate.back_translate_review`.
- Produces: `select_items(book, *, item_ids=None, status=None, store_dir=None) -> list`; `proposal_for(item, book, *, glossary=None, model=None, max_repair=2) -> dict`; `write_proposals(proposals, out_dir) -> None`; `main(argv=None)`.
- Proposal shape: `{"id", "en": <item.text.en>, "item": <item+zh>, "cuv_refs", "terms", "uncertain", "gate_ok", "gate_flags", "drift": {"drift","notes"}}`.

- [ ] **Step 1: Write the failing test**

```python
# content_bank/tests/test_translate_cli.py
import json
import pathlib
import tempfile
import unittest
from unittest import mock
from content_bank.author import translate_cli, translate

STORE = {"book": "PHP", "items": [
    {"id": "PHP-001-D1-01", "passage": "PHP.1.1-11", "dimension": "D1",
     "type": "question", "review_status": "reviewed",
     "text": {"en": "servants of Christ Jesus?"}},
    {"id": "PHP-001-D1-02", "passage": "PHP.1.1-11", "dimension": "D1",
     "type": "question", "review_status": "published",
     "text": {"en": "Who wrote the letter?"}},
]}
GOOD = '{"text": {"zh": "「基督耶稣的仆人」？"}, "terms": [], "uncertain": []}'


class TestTranslateCli(unittest.TestCase):
    def _store_dir(self):
        d = tempfile.mkdtemp()
        (pathlib.Path(d) / "php.json").write_text(json.dumps(STORE), encoding="utf-8")
        return d

    def test_select_by_status(self):
        d = self._store_dir()
        got = translate_cli.select_items("PHP", status="reviewed", store_dir=d)
        self.assertEqual([i["id"] for i in got], ["PHP-001-D1-01"])

    def test_select_by_ids(self):
        d = self._store_dir()
        got = translate_cli.select_items("PHP", item_ids=["PHP-001-D1-02"], store_dir=d)
        self.assertEqual([i["id"] for i in got], ["PHP-001-D1-02"])

    def test_proposal_shape(self):
        item = STORE["items"][0]
        with mock.patch.object(translate, "llm", return_value=GOOD), \
             mock.patch.object(translate_cli, "back_translate_review",
                               return_value={"drift": False, "notes": ""}):
            p = translate_cli.proposal_for(item, "PHP", glossary=[])
        self.assertEqual(p["id"], "PHP-001-D1-01")
        self.assertEqual(p["en"], "servants of Christ Jesus?")
        self.assertTrue(p["gate_ok"])
        self.assertEqual(p["item"]["text"]["zh"], "「基督耶稣的仆人」？")
        self.assertIn("drift", p)

    def test_write_proposals(self):
        out = tempfile.mkdtemp()
        translate_cli.write_proposals([{"id": "A-1", "gate_ok": True}], out)
        f = pathlib.Path(out) / "A-1.json"
        self.assertTrue(f.exists())
        self.assertEqual(json.loads(f.read_text())["id"], "A-1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_translate_cli -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'content_bank.author.translate_cli'`.

- [ ] **Step 3: Write minimal implementation**

```python
# content_bank/author/translate_cli.py
"""Standalone Chinese-translation tool: walk a store slice, translate each item
with strict CUV alignment + glossary enforcement, back-translation review, and
emit a human-reviewable proposal per item. NEVER writes the store — see
translate.promote for the human-gated landing step.
"""
import argparse
import json
import os
import pathlib

from ..lib import content
from . import glossary as _glossary
from .translate import translate_with_gates, back_translate_review


def select_items(book, *, item_ids=None, status=None, store_dir=None):
    items = content.load_book_store(book, store_dir).get("items", [])
    if item_ids:
        want = set(item_ids)
        return [it for it in items if it["id"] in want]
    if status:
        return [it for it in items if it.get("review_status") == status]
    return list(items)


def proposal_for(item, book, *, glossary=None, model=None, max_repair=2):
    out = translate_with_gates(item, book, glossary=glossary, model=model,
                               max_repair=max_repair)
    drift = back_translate_review(out["item"], model=model)
    return {"id": item["id"],
            "en": (item.get("text") or {}).get("en", ""),
            "item": out["item"], "cuv_refs": out.get("cuv_refs", []),
            "terms": out["terms"], "uncertain": out["uncertain"],
            "gate_ok": out["gate_ok"], "gate_flags": out["gate_flags"],
            "drift": drift}


def write_proposals(proposals, out_dir):
    d = pathlib.Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    for p in proposals:
        (d / f"{p['id']}.json").write_text(
            json.dumps(p, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--items", nargs="*")
    ap.add_argument("--status")
    ap.add_argument("--model")
    ap.add_argument("--max-repair", type=int, default=2)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    if args.model:
        os.environ["SCRIPTURE_LOOM_LLM_MODEL"] = args.model
    out_dir = args.out or f"work/content_bank_build/{args.book}/translations"
    glossary = _glossary.load_glossary()
    items = select_items(args.book, item_ids=args.items, status=args.status)
    proposals, ok = [], 0
    for it in items:
        try:
            p = proposal_for(it, args.book, glossary=glossary, model=args.model,
                             max_repair=args.max_repair)
        except Exception as exc:  # isolate per item
            print(f"[FAIL] {it['id']}: {exc}")
            continue
        proposals.append(p)
        ok += 1
        print(f"[ok] {it['id']}" + ("" if p["gate_ok"] else " (gate flags)")
              + (" (drift)" if p["drift"]["drift"] else ""))
    write_proposals(proposals, out_dir)
    print(f"Done. proposals={ok}/{len(items)} -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_translate_cli -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/translate_cli.py content_bank/tests/test_translate_cli.py
git commit -m "feat(translate): translate_cli — slice walk + proposal emission"
```

---

### Task 6: Promote — human-gated zh landing

**Files:**
- Modify: `content_bank/author/translate.py`
- Test: `content_bank/tests/test_translate_promote.py`

**Interfaces:**
- Consumes: `content.load_book_store`, `store_writer.upsert_items`.
- Produces: `promote(book, proposals, accepted_ids, *, store_dir=None) -> list` — for each accepted proposal, merge ONLY its `zh` values into the matching store item (preserving `en`, structured fields, and `review_status`), then upsert. Returns the ids promoted. A proposal whose id isn't accepted is skipped; an accepted id absent from the store raises `KeyError`.

- [ ] **Step 1: Write the failing test**

```python
# content_bank/tests/test_translate_promote.py
import json
import pathlib
import tempfile
import unittest
from content_bank.author import translate
from content_bank.lib import content

STORE = {"book": "PHP", "items": [
    {"id": "PHP-001-D1-01", "dimension": "D1", "type": "question",
     "review_status": "reviewed", "text": {"en": "servants?"}}]}
PROP = {"id": "PHP-001-D1-01",
        "item": {"id": "PHP-001-D1-01", "dimension": "D1", "type": "question",
                 "review_status": "reviewed",
                 "text": {"en": "servants?", "zh": "仆人？"}}}


class TestPromote(unittest.TestCase):
    def _store_dir(self):
        d = tempfile.mkdtemp()
        (pathlib.Path(d) / "php.json").write_text(json.dumps(STORE), encoding="utf-8")
        return d

    def test_promote_merges_zh_only(self):
        d = self._store_dir()
        ids = translate.promote("PHP", [PROP], ["PHP-001-D1-01"], store_dir=d)
        self.assertEqual(ids, ["PHP-001-D1-01"])
        it = content.load_book_store("PHP", d)["items"][0]
        self.assertEqual(it["text"]["zh"], "仆人？")
        self.assertEqual(it["text"]["en"], "servants?")     # preserved
        self.assertEqual(it["review_status"], "reviewed")   # NOT advanced

    def test_unaccepted_proposal_skipped(self):
        d = self._store_dir()
        ids = translate.promote("PHP", [PROP], [], store_dir=d)
        self.assertEqual(ids, [])
        it = content.load_book_store("PHP", d)["items"][0]
        self.assertNotIn("zh", it["text"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_translate_promote -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'promote'`.

- [ ] **Step 3: Write minimal implementation**

Add to `content_bank/author/translate.py` (add `from ..lib import content` and `from . import store_writer` to imports):

```python
def _merge_zh_into_store_item(store_item, proposal_item):
    """Copy ONLY zh text values from the proposal onto the store item."""
    out = copy.deepcopy(store_item)
    p_text = (proposal_item.get("text") or {})
    if "zh" in p_text:
        out.setdefault("text", {})["zh"] = p_text["zh"]
    p_lr = proposal_item.get("leader_reference") or {}
    o_lr = out.get("leader_reference")
    if isinstance(o_lr, dict):
        if "zh" in (p_lr.get("text") or {}):
            o_lr.setdefault("text", {})["zh"] = p_lr["text"]["zh"]
        if isinstance(o_lr.get("verse"), dict) and "zh" in (p_lr.get("verse") or {}):
            o_lr["verse"]["zh"] = p_lr["verse"]["zh"]
    return out


def promote(book, proposals, accepted_ids, *, store_dir=None):
    accepted = set(accepted_ids)
    store = content.load_book_store(book, store_dir)
    by_id = {it["id"]: it for it in store["items"]}
    to_write, promoted = [], []
    for p in proposals:
        if p["id"] not in accepted:
            continue
        if p["id"] not in by_id:
            raise KeyError(f"{p['id']} not in {book} store")
        to_write.append(_merge_zh_into_store_item(by_id[p["id"]], p["item"]))
        promoted.append(p["id"])
    if to_write:
        store_writer.upsert_items(book, to_write, store_dir)
    return promoted
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_translate_promote -v`
Expected: PASS (2 tests).
Full suite: `uv run python -m unittest discover -s content_bank/tests` — all PASS.

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/translate.py content_bank/tests/test_translate_promote.py
git commit -m "feat(translate): promote — human-gated zh landing into the store"
```

---

## Self-Review

**Spec coverage (Part C of `2026-07-21-cuv-alignment-translation-design.md`):**
- Resolve source verses (BSB + CUV per ref) → Task 1 `_aligned_scripture`. ✅
- Content-based BSB detection feeds the translator → Task 2 via `quote_detect.detect_quotes`. ✅
- Translate with verbatim-CUV `「…」`, glossary, WCF-1 fidelity, surfaced uncertainty → Tasks 1 (prompt) + 2 (parse/merge). ✅
- `cuv_quote_check` + `glossary_check` + repair → Task 3. ✅
- Back-translation doctrinal-review lens → Task 4. ✅
- Proposal emission (never writes store) → Task 5. ✅
- Confirm→promote (human-gated, zh only, en/structured/review_status preserved) → Task 6. ✅
- Default `opus` / `--model` / `--max-repair` / slice flags → Task 5 `main`. ✅ (model via `SCRIPTURE_LOOM_LLM_MODEL`; backend via the existing `SCRIPTURE_LOOM_LLM_BACKEND`.)
- **Deferred (noted):** `compare_html` en▸zh▸CUV visual review page — interim review is over proposal JSON; promote's explicit accept-list is the human gate.

**Placeholder scan:** none — every step has runnable code and exact commands.

**Type consistency:** `translate_item -> {item, terms, uncertain, cuv_refs}`; `translate_with_gates` extends it with `{gate_ok, gate_flags}`; `proposal_for` wraps that + `{id, en, drift}`; `back_translate_review -> {drift, notes}`; `promote(book, proposals, accepted_ids, *, store_dir) -> [ids]`. `_merge_zh` (translate-time, proposal copy) vs `_merge_zh_into_store_item` (promote-time, store copy) are distinct by design and named accordingly. `llm` is imported into `translate` (mock target); `translate_cli` imports `back_translate_review`/`translate_with_gates` from `translate` and is patched at `translate_cli.back_translate_review` in its test. ✅
