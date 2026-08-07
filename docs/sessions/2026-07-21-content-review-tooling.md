# Content review tooling + model-aware build pipeline

- **Date:** 2026-07-21
- **Branch / commits:** `feature/content-review-tooling` → merged to `main` as PR #21 (merge commit `9877a36`). Key commits: `60e650c` (design spec), `1f7e15f` (comparison page), `30ad4af` (model-aware run dirs), `498df24` (provenance), `a886482` (leader refs on page), `576f04c` (section leader_reference fix), `8b007de` (tooltip escaping fix), `2000cd0` (terminology doc), `eff5ae6` (usage doc), `2837cea` (CLAUDE.md links).
- **Summary:** Started from "what supports a reviewer to judge content quality and compare runs from different models?" and built the answer end-to-end: a self-contained comparison HTML page, a model-aware build pipeline (each model's whole pipeline under its own run dir), item provenance stamping, two docs, and live comparison builds of Philippians with deepseek-v4-flash vs opus.

## Request

A sequence of requests, each building on the last:
1. Explain what reviewer support exists in the repo for judging content quality and comparing runs from different LLM models.
2. Build a multi-run comparison page (interactive HTML).
3. Make the whole build pipeline model-aware: `--review` by default, model-scoped output dirs, model-dependent briefs, saved section briefs — organize all intermediates (briefs, drafts, review results, section content) by model.
4. Author a real section-brief stage (sections previously had none).
5. Build Philippians units and sections with two models and compare them.
6. Fix gaps found while reviewing (answer keys/notes missing, tooltip not showing).
7. Write terminology + usage docs, link them from CLAUDE.md.
8. Open and merge the PR.

## What we did

- **Surveyed reviewer support** (via an Explore agent): found the human review checklist/digest, deterministic gates, adversarial r1/r2 review, and the structural publish gate — but no visual UI and no cross-model comparison tool. Confirmed there was no interactive HTML interface (only the unrelated prototype kit generator).
- **Designed and built the comparison page** (`compare_html.py`) after a brainstorming pass: static generator → one self-contained HTML file, per-item accept → `decisions.json` export, named runs, per-item decision grain. Verified in-browser (accept toggles, cross-run cherry-pick, tally).
- **Added rubric + per-unit brief panels** to the page. Caught a real bug here: `_PAGE` was a plain Python string so `\n` in the new JS regexes became literal newlines and broke the page (`SyntaxError`); fixed by making it a raw string, guarded by a test.
- **Reorganized the builder to be model-aware** (design spec `2026-07-21-model-aware-run-directories-design.md`): each model's pipeline lives under `work/content_bank_build/<BOOK>/runs/<model-id>/{manifest,briefs,drafts,verdicts}`. `--review` defaults ON (`--no-review` added); verdicts are now **persisted** (previously computed then discarded — which is why only the old workflow's PHP-001 had a verdict file). Briefs became model-dependent. Legacy explicit-dir mode preserved so existing tests pass.
- **Gave sections full brief→draft parity:** the mis-named `build_section_brief_prompt` (actually the content prompt) was renamed to `build_section_draft_prompt` and now takes a brief; a genuine new `build_section_brief_prompt` distills the section arc. `compare_html` updated to read per-run briefs and `runs/<slug>/`.
- **Stamped model/run onto provenance:** `{model, backend, run}` added to drafts at write time and preserved through `publish.stamp()`; `drafted_by` now resolves to the model instead of the hardcoded `"claude"`. Round-trip verified into a temp store.
- **Ran live comparison builds:** PHP-001–004 and PHP-S1/S2 with `deepseek-v4-flash` (llm_core) and `opus` (claude backend). Flash: ~16 min, ~$0.15, 20–25 items/unit. Opus: leaner (11–17 items/unit). Opus's PHP-S1 first attempt hard-failed on an invalid `leader_reference.kind: "scripture"`; a `--max-repair 4` retry cleared it.
- **Fixed two review-time gaps found in the data:** (1) section questions had **no** answer keys/leader notes because the section draft prompt only mentioned `leader_reference` in prose, not in its JSON example — inlined the shape and rebuilt both models' sections. (2) verdict tooltips silently vanished because notes quote Scripture (contain `"`) and `esc()` didn't escape quotes for the `title="..."` attribute — added `escAttr()`.
- **Answered several terminology questions** (throughline, thread, why statement items have no answer/note, the effect of an r1/r2 fail) and captured them in a durable glossary.
- **Wrote two docs** — `content_build_terminology.md` (glossary) and `content_builder_usage.md` (how to run `build_cli.py`) — and linked both from `CLAUDE.md`.
- **Opened PR #21**, then merged it. The direct `gh pr merge` was blocked by the auto-mode classifier (a layer separate from the permission allowlist, which already permitted the command); the user merged with `gh pr merge 21 --merge --admin`.

## Artifacts

New/changed code:
- `content_bank/author/compare_html.py` — comparison page generator (new)
- `content_bank/author/build_cli.py` — model-aware run layout, run slug, verdict persistence, provenance stamp, `--review` default, `--no-review`/`--verdicts-dir`/`--run-root`
- `content_bank/author/build_section_brief_prompt.py` — new arc-brief prompt
- `content_bank/author/build_section_draft_prompt.py` — renamed from the old section content prompt; takes a brief; inlined `leader_reference` shape
- `content_bank/author/publish.py` — preserve `{model, backend, run}`; `drafted_by` from model
- Tests: `test_compare_html.py` (new), plus additions to `test_build_cli.py`, `test_publish.py`, `test_section_prompt.py`, `test_author.py`

Docs / specs:
- `docs/superpowers/specs/2026-07-21-multi-run-comparison-page-design.md`
- `docs/superpowers/specs/2026-07-21-model-aware-run-directories-design.md`
- `docs/content_build_terminology.md`
- `docs/content_builder_usage.md`
- `CLAUDE.md` (links to both docs)

Build artifacts (working files under `work/`, not committed):
- `work/content_bank_build/PHP/runs/deepseek-v4-flash/` and `.../runs/opus/` (briefs, drafts, verdicts for PHP-001–004, PHP-S1, PHP-S2)
- `work/content_bank_build/PHP/review-flash-vs-opus.html` (generated comparison page)

## Outcome

- PR #21 **merged** to `main` (`9877a36`). Full content-bank test suite passing (196+ tests) at each step.
- Reviewers now have a self-contained side-by-side comparison page showing gate/verdict badges, the seven-axis rubric, per-run briefs, and answer-key/leader-note blocks, with an accept→`decisions.json` export.
- The builder produces self-contained per-model runs; model identity survives to the store via provenance.
- Live flash-vs-opus comparison of Philippians (pericopes + first two sections) produced and reviewable.

## Follow-ups

- **Consume `decisions.json`** — a promote step that turns the page's accepted items into a `reviewed → published` store advance (still human-gated). Not built.
- **Local `main` is one behind `origin/main`** — the PR merge commit was created on GitHub; fast-forward local `main` and delete the merged `feature/content-review-tooling` branch when convenient.
- The Chrome **screenshot API errored** for part of the session (extension-side bug); later verification was done via page text / data checks rather than screenshots.
- Untracked `work/content_bank_build/build_sections*.workflow.js` still import the old `build_section_brief_prompt` name (now a brief, not content) — superseded by `build_cli`; fix or delete if revived.
