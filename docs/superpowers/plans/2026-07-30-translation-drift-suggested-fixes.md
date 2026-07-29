# Translation Drift — Suggested Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On a drift-flagged translation proposal, make one extra CUV-safe LLM call that proposes a revised zh, recorded as `suggested_fix` (never auto-replacing the original), re-gated and re-drift-checked, and surfaced on the review page for the human to accept.

**Architecture:** Additive to the existing translator. A new pure function `suggest_drift_fix` in `translate.py` reuses the existing `_merge_zh` / `zh_gate_flags` / `back_translate_review` seams; `proposal_for` in `translate_cli.py` calls it when drift fired and a `--suggest-fixes` flag is on; `translate_compare_html.py` renders the suggestion beneath the flagged cell using the existing badge/tooltip machinery. No store-item schema change (proposals are review-stage artifacts).

**Tech Stack:** Python 3 stdlib + the project's `content_bank.author` modules; `unittest` + `unittest.mock` (patch `translate.llm`).

## Global Constraints

- **Suggest-and-confirm only** — `suggested_fix` rides alongside; the original `item` is never mutated or replaced.
- **CUV-safe** — the fix prompt forbids leaving the CUV; a CUV-inherent drift is returned `changed:false`, unchanged.
- **Verify, don't trust** — re-run `zh_gate_flags` AND `back_translate_review` on any changed revision.
- **Drift-only trigger** — never fires on gate-only flags (those already have the `max_repair` loop).
- **Default on**; `--no-suggest-fixes` disables.
- `_merge_zh` already `copy.deepcopy`s its input (`translate.py:38`) — do **not** add a redundant copy.
- Spec: `docs/superpowers/specs/2026-07-30-translation-drift-suggested-fixes-design.md`.

---

### Task 1: `suggest_drift_fix` in `translate.py`

**Files:**
- Modify: `content_bank/author/translate.py` (add `_FIX_PROMPT_HEAD`, `_fix_prompt`, `suggest_drift_fix` after `back_translate_review`, ~line 131)
- Test: `content_bank/tests/test_translate.py`

**Interfaces:**
- Consumes (all already in `translate.py`): `_merge_zh(item, resp)`, `zh_gate_flags(item, glossary)`, `back_translate_review(item, *, model)`, `_extract_json(text)`, `llm(prompt, model)`, `_glossary.load_glossary()`.
- Produces: `suggest_drift_fix(item, book, drift, *, glossary=None, model=None) -> dict | None`. Returns `None` when `drift["drift"]` is false. On a changed fix: `{"changed": True, "rationale": str, "item": <revised>, "gate_ok": bool, "gate_flags": [str], "drift": {drift,notes}, "terms": [...], "uncertain": [...]}`. On a declined (CUV-inherent) fix: `{"changed": False, "rationale": str, "item": <original>, "gate_ok": bool, "gate_flags": [str], "drift": <the input drift>}`.

- [ ] **Step 1: Write the failing tests**

Add to `content_bank/tests/test_translate.py`:

```python
class TestSuggestDriftFix(unittest.TestCase):
    ITEM = {"id": "PSA-003-i14", "passage": "PSA.3.1-8", "dimension": "D7",
            "type": "question", "text": {"en": "But You, O LORD.", "zh": "但你耶和华。"}}

    def test_no_drift_returns_none_without_calling_llm(self):
        m = mock.Mock()
        with mock.patch.object(translate, "llm", m):
            out = translate.suggest_drift_fix(self.ITEM, "PSA",
                                              {"drift": False, "notes": ""}, glossary=[])
        self.assertIsNone(out)
        m.assert_not_called()

    def test_changed_fix_is_regated_and_redrifted(self):
        fix = ('{"changed": true, "reason": "removed added imagery",'
               ' "text": {"zh": "但你耶和华。"}, "terms": [], "uncertain": []}')
        redrift = '{"drift": false, "notes": "resolved"}'
        with mock.patch.object(translate, "llm", side_effect=[fix, redrift]):
            out = translate.suggest_drift_fix(
                self.ITEM, "PSA", {"drift": True, "notes": "adds shield imagery"},
                glossary=[])
        self.assertTrue(out["changed"])
        self.assertEqual(out["rationale"], "removed added imagery")
        self.assertEqual(out["item"]["text"]["zh"], "但你耶和华。")
        self.assertFalse(out["drift"]["drift"])       # re-drift ran
        self.assertIn("gate_ok", out)                 # re-gate ran
        self.assertNotIn("zh_mutated", self.ITEM)     # original untouched key-wise
        self.assertEqual(self.ITEM["text"]["zh"], "但你耶和华。")  # original object intact

    def test_declined_fix_returns_original_unchanged(self):
        fix = ('{"changed": false, "reason": "CUV renders it this way",'
               ' "text": {"zh": "但你耶和华。"}, "terms": [], "uncertain": []}')
        with mock.patch.object(translate, "llm", side_effect=[fix]):
            out = translate.suggest_drift_fix(
                self.ITEM, "PSA", {"drift": True, "notes": "guards -> knows"},
                glossary=[])
        self.assertFalse(out["changed"])
        self.assertEqual(out["rationale"], "CUV renders it this way")
        self.assertEqual(out["item"], self.ITEM)      # original returned
        self.assertEqual(out["drift"], {"drift": True, "notes": "guards -> knows"})

    def test_bad_fix_recorded_gate_false_not_raised(self):
        # A changed fix that emits a bare 「…」 with no <verse> tag -> citation flag.
        bad = ('{"changed": true, "reason": "x",'
               ' "text": {"zh": "「耶和华是我四围的盾牌」"}, "terms": [], "uncertain": []}')
        redrift = '{"drift": false, "notes": ""}'
        with mock.patch.object(translate, "llm", side_effect=[bad, redrift]):
            out = translate.suggest_drift_fix(
                self.ITEM, "PSA", {"drift": True, "notes": "n"}, glossary=[])
        self.assertTrue(out["changed"])
        self.assertFalse(out["gate_ok"])              # re-gate caught it
        self.assertTrue(out["gate_flags"])            # recorded, not dropped
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m unittest content_bank.tests.test_translate.TestSuggestDriftFix -v`
Expected: FAIL with `AttributeError: module 'content_bank.author.translate' has no attribute 'suggest_drift_fix'`.

- [ ] **Step 3: Write the implementation**

Add after `back_translate_review` in `content_bank/author/translate.py`:

```python
_FIX_PROMPT_HEAD = (
    "A back-translation drift review found a DOCTRINAL divergence between this "
    "Chinese translation and the original English / Westminster frame. Propose a "
    "revised zh that RESOLVES the drift, under these hard rules:\n"
    "- Every Scripture quote must stay a verbatim CUV span in 「…」 inside its "
    "<verse ...> tag; keep every <verse>/<doctrine> tag and its ref/std unchanged.\n"
    "- Change ONLY what the drift note requires; keep everything else identical.\n"
    "- If the drift exists ONLY because the CUV itself renders the wording this way, "
    "you CANNOT fix it without leaving the CUV. In that case DO NOT change the text: "
    "return changed=false and explain.")


def _fix_prompt(item, notes):
    return (_FIX_PROMPT_HEAD
            + "\n\n## Drift note\n" + (notes or "")
            + "\n\n## Current item (with its zh)\n"
            + json.dumps(item, ensure_ascii=False, indent=2)
            + '\n\nReturn STRICT JSON ONLY: {"changed": true|false, "reason": "...", '
              '"text": {"zh": ...}, "leader_reference": {...}, "terms": [...], '
              '"uncertain": [...]}.')


def suggest_drift_fix(item, book, drift, *, glossary=None, model=None):
    """Given a drift-flagged translated item, ask the model for a CUV-safe revision.

    Returns a suggested_fix dict (see plan), or None when ``drift`` did not fire.
    The original ``item`` is never mutated; on a declined fix it is returned as-is.
    """
    if not drift.get("drift"):
        return None
    glossary = _glossary.load_glossary() if glossary is None else glossary
    resp = _extract_json(llm(_fix_prompt(item, drift.get("notes", "")), model))
    rationale = resp.get("reason", "")
    if not resp.get("changed"):
        flags = zh_gate_flags(item, glossary)
        return {"changed": False, "rationale": rationale, "item": item,
                "gate_ok": not flags, "gate_flags": flags, "drift": drift}
    revised = _merge_zh(item, resp)
    flags = zh_gate_flags(revised, glossary)
    new_drift = back_translate_review(revised, model=model)
    return {"changed": True, "rationale": rationale, "item": revised,
            "gate_ok": not flags, "gate_flags": flags, "drift": new_drift,
            "terms": resp.get("terms", []), "uncertain": resp.get("uncertain", [])}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m unittest content_bank.tests.test_translate.TestSuggestDriftFix -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/translate.py content_bank/tests/test_translate.py
git commit -m "feat(translate): suggest_drift_fix — CUV-safe drift revision (suggest, not replace)"
```

---

### Task 2: Wire `suggest_drift_fix` into the CLI

**Files:**
- Modify: `content_bank/author/translate_cli.py` (`proposal_for` line 44-53, `run_proposals` line 56-83, `main` argparse ~line 105 and the `run_proposals` call ~line 125)
- Test: `content_bank/tests/test_translate_cli.py`

**Interfaces:**
- Consumes: `suggest_drift_fix` (import from `.translate`).
- Produces: proposal dict gains a `suggested_fix` key **only when non-None**; `proposal_for(..., suggest_fixes=True)`, `run_proposals(..., suggest_fixes=True)`, and a `--suggest-fixes` / `--no-suggest-fixes` argparse pair (default True).

- [ ] **Step 1: Write the failing tests**

Add to `content_bank/tests/test_translate_cli.py` (match the file's existing import/mocks — it imports `translate_cli`; patch `translate_cli.translate_with_gates`, `translate_cli.back_translate_review`, and `translate_cli.suggest_drift_fix`):

```python
class TestSuggestFixWiring(unittest.TestCase):
    ITEM = {"id": "PSA-003-i14", "text": {"en": "But You, O LORD.", "zh": "但你。"}}

    def _patch(self, drift, suggested):
        gated = {"item": self.ITEM, "cuv_refs": [], "terms": [], "uncertain": [],
                 "gate_ok": True, "gate_flags": []}
        return (mock.patch.object(tc, "translate_with_gates", return_value=gated),
                mock.patch.object(tc, "back_translate_review", return_value=drift),
                mock.patch.object(tc, "suggest_drift_fix", return_value=suggested))

    def test_drift_flagged_proposal_carries_suggested_fix(self):
        sug = {"changed": True, "rationale": "x", "item": self.ITEM,
               "gate_ok": True, "gate_flags": [], "drift": {"drift": False},
               "terms": [], "uncertain": []}
        a, b, c = self._patch({"drift": True, "notes": "n"}, sug)
        with a, b, c as m:
            p = tc.proposal_for(self.ITEM, "PSA", glossary=[], suggest_fixes=True)
        self.assertIn("suggested_fix", p)
        m.assert_called_once()

    def test_no_drift_no_suggested_fix_and_no_call(self):
        a, b, c = self._patch({"drift": False, "notes": ""}, None)
        with a, b, c as m:
            p = tc.proposal_for(self.ITEM, "PSA", glossary=[], suggest_fixes=True)
        self.assertNotIn("suggested_fix", p)
        m.assert_not_called()

    def test_suggest_fixes_off_suppresses_call(self):
        a, b, c = self._patch({"drift": True, "notes": "n"}, None)
        with a, b, c as m:
            p = tc.proposal_for(self.ITEM, "PSA", glossary=[], suggest_fixes=False)
        self.assertNotIn("suggested_fix", p)
        m.assert_not_called()
```

Ensure the test module has `from content_bank.author import translate_cli as tc` (add if absent) and `from unittest import mock`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m unittest content_bank.tests.test_translate_cli.TestSuggestFixWiring -v`
Expected: FAIL (`proposal_for() got an unexpected keyword argument 'suggest_fixes'`).

- [ ] **Step 3: Write the implementation**

In `content_bank/author/translate_cli.py`:

Update the import at line 15:
```python
from .translate import (translate_with_gates, back_translate_review,
                        suggest_drift_fix)
```

Replace `proposal_for` (lines 44-53):
```python
def proposal_for(item, book, *, glossary=None, model=None, max_repair=2,
                 suggest_fixes=True):
    out = translate_with_gates(item, book, glossary=glossary, model=model,
                               max_repair=max_repair)
    drift = back_translate_review(out["item"], model=model)
    proposal = {"id": item["id"],
                "en": (item.get("text") or {}).get("en", ""),
                "item": out["item"], "cuv_refs": out.get("cuv_refs", []),
                "terms": out["terms"], "uncertain": out["uncertain"],
                "gate_ok": out["gate_ok"], "gate_flags": out["gate_flags"],
                "drift": drift}
    if suggest_fixes and drift["drift"]:
        sug = suggest_drift_fix(out["item"], book, drift,
                                glossary=glossary, model=model)
        if sug is not None:
            proposal["suggested_fix"] = sug
    return proposal
```

Thread the flag through `run_proposals` — add `suggest_fixes=True` to its signature
(line 56-57) and pass `suggest_fixes=suggest_fixes` into the `ex.submit(proposal_for, …)`
call (line 70-71). Extend the progress line (line 82-83) to append `" (fix suggested)"`
when `p.get("suggested_fix", {}).get("changed")` and `" (fix: CUV-inherent)"` when a
`suggested_fix` is present but `changed` is false.

In `main` — add the argparse pair near line 105:
```python
ap.add_argument("--suggest-fixes", dest="suggest_fixes", action="store_true",
                default=True, help="propose a CUV-safe revision for drift-flagged items (default)")
ap.add_argument("--no-suggest-fixes", dest="suggest_fixes", action="store_false",
                help="skip drift fix suggestions")
```
and pass `suggest_fixes=args.suggest_fixes` into the `run_proposals(...)` call (~line 125).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m unittest content_bank.tests.test_translate_cli -v`
Expected: PASS (the new `TestSuggestFixWiring` plus all pre-existing tests).

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/translate_cli.py content_bank/tests/test_translate_cli.py
git commit -m "feat(translate_cli): attach suggested_fix on drift; --suggest-fixes flag"
```

---

### Task 3: Render `suggested_fix` on the review page

**Files:**
- Modify: `content_bank/author/translate_compare_html.py` (cell assembly `build_page` ~line 74-81; `render_html` cell body ~line 128-135; add a `_suggested_block` helper)
- Test: `content_bank/tests/test_translate_compare_html.py`

**Interfaces:**
- Consumes: a proposal's optional `suggested_fix` (`{changed, rationale, item, gate_ok, gate_flags, drift}`).
- Produces: a sub-block under the flagged cell showing the revised zh (or a "no fix" note), its own gate/drift badges, and the rationale.

- [ ] **Step 1: Write the failing tests**

Add to `content_bank/tests/test_translate_compare_html.py`:

```python
class TestSuggestedFixRendering(unittest.TestCase):
    def _cell_with_fix(self, fix):
        return {"zh": "但你。", "ref_zh": "", "verse_zh": "", "cat_zh": "",
                "gate_ok": True, "gate_flags": [], "drift": True,
                "drift_notes": "adds shield imagery", "uncertain": [],
                "suggested_fix": fix}

    def test_changed_fix_renders_revised_zh_and_rationale(self):
        fix = {"changed": True, "rationale": "removed added imagery",
               "item": {"text": {"zh": "但你耶和华。"}},
               "gate_ok": True, "gate_flags": [], "drift": {"drift": False}}
        html = tch._suggested_block(self._cell_with_fix(fix))
        self.assertIn("但你耶和华。", html)
        self.assertIn("removed added imagery", html)

    def test_declined_fix_renders_no_fix_note(self):
        fix = {"changed": False, "rationale": "CUV renders it this way",
               "item": {"text": {"zh": "但你。"}},
               "gate_ok": True, "gate_flags": [], "drift": {"drift": True}}
        html = tch._suggested_block(self._cell_with_fix(fix))
        self.assertIn("CUV renders it this way", html)
        self.assertNotIn("但你耶和华", html)  # no revised text shown

    def test_cell_without_fix_renders_empty_block(self):
        cell = {"zh": "x", "gate_ok": True, "gate_flags": [], "drift": False,
                "drift_notes": "", "uncertain": []}
        self.assertEqual(tch._suggested_block(cell), "")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m unittest content_bank.tests.test_translate_compare_html.TestSuggestedFixRendering -v`
Expected: FAIL (`module ... has no attribute '_suggested_block'`).

- [ ] **Step 3: Write the implementation**

In `build_page` (the cell dict at `translate_compare_html.py:75-81`), carry the fix
through by adding one key:
```python
                        "uncertain": p.get("uncertain", []),
                        "suggested_fix": p.get("suggested_fix")}
```

Add the helper (near `_flag_badges`):
```python
def _suggested_block(cell):
    """Render the drift suggested-fix sub-block, or '' when there is none."""
    fix = cell.get("suggested_fix") if cell else None
    if not fix:
        return ""
    hl = citation_tags.highlight_html
    badges = _flag_badges({"gate_ok": fix.get("gate_ok", True),
                           "gate_flags": fix.get("gate_flags", []),
                           "drift": (fix.get("drift") or {}).get("drift", False),
                           "drift_notes": (fix.get("drift") or {}).get("notes", ""),
                           "uncertain": []})
    if fix.get("changed"):
        zh = hl((fix.get("item") or {}).get("text", {}).get("zh", ""))
        head = f"<div class=zh>{zh}</div>"
    else:
        head = "<div class=nofix>no fix — CUV wording</div>"
    rationale = html.escape(fix.get("rationale", ""))
    return (f"<div class=suggest><span class=reflabel>Suggested fix:</span> {head}"
            f"<div class=srat>{rationale}</div>"
            f"<div class=badges>{badges}</div></div>")
```

In `render_html`, append the block to each cell (line 134-135):
```python
            sug = _suggested_block(c) if c else ""
            cells.append(f"<td><div class=zh>{zh}</div>{ref}{cat}"
                         f"<div class=badges>{_flag_badges(c)}</div>{sug}</td>")
```

Add minimal CSS near the other cell styles (the `<style>` block, ~line 150-162):
```css
 .suggest{{margin-top:6px;padding:6px;border-left:3px solid #f59e0b;background:#fffbeb}}
 .suggest .srat{{font-size:11px;color:#92400e;margin-top:2px}}
 .nofix{{font-style:italic;color:#92400e}}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m unittest content_bank.tests.test_translate_compare_html -v`
Expected: PASS (new `TestSuggestedFixRendering` plus the existing tooltip/render tests).

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/translate_compare_html.py content_bank/tests/test_translate_compare_html.py
git commit -m "feat(review): render drift suggested_fix beneath the flagged cell"
```

---

## Final steps (after all tasks)

- [ ] **Full suite:** `uv run python -m unittest discover -s content_bank/tests -v` → all green.
- [ ] **Smoke on real data (optional, costs LLM calls):** re-translate one PSA drift item and regenerate the page:
  ```bash
  uv run python -m content_bank.author.translate_cli --book PSA \
      --drafts-dir work/content_bank_build/PSA/runs/opus/drafts --items PSA-003
  uv run python -m content_bank.author.translate_compare_html PSA \
      --draft-run opus --translators deepseek-v4-flash
  ```
  Confirm a `suggested_fix` appears on a drift item and renders on `runs/opus/translations/review.html`.
- [ ] **Docs:** add a short "Drift suggested fixes" note to `docs/content_translator_usage.md` (the `--suggest-fixes` flag, the `suggested_fix` proposal field, and that it's suggest-and-confirm).

## Self-Review

- **Spec coverage:** Task 1 = `suggest_drift_fix` + CUV-safe prompt + decline path (spec §Design/Testing); Task 2 = wiring + flag (spec §Wiring); Task 3 = rendering (spec §Rendering). Promotion and auto-fix are out of scope in both. ✅
- **Type consistency:** `suggested_fix` shape is identical across producer (`suggest_drift_fix`, Task 1), carrier (`proposal_for`, Task 2), and consumer (`_suggested_block`, Task 3): keys `changed, rationale, item, gate_ok, gate_flags, drift` (+ `terms/uncertain` on changed). `_flag_badges` input keys (`gate_ok, gate_flags, drift, drift_notes, uncertain`) match what `_suggested_block` constructs. ✅
- **No placeholders:** every code and test step is complete. ✅
- **Mock arity:** the changed-fix tests use `side_effect=[fix, redrift]` because `suggest_drift_fix` calls `llm` twice on that path (fix + re-drift); the declined path uses one. ✅
