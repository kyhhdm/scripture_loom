# Model-aware run directories — design

**Date:** 2026-07-21
**Status:** approved (design), implementing
**Related:** `content_bank/author/build_cli.py` (issue #16 standalone builder);
`docs/superpowers/specs/2026-07-21-multi-run-comparison-page-design.md` (the comparison page this reorganizes for).

## Problem

The standalone builder scatters a model's intermediate artifacts: pericope briefs live in a single shared `content_bank/author/briefs/`, drafts go to ad-hoc sibling dirs (`drafts_py`, `drafts_pro`), sections have **no brief stage at all**, and `--review` verdicts are **computed but never saved**. Nothing ties one model's brief + draft + review together, so comparing models means guessing which flat dir belongs to which run.

We are experimenting across models (deepseek flash/pro, Opus). We want each model's **entire pipeline** — brief, draft, review — organized under one folder keyed by the model, so a run is self-contained and reproducible, and the comparison tool measures each model's whole job.

## Decisions (from dialogue)

- **`--review` on by default**; add `--no-review` to opt out.
- **Slug = full resolved model id** (`deepseek-v4-flash`, `deepseek-v4-pro`, `opus`).
- **Pericope briefs are model-dependent** (generated per run, not shared).
- **Sections get full parity**: a new section-brief distillation stage, saved to file, then arc content drafted *from* that brief.
- **Layout: one run directory per model** (the nested `drafts/<model>` scheme, generalized to all artifacts).

## Layout

```
work/content_bank_build/<BOOK>/
  manifest.json                    # canonical unit list (kind) — unchanged, model-agnostic
  runs/<model-slug>/
    manifest.json                  # this model's stage ledger, seeded from the canonical list
    briefs/<unit>.md               # per-model briefs (pericope AND section)
    drafts/<unit>.json             # per-model drafted items
    verdicts/<unit>.json           # per-model review results (item-keyed), when --review runs
```

The canonical `<BOOK>/manifest.json` stays the source of the unit list; each run's
`manifest.json` is seeded from it (all `pending`) and tracks that model's progress
independently.

## Consequence, accepted

Model-dependent briefs mean the comparison no longer holds the brief fixed — it now
measures each model's **whole pipeline** (its brief and its drafts). `compare_html`
is updated to read per-run briefs and show each run's own brief per unit.

## Components

### Section prompts (rename + new)

- `build_section_brief_prompt.py` (currently the section **content** prompt, misnamed)
  → renamed **`build_section_draft_prompt.py`**; `build(sid, book, brief="")` now
  embeds the section brief before the content shape/schema.
- New **`build_section_brief_prompt.py`** = a genuine section-brief distillation
  prompt: from the section's pericope texts + WCF ch.1, produce a compact arc brief
  (the arc's spine, recurring motifs with member verse refs, cross-pericope
  connections, doctrinal anchors) — the section analogue of `build_brief_prompt`.

Parallel naming after the change: pericope = `build_brief_prompt` + `build_draft_prompt`;
section = `build_section_brief_prompt` + `build_section_draft_prompt`.

### `build_cli.py`

- `_effective_model(backend, model)` → `model` or the backend default
  (`deepseek-v4-flash` for llm_core, `opus` for claude).
- `_run_slug(backend, model)` → the effective model id, lower-cased, non-`[a-z0-9.]`
  → `-`.
- `_run_layout(book, slug, root)` → the run's `{manifest, briefs, drafts, verdicts}`
  paths; seeds `runs/<slug>/manifest.json` from the canonical book manifest if absent.
- `_verdicts_by_item(review_out)` → converts `review()`'s reviewer-keyed output
  (`[{reviewer, verdicts:{id:{verdict,notes}}}]`) into the item-keyed file format
  (`{id:[{reviewer,verdict,notes}]}`) that `compare_html` and the existing files use.
- `build_pericope` / `build_section` gain `verdicts_dir`; when review runs they write
  `verdicts/<unit>.json`. `build_section` gains the brief→draft split (brief stage
  writes `briefs/<sid>.md` and bumps stage to `briefed`, mirroring pericopes).
- `run()`: when neither `manifest_path` nor `drafts_dir` is passed (the normal CLI
  path), derive the run layout from the slug and use the per-run manifest; when they
  are passed (existing tests / advanced use), keep the legacy explicit-dir behavior.
- `main()`: `--review` defaults **True** (`--no-review` to disable); add
  `--verdicts-dir` and `--run-root` overrides.

### `compare_html.py`

- A run name resolves to `<BOOK>/runs/<name>` if present, else `<BOOK>/<name>` (legacy
  flat dirs still work). Draft files come from `<rundir>/drafts/` if present else
  `<rundir>/` directly. Verdicts from `<rundir>/verdicts/` if present else the shared
  `<BOOK>/verdicts/`.
- Briefs become **per run**: each unit carries `briefs: {run: text|None}`, read from
  `<rundir>/briefs/<unit>.md`, falling back to the shared `author/briefs/<unit>.md`.
- The page shows one brief panel if all runs share identical brief text, else one
  collapsible brief panel per run.

## Backward compatibility

- `build_pericope` / `build_section` keep their explicit-dir signatures (plus the new
  optional `verdicts_dir`), so existing `build_cli` tests pass unchanged.
- `compare_html` legacy resolution keeps the old flat `drafts_py` / shared-verdicts /
  shared-briefs data working.

## Testing

- `test_section_prompt.py`: point content-schema assertions at
  `build_section_draft_prompt`; add a section-brief prompt test.
- `test_build_cli.py`: add `_run_slug` / `_verdicts_by_item` unit tests, a section
  brief→draft build test, and a verdict-persistence test.
- `test_compare_html.py`: update to the per-run `briefs` dict; add per-run brief and
  `runs/<slug>` resolution tests.
