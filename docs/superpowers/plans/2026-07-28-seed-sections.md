# seed_sections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an LLM-proposed, validator-guaranteed section-map seeder so any book with pericopes can get a review-ready book-arc partition without hand-authoring.

**Architecture:** One new module `content_bank/author/seed_sections.py` with pure, separately-tested pieces (gather inputs → build prompt → parse/normalize proposal → verify markers → write staging + report) wired by an orchestrator `seed()` and an argparse `main()`. It reuses the existing `content_bank/author/llm.py:llm()` seam, `content_bank/lib/corpus_bridge.py`, `corpus/lib/refs.py`, and — as the deterministic gate — `corpus/lib/sections.py:validate_data`. Output is staged, never written to canon by default.

**Tech Stack:** Python (uv/.venv), stdlib + existing project modules only. Tests via `unittest`, LLM seam mocked (network-free).

## Global Constraints

- **Design pattern is propose → validate → confirm.** The LLM proposes; `sections.validate_data` (existing, unchanged) is the hard gate; markers are machine-verified against the corpus; a human confirms. Never emit an invalid partition.
- **Corpus rebuild determinism is untouched.** This tool is NOT added to any corpus rebuild chain. It lives in `content_bank/author/`, and its output is a committed source, treated like a hand-authored map.
- **Default output is staging:** `work/section_seeds/<book>.json` (lowercase book code). The tool writes `corpus/canon/structure/sections/` ONLY if `--out` is explicitly aimed there.
- **Section ids are assigned deterministically** as `<BOOK>-S<n>` (1-based, array order) — the model never supplies ids.
- **Output section objects** carry exactly: `id`, `title_en`, `title_zh` (always `""`), `first_pericope`, `last_pericope`, `marker` (canonical `BOOK.CH.V` string or `null`), `status` (always `"seeded"`). `rationale` is NEVER stored in the JSON — it goes to stdout / the optional sidecar only.
- **Title convention:** `title_en` uses the dual `"Label: Description"` form (e.g. `"Book One: The Sermon on the Mount"`), matching the existing MAT/PHP/ECC maps.
- **Grounding is JFB-first, MHC-fallback**, each snippet truncated to ~200 chars.
- **CLI defaults:** `--backend claude`, `--model opus` (whole-book arc reasoning), `--max-repair 2`.
- Run everything under `uv`. Tests must not hit the network — patch `seed_sections.llm`.

---

## Verified interfaces (already exist — consume, don't recreate)

- `content_bank/lib/corpus_bridge.py`:
  - `pericopes(book) -> list[dict]` — ordered; each `{"id","range","title_en","title_zh","status"}`.
  - `book_name(book, lang="en") -> str`.
  - `commentary(range_str, book="MAT", works=("mhc","jfb")) -> {work: [ {"range","text"}, ... ]}` — blocks overlapping the range. Cross-chapter ranges silently yield `[]` (helper limitation; acceptable — grounding is best-effort).
- `corpus/lib/refs.py`:
  - `parse(ref) -> (book,ch,v)`; raises `ValueError` on malformed/unknown-book.
  - `parse_range(r) -> ((book,ch,v),(book,ch,v))` — handles `PHP.1.1-11` and `MAT.5.1-MAT.6.4`.
  - `in_range(ref_tuple, range_tuple) -> bool`.
- `corpus/lib/sections.py`:
  - `validate_data(data, order) -> list[str]` — `data` is `{"sections":[...]}`, `order` is the ordered pericope-id list. `[]` means valid. Requires each section have `id,title_en,first_pericope,last_pericope`; enforces contiguity, full coverage, marker format. Ignores unknown keys (so `title_zh`/`status` are fine).
- `content_bank/author/llm.py`:
  - `llm(prompt: str, model: str|None = None) -> str` — backend from `SCRIPTURE_LOOM_LLM_BACKEND` env, model arg or `SCRIPTURE_LOOM_LLM_MODEL`. Raises `RuntimeError` on failure.
- `llm_core.llm_configured() -> bool` — credential present for the llm_core backend.

---

## Task 1: Input gathering + commentary grounding

**Files:**
- Create: `content_bank/author/seed_sections.py`
- Test: `content_bank/tests/test_seed_sections.py`

**Interfaces:**
- Produces:
  - `commentary_snippet(range_str, book, max_chars=200) -> (work: str|None, text: str)` — JFB-first, MHC-fallback; `(None, "")` if neither overlaps.
  - `gather_inputs(book) -> dict` — `{"book": book, "book_name": str, "pericopes": [ {"id","range","title_en","grounding_work","grounding_text"}, ... ]}` in pericope order.
- Consumes: `corpus_bridge.pericopes`, `corpus_bridge.book_name`, `corpus_bridge.commentary`.

- [ ] **Step 1: Write the failing test**

```python
import unittest
from content_bank.author import seed_sections as ss


class TestGatherInputs(unittest.TestCase):
    def test_snippet_prefers_jfb_and_truncates(self):
        work, text = ss.commentary_snippet("PHP.1.1-11", "PHP", max_chars=80)
        self.assertIn(work, ("jfb", "mhc"))       # PHP has commentary coverage
        self.assertTrue(text)                      # non-empty grounding
        self.assertLessEqual(len(text), 80)        # truncated
        self.assertNotIn("\n", text)               # newlines flattened

    def test_snippet_missing_returns_none(self):
        # A syntactically valid but uncovered range yields no grounding, no raise.
        work, text = ss.commentary_snippet("PHP.99.1-2", "PHP")
        self.assertIsNone(work)
        self.assertEqual(text, "")

    def test_gather_inputs_php_shape(self):
        data = ss.gather_inputs("PHP")
        self.assertEqual(data["book"], "PHP")
        self.assertEqual(data["book_name"], "Philippians")
        ps = data["pericopes"]
        self.assertEqual(ps[0]["id"], "PHP-001")
        self.assertEqual(ps[0]["range"], "PHP.1.1-11")
        self.assertIn("title_en", ps[0])
        self.assertIn("grounding_work", ps[0])
        self.assertIn("grounding_text", ps[0])
        # order preserved and complete
        self.assertEqual([p["id"] for p in ps],
                         [p["id"] for p in __import__(
                             "content_bank.lib.corpus_bridge",
                             fromlist=["pericopes"]).pericopes("PHP")])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_seed_sections.TestGatherInputs -v`
Expected: FAIL (`module 'seed_sections' has no attribute 'commentary_snippet'` / ImportError).

- [ ] **Step 3: Write minimal implementation**

```python
"""Seed a book's section map with an LLM, guaranteed by the partition validator.

Sibling of corpus/ingest/seed_pericopes.py, but LLM-based: it PROPOSES a
contiguous named partition of a book's pericopes, the existing
corpus/lib/sections.py validator GUARANTEES it, proposed markers are verified
against the corpus, and the result is STAGED for human confirmation. Not part of
the corpus deterministic rebuild — its committed output is treated as a source.
"""
import argparse
import json
import os
import pathlib
import shutil
import sys

from content_bank.lib import corpus_bridge

_GROUNDING_WORKS = ("jfb", "mhc")   # JFB first (terser), Matthew Henry fallback


def commentary_snippet(range_str, book, max_chars=200):
    """First overlapping commentary block, JFB-preferred, flattened + truncated."""
    blocks_by_work = corpus_bridge.commentary(range_str, book,
                                               works=_GROUNDING_WORKS)
    for work in _GROUNDING_WORKS:
        blocks = blocks_by_work.get(work) or []
        if blocks:
            text = " ".join(blocks[0]["text"].split())
            return work, text[:max_chars]
    return None, ""


def gather_inputs(book):
    peris = []
    for p in corpus_bridge.pericopes(book):
        work, text = commentary_snippet(p["range"], book)
        peris.append({"id": p["id"], "range": p["range"],
                      "title_en": p.get("title_en", ""),
                      "grounding_work": work, "grounding_text": text})
    return {"book": book, "book_name": corpus_bridge.book_name(book),
            "pericopes": peris}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_seed_sections.TestGatherInputs -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/seed_sections.py content_bank/tests/test_seed_sections.py
git commit -m "feat(seed_sections): input gathering + JFB-first commentary grounding"
```

---

## Task 2: Prompt builder

**Files:**
- Modify: `content_bank/author/seed_sections.py`
- Test: `content_bank/tests/test_seed_sections.py`

**Interfaces:**
- Produces: `build_prompt(inputs: dict) -> str`; `build_repair_prompt(base_prompt: str, proposal: dict, errors: list[str]) -> str`.
- Consumes: the `gather_inputs` dict shape from Task 1.

- [ ] **Step 1: Write the failing test**

```python
class TestBuildPrompt(unittest.TestCase):
    def _inputs(self):
        return {"book": "PHP", "book_name": "Philippians", "pericopes": [
            {"id": "PHP-001", "range": "PHP.1.1-11", "title_en": "Greeting",
             "grounding_work": "jfb", "grounding_text": "the inscription..."},
            {"id": "PHP-002", "range": "PHP.1.12-26", "title_en": "Imprisonment",
             "grounding_work": "jfb", "grounding_text": "his bonds..."},
        ]}

    def test_prompt_has_spine_rules_and_json(self):
        p = ss.build_prompt(self._inputs())
        self.assertIn("Philippians", p)
        self.assertIn("PHP-001", p)
        self.assertIn("PHP-002", p)
        self.assertIn("the inscription...", p)          # grounding included
        self.assertIn("Label: Description", p)           # dual-title convention
        self.assertIn("marker", p.lower())               # marker rule present
        self.assertIn("null", p)                         # marker may be null
        self.assertIn("JSON", p)                         # strict-JSON instruction
        self.assertNotIn('"id"', p)                      # model must NOT supply ids

    def test_repair_prompt_carries_errors(self):
        base = ss.build_prompt(self._inputs())
        proposal = {"sections": [{"title_en": "X", "first_pericope": "PHP-001",
                                  "last_pericope": "PHP-001", "marker": None}]}
        rp = ss.build_repair_prompt(base, proposal, ["S?: gap/overlap ..."])
        self.assertIn("gap/overlap", rp)
        self.assertIn("PHP-001", rp)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_seed_sections.TestBuildPrompt -v`
Expected: FAIL (no `build_prompt`).

- [ ] **Step 3: Write minimal implementation**

```python
_RANGE_HINT = "roughly 3-12, more for long narrative books"


def build_prompt(inputs):
    lines = [
        f"You are partitioning the book of {inputs['book_name']} "
        f"({inputs['book']}) into its major movements (\"sections\").",
        "",
        "You are given the book's pericopes IN ORDER, each with a short title "
        "and a snippet of public-domain commentary (Jamieson-Fausset-Brown or "
        "Matthew Henry) for grounding. Group these pericopes into contiguous "
        f"named movements ({_RANGE_HINT}). Rules:",
        "- Every pericope belongs to exactly ONE section; sections are "
        "contiguous and in order (no gaps, no overlaps, full coverage).",
        "- title_en uses the form \"Label: Description\" "
        "(e.g. \"Book One: The Sermon on the Mount\").",
        "- marker: a canonical verse ref BOOK.CH.V ONLY where a clear repeating "
        "textual formula hinges the movement (e.g. Matthew's \"when Jesus had "
        "finished\"); otherwise null. Do not invent markers.",
        "- rationale: ONE line, grounded in the commentary, for the boundary.",
        "- Do NOT include an \"id\" field; ids are assigned downstream.",
        "",
        "Pericopes:",
    ]
    for p in inputs["pericopes"]:
        g = f"  [{p['grounding_work']}] {p['grounding_text']}" if p["grounding_text"] else ""
        lines.append(f"- {p['id']} ({p['range']}): {p['title_en']}{g}")
    lines += [
        "",
        "Respond with STRICT JSON only, no prose, no code fence:",
        '{"sections": [{"title_en": "...", "first_pericope": "<id>", '
        '"last_pericope": "<id>", "marker": null, "rationale": "..."}]}',
    ]
    return "\n".join(lines)


def build_repair_prompt(base_prompt, proposal, errors):
    return (base_prompt + "\n\nYour previous answer was:\n"
            + json.dumps(proposal, ensure_ascii=False)
            + "\n\nIt FAILED validation:\n- " + "\n- ".join(errors)
            + "\n\nReturn corrected STRICT JSON only.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_seed_sections.TestBuildPrompt -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/seed_sections.py content_bank/tests/test_seed_sections.py
git commit -m "feat(seed_sections): prompt + repair-prompt builders"
```

---

## Task 3: Proposal parsing + id assignment

**Files:**
- Modify: `content_bank/author/seed_sections.py`
- Test: `content_bank/tests/test_seed_sections.py`

**Interfaces:**
- Produces:
  - `parse_proposal(text: str) -> dict` — returns `{"sections":[...]}`; raises `ValueError` if no JSON object with a `sections` list is found. Tolerates ```` ```json ```` fences and surrounding prose.
  - `assign_section_ids(proposal: dict, book: str) -> dict` — sets each section's `id` to `<BOOK>-S<n>` (1-based, array order); returns the same dict.

- [ ] **Step 1: Write the failing test**

```python
class TestParseAndAssign(unittest.TestCase):
    def test_parse_bare_json(self):
        d = ss.parse_proposal('{"sections": [{"title_en": "A"}]}')
        self.assertEqual(len(d["sections"]), 1)

    def test_parse_fenced_json_with_prose(self):
        raw = 'Here you go:\n```json\n{"sections": [{"title_en": "A"}]}\n```\n'
        d = ss.parse_proposal(raw)
        self.assertEqual(d["sections"][0]["title_en"], "A")

    def test_parse_garbage_raises(self):
        with self.assertRaises(ValueError):
            ss.parse_proposal("no json here")

    def test_assign_ids_sequential(self):
        d = {"sections": [{"title_en": "A"}, {"title_en": "B"}]}
        ss.assign_section_ids(d, "PHP")
        self.assertEqual([s["id"] for s in d["sections"]],
                         ["PHP-S1", "PHP-S2"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_seed_sections.TestParseAndAssign -v`
Expected: FAIL (no `parse_proposal`).

- [ ] **Step 3: Write minimal implementation**

```python
def parse_proposal(text):
    s = text.strip()
    if "```" in s:                                  # strip a code fence if present
        parts = s.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                s = part
                break
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object in completion")
    obj = json.loads(s[start:end + 1])
    if not isinstance(obj, dict) or not isinstance(obj.get("sections"), list):
        raise ValueError("JSON has no 'sections' list")
    return obj


def assign_section_ids(proposal, book):
    for i, sec in enumerate(proposal["sections"], start=1):
        sec["id"] = f"{book}-S{i}"
    return proposal
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_seed_sections.TestParseAndAssign -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/seed_sections.py content_bank/tests/test_seed_sections.py
git commit -m "feat(seed_sections): tolerant JSON parse + deterministic id assignment"
```

---

## Task 4: Marker verification

**Files:**
- Modify: `content_bank/author/seed_sections.py`
- Test: `content_bank/tests/test_seed_sections.py`

**Interfaces:**
- Produces: `verify_markers(sections: list[dict], pericope_range_by_id: dict[str,str]) -> (list[dict], list[dict])` — returns `(sections, dropped)`. For each section with a non-null `marker`: keep it only if it `refs.parse`s AND falls within the section's span (first_pericope range start → last_pericope range end via `refs.in_range`); otherwise set `marker=None` and append `{"id","marker","reason"}` to `dropped`. Mutates section dicts in place; also returns them.
- Consumes: `corpus/lib/refs.py`.

- [ ] **Step 1: Write the failing test**

```python
class TestVerifyMarkers(unittest.TestCase):
    def _by_id(self):
        return {"PHP-001": "PHP.1.1-11", "PHP-002": "PHP.1.12-26"}

    def test_keeps_in_span_marker(self):
        secs = [{"id": "PHP-S1", "first_pericope": "PHP-001",
                 "last_pericope": "PHP-002", "marker": "PHP.1.6"}]
        _, dropped = ss.verify_markers(secs, self._by_id())
        self.assertEqual(secs[0]["marker"], "PHP.1.6")
        self.assertEqual(dropped, [])

    def test_drops_out_of_span_marker(self):
        secs = [{"id": "PHP-S1", "first_pericope": "PHP-001",
                 "last_pericope": "PHP-001", "marker": "PHP.4.1"}]
        _, dropped = ss.verify_markers(secs, self._by_id())
        self.assertIsNone(secs[0]["marker"])
        self.assertEqual(dropped[0]["id"], "PHP-S1")

    def test_drops_unparseable_marker(self):
        secs = [{"id": "PHP-S1", "first_pericope": "PHP-001",
                 "last_pericope": "PHP-001", "marker": "ZZZ.1.1"}]
        _, dropped = ss.verify_markers(secs, self._by_id())
        self.assertIsNone(secs[0]["marker"])
        self.assertEqual(len(dropped), 1)

    def test_null_marker_untouched(self):
        secs = [{"id": "PHP-S1", "first_pericope": "PHP-001",
                 "last_pericope": "PHP-001", "marker": None}]
        _, dropped = ss.verify_markers(secs, self._by_id())
        self.assertEqual(dropped, [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_seed_sections.TestVerifyMarkers -v`
Expected: FAIL (no `verify_markers`).

- [ ] **Step 3: Write minimal implementation**

Add the corpus lib to `sys.path` once (module import time) so `refs` resolves, matching how `corpus_bridge` reaches `corpus/lib`:

```python
_CORPUS_LIB = str(pathlib.Path(corpus_bridge.__file__).resolve().parents[2] / "corpus")
if _CORPUS_LIB not in sys.path:
    sys.path.insert(0, _CORPUS_LIB)
from lib import refs  # corpus/lib/refs.py  # noqa: E402


def verify_markers(sections, pericope_range_by_id):
    dropped = []
    for sec in sections:
        mk = sec.get("marker")
        if not mk:
            continue
        reason = None
        try:
            ref = refs.parse(mk)
            span = (refs.parse_range(pericope_range_by_id[sec["first_pericope"]])[0],
                    refs.parse_range(pericope_range_by_id[sec["last_pericope"]])[1])
            if not refs.in_range(ref, span):
                reason = "marker outside section span"
        except (ValueError, KeyError) as e:
            reason = f"marker unresolvable ({e})"
        if reason:
            dropped.append({"id": sec["id"], "marker": mk, "reason": reason})
            sec["marker"] = None
    return sections, dropped
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_seed_sections.TestVerifyMarkers -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/seed_sections.py content_bank/tests/test_seed_sections.py
git commit -m "feat(seed_sections): machine-verify proposed markers (drop invalid)"
```

---

## Task 5: Output writer + human report

**Files:**
- Modify: `content_bank/author/seed_sections.py`
- Test: `content_bank/tests/test_seed_sections.py`

**Interfaces:**
- Produces:
  - `to_output(sections: list[dict], book: str) -> dict` — the canon-shaped map `{"book": book, "sections":[ {id,title_en,title_zh:"",first_pericope,last_pericope,marker,status:"seeded"} ]}`; `rationale` stripped.
  - `write_output(sections, book, out_path) -> pathlib.Path` — writes the JSON (mkdir parents, `indent=1`, `ensure_ascii=False`, trailing newline).
  - `render_report(book, sections, dropped) -> str` — human table + per-section rationale + dropped-marker notes.
- Consumes: Task 1–4 shapes; `corpus/lib/sections.py:validate_data` (test only, to prove the written map validates).

- [ ] **Step 1: Write the failing test**

```python
import json as _json
import pathlib as _pl
import tempfile


class TestOutputAndReport(unittest.TestCase):
    def _secs(self):
        return [
            {"id": "PHP-S1", "title_en": "Opening: Greeting",
             "first_pericope": "PHP-001", "last_pericope": "PHP-001",
             "marker": None, "rationale": "sets the frame"},
            {"id": "PHP-S2", "title_en": "Body: The Gospel Life",
             "first_pericope": "PHP-002", "last_pericope": "PHP-002",
             "marker": "PHP.1.12", "rationale": "turns to his circumstances"},
        ]

    def test_to_output_shape(self):
        out = ss.to_output(self._secs(), "PHP")
        s0 = out["sections"][0]
        self.assertEqual(s0["title_zh"], "")
        self.assertEqual(s0["status"], "seeded")
        self.assertNotIn("rationale", s0)          # rationale never stored
        self.assertEqual(set(s0), {"id", "title_en", "title_zh",
                                   "first_pericope", "last_pericope",
                                   "marker", "status"})

    def test_written_map_validates(self):
        # Build a 2-section partition over the real first two PHP pericopes...
        # (PHP-001, PHP-002) and prove it passes the existing validator.
        from corpus.lib import sections as csecs
        from content_bank.lib import corpus_bridge as cb
        order = [p["id"] for p in cb.pericopes("PHP")]
        secs = [
            {"id": "PHP-S1", "title_en": "A", "first_pericope": order[0],
             "last_pericope": order[0], "marker": None, "rationale": "x"},
            {"id": "PHP-S2", "title_en": "B", "first_pericope": order[1],
             "last_pericope": order[-1], "marker": None, "rationale": "y"},
        ]
        out = ss.to_output(secs, "PHP")
        self.assertEqual(csecs.validate_data(out, order), [])

    def test_write_output_roundtrip(self):
        d = _pl.Path(tempfile.mkdtemp()) / "sub" / "php.json"
        ss.write_output(self._secs(), "PHP", d)
        written = _json.loads(d.read_text(encoding="utf-8"))
        self.assertEqual(written["book"], "PHP")
        self.assertNotIn("rationale", written["sections"][0])

    def test_report_has_rationale_and_dropped(self):
        rpt = ss.render_report("PHP", self._secs(),
                               [{"id": "PHP-S9", "marker": "PHP.9.9",
                                 "reason": "marker outside section span"}])
        self.assertIn("PHP-S1", rpt)
        self.assertIn("sets the frame", rpt)          # rationale surfaced
        self.assertIn("PHP.1.12", rpt)                # kept marker shown
        self.assertIn("outside section span", rpt)    # dropped note surfaced
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_seed_sections.TestOutputAndReport -v`
Expected: FAIL (no `to_output`).

- [ ] **Step 3: Write minimal implementation**

```python
def to_output(sections, book):
    # Canonical field order: id, title_en, title_zh, first, last, marker, status.
    # rationale is intentionally dropped; title_zh/status are added.
    out = [{"id": s["id"], "title_en": s["title_en"], "title_zh": "",
            "first_pericope": s["first_pericope"],
            "last_pericope": s["last_pericope"],
            "marker": s.get("marker"), "status": "seeded"} for s in sections]
    return {"book": book, "sections": out}


def write_output(sections, book, out_path):
    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(to_output(sections, book), ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    return out_path


def render_report(book, sections, dropped):
    lines = [f"{book}: {len(sections)} sections (status: seeded)"]
    for s in sections:
        mk = s.get("marker") or "-"
        lines.append(f"  {s['id']}  {s['first_pericope']}..{s['last_pericope']}"
                     f"  [{mk}]  {s['title_en']}")
        if s.get("rationale"):
            lines.append(f"      → {s['rationale']}")
    if dropped:
        lines.append("  dropped markers:")
        for d in dropped:
            lines.append(f"    {d['id']}: {d['marker']} ({d['reason']})")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_seed_sections.TestOutputAndReport -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/seed_sections.py content_bank/tests/test_seed_sections.py
git commit -m "feat(seed_sections): staging writer + human review report"
```

---

## Task 6: Orchestrator `seed()` + CLI `main()`

**Files:**
- Modify: `content_bank/author/seed_sections.py`
- Test: `content_bank/tests/test_seed_sections.py`

**Interfaces:**
- Produces:
  - `DEFAULT_OUT(book) -> pathlib.Path` = `work/section_seeds/<book>.json`.
  - `seed(book, *, backend="claude", model=None, max_repair=2, out=None, rationale_file=None, force=False) -> dict` — orchestrates gather → prompt → llm (repair loop, ≤ `max_repair` extra rounds) → parse+assign_ids → `sections.validate_data` gate → `verify_markers` → `write_output`. Raises `RuntimeError` with the final validation errors if still invalid after the budget (writes nothing). Raises `FileExistsError` if `out` exists and not `force`. Returns `{"out": Path, "sections": [...], "dropped": [...], "report": str}`.
  - `main(argv=None) -> int` — argparse; prints the report; returns/exits non-zero on failure.
- Consumes: `content_bank.author.llm.llm` (imported as module attr `llm` so tests can patch `seed_sections.llm`), `corpus/lib/sections.py:validate_data`, `llm_core.llm_configured`, `shutil.which`.

- [ ] **Step 1: Write the failing test**

```python
from unittest import mock


def _valid_completion_php(order):
    # One section per pericope? No — make 2 contiguous sections covering all.
    secs = [{"title_en": "Opening: A", "first_pericope": order[0],
             "last_pericope": order[0], "marker": None, "rationale": "r1"},
            {"title_en": "Body: B", "first_pericope": order[1],
             "last_pericope": order[-1], "marker": None, "rationale": "r2"}]
    return json.dumps({"sections": secs})


class TestSeedOrchestrator(unittest.TestCase):
    def setUp(self):
        from content_bank.lib import corpus_bridge as cb
        self.order = [p["id"] for p in cb.pericopes("PHP")]
        # Credential/PATH guard is orthogonal to orchestration — neutralize it so
        # these tests never depend on ARK_API_KEY or a `claude` binary.
        g = mock.patch.object(ss, "_require_backend")
        g.start()
        self.addCleanup(g.stop)

    def test_happy_path_writes_staging(self):
        out = _pl.Path(tempfile.mkdtemp()) / "php.json"
        with mock.patch.object(ss, "llm",
                               return_value=_valid_completion_php(self.order)):
            res = ss.seed("PHP", backend="llm_core", out=out)
        self.assertTrue(out.exists())
        from corpus.lib import sections as csecs
        written = _json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(csecs.validate_data(written, self.order), [])
        self.assertEqual(written["sections"][0]["id"], "PHP-S1")

    def test_invalid_after_budget_writes_nothing(self):
        bad = json.dumps({"sections": [{"title_en": "only one",
                          "first_pericope": self.order[0],
                          "last_pericope": self.order[0], "marker": None}]})
        out = _pl.Path(tempfile.mkdtemp()) / "php.json"
        with mock.patch.object(ss, "llm", return_value=bad):
            with self.assertRaises(RuntimeError):
                ss.seed("PHP", backend="llm_core", max_repair=1, out=out)
        self.assertFalse(out.exists())          # nothing emitted

    def test_refuses_overwrite_without_force(self):
        out = _pl.Path(tempfile.mkdtemp()) / "php.json"
        out.write_text("{}", encoding="utf-8")
        with mock.patch.object(ss, "llm",
                               return_value=_valid_completion_php(self.order)):
            with self.assertRaises(FileExistsError):
                ss.seed("PHP", backend="llm_core", out=out)

    def test_default_out_is_staging(self):
        self.assertEqual(str(ss.DEFAULT_OUT("PHP")).replace("\\", "/")
                         .endswith("work/section_seeds/php.json"), True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_seed_sections.TestSeedOrchestrator -v`
Expected: FAIL (no `seed`/`DEFAULT_OUT`).

- [ ] **Step 3: Write minimal implementation**

```python
from content_bank.author.llm import llm  # patched as seed_sections.llm in tests
from corpus.lib import sections as _sections  # validator (corpus lib on sys.path)

_REPO = pathlib.Path(corpus_bridge.__file__).resolve().parents[2]


def DEFAULT_OUT(book):
    return _REPO / "work" / "section_seeds" / f"{book.lower()}.json"


def _require_backend(backend):
    if backend == "claude":
        if not shutil.which("claude"):
            raise RuntimeError("backend=claude but the 'claude' CLI is not on "
                               "PATH; install Claude Code or use --backend llm_core")
    else:
        from llm_core import llm_configured
        if not llm_configured():
            raise RuntimeError("no LLM credential configured (ARK_API_KEY); see "
                               ".env.example")


def seed(book, *, backend="claude", model=None, max_repair=2,
         out=None, rationale_file=None, force=False):
    _require_backend(backend)
    os.environ["SCRIPTURE_LOOM_LLM_BACKEND"] = backend
    if model:
        os.environ["SCRIPTURE_LOOM_LLM_MODEL"] = model
    else:
        os.environ.pop("SCRIPTURE_LOOM_LLM_MODEL", None)

    out = pathlib.Path(out) if out else DEFAULT_OUT(book)
    if out.exists() and not force:
        raise FileExistsError(f"{out} exists; pass force=True/--force to overwrite")

    inputs = gather_inputs(book)
    order = [p["id"] for p in inputs["pericopes"]]
    range_by_id = {p["id"]: p["range"] for p in inputs["pericopes"]}
    prompt = build_prompt(inputs)

    errors, proposal = ["(no attempt)"], None
    for _ in range(max_repair + 1):
        text = llm(prompt, model)
        proposal = parse_proposal(text)
        assign_section_ids(proposal, book)
        errors = _sections.validate_data(proposal, order)
        if not errors:
            break
        prompt = build_repair_prompt(build_prompt(inputs), proposal, errors)
    if errors:
        raise RuntimeError("section partition still invalid after "
                           f"{max_repair} repair(s): {errors}")

    sections, dropped = verify_markers(proposal["sections"], range_by_id)
    write_output(sections, book, out)
    report = render_report(book, sections, dropped)
    if rationale_file:
        pathlib.Path(rationale_file).write_text(report + "\n", encoding="utf-8")
    return {"out": out, "sections": sections, "dropped": dropped, "report": report}


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Seed a book's section map (LLM-proposed, validator-guaranteed).")
    ap.add_argument("--book", required=True)
    ap.add_argument("--backend", choices=("claude", "llm_core"), default="claude")
    ap.add_argument("--model", help="override model (default: opus for claude, "
                    "deepseek-v4-flash for llm_core)")
    ap.add_argument("--max-repair", type=int, default=2)
    ap.add_argument("--out", help="output path (default: work/section_seeds/<book>.json)")
    ap.add_argument("--rationale-file", help="also write the report here")
    ap.add_argument("--force", action="store_true", help="overwrite existing --out")
    a = ap.parse_args(argv)
    try:
        res = seed(a.book, backend=a.backend, model=a.model,
                   max_repair=a.max_repair, out=a.out,
                   rationale_file=a.rationale_file, force=a.force)
    except (RuntimeError, FileExistsError) as e:
        print(f"[FAIL] {a.book}: {e}", file=sys.stderr)
        return 1
    print(res["report"])
    print(f"\nStaged → {res['out']}  (review, then copy to "
          f"corpus/canon/structure/sections/{a.book.lower()}.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Note: the `test_default_out_is_staging` assertion should read
`self.assertTrue(str(ss.DEFAULT_OUT("PHP")).replace("\\", "/").endswith("work/section_seeds/php.json"))`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_seed_sections.TestSeedOrchestrator -v`
Expected: PASS.

- [ ] **Step 5: Run the whole new test module + the existing suite**

Run: `uv run python -m unittest content_bank.tests.test_seed_sections -v`
Run: `uv run python -m unittest discover -s content_bank/tests` and `uv run python -m unittest discover -s corpus/tests`
Expected: all PASS (no regressions).

- [ ] **Step 6: Commit**

```bash
git add content_bank/author/seed_sections.py content_bank/tests/test_seed_sections.py
git commit -m "feat(seed_sections): orchestrator + CLI (staging, repair loop, guards)"
```

---

## Task 7: Documentation

**Files:**
- Create: `docs/content_section_seeder_usage.md`
- Modify: `docs/content_build_terminology.md` (add a "section seeder" glossary line), `CLAUDE.md` (one line under `content_bank/` mentioning the seeder), `corpus/ingest/seed_pericopes.py` (a one-line module-docstring pointer to its LLM-based sibling — optional, no code change to logic).

**Interfaces:** none (docs only).

- [ ] **Step 1: Write `docs/content_section_seeder_usage.md`**

Cover: what it does (propose→validate→confirm), the exact command
(`uv run python -m content_bank.author.seed_sections --book JON`), all flags,
the JFB-first grounding, that markers are verified/dropped, that output is
**staged** to `work/section_seeds/<book>.json` and must be human-reviewed and
copied into `corpus/canon/structure/sections/<book>.json`, and that it is NOT
part of the corpus deterministic rebuild. Mirror the tone of
`docs/content_builder_usage.md`.

- [ ] **Step 2: Add glossary + CLAUDE.md lines**

One line in `docs/content_build_terminology.md` defining the section seeder, and
one line in `CLAUDE.md`'s `content_bank/` bullet pointing at the new usage doc.

- [ ] **Step 3: Commit**

```bash
git add docs/content_section_seeder_usage.md docs/content_build_terminology.md CLAUDE.md corpus/ingest/seed_pericopes.py
git commit -m "docs(seed_sections): usage guide + glossary + pointers"
```

---

## Self-review notes

- **Spec coverage:** grounding (T1), prompt (T2), parse/normalize (T3), marker
  verify (T4), staging output + report (T5), orchestrator/CLI with repair loop +
  guards (T6), docs (T7). All spec sections map to a task.
- **Determinism:** the validator (`corpus/lib/sections.py`, unchanged) is the
  gate; the tool is never added to the rebuild chain; output is staged.
- **Type consistency:** `sections` list of dicts flows unchanged T3→T4→T5;
  `range_by_id`/`order` derived once in T6 from the T1 shape; `to_output` strips
  `rationale` and adds `title_zh`/`status`; `verify_markers` mutates in place and
  returns. `llm` is imported as a module attribute so tests patch
  `seed_sections.llm`.
- **No placeholders:** every code and test step is complete and runnable.
