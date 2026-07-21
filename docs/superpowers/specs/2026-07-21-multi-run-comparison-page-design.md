# Multi-run comparison review page — design

**Date:** 2026-07-21
**Status:** approved (design), pending implementation
**Related:** issue #16 standalone builder; `docs/sessions/2026-07-20-php-python-vs-claude-comparison.md` (the manual four-way comparison this tool automates)

## Problem

We are running content-bank builds with different LLM models (deepseek flash / pro, Opus via `--backend claude`, the Claude Code workflow) and gate variants, each landing in a sibling `work/content_bank_build/<BOOK>/drafts*/` directory. Re-affirming that **human review is the ultimate quality gate** requires a reviewer to compare these runs and pick the best content. Today that comparison is entirely manual: open several `drafts_*/PHP-001.json` files by hand and mentally diff them. There is no reviewer-facing interface of any kind (the only HTML in the repo is the unrelated prototype kit generator).

The known model failure mode (documented in the 2026-07-20 comparison session) is **dimension padding and off-genre items** — a cheaper model emits more, weaker items per dimension while all deterministic gates stay green. So the comparison must make per-dimension item volume and per-item quality visible side by side.

## Goal

A single self-contained HTML page that shows multiple runs side by side for one book, lets a human accept/reject individual items, and exports those decisions as JSON. It is a review **instrument**, not a publish path — it never writes the store.

## Non-goals (YAGNI)

- No server, no live reload, no store writeback, no auto-promote.
- No auth.
- No cross-unit or per-dimension "winner" rollup — decision grain is per-item.
- No on-page seven-axis rubric checkboxes — per-item accept *is* the decision; the rubric (`rubric.py`, `review_checklist.py`) stays the reviewer's mental checklist.
- No browser/JS test harness.

## Decisions (from brainstorming)

- **Interactivity:** capture decisions (per-item accept) + export JSON. Read-only-plus.
- **Delivery:** static generator → one self-contained HTML file. No server.
- **Run scope:** named runs via `--runs` argument.
- **Decision grain:** per-item accept/reject.
- **Layout:** all dimensions for a unit visible at once, each dimension block collapsible.
- **Stopping point:** export `decisions.json`; a separate future step consumes it to promote. Not in this scope.

## Architecture

Two components: a Python generator and the embedded page it emits. Data flows one way (JSON files → generator → embedded HTML); the page's only output is a downloaded decisions file.

### Component 1 — `content_bank/author/compare_html.py` (generator)

CLI:

```
uv run python -m content_bank.author.compare_html PHP \
    --runs drafts_py,drafts_pro,drafts_claude \
    [--out work/content_bank_build/PHP/review.html]
```

Responsibilities:

1. **Load.** For book `PHP`, for each run dir in `--runs`, read every `<UNIT>.json` under `work/content_bank_build/PHP/<run>/`. Each file is a flat JSON list of items. A run may be missing a unit file (treated as zero items for that unit).
2. **Shape.** Build a nested model **unit → dimension (D1–D8) → run → [items]**. Cells are ragged by design (0–3 items). Preserve item order within a run.
3. **Gate (best-effort).** Per run's per-unit items:
   - `gates.schema_check` — always (no corpus dependency).
   - `gates.quote_check` and `gates.refs_in_range` / `thread_span_check` — run **if** the book text and allowed ranges load from the corpus/pericope layer; otherwise skip and record a page-level note "quote/range gates not run (corpus text unavailable)."
   - Store per-item gate result: `ok` or a list of problem strings.
4. **Verdicts (best-effort, id-match only).** If `work/content_bank_build/PHP/verdicts/<UNIT>.json` exists, attach a verdict to an item **only when the item id is a key** in that file. Verdict ids historically use slugs (`php1-d1-writers`) that do not match numbered draft ids (`php-001-d1-001`), so most items will show "no verdict"; that is expected and must not error.
5. **Emit.** Write one self-contained HTML file: inline `<style>`, inline `<script>`, and the shaped model embedded as `<script type="application/json" id="review-data">…</script>`. No external requests, no third-party libraries.

The generator does no ranking or judgment — it only assembles and annotates. All quality judgment is the human's, on the page.

### Component 2 — the embedded page (vanilla JS, no deps)

- **Unit nav:** a sticky list/select of units (PHP-001 …). Selecting a unit renders its dimension blocks.
- **Dimension blocks:** all of D1–D8 present for the unit are shown, each a collapsible block. Block header shows the dimension and, per run, that run's item count for the dimension (so padding is visible at a glance, e.g. `D6 — flash:3 pro:2 opus:1`).
- **Columns:** within a block, one column per run (column header = run name + count).
- **Item card:** `text.en`; chips for `age_tier` / `difficulty` / `type`; a **gate badge** (green "ok" or amber with the problem reason on hover); a **verdict badge** when matched (else "no verdict"); and an **accept checkbox**.
- **Tally + export:** a fixed header shows `N accepted / M total`. An **Export decisions** button downloads `decisions.json`.
- **Persistence:** accept state mirrors to `localStorage` keyed by book so a reload does not lose work. Export reads current state.

### `decisions.json` shape

```json
{
  "book": "PHP",
  "runs": ["drafts_py", "drafts_pro", "drafts_claude"],
  "generated_from": "review.html",
  "accepted_item_ids": ["php-001-d1-001", "..."],
  "rejected_item_ids": ["php-001-d1-002", "..."]
}
```

An item is "rejected" only if explicitly unchecked after being touched; untouched items appear in neither list (undecided). Consuming this file to promote items is a separate, future, human-gated step and is out of scope here.

## Data contracts (verified against real files)

- Draft item (in `drafts*/<UNIT>.json`, flat list): `id`, `passage` **or** `section`, `dimension` (D1–D8), `type`, `age_tier`, `difficulty`, `review_status`, `text` (lang map, at least `en`), `version`; optionally `leader_reference`, `refs`.
- Verdict file (`verdicts/<UNIT>.json`): `{ <item-id-or-slug>: [ {reviewer, verdict, notes}, ... ] }`.

## Error handling

- Missing run dir → hard error listing which of `--runs` was not found.
- Missing unit file within a run → that run contributes zero items for the unit (no error).
- Item missing `text.en` → render `(no en text)` placeholder, do not crash.
- Corpus text/ranges unavailable → skip quote/range gates, show page-level note, still emit the page.
- Verdict id not matching any item → ignored silently (expected).

## Testing

`content_bank/tests/test_compare_html.py`, using a small synthetic fixture of two runs × two units under a temp dir:

- Ragged alignment: a dimension where run A has 2 items and run B has 0 is shaped correctly.
- Missing unit file in one run yields zero items, not an error.
- Verdict id-match: a matching id attaches its verdict; a non-matching slug does not, and does not error.
- Gate best-effort: schema check runs; quote/range gates skipped cleanly when corpus text is absent, with the note recorded.
- Output is a single file containing the embedded JSON and no external `http(s)://` resource references.

No JS is unit-tested; the page logic is exercised manually via the `verify` skill after generation (open the emitted file, toggle accepts, export, inspect JSON).

## File touch list

- `content_bank/author/compare_html.py` — new generator + CLI + embedded HTML/JS template.
- `content_bank/tests/test_compare_html.py` — new tests.
- Reuses: `content_bank/author/gates.py`, `content_bank/lib/schema.py`, corpus passage read path (best-effort).
