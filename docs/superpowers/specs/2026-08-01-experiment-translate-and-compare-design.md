# Experiment CLI: translation step + comparison tools

- **Follows:** #35 experiment framework (PR #38).
- **Date:** 2026-08-01
- **Status:** Approved; implementing.

## Problem

1. **Translation is broken in production.** The #35 seam refactor changed `llm(prompt, route)`; `translate.py` still calls `llm(prompt, model_string)` → `'str' object has no attribute 'backend'`. Only green because translate tests mock the seam.
2. The experiment CLI can't translate an experiment's drafts, and `compare` requires `--book` (awkward for cross-book experiments and baseline comparison). No ZH translation comparison exists in the experiment CLI.

## Part 1 — Migrate `translate.py` onto routes (bugfix)

Change the five seam call sites to explicit routing:
- `translate_item(item, book, *, glossary=None, route=None)` → `llm_text(prompt, route or route_from_env())`.
- `translate_with_gates(..., route=None, sink=None, attr=None)`.
- `back_translate_review(item, *, drift_route=None, sink=None, attr=None)`.
- `suggest_drift_fix(..., route=None, drift_route=None, sink=None, attr=None)`.
- `_cuv_divergence_note(item, notes, route=None)`.

`translate_cli` builds `Route(backend, model)` and `Route(backend, drift_model or model)`, passes them down, and drops its `os.environ["SCRIPTURE_LOOM_LLM_BACKEND"]` line. Telemetry: an optional `sink` + attribution (experiment, unit_id, kind) recorded per seam call via `telemetry.record_call`, stages `translate` / `translate_repair` / `drift` / `translate_fix`. Default (`sink=None`) records nothing — the normal `translate_cli` is unaffected.

## Part 2 — `experiment_cli translate NAME`

- **Config:** optional `translate` and `drift` route blocks (not in `routing.STAGES`; validated only if present). Absent ⇒ default `{"backend":"llm_core","model":"deepseek-v4-flash"}` for translate, drift = translate.
- **Command:** `translate NAME [--out-root R] [--concurrency N] [--drift-model M]`. For each book in the experiment: load `…/runs/NAME/drafts/*.json`, run `translate_cli.run_proposals(items, book, route=…, drift_route=…, glossary=…, sink=shared)`, write proposals to `…/runs/NAME/translations/<translate-slug>/`. Append telemetry to the experiment's `calls.jsonl`. Proposals stay draft-only; promotion is unchanged and human-gated.

## Part 3 — Comparison

- **`compare`:** `--book` optional. Omitted ⇒ discover books across the named experiments (union of `manifest["books"]`/`book`), and for each book render `compare_<BOOK>.html` from only the experiments that contain it.
- **`compare-translations` (new):** per book, render an English ▸ CUV ▸ zh-per-experiment review page from each experiment's translation proposals (adapting `translate_compare_html`). `--book` optional with the same auto-discovery.

## Testing (network-free; seam mocked)

Per part: translate route dispatch + telemetry recording; `translate` subcommand writes proposals + telemetry under the experiment; `compare` auto-book discovery + presence filtering; `compare-translations` renders EN/CUV/zh columns. Full suite stays green.

## Non-goals

- Auto-promoting translations (stays human-gated).
- Changing CUV/glossary/drift gate semantics.
