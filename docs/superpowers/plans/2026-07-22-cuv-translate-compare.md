# CUV Translation — run-drafts input + translator comparison (Plan 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `translate_cli` translate a build run's English **drafts** (`runs/<model>/drafts/`) — not just the store — with per-**translator** output routing, and add a self-contained page that compares the same drafts' translations across translator models.

**Architecture:** Small extension of the Plan-2 tool. `translate_cli` gains a `--drafts-dir` source and a `--backend`, routing output to `runs/<draft-model>/translations/<translator-slug>/` (slug via the existing `build_cli._run_slug`). A new `translate_compare_html` reads those per-translator proposal dirs and renders English ▸ CUV-source ▸ one zh column per translator ▸ flags. Stacks on the Plan-2 branch (needs `translate_cli.py`). Spec: `docs/superpowers/specs/2026-07-21-cuv-alignment-translation-design.md`.

**Tech Stack:** Python 3, `uv`, stdlib + in-repo packages, `unittest` (LLM seam mocked; static HTML generator).

## Global Constraints

- Run everything under `uv`. Tests: `uv run python -m unittest …`.
- **Tests are network-free**: patch `content_bank.author.translate.llm` and `translate_cli.back_translate_review`; the HTML generator reads local proposal JSON + local corpus only.
- **Translator slug** = `build_cli._run_slug(backend, model)` (e.g. `deepseek-v4-flash`, `opus`) — reuse it; do not reinvent.
- **Backend** reaches the seam ONLY via the `SCRIPTURE_LOOM_LLM_BACKEND` env var (mirror `build_cli.main` which sets it); `model` is threaded explicitly as before.
- **Output routing**: with `--drafts-dir DIR`, default output is `Path(DIR).parent / "translations" / <slug>` — i.e. `runs/<draft-model>/translations/<translator>/`. `--out` still overrides.
- Drafts are per-unit JSON **arrays** of items (`runs/<model>/drafts/<unit>.json`), English-only, `review_status: "draft"`. The tool translates them exactly as it does store items.
- The tool still NEVER writes the store; it only emits proposals. (`promote` remains the store gate.)
- New tests live in `content_bank/tests/test_*.py`; the HTML page is self-contained (inline CSS, no external refs).

## File Structure

- Modify `content_bank/author/translate_cli.py` — `--drafts-dir`, `--backend`, `load_drafts`, output routing (Task 1).
- Create `content_bank/author/translate_compare_html.py` — the translator comparison page (Task 2).
- Tests: extend `test_translate_cli.py` (Task 1); new `test_translate_compare_html.py` (Task 2).

---

### Task 1: `translate_cli` — run-drafts input + `--backend` + translator routing

**Files:**
- Modify: `content_bank/author/translate_cli.py`
- Test: `content_bank/tests/test_translate_cli.py` (add class)

**Interfaces:**
- Consumes: `build_cli._run_slug`.
- Produces: `load_drafts(drafts_dir) -> list[dict]` (concatenate all `*.json` item-arrays, filename-sorted); `out_dir_for(drafts_dir, backend, model) -> str`; `main` gains `--drafts-dir`, `--backend {llm_core,claude}`.

- [ ] **Step 1: Write the failing test**

```python
# add to content_bank/tests/test_translate_cli.py
import os
from content_bank.author import build_cli


class TestDraftsInput(unittest.TestCase):
    def _drafts_dir(self):
        # a runs/<model>/drafts layout with two unit files
        root = tempfile.mkdtemp()
        d = pathlib.Path(root) / "PHP" / "runs" / "opus" / "drafts"
        d.mkdir(parents=True)
        (d / "PHP-001.json").write_text(json.dumps(
            [{"id": "PHP-001-D1-01", "passage": "PHP.1.1-11", "dimension": "D1",
              "type": "question", "text": {"en": "servants of Christ Jesus?"}}]),
            encoding="utf-8")
        (d / "PHP-002.json").write_text(json.dumps(
            [{"id": "PHP-002-D1-01", "passage": "PHP.1.12-18", "dimension": "D1",
              "type": "question", "text": {"en": "Who is emboldened?"}}]),
            encoding="utf-8")
        return str(d)

    def test_load_drafts_concatenates_sorted(self):
        got = translate_cli.load_drafts(self._drafts_dir())
        self.assertEqual([i["id"] for i in got],
                         ["PHP-001-D1-01", "PHP-002-D1-01"])

    def test_out_dir_routes_by_translator_slug(self):
        dd = self._drafts_dir()
        out = translate_cli.out_dir_for(dd, "llm_core", None)  # -> deepseek-v4-flash
        self.assertTrue(out.endswith("runs/opus/translations/deepseek-v4-flash"))
        out2 = translate_cli.out_dir_for(dd, "claude", "opus")
        self.assertTrue(out2.endswith("runs/opus/translations/opus"))

    def test_main_drafts_dir_writes_proposals_to_translator_dir(self):
        dd = self._drafts_dir()
        with mock.patch.object(translate, "llm",
                               return_value='{"text": {"zh": "「基督耶稣的仆人」？"}, '
                                            '"terms": [], "uncertain": []}'), \
             mock.patch.object(translate_cli, "back_translate_review",
                               return_value={"drift": False, "notes": ""}):
            translate_cli.main(["--book", "PHP", "--drafts-dir", dd,
                                "--items", "PHP-001-D1-01"])
        f = (pathlib.Path(dd).parent / "translations" / "deepseek-v4-flash"
             / "PHP-001-D1-01.json")
        self.assertTrue(f.exists())
        self.assertEqual(os.environ.get("SCRIPTURE_LOOM_LLM_BACKEND"), "llm_core")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_translate_cli.TestDraftsInput -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'load_drafts'`.

- [ ] **Step 3: Write minimal implementation**

Edit `content_bank/author/translate_cli.py`. Add imports at top (`os` was removed in Plan 2 — re-add it):

```python
import argparse
import json
import os
import pathlib

from ..lib import content
from . import glossary as _glossary
from .build_cli import _run_slug
from .translate import translate_with_gates, back_translate_review
```

Add the two helpers (after `select_items`):

```python
def load_drafts(drafts_dir):
    """Load items from a build run's drafts dir (per-unit JSON arrays)."""
    items = []
    for path in sorted(pathlib.Path(drafts_dir).glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            items.extend(data)
    return items


def out_dir_for(drafts_dir, backend, model):
    """Default proposal dir for a drafts run: runs/<draft-model>/translations/<slug>."""
    slug = _run_slug(backend, model)
    return str(pathlib.Path(drafts_dir).parent / "translations" / slug)
```

Rewrite `main` to accept `--drafts-dir` / `--backend` and route accordingly:

```python
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--items", nargs="*")
    ap.add_argument("--status")
    ap.add_argument("--drafts-dir",
                    help="translate a build run's drafts (runs/<model>/drafts) "
                         "instead of the store")
    ap.add_argument("--backend", choices=("llm_core", "claude"), default="llm_core")
    ap.add_argument("--model")
    ap.add_argument("--max-repair", type=int, default=2)
    ap.add_argument("--out")
    args = ap.parse_args(argv)

    os.environ["SCRIPTURE_LOOM_LLM_BACKEND"] = args.backend

    if args.drafts_dir:
        items = load_drafts(args.drafts_dir)
        if args.items:
            want = set(args.items)
            items = [it for it in items if it["id"] in want]
        out_dir = args.out or out_dir_for(args.drafts_dir, args.backend, args.model)
    else:
        items = select_items(args.book, item_ids=args.items, status=args.status)
        out_dir = args.out or f"work/content_bank_build/{args.book}/translations"

    glossary = _glossary.load_glossary()
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m unittest content_bank.tests.test_translate_cli -v`
Expected: PASS (existing 4 + new 3).
Full suite: `uv run python -m unittest discover -s content_bank/tests` — all PASS.

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/translate_cli.py content_bank/tests/test_translate_cli.py
git commit -m "feat(translate): --drafts-dir + --backend, translator-slug output routing"
```

---

### Task 2: `translate_compare_html` — translator comparison page

**Files:**
- Create: `content_bank/author/translate_compare_html.py`
- Test: `content_bank/tests/test_translate_compare_html.py`

**Interfaces:**
- Consumes: `corpus_bridge.passage_text(ref, version="CUV")`.
- Produces: `build_page(book, draft_run, translators, *, root="work/content_bank_build") -> dict`; `render_html(page) -> str`; `main(argv=None)`. Page rows are per item id: `{id, en, cuv, cells: {translator: {zh, gate_ok, gate_flags, drift, uncertain}}}`.

- [ ] **Step 1: Write the failing test**

```python
# content_bank/tests/test_translate_compare_html.py
import json
import pathlib
import tempfile
import unittest
from content_bank.author import translate_compare_html as tch


def _proposal(iid, zh, gate_ok=True):
    return {"id": iid, "en": "servants of Christ Jesus?",
            "item": {"id": iid, "text": {"en": "servants of Christ Jesus?",
                                         "zh": zh}},
            "cuv_refs": ["PHP.1.1-11"], "terms": [], "uncertain": [],
            "gate_ok": gate_ok, "gate_flags": [], "drift": {"drift": False, "notes": ""}}


class TestTranslateComparePage(unittest.TestCase):
    def _root(self):
        root = tempfile.mkdtemp()
        base = pathlib.Path(root) / "PHP" / "runs" / "opus" / "translations"
        for tr, zh in (("deepseek-v4-flash", "「基督耶稣的仆人」甲"),
                       ("opus", "「基督耶稣的仆人」乙")):
            d = base / tr
            d.mkdir(parents=True)
            (d / "PHP-001-D1-01.json").write_text(
                json.dumps(_proposal("PHP-001-D1-01", zh)), encoding="utf-8")
        return root

    def test_build_page_collects_translators(self):
        page = tch.build_page("PHP", "opus", ["deepseek-v4-flash", "opus"],
                              root=self._root())
        self.assertEqual(page["translators"], ["deepseek-v4-flash", "opus"])
        row = page["rows"][0]
        self.assertEqual(row["id"], "PHP-001-D1-01")
        self.assertIn("基督耶稣的仆人", row["cuv"])  # CUV source verse pulled
        self.assertEqual(row["cells"]["deepseek-v4-flash"]["zh"], "「基督耶稣的仆人」甲")
        self.assertEqual(row["cells"]["opus"]["zh"], "「基督耶稣的仆人」乙")

    def test_render_html_is_self_contained(self):
        page = tch.build_page("PHP", "opus", ["deepseek-v4-flash", "opus"],
                              root=self._root())
        html = tch.render_html(page)
        self.assertIn("servants of Christ Jesus?", html)   # en
        self.assertIn("「基督耶稣的仆人」甲", html)            # translator zh
        self.assertIn("「基督耶稣的仆人」乙", html)
        self.assertNotIn("http://", html)                  # no external refs
        self.assertNotIn("https://", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_translate_compare_html -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'content_bank.author.translate_compare_html'`.

- [ ] **Step 3: Write minimal implementation**

```python
# content_bank/author/translate_compare_html.py
"""Self-contained page comparing one build run's draft translations across
translator models. Reads runs/<draft_run>/translations/<translator>/*.json and
renders: English ▸ CUV source verse ▸ one zh column per translator ▸ flags.
Read-only review instrument; never writes the store.
"""
import argparse
import html
import json
import pathlib

from ..lib import corpus_bridge

_ROOT = "work/content_bank_build"


def _load_translator(book, draft_run, translator, root):
    d = pathlib.Path(root) / book / "runs" / draft_run / "translations" / translator
    out = {}
    for path in sorted(d.glob("*.json")):
        p = json.loads(path.read_text(encoding="utf-8"))
        out[p["id"]] = p
    return out


def _cuv_for(refs):
    for ref in refs or []:
        try:
            return corpus_bridge.passage_text(ref, version="CUV")
        except Exception:
            continue
    return ""


def build_page(book, draft_run, translators, *, root=_ROOT):
    loaded = {t: _load_translator(book, draft_run, t, root) for t in translators}
    ids = []
    for t in translators:
        for iid in loaded[t]:
            if iid not in ids:
                ids.append(iid)
    rows = []
    for iid in ids:
        first = next((loaded[t][iid] for t in translators if iid in loaded[t]), {})
        cells = {}
        for t in translators:
            p = loaded[t].get(iid)
            if not p:
                cells[t] = None
                continue
            cells[t] = {"zh": (p["item"].get("text") or {}).get("zh", ""),
                        "gate_ok": p.get("gate_ok", True),
                        "gate_flags": p.get("gate_flags", []),
                        "drift": p.get("drift", {}).get("drift", False),
                        "uncertain": p.get("uncertain", [])}
        rows.append({"id": iid, "en": first.get("en", ""),
                     "cuv": _cuv_for(first.get("cuv_refs")), "cells": cells})
    return {"book": book, "draft_run": draft_run, "translators": translators,
            "rows": rows}


def _flag_badges(cell):
    if cell is None:
        return "<span class=missing>—</span>"
    bits = []
    if not cell["gate_ok"]:
        bits.append('<span class="bad">gate</span>')
    if cell["drift"]:
        bits.append('<span class="bad">drift</span>')
    if cell["uncertain"]:
        bits.append('<span class="warn">uncertain</span>')
    return " ".join(bits) or '<span class="ok">ok</span>'


def render_html(page):
    esc = html.escape
    cols = "".join(f"<th>{esc(t)}</th>" for t in page["translators"])
    body = []
    for r in page["rows"]:
        cells = []
        for t in page["translators"]:
            c = r["cells"].get(t)
            zh = esc(c["zh"]) if c else "—"
            cells.append(f"<td><div class=zh>{zh}</div>"
                         f"<div class=badges>{_flag_badges(c)}</div></td>")
        body.append(
            f"<tr><td class=id>{esc(r['id'])}</td>"
            f"<td class=en>{esc(r['en'])}</td>"
            f"<td class=cuv>{esc(r['cuv'])}</td>{''.join(cells)}</tr>")
    return f"""<!-- self-contained -->
<meta charset="utf-8"><title>Translation comparison — {esc(page['book'])} \
{esc(page['draft_run'])}</title>
<style>
 body{{font:14px/1.5 system-ui,sans-serif;margin:1rem;color:#111}}
 table{{border-collapse:collapse;width:100%}}
 th,td{{border:1px solid #ccc;padding:6px 8px;vertical-align:top;text-align:left}}
 th{{background:#f4f4f4}} .id{{font-family:monospace;font-size:12px;white-space:nowrap}}
 .en{{max-width:22ch}} .cuv{{max-width:26ch;color:#333}} .zh{{max-width:30ch}}
 .badges{{margin-top:4px;font-size:11px}}
 .ok{{color:#2a7}}.bad{{color:#c22;font-weight:600}}.warn{{color:#b70}}
 .missing{{color:#999}}
</style>
<h1>Translation comparison — {esc(page['book'])} · draft run \
<code>{esc(page['draft_run'])}</code></h1>
<p>English ▸ CUV source ▸ one column per translator. Flags: gate (CUV/glossary \
fail), drift (back-translation), uncertain (model-flagged).</p>
<table><thead><tr><th>id</th><th>English</th><th>CUV source</th>{cols}</tr></thead>
<tbody>{''.join(body)}</tbody></table>"""


def main(argv=None):
    ap = argparse.ArgumentParser(description="Compare draft translations across "
                                             "translator models.")
    ap.add_argument("book")
    ap.add_argument("--draft-run", required=True,
                    help="the drafting run dir name, e.g. opus")
    ap.add_argument("--translators", required=True,
                    help="comma-separated translator slugs, e.g. "
                         "deepseek-v4-flash,opus")
    ap.add_argument("--root", default=_ROOT)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    translators = [t.strip() for t in args.translators.split(",") if t.strip()]
    page = build_page(args.book, args.draft_run, translators, root=args.root)
    out = args.out or str(pathlib.Path(args.root) / args.book / "runs"
                          / args.draft_run / "translations" / "review.html")
    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(out).write_text(render_html(page), encoding="utf-8")
    print(f"wrote {out} ({len(page['rows'])} items, "
          f"{len(translators)} translators)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m unittest content_bank.tests.test_translate_compare_html -v`
Expected: PASS (2 tests).
Full suite: `uv run python -m unittest discover -s content_bank/tests` — all PASS.

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/translate_compare_html.py content_bank/tests/test_translate_compare_html.py
git commit -m "feat(translate): translator comparison page (en/CUV/per-translator zh)"
```

---

## Self-Review

**Spec coverage (the enhancement discussed):**
- Translate run drafts (not just the store) → Task 1 `--drafts-dir` + `load_drafts`. ✅
- Per-translator output routing (`runs/<draft-model>/translations/<translator>/`) → Task 1 `out_dir_for` + `--backend`. ✅
- Backend reaches the seam via `SCRIPTURE_LOOM_LLM_BACKEND` → Task 1 `main`. ✅
- Compare translators side by side (en ▸ CUV ▸ per-translator zh ▸ flags) → Task 2 `translate_compare_html`. ✅
- Tool still never writes the store → unchanged; only proposals emitted. ✅

**Placeholder scan:** none — every step has runnable code and exact commands.

**Type consistency:** `load_drafts -> [item]`; `out_dir_for(drafts_dir, backend, model) -> str` (reuses `build_cli._run_slug`); `build_page(...) -> {book, draft_run, translators, rows:[{id,en,cuv,cells:{tr:{zh,gate_ok,gate_flags,drift,uncertain}|None}}]}`; `render_html(page) -> str`. Proposal shape consumed here matches Task-5 emission `{id, en, item, cuv_refs, terms, uncertain, gate_ok, gate_flags, drift}`. ✅
