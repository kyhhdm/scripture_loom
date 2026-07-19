# Content-bank Scale-out Tooling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the tested, reusable tooling that carries a book from drafted content to published content bank at ~170-pericope scale — a build manifest, a store writer, a provenance-stamping publisher, and a tiered review digest — feeding the existing schema/validate/sections gates.

**Architecture:** Four small, offline, stdlib-only Python modules under `content_bank/author/`, each with one responsibility, all unit-tested. They are driven at build time by a Claude Code workflow fan-out script that lives in untracked `work/` (it dispatches subagents, so it is scaffolding, never shipped/imported). The committed modules never call an API and never touch the store until a human confirms; the workflow writes all drafts/verdicts/digests/manifest under `work/content_bank_build/`.

**Tech Stack:** Python 3 standard library only (`json`, `pathlib`, `copy`, `argparse`, `unittest`). No third-party packages. Orchestration script is a Claude Code Workflow (JavaScript).

## Global Constraints

- **Python 3 standard library only** — no third-party imports in any committed module.
- **Committed `content_bank/` stays offline** — no network/API calls. The orchestration (which dispatches Claude subagents) lives in untracked `work/content_bank_build/`, is never imported by a committed module, and never appears in the product read path (`content_bank/lib/content.py`).
- **Nothing enters `content_bank/store/` until a human confirms.** The workflow writes only under `work/content_bank_build/`. Only the `publish` path writes the store.
- **Provenance on publish (exact keys):** `drafted_by="claude"`, `reviewed_by="claude-adversarial"`, `confirmed_by=<human>`, `reviewed_date=<YYYY-MM-DD>`, `guardrail="WCF-1"`; `review_status="published"`. The same three provenance keys (`reviewed_by`, `reviewed_date`, `guardrail`) are also stamped inside any `leader_reference.provenance`.
- **Tiered-by-risk review:** dimensions D1–D5 form the per-pericope **batch** tier; D6/D7/D8 and the section-scoped types (`throughline`, `thread`) form the **item-by-item** tier.
- **Reuse, never bypass, existing gates:** `content_bank/lib/schema.py`, `content_bank/lib/validate.py`, `content_bank/author/review_checklist.py`, `corpus/lib/sections.py`. No change to `content_bank/author/dimensions.py`.
- **English-first.** No `zh` content in this plan; `title_zh` left blank in any new corpus structure.
- **Tests:** the suite stays green — `python3 -m unittest discover -s content_bank/tests -v` (currently 107 passing). New modules add `unittest` tests in `content_bank/tests/`.
- **Run all commands from the repo root** `/media/pb/data/pjllc/scripture_loom`.

---

## File Structure

**Created (committed, tested):**
- `content_bank/author/manifest.py` — per-book build state ledger (stage per unit).
- `content_bank/author/store_writer.py` — merge items into `store/<book>.json` by id.
- `content_bank/author/publish.py` — stamp provenance, set published, upsert, validate.
- `content_bank/author/digest.py` — build + render the tiered review digest.
- `content_bank/tests/test_manifest.py`, `test_store_writer.py`, `test_publish.py`, `test_digest.py`.

**Modified (committed):**
- `content_bank/lib/content.py` — expose a public `store_path(book, store_dir=None)` (used by the store writer; `_store_path` becomes a thin wrapper).

**Created (untracked, scaffolding — NOT committed):**
- `work/content_bank_build/build_book.workflow.js` — the fan-out orchestration.
- `work/content_bank_build/<book>/manifest.json`, `.../drafts/`, `.../verdicts/`, `.../queue/` — runtime artifacts.

---

### Task 1: Build manifest ledger

**Files:**
- Create: `content_bank/author/manifest.py`
- Test: `content_bank/tests/test_manifest.py`

**Interfaces:**
- Consumes: nothing (leaf module; stdlib only).
- Produces:
  - `STAGES: tuple[str, ...]` — ordered build stages.
  - `init_manifest(book: str, pericope_ids, section_ids=()) -> dict`
  - `load(path) -> dict`
  - `save(path, manifest) -> None`
  - `set_stage(manifest: dict, unit_id: str, stage: str) -> None` (mutates in place)
  - `units_at(manifest: dict, stage: str) -> list[str]` (sorted)

- [ ] **Step 1: Write the failing test**

Create `content_bank/tests/test_manifest.py`:

```python
import json
import pathlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.author import manifest


class TestManifest(unittest.TestCase):
    def test_init_marks_all_units_pending(self):
        m = manifest.init_manifest("PHP", ["PHP-p1", "PHP-p2"], ["PHP-S1"])
        self.assertEqual(m["book"], "PHP")
        self.assertEqual(m["units"]["PHP-p1"], {"kind": "pericope", "stage": "pending"})
        self.assertEqual(m["units"]["PHP-S1"], {"kind": "section", "stage": "pending"})

    def test_set_stage_advances_one_unit(self):
        m = manifest.init_manifest("PHP", ["PHP-p1"])
        manifest.set_stage(m, "PHP-p1", "drafted")
        self.assertEqual(m["units"]["PHP-p1"]["stage"], "drafted")

    def test_set_stage_rejects_unknown_stage(self):
        m = manifest.init_manifest("PHP", ["PHP-p1"])
        with self.assertRaises(ValueError):
            manifest.set_stage(m, "PHP-p1", "bogus")

    def test_set_stage_rejects_unknown_unit(self):
        m = manifest.init_manifest("PHP", ["PHP-p1"])
        with self.assertRaises(KeyError):
            manifest.set_stage(m, "PHP-p9", "drafted")

    def test_units_at_returns_sorted(self):
        m = manifest.init_manifest("PHP", ["PHP-p2", "PHP-p1", "PHP-p3"])
        manifest.set_stage(m, "PHP-p2", "drafted")
        self.assertEqual(manifest.units_at(m, "pending"), ["PHP-p1", "PHP-p3"])
        self.assertEqual(manifest.units_at(m, "drafted"), ["PHP-p2"])

    def test_save_then_load_roundtrips(self):
        m = manifest.init_manifest("PHP", ["PHP-p1"])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sub" / "manifest.json"
            manifest.save(p, m)
            self.assertEqual(manifest.load(p), m)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest content_bank.tests.test_manifest -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'content_bank.author.manifest'`

- [ ] **Step 3: Write minimal implementation**

Create `content_bank/author/manifest.py`:

```python
"""Per-book build ledger: the stage each pericope/section unit has reached.

Lives in untracked work/ at runtime; this module only reads/writes the JSON.
Stdlib only, offline.
"""
import json
import pathlib

STAGES = ("pending", "briefed", "drafted", "reviewed",
          "in_queue", "confirmed", "published")


def init_manifest(book, pericope_ids, section_ids=()):
    units = {}
    for pid in pericope_ids:
        units[pid] = {"kind": "pericope", "stage": "pending"}
    for sid in section_ids:
        units[sid] = {"kind": "section", "stage": "pending"}
    return {"book": book, "units": units}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, manifest):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def set_stage(manifest, unit_id, stage):
    if stage not in STAGES:
        raise ValueError(f"unknown stage '{stage}' (expected one of {STAGES})")
    if unit_id not in manifest["units"]:
        raise KeyError(f"no unit '{unit_id}' in manifest")
    manifest["units"][unit_id]["stage"] = stage


def units_at(manifest, stage):
    return sorted(u for u, meta in manifest["units"].items()
                  if meta["stage"] == stage)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest content_bank.tests.test_manifest -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/manifest.py content_bank/tests/test_manifest.py
git commit -m "author: build manifest ledger for scale-out"
```

---

### Task 2: Store writer (id-merge upsert)

**Files:**
- Modify: `content_bank/lib/content.py` (add public `store_path`)
- Create: `content_bank/author/store_writer.py`
- Test: `content_bank/tests/test_store_writer.py`

**Interfaces:**
- Consumes: `content.load_book_store(book, store_dir)`, new `content.store_path(book, store_dir)`.
- Produces: `store_writer.upsert_items(book: str, items: list[dict], store_dir=None) -> dict` — merges by `id` (existing id replaced in place, new id appended), writes `store/<book>.json`, returns the written store dict.

- [ ] **Step 1: Write the failing test**

Create `content_bank/tests/test_store_writer.py`:

```python
import json
import pathlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.author import store_writer


def _item(iid, text="hi"):
    return {"id": iid, "passage": "PHP-p1", "dimension": "D1", "type": "question",
            "age_tier": "all", "difficulty": 1, "review_status": "draft",
            "text": {"en": text}, "version": 1}


class TestStoreWriter(unittest.TestCase):
    def test_creates_store_when_absent(self):
        with tempfile.TemporaryDirectory() as d:
            store = store_writer.upsert_items("PHP", [_item("a")], store_dir=d)
            self.assertEqual(store["book"], "PHP")
            on_disk = json.loads((Path(d) / "php.json").read_text())
            self.assertEqual(len(on_disk["items"]), 1)

    def test_appends_new_id(self):
        with tempfile.TemporaryDirectory() as d:
            store_writer.upsert_items("PHP", [_item("a")], store_dir=d)
            store = store_writer.upsert_items("PHP", [_item("b")], store_dir=d)
            self.assertEqual([i["id"] for i in store["items"]], ["a", "b"])

    def test_replaces_existing_id_in_place(self):
        with tempfile.TemporaryDirectory() as d:
            store_writer.upsert_items("PHP", [_item("a", "old"), _item("b")], store_dir=d)
            store = store_writer.upsert_items("PHP", [_item("a", "new")], store_dir=d)
            self.assertEqual([i["id"] for i in store["items"]], ["a", "b"])
            self.assertEqual(store["items"][0]["text"]["en"], "new")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest content_bank.tests.test_store_writer -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'content_bank.author.store_writer'`

- [ ] **Step 3a: Expose `store_path` in `content.py`**

In `content_bank/lib/content.py`, replace the private helper (lines 12-14) so a public function exists and the private one delegates:

```python
def store_path(book, store_dir=None):
    base = pathlib.Path(store_dir) if store_dir is not None else _STORE_DIR
    return base / f"{book.lower()}.json"


def _store_path(book, store_dir):
    return store_path(book, store_dir)
```

- [ ] **Step 3b: Write the store writer**

Create `content_bank/author/store_writer.py`:

```python
"""Merge content items into store/<book>.json by id.

Existing ids are replaced in place (preserving order); new ids are appended.
The only committed-code path that writes the store. Stdlib only, offline.
"""
import json

from ..lib import content


def upsert_items(book, items, store_dir=None):
    path = content.store_path(book, store_dir)
    if path.exists():
        store = content.load_book_store(book, store_dir)
    else:
        store = {"book": book.upper(), "items": []}
    existing = store["items"]
    index = {it["id"]: i for i, it in enumerate(existing)}
    for it in items:
        if it["id"] in index:
            existing[index[it["id"]]] = it
        else:
            index[it["id"]] = len(existing)
            existing.append(it)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return store
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest content_bank.tests.test_store_writer -v`
Expected: PASS (3 tests)

Run the full suite to confirm the `content.py` change broke nothing:
Run: `python3 -m unittest discover -s content_bank/tests -v`
Expected: OK (116 tests) — 107 baseline + 6 (Task 1) + 3 (this task)

- [ ] **Step 5: Commit**

```bash
git add content_bank/lib/content.py content_bank/author/store_writer.py content_bank/tests/test_store_writer.py
git commit -m "author: store writer with id-merge upsert; expose content.store_path"
```

---

### Task 3: Publisher (stamp provenance, publish, validate)

**Files:**
- Create: `content_bank/author/publish.py`
- Test: `content_bank/tests/test_publish.py`

**Interfaces:**
- Consumes: `store_writer.upsert_items(book, items, store_dir)`, `validate.validate_store(book, store_dir)`.
- Produces:
  - `stamp(items: list[dict], *, reviewed_date: str, confirmed_by: str, drafted_by="claude", reviewed_by="claude-adversarial", guardrail="WCF-1") -> list[dict]` — deep-copied items with `review_status="published"`, item `provenance` filled, and `leader_reference.provenance` filled when a leader_reference is present.
  - `publish(book, items, *, reviewed_date, confirmed_by, store_dir=None, **stamp_kw) -> dict` — stamps, upserts, runs `validate_store`, raises `ValueError` if the resulting store has errors; returns the validation report.

- [ ] **Step 1: Write the failing test**

Create `content_bank/tests/test_publish.py`:

```python
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.author import publish
from content_bank.lib import schema


def _q(iid="php1-q1"):
    return {"id": iid, "passage": "PHP-p1", "dimension": "D1", "type": "question",
            "age_tier": "all", "difficulty": 1, "review_status": "draft",
            "text": {"en": "Who wrote to the Philippians?"}, "version": 1,
            "leader_reference": {"kind": "answer_key", "text": {"en": "Paul"}}}


class TestStamp(unittest.TestCase):
    def test_stamp_sets_published_and_provenance(self):
        out = publish.stamp([_q()], reviewed_date="2026-07-19", confirmed_by="kyhhdm")
        it = out[0]
        self.assertEqual(it["review_status"], "published")
        self.assertEqual(it["provenance"]["drafted_by"], "claude")
        self.assertEqual(it["provenance"]["reviewed_by"], "claude-adversarial")
        self.assertEqual(it["provenance"]["confirmed_by"], "kyhhdm")
        self.assertEqual(it["provenance"]["guardrail"], "WCF-1")

    def test_stamp_fills_leader_reference_provenance(self):
        out = publish.stamp([_q()], reviewed_date="2026-07-19", confirmed_by="kyhhdm")
        prov = out[0]["leader_reference"]["provenance"]
        self.assertEqual(prov["reviewed_by"], "claude-adversarial")
        self.assertEqual(prov["guardrail"], "WCF-1")

    def test_stamped_item_is_schema_valid(self):
        out = publish.stamp([_q()], reviewed_date="2026-07-19", confirmed_by="kyhhdm")
        self.assertEqual(schema.validate_item(out[0]), [])

    def test_stamp_does_not_mutate_input(self):
        item = _q()
        publish.stamp([item], reviewed_date="2026-07-19", confirmed_by="kyhhdm")
        self.assertEqual(item["review_status"], "draft")


if __name__ == "__main__":
    unittest.main()
```

Note: `publish()` itself calls `validate_store`, which needs corpus pericope ids and is covered by the live smoke run in Task 5, not here — these unit tests exercise `stamp` (pure) against the real `schema.validate_item`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest content_bank.tests.test_publish -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'content_bank.author.publish'`

- [ ] **Step 3: Write minimal implementation**

Create `content_bank/author/publish.py`:

```python
"""Confirm drafted items: stamp provenance, set published, upsert, validate.

The human-confirmation write path. Stdlib only, offline.
"""
import copy

from . import store_writer
from ..lib import validate


def _provenance(reviewed_date, confirmed_by, drafted_by, reviewed_by, guardrail):
    return {"drafted_by": drafted_by, "reviewed_by": reviewed_by,
            "reviewed_date": reviewed_date, "guardrail": guardrail,
            "confirmed_by": confirmed_by}


def stamp(items, *, reviewed_date, confirmed_by, drafted_by="claude",
          reviewed_by="claude-adversarial", guardrail="WCF-1"):
    prov = _provenance(reviewed_date, confirmed_by, drafted_by, reviewed_by, guardrail)
    out = []
    for it in items:
        it = copy.deepcopy(it)
        it["review_status"] = "published"
        it["provenance"] = dict(prov)
        ref = it.get("leader_reference")
        if ref is not None:
            ref["provenance"] = {"reviewed_by": reviewed_by,
                                 "reviewed_date": reviewed_date,
                                 "guardrail": guardrail}
        out.append(it)
    return out


def publish(book, items, *, reviewed_date, confirmed_by, store_dir=None, **stamp_kw):
    stamped = stamp(items, reviewed_date=reviewed_date, confirmed_by=confirmed_by,
                    **stamp_kw)
    store_writer.upsert_items(book, stamped, store_dir)
    report = validate.validate_store(book, store_dir)
    if report["errors"]:
        raise ValueError("store invalid after publish: " + "; ".join(report["errors"]))
    return report
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest content_bank.tests.test_publish -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/publish.py content_bank/tests/test_publish.py
git commit -m "author: publisher stamps provenance, publishes, validates store"
```

---

### Task 4: Tiered review digest

**Files:**
- Create: `content_bank/author/digest.py`
- Test: `content_bank/tests/test_digest.py`

**Interfaces:**
- Consumes: nothing (leaf; stdlib only). Operates on item dicts + a verdicts map.
- Produces:
  - `BATCH_DIMENSIONS: set[str]` = `{"D1","D2","D3","D4","D5"}`.
  - `tier_of(item: dict) -> str` — `"batch"` or `"item"` (section-scoped types and D6/D7/D8 are `"item"`; everything else `"batch"`).
  - `build_digest(unit_id: str, items: list[dict], verdicts: dict) -> dict` — `verdicts` maps `item_id -> list[{"reviewer","verdict","notes"}]`; returns `{"unit","batch","item_tier","verdicts"}`.
  - `render_digest(digest: dict) -> str` — Markdown for the human reviewer.

- [ ] **Step 1: Write the failing test**

Create `content_bank/tests/test_digest.py`:

```python
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.author import digest


def _item(iid, dim, typ="question", scope=("passage", "PHP-p1")):
    it = {"id": iid, "dimension": dim, "type": typ, "age_tier": "all",
          "difficulty": 1, "review_status": "draft", "text": {"en": iid}, "version": 1}
    it[scope[0]] = scope[1]
    return it


class TestTierOf(unittest.TestCase):
    def test_closed_dimension_is_batch(self):
        self.assertEqual(digest.tier_of(_item("a", "D3")), "batch")

    def test_open_dimension_is_item(self):
        self.assertEqual(digest.tier_of(_item("a", "D7")), "item")

    def test_throughline_is_item(self):
        it = _item("t", "D7", "throughline", scope=("section", "PHP-S1"))
        self.assertEqual(digest.tier_of(it), "item")


class TestBuildDigest(unittest.TestCase):
    def test_splits_by_tier(self):
        items = [_item("a", "D1"), _item("b", "D7")]
        d = digest.build_digest("PHP-p1", items, {})
        self.assertEqual([i["id"] for i in d["batch"]], ["a"])
        self.assertEqual([i["id"] for i in d["item_tier"]], ["b"])


class TestRenderDigest(unittest.TestCase):
    def test_render_has_both_sections_and_verdicts(self):
        items = [_item("a", "D1"), _item("b", "D7")]
        verdicts = {"b": [{"reviewer": "r1", "verdict": "pass", "notes": "ok"}]}
        text = digest.render_digest(digest.build_digest("PHP-p1", items, verdicts))
        self.assertIn("PHP-p1", text)
        self.assertIn("Batch review (D1-D5)", text)
        self.assertIn("Item-by-item review", text)
        self.assertIn("r1", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest content_bank.tests.test_digest -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'content_bank.author.digest'`

- [ ] **Step 3: Write minimal implementation**

Create `content_bank/author/digest.py`:

```python
"""Tiered-by-risk review digest for one build unit.

Closed dimensions (D1-D5) are batch-reviewed together; open dimensions
(D6-D8) and section-scoped types (throughline/thread) are reviewed item by
item. Renders Markdown for a human. Stdlib only, offline.
"""

BATCH_DIMENSIONS = {"D1", "D2", "D3", "D4", "D5"}
_ITEM_TYPES = {"throughline", "thread"}


def tier_of(item):
    if item.get("type") in _ITEM_TYPES:
        return "item"
    if item.get("dimension") not in BATCH_DIMENSIONS:
        return "item"
    return "batch"


def build_digest(unit_id, items, verdicts):
    return {
        "unit": unit_id,
        "batch": [it for it in items if tier_of(it) == "batch"],
        "item_tier": [it for it in items if tier_of(it) == "item"],
        "verdicts": verdicts,
    }


def _verdict_lines(item_id, verdicts):
    lines = []
    for v in verdicts.get(item_id, []):
        lines.append(f"  - {v['reviewer']}: {v['verdict']} — {v.get('notes', '')}")
    return lines


def _item_block(it, verdicts):
    scope = it.get("passage") or it.get("section")
    lines = [f"- **{it['id']}** [{it['dimension']}/{it['type']}/{it['age_tier']}] "
             f"({scope}): {it['text'].get('en', '')}"]
    lines.extend(_verdict_lines(it["id"], verdicts))
    return lines


def render_digest(digest):
    out = [f"# Review digest — {digest['unit']}", ""]
    out.append("## Batch review (D1-D5) — confirm/reject together, spot-edit")
    for it in digest["batch"]:
        out.extend(_item_block(it, digest["verdicts"]))
    out.append("")
    out.append("## Item-by-item review (D6-D8, throughline, thread) — confirm each")
    for it in digest["item_tier"]:
        out.extend(_item_block(it, digest["verdicts"]))
    return "\n".join(out) + "\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest content_bank.tests.test_digest -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Run the full suite**

Run: `python3 -m unittest discover -s content_bank/tests -v`
Expected: OK (125 tests) — 107 baseline + 6 + 3 + 4 + 5

- [ ] **Step 6: Commit**

```bash
git add content_bank/author/digest.py content_bank/tests/test_digest.py
git commit -m "author: tiered-by-risk review digest builder + renderer"
```

---

### Task 5: Fan-out orchestration + live smoke run (integration)

This task wires the four modules into a Claude Code workflow and proves the pipeline end-to-end on **one real Philippians pericope**. It is verified by observation (manifest advances, a digest file appears), not by `unittest` — it dispatches subagents and reads the corpus, so it is scaffolding in untracked `work/`, never committed as importable code.

**Prerequisite (Phase 0, minimal slice):** `corpus/canon/structure/pericopes/php.json` must exist with at least the first pericope (`PHP-p1`, a `range`, `title_en`). Author it MHC-first (MHC is the primary boundary authority). Validate the file loads: `python3 -c "from content_bank.lib import corpus_bridge; print(corpus_bridge.pericope_ids('PHP'))"`.

**Files:**
- Create (untracked): `work/content_bank_build/build_book.workflow.js`

**Interfaces:**
- Consumes (via a finalize agent running Bash): `content_bank.author.build_brief_prompt`, `build_draft_prompt` (existing CLIs), and the Task 1–4 modules.
- Produces: `work/content_bank_build/PHP/manifest.json`, `.../drafts/PHP-p1.json`, `.../verdicts/PHP-p1.json`, `.../queue/PHP-p1.md`.

- [ ] **Step 1: Write the orchestration script**

Create `work/content_bank_build/build_book.workflow.js`. Per pericope it fans out: brief → draft → ≥2 adversarial reviewers → a finalize agent that writes drafts+verdicts and renders the digest via the Task 4 module, advancing the manifest. `args` is `{book, pericopes}`.

```javascript
export const meta = {
  name: 'build-book',
  description: 'Fan out brief/draft/adversarial-review per pericope into a review queue',
  phases: [{ title: 'Draft' }, { title: 'Review' }, { title: 'Finalize' }],
}

const book = args.book
const root = `work/content_bank_build/${book}`

await pipeline(
  args.pericopes,
  // Stage 1: brief + draft
  (pid) => agent(
    `Assemble the draft pack by running \`python3 -m content_bank.author.build_draft_prompt ${pid} --book ${book}\` `
    + `(run build_brief_prompt first and commit content_bank/author/briefs/${pid.toLowerCase()}.md if no brief exists). `
    + `Draft the D1-D8 items as a JSON array per the pack's output schema. Return ONLY the JSON array.`,
    { label: `draft:${pid}`, phase: 'Draft' }
  ).then((draftJson) => ({ pid, draftJson })),

  // Stage 2: >=2 adversarial reviewers
  ({ pid, draftJson }) =>
    parallel([1, 2].map((n) => () => agent(
      `Adversarially review these drafted items for ${pid} against the passage and WCF-1. `
      + `For each item id, return {reviewer:"r${n}", verdict:"pass"|"fail", notes:"..."}. Items:\n${draftJson}`,
      { label: `review:${pid}:r${n}`, phase: 'Review' }
    ))).then((verdicts) => ({ pid, draftJson, verdicts: verdicts.filter(Boolean) })),

  // Stage 3: finalize — persist drafts + verdicts, render digest, advance manifest
  ({ pid, draftJson, verdicts }) => agent(
    `You are finalizing ${pid}. Do exactly this with Bash/Write:\n`
    + `1. Write the draft JSON array to ${root}/drafts/${pid}.json:\n${draftJson}\n`
    + `2. Write the reviewer verdicts (merge into {item_id: [ {reviewer,verdict,notes} ]}) to ${root}/verdicts/${pid}.json:\n${JSON.stringify(verdicts)}\n`
    + `3. Run this Python to render the digest and advance the manifest:\n`
    + `python3 - <<'PY'\n`
    + `import json, pathlib\n`
    + `from content_bank.author import digest, manifest\n`
    + `root = pathlib.Path("${root}")\n`
    + `items = json.loads((root/"drafts/${pid}.json").read_text())\n`
    + `verdicts = json.loads((root/"verdicts/${pid}.json").read_text())\n`
    + `d = digest.build_digest("${pid}", items, verdicts)\n`
    + `(root/"queue").mkdir(parents=True, exist_ok=True)\n`
    + `(root/"queue/${pid}.md").write_text(digest.render_digest(d), encoding="utf-8")\n`
    + `mp = root/"manifest.json"\n`
    + `m = manifest.load(mp)\n`
    + `manifest.set_stage(m, "${pid}", "in_queue")\n`
    + `manifest.save(mp, m)\n`
    + `PY\n`
    + `Report the path of the digest you wrote.`,
    { label: `finalize:${pid}`, phase: 'Finalize' }
  )
)

return { queued: args.pericopes.length }
```

- [ ] **Step 2: Initialize the manifest for Philippians**

Run:
```bash
python3 - <<'PY'
from content_bank.lib import corpus_bridge
from content_bank.author import manifest
book = "PHP"
m = manifest.init_manifest(book, sorted(corpus_bridge.pericope_ids(book)),
                           sorted(corpus_bridge.section_ids(book)))
manifest.save(f"work/content_bank_build/{book}/manifest.json", m)
print("units:", len(m["units"]))
PY
```
Expected: prints the unit count (≥1).

- [ ] **Step 3: Run the workflow on one pericope**

Invoke the Workflow tool with `scriptPath: "work/content_bank_build/build_book.workflow.js"` and `args: {"book": "PHP", "pericopes": ["PHP-p1"]}`.

Expected on completion: `{ queued: 1 }`.

- [ ] **Step 4: Verify the artifacts (observation, not a unit test)**

Run:
```bash
cat work/content_bank_build/PHP/queue/PHP-p1.md
python3 -c "from content_bank.author import manifest; m=manifest.load('work/content_bank_build/PHP/manifest.json'); print(m['units']['PHP-p1']['stage'])"
```
Expected: the digest shows a **Batch review (D1-D5)** section and an **Item-by-item review** section with reviewer verdicts; the manifest stage prints `in_queue`.

- [ ] **Step 5: Verify the human confirm → publish path on the drafted items**

Simulate confirmation of the batch tier for `PHP-p1` (spot-edit first in a real run), then publish:
```bash
python3 - <<'PY'
import json, pathlib
from content_bank.author import publish, manifest
items = json.loads(pathlib.Path("work/content_bank_build/PHP/drafts/PHP-p1.json").read_text())
report = publish.publish("PHP", items, reviewed_date="2026-07-19", confirmed_by="kyhhdm")
print("errors:", report["errors"])
print("published:", report["counts"]["published"])
mp = "work/content_bank_build/PHP/manifest.json"
m = manifest.load(mp); manifest.set_stage(m, "PHP-p1", "published"); manifest.save(mp, m)
PY
```
Expected: `errors: []`, `published:` > 0, and `content_bank/store/php.json` now exists with published items. (In a real run this happens only after the human clears the tiered digest.)

- [ ] **Step 6: Confirm the whole suite is still green**

Run: `python3 -m unittest discover -s content_bank/tests -v`
Expected: OK (125 tests) — the store write does not touch the test suite.

- [ ] **Step 7: Commit (docs/manifest only; drafts and store content are separate authoring commits)**

The workflow script and its runtime artifacts live in untracked `work/` by design and are **not** committed here. If `store/php.json` was written by the smoke run against real content you intend to keep, commit it as its own authoring commit; otherwise discard it:
```bash
git checkout -- content_bank/store/php.json 2>/dev/null || rm -f content_bank/store/php.json
```

---

## Operational phases (post-tooling — not TDD tasks)

With the tooling built and proven, the three books are authored by *running* it. These are guided operations gated on human review, not code:

- **Phase 0 — Corpus structure (PHP, then ECC).** Author full `pericopes/<book>.json` then `sections/<book>.json`, MHC as the primary boundary authority; validate with `corpus/lib/sections.py`. (Task 5 needs only the first PHP pericope; the rest of Phase 0 is completed here before Phase 1 proper.)
- **Phase 1 — Philippians (proof).** `init_manifest` for all PHP pericopes/sections; run `build_book` across them (pericope tier, then the section/arc tier once a section's pericopes are drafted); clear the tiered review queue; `publish` per confirmed unit. Retrospective before Phase 2.
- **Phase 2 — Ecclesiastes.** Same loop; genre stress-test.
- **Phase 3 — Matthew.** Same loop over the 149 non-grandfathered pericopes plus the section/arc tier, reconciling section membership around the four grandfathered pilot pericopes.

The section/arc tier reuses the same pipeline with `build_section_brief_prompt` in the draft stage and `throughline`/`thread`/arc-question outputs; `digest.tier_of` already routes those to item-by-item review.

## Definition of done (this plan)

- Tasks 1–4 committed, `python3 -m unittest discover -s content_bank/tests -v` reports **OK (125 tests)**.
- Task 5 smoke run produces a tiered digest and advances the manifest for one real PHP pericope; the confirm→publish path writes a schema-valid `store/php.json` with correct provenance.
- No committed module imports the workflow or makes a network call; the product read path (`content.get_content`) is unchanged.
