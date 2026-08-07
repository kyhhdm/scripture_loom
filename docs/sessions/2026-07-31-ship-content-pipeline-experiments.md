# Building and shipping the content-pipeline experiment framework (issue #35)

- **Date:** 2026-07-31 (through merge on 2026-08-07)
- **Branch / commits:** `feature/content-pipeline-experiments` → merged to `main` as `be64dce` (PR #38, +5,350 lines). Key commits: `c17f79b` (genre_probe_hybrid), `231d98d`/`eeae284` (built-unit fit filter), `c88e689` (raw-draft freeze + `--reuse-drafts`), `70f58ef` (compare page first-draft-vs-final).
- **Summary:** Designed, built, and merged the full scope of issue #35 — named content-pipeline experiments with per-stage model routing, normalized token/timing telemetry, gate traces, a D1–D8 classification-fit evaluator, cross-book experiments, frozen-draft reuse, and a comparison web page. Issue #35 auto-closed on merge.

## Request
The user asked, in sequence: evaluate issues #35 and #36; build #35 first (full scope) and open a PR; import existing Opus draft runs (PHP/JON/ECC) as baselines; add cross-book experiment support and fold it into PR #38; make `compare` emit a single correctly-named file and confirm a D1–D8 classification-error evaluator exists; wire a sonnet-vs-opus comparison with an independent evaluator; create a hybrid config to test whether cheap models can run non-draft steps without quality loss; persist intermediate results so expensive Claude calls can be skipped on re-runs; surface the first-round draft in the comparison page so reviewers see repair/revise edits; then merge PR #38, delete the branch, pull `main`, and close #35.

## What we did
- **Sequenced #35 before #36.** Prior measurement showed the subscription quota is usage-metered, not invocation-metered, weakening #36's (draft-packing) motivation; #35 is the prerequisite for measuring it anyway. Built #35 in full via brainstorming → spec → plan → implementation.
- **Per-stage routing** (`routing.py`): `Route(backend, model, settings)` + `RouteConfig` over stages `brief/draft/repair/review_r1/review_r2/revise`, replacing the removed process-wide `SCRIPTURE_LOOM_LLM_BACKEND/MODEL` env switching.
- **Telemetry** (`telemetry.py`): `LLMResult`/`CallRecord`, append-only JSONL sink, `usage_source` tagged `provider` (claude `-p --output-format json`) vs `local_estimate`. Discovered Claude prompt caching splits input into `input`/`cache_creation`/`cache_read` — the uncached `input` field is tiny, so totals must sum all three (this explained a "tokens_in: 50" anomaly the user flagged).
- **Immutable named experiments** (`experiment_config.py`): `config_hash` folds config + `corpus_rev` + prompt version; credential-leak scan rejects `api_key`/`token` fields.
- **Cross-book experiments:** omit `book`, list units spanning books (`genre_probe` = PSA-003, PHP-002, JON-002, ECC-018); runner groups by book and merges telemetry/traces/report under one name.
- **D1–D8 fit evaluator** (`quality_eval.py`): independent judge returns accurate/mixed/misclassified; `evaluate … --fit --fit-model <judge>` fit-scores an already-built baseline with a shared third-model judge for fair classification-error comparison. Established the `evaluator_is_drafter` guard (a judge that also drafted is not independent).
- **Frozen-draft reuse** (`c88e689`): persist each unit's pre-review `raw_drafts/`; `--reuse-drafts SOURCE` skips brief+draft (no Opus cost), running only downstream ops from an identical draft so comparisons isolate the ops stages.
- **Compare page first-draft-vs-final** (`70f58ef`): the page now reads `raw_drafts/` and marks edited items (`changed` chip + collapsible "1st draft" block), retagged items (e.g. D3→D7 badge), and dropped items (dashed ghost cards); acceptance tally excludes dropped cards.
- **Finding from `genre_probe_hybrid`** (Opus draft, deepseek repair/review/revise, gemini judge): cheap ops fail to converge gates on quote-dense units (PSA-003, PHP-002) — consistent with prior "cheap models weak on quote-dense citation" results. Gates protect accepted-item quality; yield drops. Conclusions the user recorded: Opus draft quality > sonnet; gemini-3.6-flash is adequate for D1–D8 classification.
- **Merge & cleanup:** PR #38 was `MERGEABLE`/`CLEAN`; merged to `main`, fast-forwarded local `main` to `be64dce`, deleted local + remote feature branch. Issue #35 auto-closed via the PR reference.

## Artifacts
- New modules: `content_bank/author/{routing,telemetry,experiment_config,experiment_cli,experiment_report,quality_eval}.py`; edits to `build_cli.py`, `llm.py`, `review.py`, `translate.py`, `translate_cli.py`, `compare_html.py`, `translate_compare_html.py`; `llm_core/sync.py` (`run_sync_llm_result`).
- Experiments: `experiments/{example,genre_probe,genre_probe_sonnet,genre_probe_hybrid}.json`.
- Docs: `docs/content_experiment_usage.md`, `docs/content_quality_evaluator_usage.md`, spec `docs/superpowers/specs/2026-07-31-content-pipeline-experiments-design.md`, plan `docs/superpowers/plans/2026-07-31-content-pipeline-experiments.md`, `docs/superpowers/specs/2026-08-01-experiment-translate-and-compare-design.md`.
- Tests: new suites for routing/telemetry/experiment config/runner/report/quality_eval plus fixture updates — full content_bank + corpus suites green.
- PR #38 (merged, `be64dce`); issue #35 (closed).

## Outcome
Issue #35 shipped to `main`: named, immutable, single- or cross-book experiments run the real gated pipeline with per-stage routes, emit normalized per-call telemetry and gate traces, run the D1–D8 fit evaluator on a fixed independent route, support frozen-draft reuse to iterate cheap stages without re-paying Opus, and produce a single comparison page that surfaces review edits. Branch deleted, `main` pulled.

## Follow-ups
- `raw_drafts/` is captured going forward only — experiments built before it shipped (e.g. the imported `genre_probe` baseline) must be re-run once to freeze drafts before `--reuse-drafts` works against them.
- Optional: re-score `genre_probe` with the gemini judge for a fully fair sonnet-vs-opus classification comparison.
- #36 (draft packing) remains deferred; #35 is now available to measure it if revisited.
