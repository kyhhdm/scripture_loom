# Standalone Python Content-Bank Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Claude Code Workflow fan-out that builds the draft content library with a committed, standalone Python program (`build_cli.py`) that drives the same deterministic pipeline and calls the LLM through the vendored `llm_core` seam, plus an optional adversarial-review step; then build the Philippians draft library with it and compare quality against the existing Claude-Code build.

**Architecture:** A thin orchestrator (`build_cli.py`) walks a per-book manifest, and per unit calls the existing pure prompt-builders → the `llm()` seam → a JSON parse → deterministic gates (`gates.py`) with a bounded repair loop → writes a gated draft JSON file. An optional `--review` step (`review.py`) inserts a two-lens adversarial review + one revise pass before the final gates. Failure is isolated per unit; nothing partial is written.

**Tech Stack:** Python 3 (run via `uv`), stdlib + `content_bank`/`corpus`/`llm_core` in-repo packages, `unittest`. LLM via `content_bank.author.llm.llm` → `llm_core` (deepseek-v4-flash). No new third-party deps.

## Global Constraints

- Run all Python via `uv run …`. Tests: `uv run python -m unittest discover -s content_bank/tests -v`.
- LLM access ONLY through `content_bank.author.llm.llm(prompt)`. Every test mocks it — **no network in tests**.
- Items are written `review_status: "draft"`. The builder NEVER writes the committed store and NEVER self-publishes.
- Builder output goes to a drafts dir (default `work/content_bank_build/<book>/drafts/`), overridable with `--drafts-dir`. Staging into the store stays a separate, human-gated step.
- Test files: `content_bank/tests/test_*.py`, unittest style, each starting with `sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))`.
- Repo root from a module in `content_bank/author/`: `pathlib.Path(__file__).resolve().parents[2]`.
- Schema facts: dimensions `D1..D8`; `CLOSED_DIMENSIONS={D1..D5}`, `OPEN_DIMENSIONS={D6,D7,D8}`; ref token form `BOOK.C.V` (regex `^[A-Z0-9]{3}\.\d+\.\d+$`); pericope ranges are single-chapter (`corpus_bridge._parse_range("MAT.8.5-13") -> ("MAT",8,5,13)`).
- Do NOT delete the now-dead `work/content_bank_build/*.workflow.js` or `work/content_bank_build/quote_check.py` scaffolding.

---

### Task 1: Gate module — promote `quote_check` and `schema_check`

**Files:**
- Create: `content_bank/author/gates.py`
- Test: `content_bank/tests/test_gates.py`

**Interfaces:**
- Consumes: `content_bank.lib.schema.validate_item`, `content_bank.lib.corpus_bridge`.
- Produces:
  - `quote_check(book: str, items: list[dict]) -> dict[str, list[str]]`
  - `schema_check(items: list[dict]) -> dict[str, list[str]]`

- [ ] **Step 1: Write the failing test**

Create `content_bank/tests/test_gates.py`:

```python
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.author import gates


def _item(**kw):
    base = dict(id="x-d1-a", dimension="D1", type="question", age_tier="child",
                difficulty=1, review_status="draft", version=1,
                passage="MAT-035", text={"en": "Who came to Jesus?"})
    base.update(kw)
    return base


class QuoteCheckTest(unittest.TestCase):
    def test_flags_non_verbatim_quote(self):
        it = _item(text={"en": 'He said "partakers of grace" to them.'})
        flags = gates.quote_check("MAT", [it])
        self.assertIn("x-d1-a", flags)

    def test_passes_verbatim_bsb_quote(self):
        # "I have not found" appears verbatim in Matthew 8:10 (BSB).
        it = _item(text={"en": 'Jesus said "I have not found" such faith.'})
        self.assertEqual(gates.quote_check("MAT", [it]), {})


class SchemaCheckTest(unittest.TestCase):
    def test_surfaces_validate_item_errors_by_id(self):
        bad = _item(dimension="D9")  # invalid dimension
        flags = gates.schema_check([bad])
        self.assertIn("x-d1-a", flags)
        self.assertTrue(flags["x-d1-a"])

    def test_clean_item_absent(self):
        self.assertEqual(gates.schema_check([_item()]), {})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_gates -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'content_bank.author.gates'`.

- [ ] **Step 3: Write minimal implementation**

Create `content_bank/author/gates.py`:

```python
"""Deterministic content gates for the standalone builder (issue #16).

Pure functions, each returning ``{item_id: [problems]}`` (empty dict = clean):
- quote_check : quoted spans must be verbatim BSB (whole-Bible haystack)
- schema_check: content_bank.lib.schema.validate_item, keyed by id
- refs_in_range (Task 2): stated verse references must fall in the unit's range

Committed replacement for the untracked work/content_bank_build/quote_check.py.
Stdlib + in-repo packages only; offline.
"""
import json
import pathlib
import re

from ..lib import corpus_bridge, schema

_ROOT = pathlib.Path(__file__).resolve().parents[2]
MIN_WORDS = 3


def _norm(s):
    s = re.sub(r"[\"'“”‘’]", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def _book_text(_book):
    # Haystack = the WHOLE BSB, so legitimate cross-reference quotes validate.
    bsb = _ROOT / "corpus" / "canon" / "bibles" / "bsb.json"
    data = json.loads(bsb.read_text(encoding="utf-8"))
    parts = []
    for bk in data["books"].values():
        for ch in bk.values():
            for verse in ch.values():
                if isinstance(verse, str):
                    parts.append(verse)
    return _norm(" ".join(parts))


def _quoted_spans(s):
    return re.findall(r'"([^"]{3,300})"', s) + re.findall(r"“([^”]{3,300})”", s)


def _item_strings(item):
    out = list((item.get("text") or {}).values())
    ref = item.get("leader_reference") or {}
    out += list((ref.get("text") or {}).values())
    out += list((ref.get("verse") or {}).values())
    return out


def quote_check(book, items):
    hay = _book_text(book)
    flags = {}
    for it in items:
        misses = []
        for s in _item_strings(it):
            for span in _quoted_spans(s):
                core = span.strip(" \t\n,.;:!?\"'—-…")
                if len(core.split()) < MIN_WORDS:
                    continue
                if _norm(core) not in hay:
                    misses.append(span)
        if misses:
            flags[it["id"]] = misses
    return flags


def schema_check(items):
    flags = {}
    for it in items:
        errs = schema.validate_item(it)
        if errs:
            flags[it["id"]] = errs
    return flags
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_gates -v`
Expected: PASS (4 tests). If `test_passes_verbatim_bsb_quote` fails, adjust the quoted phrase to one you confirm is verbatim BSB via `uv run python -c "from content_bank.lib import corpus_bridge; print(corpus_bridge.passage_text('MAT.8.10'))"`.

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/gates.py content_bank/tests/test_gates.py
git commit -m "feat(gates): committed quote + schema gates for standalone builder (#16)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `refs_in_range` gate + allowed-range helpers + `run_all`

**Files:**
- Modify: `content_bank/author/gates.py`
- Test: `content_bank/tests/test_gates.py`

**Interfaces:**
- Consumes: `corpus_bridge.pericopes`, `corpus.lib.sections.load`, `corpus_bridge._parse_range`.
- Produces:
  - `pericope_allowed(book: str, pericope_id: str) -> list[tuple]` — allowed parsed ranges for a pericope (its own range).
  - `section_allowed(book: str, section_id: str) -> list[tuple]` — allowed parsed ranges for a section (each member pericope's range).
  - `refs_in_range(items: list[dict], allowed: list[tuple]) -> dict[str, list[str]]` — flags stated `BOOK.C.V` references outside `allowed`. D5 (Connections) pericope items are exempt (they legitimately cross-reference).
  - `run_all(book: str, items: list[dict], allowed: list[tuple]) -> dict[str, list[str]]` — merges quote + schema + refs_in_range flags by id.

- [ ] **Step 1: Write the failing test**

Append to `content_bank/tests/test_gates.py` (before `if __name__`):

```python
class RefsInRangeTest(unittest.TestCase):
    def setUp(self):
        # MAT-035 = "The Faith of the Centurion", MAT.8.5-13.
        self.allowed = gates.pericope_allowed("MAT", "MAT-035")

    def test_flags_mat035_drift_matthew15_reference(self):
        # Reconstruct the historical drift: a non-D5 item in the Matthew-8
        # pericope carrying a Matthew-15 reference token.
        drift = _item(id="mat-35-d1-drift",
                      leader_reference={"kind": "answer_key", "text": {"en": "See MAT.15.8."},
                                        "verse": {"en": "MAT.15.8"},
                                        "provenance": {"reviewed_by": "x", "reviewed_date": "2026-07-20",
                                                       "guardrail": "WCF-1"}})
        flags = gates.refs_in_range([drift], self.allowed)
        self.assertIn("mat-35-d1-drift", flags)

    def test_in_range_reference_not_flagged(self):
        ok = _item(id="mat-35-d1-ok",
                   leader_reference={"kind": "answer_key", "text": {"en": "See MAT.8.10."},
                                     "provenance": {"reviewed_by": "x", "reviewed_date": "2026-07-20",
                                                    "guardrail": "WCF-1"}})
        self.assertEqual(gates.refs_in_range([ok], self.allowed), {})

    def test_d5_item_exempt_from_range(self):
        d5 = _item(id="mat-35-d5-x", dimension="D5",
                   text={"en": "How does this connect to MAT.15.28?"})
        self.assertEqual(gates.refs_in_range([d5], self.allowed), {})

    def test_section_thread_ref_outside_span_flagged(self):
        allowed = gates.section_allowed("PHP", "PHP-S1")
        thread = dict(id="php-s1-thread-x", dimension="D7", type="thread",
                      age_tier="all", difficulty=2, review_status="draft", version=1,
                      section="PHP-S1", text={"en": "joy motif"}, refs=["PHP.4.4"])
        # PHP-S1 does not span chapter 4; PHP.4.4 must be flagged.
        flags = gates.refs_in_range([thread], allowed)
        self.assertIn("php-s1-thread-x", flags)


class RunAllTest(unittest.TestCase):
    def test_merges_all_three_gates(self):
        allowed = gates.pericope_allowed("MAT", "MAT-035")
        bad = _item(id="bad", dimension="D9",  # schema failure
                    text={"en": 'quote "partakers of grace" and ref MAT.15.8'})
        flags = gates.run_all("MAT", [bad], allowed)
        self.assertIn("bad", flags)
        self.assertTrue(len(flags["bad"]) >= 2)  # schema + quote (+ ref)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_gates -v`
Expected: FAIL — `AttributeError: module 'content_bank.author.gates' has no attribute 'pericope_allowed'`.

- [ ] **Step 3: Write minimal implementation**

Append to `content_bank/author/gates.py`:

```python
_REF_TOKEN = re.compile(r"\b[A-Z0-9]{3}\.\d+\.\d+\b")


def _parsed(range_str):
    return corpus_bridge._parse_range(range_str)


def pericope_allowed(book, pericope_id):
    peris = {p["id"]: p for p in corpus_bridge.pericopes(book)}
    if pericope_id not in peris:
        raise ValueError(f"{pericope_id} is not a {book} pericope")
    return [_parsed(peris[pericope_id]["range"])]


def section_allowed(book, section_id):
    from corpus.lib import sections as _sections
    secs = {s["id"]: s for s in _sections.load(book)["sections"]}
    if section_id not in secs:
        raise ValueError(f"{section_id} is not a {book} section")
    sec = secs[section_id]
    peris = corpus_bridge.pericopes(book)
    ids = [p["id"] for p in peris]
    i, j = ids.index(sec["first_pericope"]), ids.index(sec["last_pericope"])
    return [_parsed(p["range"]) for p in peris[i:j + 1]]


def _in_any(book, chapter, verse, allowed):
    return any(b == book and c == chapter and lo <= verse <= hi
               for (b, c, lo, hi) in allowed)


def _stated_refs(item):
    blob = json.dumps(item, ensure_ascii=False)
    tokens = set(_REF_TOKEN.findall(blob))
    tokens.update(item.get("refs") or [])
    return sorted(tokens)


def refs_in_range(items, allowed):
    flags = {}
    for it in items:
        # D5 (Connections) pericope items legitimately cross-reference.
        if "passage" in it and it.get("dimension") == "D5":
            continue
        bad = []
        for ref in _stated_refs(it):
            try:
                b, c, lo, hi = _parsed(ref)
            except (ValueError, AttributeError):
                continue
            if not _in_any(b, c, lo, allowed) or not _in_any(b, c, hi, allowed):
                bad.append(ref)
        if bad:
            flags[it["id"]] = bad
    return flags


def run_all(book, items, allowed):
    merged = {}
    for gate in (quote_check(book, items), schema_check(items),
                 refs_in_range(items, allowed)):
        for k, v in gate.items():
            merged.setdefault(k, []).extend(v)
    return merged
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_gates -v`
Expected: PASS (all gate tests). If `test_section_thread_ref_outside_span_flagged` errors on `section_allowed("PHP","PHP-S1")`, confirm the section id with `uv run python -c "from corpus.lib import sections; print([s['id'] for s in sections.load('PHP')['sections']])"` and use a ref genuinely outside PHP-S1's span.

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/gates.py content_bank/tests/test_gates.py
git commit -m "feat(gates): refs_in_range range gate + run_all merge (#16)

Catches non-D5 scope drift (e.g. MAT-035 Matthew-15 ref in a Matthew-8
pericope) that the quote gate passes when the quote is verbatim.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Make the section prompt self-contained

**Files:**
- Modify: `content_bank/author/build_section_brief_prompt.py`
- Test: `content_bank/tests/test_gates.py` is unrelated; add `content_bank/tests/test_section_prompt.py`

**Interfaces:**
- Consumes: existing `build_section_brief_prompt.build(section_id, book)`.
- Produces: the returned prompt now includes an explicit JSON output-schema block (item shapes + id conventions + "exactly one throughline") so no external workflow prose is needed.

- [ ] **Step 1: Write the failing test**

Create `content_bank/tests/test_section_prompt.py`:

```python
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.author import build_section_brief_prompt as bsp


class SectionPromptSelfContainedTest(unittest.TestCase):
    def test_prompt_specifies_json_item_schema(self):
        text = bsp.build("PHP-S1", "PHP")
        # The item shapes must be in the prompt itself (previously only in the
        # workflow JS), so the standalone builder needs no external template.
        for needle in ('"type":"throughline"', '"type":"thread"',
                       "exactly one throughline", "JSON array"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_section_prompt -v`
Expected: FAIL — the assertions on `"type":"throughline"` etc. are not present.

- [ ] **Step 3: Write minimal implementation**

In `content_bank/author/build_section_brief_prompt.py`, add an output-schema constant and append it in `build()`. After the `_SHAPE` string definition, add:

```python
_OUTPUT_SCHEMA = """## Output — a JSON array of section-scoped ContentItems

Return ONLY a JSON array (no prose). Item shapes, using the section id <SID>
(lower-case in ids) and book <BOOK>:

- EXACTLY ONE throughline:
  {"id":"<sid>-throughline","section":"<SID>","dimension":"D7",
   "type":"throughline","age_tier":"all","difficulty":2,
   "review_status":"draft","text":{"en":"..."},"version":1}
- ZERO OR MORE threads (only if the motif genuinely RECURS across 2+ pericopes):
  {"id":"<sid>-thread-<slug>","section":"<SID>","dimension":"D7"|"D3",
   "type":"thread","age_tier":"all","difficulty":2,"review_status":"draft",
   "text":{"en":"<name + what the recurrence teaches>"},
   "refs":["<BOOK>.C.V", "..."],"version":1}   (refs = >=2 member verses)
- 2-4 arc QUESTIONS answerable only ACROSS the section:
  {"id":"<sid>-q-<slug>","section":"<SID>","dimension":"D5"|"D6"|"D7",
   "type":"question","age_tier":"youth"|"adult"|"all","difficulty":2|3,
   "review_status":"draft","text":{"en":"..."},"version":1}
  Give D6/D7 a leader_note and D5 an answer_key, each with provenance
  {"reviewed_by":"claude","reviewed_date":"2026-07-20","guardrail":"WCF-1"};
  throughline/thread need no leader_reference.

Keep EXACTLY ONE throughline. Quoted words must be verbatim BSB."""
```

Then in `build()`, replace the final two lines:

```python
    parts.append(_SHAPE)
    return "\n".join(parts)
```

with:

```python
    parts.append(_SHAPE)
    parts.append("\n" + _OUTPUT_SCHEMA
                 .replace("<SID>", section_id)
                 .replace("<sid>", section_id.lower())
                 .replace("<BOOK>", book))
    return "\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_section_prompt -v`
Expected: PASS. Also re-run existing author tests to confirm no regression: `uv run python -m unittest content_bank.tests.test_author -v`.

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/build_section_brief_prompt.py content_bank/tests/test_section_prompt.py
git commit -m "feat(author): fold section item-schema into build() for standalone builder (#16)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Builder helpers — parse, backoff, repair loop, errors

**Files:**
- Create: `content_bank/author/build_cli.py` (helpers only this task)
- Test: `content_bank/tests/test_build_cli.py`

**Interfaces:**
- Consumes: `content_bank.author.gates.run_all`, `content_bank.author.llm.llm`, `llm_core.llm_configured`.
- Produces:
  - `GateError(Exception)`, `LLMUnavailable(Exception)`
  - `_parse_items(text: str) -> list[dict]`
  - `_llm_with_backoff(prompt: str, *, tries: int = 4, base: float = 2.0) -> str`
  - `_draft_with_repair(prompt: str, book: str, allowed: list[tuple], *, max_repair: int = 2) -> list[dict]`

- [ ] **Step 1: Write the failing test**

Create `content_bank/tests/test_build_cli.py`:

```python
import json
import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.author import build_cli


class ParseItemsTest(unittest.TestCase):
    def test_strips_json_fence(self):
        text = 'Here you go:\n```json\n[{"id": "a"}]\n```\nDone.'
        self.assertEqual(build_cli._parse_items(text), [{"id": "a"}])

    def test_bare_array(self):
        self.assertEqual(build_cli._parse_items('[{"id":"b"}]'), [{"id": "b"}])

    def test_unparseable_raises(self):
        with self.assertRaises(ValueError):
            build_cli._parse_items("no json here")


class BackoffTest(unittest.TestCase):
    def test_retries_then_succeeds(self):
        calls = {"n": 0}

        def flaky(_p):
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("rate limit")
            return "ok"

        with mock.patch("content_bank.author.build_cli.llm", side_effect=flaky), \
             mock.patch("content_bank.author.build_cli.time.sleep"):
            out = build_cli._llm_with_backoff("p", tries=4)
        self.assertEqual(out, "ok")
        self.assertEqual(calls["n"], 3)

    def test_gives_up_after_tries(self):
        with mock.patch("content_bank.author.build_cli.llm",
                        side_effect=RuntimeError("rate limit")), \
             mock.patch("content_bank.author.build_cli.time.sleep"):
            with self.assertRaises(RuntimeError):
                build_cli._llm_with_backoff("p", tries=2)


class RepairLoopTest(unittest.TestCase):
    def _allowed(self):
        from content_bank.author import gates
        return gates.pericope_allowed("MAT", "MAT-035")

    def test_dirty_then_clean(self):
        good = json.dumps([dict(id="m-d1-a", dimension="D1", type="question",
                                age_tier="child", difficulty=1, review_status="draft",
                                version=1, passage="MAT-035",
                                text={"en": "Who came to Jesus?"})])
        bad = json.dumps([dict(id="m-d1-a", dimension="D9", type="question",
                               age_tier="child", difficulty=1, review_status="draft",
                               version=1, passage="MAT-035", text={"en": "x"})])
        seq = [bad, good]
        with mock.patch("content_bank.author.build_cli._llm_with_backoff",
                        side_effect=seq):
            items = build_cli._draft_with_repair("PROMPT", "MAT", self._allowed(),
                                                 max_repair=2)
        self.assertEqual(items[0]["dimension"], "D1")

    def test_never_clean_raises_gateerror(self):
        bad = json.dumps([dict(id="m-d1-a", dimension="D9", type="question",
                               age_tier="child", difficulty=1, review_status="draft",
                               version=1, passage="MAT-035", text={"en": "x"})])
        with mock.patch("content_bank.author.build_cli._llm_with_backoff",
                        return_value=bad):
            with self.assertRaises(build_cli.GateError):
                build_cli._draft_with_repair("PROMPT", "MAT", self._allowed(),
                                             max_repair=1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_build_cli -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'content_bank.author.build_cli'`.

- [ ] **Step 3: Write minimal implementation**

Create `content_bank/author/build_cli.py`:

```python
"""Standalone content-bank draft builder (issue #16).

Walks a per-book manifest and, per unit, drives the deterministic pipeline:
prompt-builder -> llm() -> parse -> gates (+ bounded repair) -> gated draft file.
Optional --review adds a two-lens adversarial pass. Items are written
review_status "draft"; staging into the store stays a separate human-gated step.
"""
import json
import random
import re
import time

from .gates import run_all
from .llm import llm

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class GateError(Exception):
    """Gates never came clean within the repair budget."""


class LLMUnavailable(Exception):
    """No LLM credential configured; the run cannot proceed."""


def _parse_items(text):
    m = _FENCE.search(text)
    body = m.group(1) if m else text
    start = body.find("[")
    end = body.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"no JSON array in LLM output: {text[:200]!r}")
    return json.loads(body[start:end + 1])


def _llm_with_backoff(prompt, *, tries=4, base=2.0):
    last = None
    for attempt in range(1, tries + 1):
        try:
            return llm(prompt)
        except RuntimeError as exc:  # rate-limit / transient; llm_core already retried
            last = exc
            if attempt == tries:
                break
            time.sleep(base ** attempt + random.uniform(0, 1))
    raise last


def _repair_prompt(prompt, items, flags):
    return (prompt
            + "\n\n## Previous attempt (fix and RETURN THE FULL CORRECTED ARRAY)\n"
            + json.dumps(items, ensure_ascii=False)
            + "\n\n## Gate problems to fix (item id -> problems)\n"
            + json.dumps(flags, ensure_ascii=False)
            + "\n\nReturn ONLY the corrected JSON array.")


def _draft_with_repair(prompt, book, allowed, *, max_repair=2):
    items = _parse_items(_llm_with_backoff(prompt))
    flags = run_all(book, items, allowed)
    rounds = 0
    while flags and rounds < max_repair:
        rounds += 1
        items = _parse_items(_llm_with_backoff(_repair_prompt(prompt, items, flags)))
        flags = run_all(book, items, allowed)
    if flags:
        raise GateError(f"gates unclean after {max_repair} repair(s): {flags}")
    return items
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_build_cli -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/build_cli.py content_bank/tests/test_build_cli.py
git commit -m "feat(build_cli): parse/backoff/repair helpers for standalone builder (#16)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Builder orchestrator — per-unit flow, manifest, isolation, CLI

**Files:**
- Modify: `content_bank/author/build_cli.py`
- Test: `content_bank/tests/test_build_cli.py`

**Interfaces:**
- Consumes: `build_brief_prompt.build`, `build_draft_prompt.build`, `build_section_brief_prompt.build`, `manifest` module, `gates.pericope_allowed`/`section_allowed`, `llm_core.llm_configured`.
- Produces:
  - `build_pericope(pid, book, *, drafts_dir, briefs_dir, manifest_obj, manifest_path, review_on, max_repair) -> str` (returns final stage) 
  - `build_section(sid, book, *, drafts_dir, manifest_obj, manifest_path, review_on, max_repair) -> str`
  - `run(book, *, units=None, kind="all", review_on=False, max_repair=2, limit=None, manifest_path=None, drafts_dir=None) -> dict` (returns `{"ok": [...], "failed": {id: reason}}`)
  - `main(argv=None)`

- [ ] **Step 1: Write the failing test**

Append to `content_bank/tests/test_build_cli.py` (before `if __name__`):

```python
import tempfile
from content_bank.author import manifest as manifest_mod


class OrchestratorTest(unittest.TestCase):
    def _draft_json(self, pid):
        return json.dumps([dict(id=f"{pid.lower()}-d1-a", dimension="D1",
                                type="question", age_tier="child", difficulty=1,
                                review_status="draft", version=1, passage=pid,
                                text={"en": "Who came to Jesus?"})])

    def test_pericope_writes_draft_and_bumps_stage(self):
        with tempfile.TemporaryDirectory() as d:
            drafts = pathlib.Path(d) / "drafts"
            briefs = pathlib.Path(d) / "briefs"
            m = manifest_mod.init_manifest("MAT", ["MAT-035"])
            mpath = pathlib.Path(d) / "manifest.json"
            manifest_mod.save(mpath, m)
            # brief call returns any text; draft call returns clean items.
            outputs = iter(["BRIEF TEXT", self._draft_json("MAT-035")])
            with mock.patch("content_bank.author.build_cli._llm_with_backoff",
                            side_effect=lambda *_a, **_k: next(outputs)):
                stage = build_cli.build_pericope(
                    "MAT-035", "MAT", drafts_dir=drafts, briefs_dir=briefs,
                    manifest_obj=m, manifest_path=mpath, review_on=False, max_repair=2)
            self.assertEqual(stage, "drafted")
            self.assertTrue((drafts / "MAT-035.json").exists())
            self.assertEqual(m["units"]["MAT-035"]["stage"], "drafted")

    def test_failure_isolated_stage_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            drafts = pathlib.Path(d) / "drafts"
            m = manifest_mod.init_manifest("MAT", ["MAT-035", "MAT-036"])
            mpath = pathlib.Path(d) / "manifest.json"
            manifest_mod.save(mpath, m)

            def boom(*_a, **_k):
                raise RuntimeError("llm exploded")

            with mock.patch("content_bank.author.build_cli._llm_with_backoff",
                            side_effect=boom):
                res = build_cli.run("MAT", units=["MAT-035"], kind="pericope",
                                    manifest_path=mpath, drafts_dir=drafts,
                                    briefs_dir=pathlib.Path(d) / "briefs")
            self.assertIn("MAT-035", res["failed"])
            self.assertEqual(m["units"]["MAT-035"]["stage"], "pending")

    def test_run_fails_fast_when_unconfigured(self):
        with mock.patch("content_bank.author.build_cli.llm_configured",
                        return_value=False):
            with self.assertRaises(build_cli.LLMUnavailable):
                build_cli.run("MAT", units=["MAT-035"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_build_cli -v`
Expected: FAIL — `AttributeError: module 'content_bank.author.build_cli' has no attribute 'build_pericope'`.

- [ ] **Step 3: Write minimal implementation**

Add imports at the top of `content_bank/author/build_cli.py`:

```python
import argparse
import pathlib

from . import (build_brief_prompt, build_draft_prompt,
               build_section_brief_prompt, manifest as manifest_mod)
from . import gates
from llm_core import llm_configured
```

Append the orchestrator functions:

```python
_BRIEFS_DIR = pathlib.Path(__file__).parent / "briefs"


def _write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def build_pericope(pid, book, *, drafts_dir, briefs_dir=None, manifest_obj,
                   manifest_path, review_on=False, max_repair=2):
    briefs_dir = briefs_dir or _BRIEFS_DIR
    brief_path = pathlib.Path(briefs_dir) / f"{pid.lower()}.md"
    if manifest_obj["units"][pid]["stage"] == "pending":
        brief = _llm_with_backoff(build_brief_prompt.build(pid, book))
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        brief_path.write_text(brief, encoding="utf-8")
        manifest_mod.set_stage(manifest_obj, pid, "briefed")
        manifest_mod.save(manifest_path, manifest_obj)
    else:
        brief = brief_path.read_text(encoding="utf-8")

    allowed = gates.pericope_allowed(book, pid)
    prompt = build_draft_prompt.build(pid, book, brief)
    if review_on:
        from . import review as review_mod
        items = _parse_items(_llm_with_backoff(prompt))
        ctx = dict(passage_text=_passage_text(book, pid), brief=brief,
                   book=book, unit_id=pid)
        verdicts = review_mod.review(items, **ctx)
        items = review_mod.revise(items, verdicts, passage_text=ctx["passage_text"],
                                  brief=brief)
        items = _regate(prompt, items, book, allowed, max_repair=max_repair)
    else:
        items = _draft_with_repair(prompt, book, allowed, max_repair=max_repair)

    _write_json(pathlib.Path(drafts_dir) / f"{pid}.json", items)
    manifest_mod.set_stage(manifest_obj, pid, "drafted")
    manifest_mod.save(manifest_path, manifest_obj)
    return "drafted"


def build_section(sid, book, *, drafts_dir, manifest_obj, manifest_path,
                  review_on=False, max_repair=2):
    allowed = gates.section_allowed(book, sid)
    prompt = build_section_brief_prompt.build(sid, book)
    if review_on:
        from . import review as review_mod
        items = _parse_items(_llm_with_backoff(prompt))
        verdicts = review_mod.review(items, passage_text=_section_text(book, sid),
                                     brief="", book=book, unit_id=sid)
        items = review_mod.revise(items, verdicts,
                                  passage_text=_section_text(book, sid), brief="")
        items = _regate(prompt, items, book, allowed, max_repair=max_repair)
    else:
        items = _draft_with_repair(prompt, book, allowed, max_repair=max_repair)
    _write_json(pathlib.Path(drafts_dir) / f"{sid}.json", items)
    manifest_mod.set_stage(manifest_obj, sid, "drafted")
    manifest_mod.save(manifest_path, manifest_obj)
    return "drafted"


def _regate(prompt, items, book, allowed, *, max_repair):
    flags = run_all(book, items, allowed)
    rounds = 0
    while flags and rounds < max_repair:
        rounds += 1
        items = _parse_items(_llm_with_backoff(_repair_prompt(prompt, items, flags)))
        flags = run_all(book, items, allowed)
    if flags:
        raise GateError(f"gates unclean after review+{max_repair} repair(s): {flags}")
    return items


def _passage_text(book, pid):
    from ..lib import corpus_bridge
    p = {x["id"]: x for x in corpus_bridge.pericopes(book)}[pid]
    return corpus_bridge.passage_text(p["range"])


def _section_text(book, sid):
    from ..lib import corpus_bridge
    from corpus.lib import sections as _sections
    sec = {s["id"]: s for s in _sections.load(book)["sections"]}[sid]
    peris = corpus_bridge.pericopes(book)
    ids = [p["id"] for p in peris]
    i, j = ids.index(sec["first_pericope"]), ids.index(sec["last_pericope"])
    return "\n\n".join(corpus_bridge.passage_text(p["range"]) for p in peris[i:j + 1])


def _default_manifest_path(book):
    return (pathlib.Path("work/content_bank_build") / book / "manifest.json")


def run(book, *, units=None, kind="all", review_on=False, max_repair=2,
        limit=None, manifest_path=None, drafts_dir=None, briefs_dir=None):
    if not llm_configured():
        raise LLMUnavailable(
            "no LLM credential (set ARK_API_KEY or llm_api_key); see CLAUDE.md")
    manifest_path = pathlib.Path(manifest_path or _default_manifest_path(book))
    m = manifest_mod.load(manifest_path)
    drafts_dir = pathlib.Path(drafts_dir
                              or manifest_path.parent / "drafts")

    if units:
        todo = list(units)
    else:
        todo = manifest_mod.units_at(m, "pending") + manifest_mod.units_at(m, "briefed")
        if kind != "all":
            todo = [u for u in todo if m["units"][u]["kind"] == kind]
    if limit:
        todo = todo[:limit]

    ok, failed = [], {}
    for uid in todo:
        meta = m["units"][uid]
        try:
            if meta["kind"] == "pericope":
                build_pericope(uid, book, drafts_dir=drafts_dir, briefs_dir=briefs_dir,
                               manifest_obj=m, manifest_path=manifest_path,
                               review_on=review_on, max_repair=max_repair)
            else:
                build_section(uid, book, drafts_dir=drafts_dir, manifest_obj=m,
                              manifest_path=manifest_path, review_on=review_on,
                              max_repair=max_repair)
            ok.append(uid)
            print(f"[ok] {uid}")
        except (GateError, RuntimeError, ValueError) as exc:
            failed[uid] = str(exc)
            print(f"[FAIL] {uid}: {exc}")
    return {"ok": ok, "failed": failed}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Standalone content-bank draft builder")
    ap.add_argument("--book", required=True)
    ap.add_argument("--units", nargs="*")
    ap.add_argument("--kind", choices=("pericope", "section", "all"), default="all")
    ap.add_argument("--review", action="store_true")
    ap.add_argument("--max-repair", type=int, default=2)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--manifest")
    ap.add_argument("--drafts-dir")
    a = ap.parse_args(argv)
    res = run(a.book, units=a.units, kind=a.kind, review_on=a.review,
              max_repair=a.max_repair, limit=a.limit, manifest_path=a.manifest,
              drafts_dir=a.drafts_dir)
    print(f"\nDone. ok={len(res['ok'])} failed={len(res['failed'])}")
    return 1 if res["failed"] else 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_build_cli -v`
Expected: PASS (all orchestrator tests). `test_run_fails_fast_when_unconfigured` requires `llm_configured` be importable as a module attribute — it is (imported at top).

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/build_cli.py content_bank/tests/test_build_cli.py
git commit -m "feat(build_cli): orchestrator with manifest walk + per-unit isolation (#16)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Adversarial review + revise (`review.py`)

**Files:**
- Create: `content_bank/author/review.py`
- Test: `content_bank/tests/test_review.py`

**Interfaces:**
- Consumes: `content_bank.author.rubric.build`, `rubric.reference_criteria`, `content_bank.author.llm.llm`.
- Produces:
  - `review(items, *, passage_text, brief, book, unit_id) -> list[dict]` — returns a list of per-reviewer verdict dicts `{"reviewer","verdicts":{id:{"verdict","notes"}}}`.
  - `revise(items, verdicts, *, passage_text, brief) -> list[dict]` — returns the full revised item array (only failed items changed; unfixable items may be dropped).

- [ ] **Step 1: Write the failing test**

Create `content_bank/tests/test_review.py`:

```python
import json
import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.author import review


def _item(iid, **kw):
    base = dict(id=iid, dimension="D1", type="question", age_tier="child",
                difficulty=1, review_status="draft", version=1, passage="PHP-001",
                text={"en": "Who wrote to the Philippians?"})
    base.update(kw)
    return base


class ReviewTest(unittest.TestCase):
    def test_review_parses_two_reviewer_verdicts(self):
        r1 = json.dumps({"a": {"verdict": "pass", "notes": ""}})
        r2 = json.dumps({"a": {"verdict": "fail", "notes": "judgment language"}})
        with mock.patch("content_bank.author.review.llm", side_effect=[r1, r2]):
            verdicts = review.review([_item("a")], passage_text="P", brief="B",
                                     book="PHP", unit_id="PHP-001")
        self.assertEqual(len(verdicts), 2)
        merged = {v["reviewer"]: v["verdicts"] for v in verdicts}
        self.assertEqual(merged["r2"]["a"]["verdict"], "fail")


class ReviseTest(unittest.TestCase):
    def test_revise_returns_corrected_array(self):
        items = [_item("a"), _item("b")]
        verdicts = [{"reviewer": "r1", "verdicts": {"a": {"verdict": "fail",
                     "notes": "fix"}}}]
        corrected = json.dumps([_item("a", text={"en": "Paul — who wrote it?"}),
                                _item("b")])
        with mock.patch("content_bank.author.review.llm", return_value=corrected):
            out = review.revise(items, verdicts, passage_text="P", brief="B")
        self.assertEqual(out[0]["text"]["en"], "Paul — who wrote it?")
        self.assertEqual(len(out), 2)

    def test_no_failures_skips_llm(self):
        items = [_item("a")]
        verdicts = [{"reviewer": "r1", "verdicts": {"a": {"verdict": "pass"}}}]
        with mock.patch("content_bank.author.review.llm") as m:
            out = review.revise(items, verdicts, passage_text="P", brief="B")
        m.assert_not_called()
        self.assertEqual(out, items)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_review -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'content_bank.author.review'`.

- [ ] **Step 3: Write minimal implementation**

Create `content_bank/author/review.py`:

```python
"""Optional adversarial review + revise step for the standalone builder (#16).

Two complementary reviewer lenses (r1 accuracy/WCF-1/answerability; r2
evidence-not-judgment/age/dimension/pedagogy/leader-references), single-sourced
against author/rubric.py, then one revise pass over only the failed items. Never
bypasses the deterministic gates (the caller re-gates afterward). Items stay
review_status "draft"; this sharpens the draft, it does not confer human review.
"""
import json
import re

from . import rubric
from .llm import llm

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

_R1 = ("ADVERSARIAL review, lens r1 (accuracy, WCF-1 conformity, answerability). "
       "Hunt for faults: wrong facts/verse refs, quotes not verbatim BSB, keys not "
       "grounded, non-D5 items not answerable from THIS passage, imported doctrine "
       "the passage does not bear, hedging on WCF-1.")
_R2 = ("ADVERSARIAL review, lens r2 (evidence-not-judgment, age fitness, dimension "
       "fit, pedagogy, leader-reference correctness). Hunt for faults: prompts that "
       "assess faith/character/spiritual state; language mismatched to age_tier; "
       "item not exercising its tagged dimension; answer_key on D6-D8 or leader_note "
       "on D1-D5 or any leader_reference on a memory_verse; leading/trivial prompts.")


def _extract_json(text):
    m = _FENCE.search(text)
    body = m.group(1) if m else text
    for op, cl in (("{", "}"), ("[", "]")):
        s, e = body.find(op), body.rfind(cl)
        if s != -1 and e > s:
            try:
                return json.loads(body[s:e + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"no JSON in reviewer output: {text[:200]!r}")


def _reviewer_prompt(lens, rubric_text, items, passage_text, brief):
    return (f"{lens}\n\n## Rubric\n{rubric_text}\n\n## Passage\n{passage_text}\n\n"
            f"## Brief\n{brief}\n\n## Draft items (JSON)\n"
            f"{json.dumps(items, ensure_ascii=False)}\n\n"
            "Return STRICT JSON ONLY: an object mapping item id -> "
            '{"verdict":"pass"|"fail","notes":"concrete"}. No prose.')


def review(items, *, passage_text, brief, book, unit_id):
    out = []
    for name, lens, rubric_text in (
            ("r1", _R1, rubric.build()),
            ("r2", _R2, rubric.build() + "\n" + rubric.reference_criteria())):
        raw = llm(_reviewer_prompt(lens, rubric_text, items, passage_text, brief))
        out.append({"reviewer": name, "verdicts": _extract_json(raw)})
    return out


def _failed_ids(verdicts):
    ids = set()
    for v in verdicts:
        for iid, verdict in v.get("verdicts", {}).items():
            if verdict.get("verdict") == "fail":
                ids.add(iid)
    return ids


def revise(items, verdicts, *, passage_text, brief):
    failed = _failed_ids(verdicts)
    if not failed:
        return items
    prompt = (
        "Revise ONLY the flagged items to address each reviewer note precisely "
        "(fix fact/quote; retag dimension and switch answer_key<->leader_note to "
        "match; reframe judgment->observable behavior; make answerable/grounded). "
        "Leave passing items byte-identical. If an item cannot be made both accurate "
        "and gate-clean, DROP it.\n\n"
        f"## Passage\n{passage_text}\n\n## Brief\n{brief}\n\n"
        f"## Reviewer verdicts (JSON)\n{json.dumps(verdicts, ensure_ascii=False)}\n\n"
        f"## Current items (JSON)\n{json.dumps(items, ensure_ascii=False)}\n\n"
        "Return ONLY the full corrected JSON array.")
    raw = llm(prompt)
    return _extract_json(raw)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_review -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/review.py content_bank/tests/test_review.py
git commit -m "feat(review): optional two-lens adversarial review + revise (#16)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: End-to-end wiring check with `--review`

**Files:**
- Test: `content_bank/tests/test_build_cli.py`

**Interfaces:**
- Consumes: everything above. No new production code — this task proves `review_on=True` flows draft → review → revise → gates → file, all with `llm()` mocked.

- [ ] **Step 1: Write the failing test**

Append to `content_bank/tests/test_build_cli.py` (before `if __name__`):

```python
class ReviewFlowTest(unittest.TestCase):
    def test_review_on_runs_review_then_regate_then_writes(self):
        with tempfile.TemporaryDirectory() as d:
            drafts = pathlib.Path(d) / "drafts"
            briefs = pathlib.Path(d) / "briefs"
            m = manifest_mod.init_manifest("MAT", ["MAT-035"])
            mpath = pathlib.Path(d) / "manifest.json"
            manifest_mod.save(mpath, m)
            clean = json.dumps([dict(id="mat-035-d1-a", dimension="D1",
                                     type="question", age_tier="child", difficulty=1,
                                     review_status="draft", version=1, passage="MAT-035",
                                     text={"en": "Who came to Jesus?"})])
            # brief, draft, r1, r2 (revise skipped: all pass)
            r_pass = json.dumps({"mat-035-d1-a": {"verdict": "pass", "notes": ""}})
            seq = iter(["BRIEF", clean, r_pass, r_pass])
            with mock.patch("content_bank.author.build_cli._llm_with_backoff",
                            side_effect=lambda *_a, **_k: next(seq)), \
                 mock.patch("content_bank.author.review.llm",
                            side_effect=[r_pass, r_pass]):
                stage = build_cli.build_pericope(
                    "MAT-035", "MAT", drafts_dir=drafts, briefs_dir=briefs,
                    manifest_obj=m, manifest_path=mpath, review_on=True, max_repair=1)
            self.assertEqual(stage, "drafted")
            self.assertTrue((drafts / "MAT-035.json").exists())
```

Note: `build_pericope` with `review_on=True` calls `_llm_with_backoff` for the brief, then for the draft, then `review.review` calls `review.llm` directly (patched separately), then `_regate` may call `_llm_with_backoff` again only if gates are dirty (they are clean here, so it won't). The `seq` therefore yields brief + draft; the `review.llm` patch yields the two reviewer verdicts.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_build_cli.ReviewFlowTest -v`
Expected: FAIL initially if any wiring is off (e.g. StopIteration or a gate error). Diagnose against the note above.

- [ ] **Step 3: Fix wiring if needed**

If the test fails because `_regate` consumed a `seq` element, confirm the draft items are gate-clean for MAT-035 (they are: in-range, valid schema). No production change should be needed; if `review.review` context args mismatch, align `build_pericope`'s `ctx` with `review.review`'s signature (`passage_text, brief, book, unit_id`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_build_cli -v`
Expected: PASS (all build_cli tests, including ReviewFlowTest).

- [ ] **Step 5: Commit**

```bash
git add content_bank/tests/test_build_cli.py
git commit -m "test(build_cli): end-to-end --review flow with llm mocked (#16)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: Full suite green + issue #16 acceptance note

**Files:**
- Modify: `docs/superpowers/specs/2026-07-20-standalone-content-bank-builder-design.md` (tick acceptance boxes that are now met)

- [ ] **Step 1: Run the whole content-bank suite**

Run: `uv run python -m unittest discover -s content_bank/tests -v`
Expected: PASS (all existing + new tests). Fix any regression before proceeding.

- [ ] **Step 2: Run the llm_core suite (seam untouched, but confirm)**

Run: `uv run python -m unittest discover -s llm_core/tests -v`
Expected: PASS.

- [ ] **Step 3: Tick the acceptance boxes in the spec that code now satisfies**

Edit the spec's Acceptance criteria section, changing `- [ ]` to `- [x]` for: same draft items gated on quote+schema+ref-range; single `llm()` seam; backoff + isolation; mocked unit tests; stdlib-vs-SDK decision recorded; optional `--review`. Leave the PHP-build/comparison box unticked (Task 9–10).

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-07-20-standalone-content-bank-builder-design.md
git commit -m "docs(#16): standalone builder acceptance criteria met (code)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 9: Build the Philippians draft library with the Python builder (`--review`)

**Files:**
- Create (untracked output): `work/content_bank_build/PHP/drafts_py/*.json`

**Note:** This task makes REAL LLM calls and needs `ARK_API_KEY` in `.env`. The existing Claude-Code PHP build lives in `work/content_bank_build/PHP/drafts/` — do NOT overwrite it; the Python build goes to a separate `drafts_py/` dir via `--drafts-dir`.

- [ ] **Step 1: Confirm the LLM is configured**

Run: `uv run python -c "from llm_core import llm_configured; print(llm_configured())"`
Expected: `True`. If `False`, stop and tell the user to set `ARK_API_KEY` in `.env` (per CLAUDE.md); do not proceed.

- [ ] **Step 2: Reset a working copy of the PHP manifest to `pending`**

The committed/real PHP manifest may already be advanced. Make a fresh manifest for this run so all units are pending:

Run:
```bash
uv run python -c "
from content_bank.author import manifest
from content_bank.lib import corpus_bridge
from corpus.lib import sections
import pathlib
pids=[p['id'] for p in corpus_bridge.pericopes('PHP')]
sids=[s['id'] for s in sections.load('PHP')['sections']]
m=manifest.init_manifest('PHP', pids, sids)
manifest.save(pathlib.Path('work/content_bank_build/PHP/manifest_py.json'), m)
print('pericopes',len(pids),'sections',len(sids))
"
```
Expected: prints the counts; writes `manifest_py.json`.

- [ ] **Step 3: Build all PHP units with review on**

Run:
```bash
uv run python -m content_bank.author.build_cli --book PHP --review \
  --manifest work/content_bank_build/PHP/manifest_py.json \
  --drafts-dir work/content_bank_build/PHP/drafts_py
```
Expected: `[ok] PHP-001 …` lines; final `Done. ok=N failed=M`. Some units may fail (rate limits / gate exhaustion) — that is expected per-unit isolation, not a crash. Re-run the same command to retry stragglers (only `pending`/`briefed` units are picked up).

- [ ] **Step 4: Sanity-check the output**

Run:
```bash
uv run python -c "
import json,glob
n=0
for f in sorted(glob.glob('work/content_bank_build/PHP/drafts_py/*.json')):
    items=json.load(open(f)); n+=len(items)
    print(f.split('/')[-1], len(items))
print('total items', n)
"
```
Expected: one line per built unit + a total. Confirms the builder produced gated drafts.

- [ ] **Step 5: (No commit — untracked build artifacts.)**

`work/` is git-ignored; nothing to commit. Note the `ok`/`failed` tallies for Task 10.

---

### Task 10: Quality comparison — Python build vs Claude-Code build

**Files:**
- Create: `docs/sessions/2026-07-20-php-python-vs-claude-comparison.md`

- [ ] **Step 1: Gather comparable metrics for both builds**

Run:
```bash
uv run python work/content_bank_build/_compare_php.py 2>/dev/null || uv run python -c "
import json, glob, collections
def summ(dirpath):
    per=collections.Counter(); types=collections.Counter(); items=0; units=0
    for f in sorted(glob.glob(dirpath+'/*.json')):
        units+=1
        for it in json.load(open(f)):
            items+=1; per[it.get('dimension')] += 1; types[it['type']] += 1
    return dict(units=units, items=items, per_dim=dict(per), per_type=dict(types))
claude=summ('work/content_bank_build/PHP/drafts')
py=summ('work/content_bank_build/PHP/drafts_py')
print('CLAUDE', json.dumps(claude, indent=2))
print('PYTHON', json.dumps(py, indent=2))
"
```
Expected: two summaries (unit count, item count, per-dimension and per-type spread).

- [ ] **Step 2: Run the committed gates over BOTH builds for an apples-to-apples defect count**

Run:
```bash
uv run python -c "
import json, glob
from content_bank.author import gates
from content_bank.lib import corpus_bridge
peri={p['id']:p for p in corpus_bridge.pericopes('PHP')}
def defects(dirpath):
    total=0
    for f in sorted(glob.glob(dirpath+'/*.json')):
        uid=f.split('/')[-1][:-5]
        items=json.load(open(f))
        allowed=(gates.pericope_allowed('PHP',uid) if uid in peri
                 else gates.section_allowed('PHP',uid))
        total+=sum(len(v) for v in gates.run_all('PHP',items,allowed).values())
    return total
print('claude defects', defects('work/content_bank_build/PHP/drafts'))
print('python defects', defects('work/content_bank_build/PHP/drafts_py'))
"
```
Expected: two defect counts. (The Python build should be ~0 by construction — it only writes gate-clean drafts. The point is whether the Claude build has residual defects the new `refs_in_range` gate now catches.)

- [ ] **Step 3: Qualitative side-by-side on 2-3 shared units**

For 2-3 units present in both dirs (e.g. `PHP-001`, `PHP-002`, `PHP-S1`), read both versions and judge against `rubric.py`'s seven axes: accuracy, answerability, evidence-not-judgment, age fitness, dimension fit, pedagogy, WCF-1 conformity. Note concrete differences (coverage, leader-reference quality, scope discipline, cost/latency).

Run (to eyeball a pair):
```bash
uv run python -c "
import json
for d in ('drafts','drafts_py'):
    print('===',d,'===')
    print(json.dumps(json.load(open(f'work/content_bank_build/PHP/{d}/PHP-001.json')), indent=2, ensure_ascii=False)[:2000])
"
```

- [ ] **Step 4: Write the comparison report**

Create `docs/sessions/2026-07-20-php-python-vs-claude-comparison.md` with: the quantitative table (units/items/dimension spread/defect counts from Steps 1–2), the qualitative findings (Step 3), token/time cost if observable, and a recommendation (is the standalone builder good enough to replace the workflow for draft libraries?). Tie back to issue #16's "net" claim.

- [ ] **Step 5: Tick the final acceptance box and commit**

Edit the spec to tick the PHP-build/comparison acceptance box, then:
```bash
git add docs/sessions/2026-07-20-php-python-vs-claude-comparison.md docs/superpowers/specs/2026-07-20-standalone-content-bank-builder-design.md
git commit -m "docs(#16): PHP python-vs-claude quality comparison

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review notes

- **Spec coverage:** gates (Tasks 1–2), section self-containment (3), builder helpers (4), orchestrator + isolation + CLI (5), adversarial review (6), --review wiring (7), acceptance/suite (8), PHP build (9), comparison (10). All spec sections mapped.
- **Type consistency:** `run_all(book, items, allowed)`, `_draft_with_repair(prompt, book, allowed, *, max_repair)`, `review(items, *, passage_text, brief, book, unit_id)`, `revise(items, verdicts, *, passage_text, brief)` used consistently across tasks 4–7. `pericope_allowed`/`section_allowed` return `list[tuple]` consumed by `refs_in_range`/`run_all`.
- **Placeholder scan:** every code step shows complete code; commands have expected output. Task 9/10 are execution/analysis tasks (real LLM calls) with concrete commands.
- **Known risk to watch during execution:** Task 7's `seq` counting depends on gates staying clean (no repair `_llm_with_backoff` call). If MAT-035 fixture items ever trip a gate, adjust the fixture, not the sequence.
```