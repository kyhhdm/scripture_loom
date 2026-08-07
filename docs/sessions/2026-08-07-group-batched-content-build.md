# Group-batched content build mode

- **Date:** 2026-08-07
- **Branch / commits:** `feature/group-batched-content-build` (merged, deleted) → **PR #39**, merged to `main` as `8f4422e`. Feature commits: `82f2a07` (spec), `98ee44c` (plan), `bfa1366` (group build mode), `14bc592` (group docs), `f8b8a7f` (experiment wiring), `a0c714f` (draft-batch cap), `4fcd383` (doc refresh).
- **Summary:** Designed and shipped a `--group` execution mode for the content builder that batches a section + its pericopes into one LLM call per stage — cutting request count on the Opus/subscription backend — then wired it into the experiment runner, validated it with a real A/B on PHP-S2, added a draft-stage batch cap to close the residual gap, and merged the whole stack.

## Request
The user proposed batching a section and all its pericopes into single LLM calls per stage (brief → draft → review → revise), sending multiple items per request to cut cost. They first asked for a critique, then — after the design converged — asked to build it, wire it into the experiment runner, run an A/B validation, add a unit-count cap, update docs, and merge.

## What we did
- **Critique → convergence.** Initial critique pushed back: batching saves input tokens (better via prompt caching) but not output tokens; the draft stage risks truncation on a cheap model; blast radius, telemetry attribution, and attention dilution were concerns. The user reframed the constraint that changed the calculus: on the `claude`/Opus **subscription** backend, the usage window meters **request count** as well as tokens, so collapsing calls is a first-class win. With Opus (not a cheap model) and failed-units-only repair/revise, the objections largely dissolved.
- **Design (spec + plan).** Group = a section + its span's pericopes. Batch at the LLM I/O boundary only: each stage wraps the *existing* per-unit prompts in a `{"units":{…}}` envelope (max fidelity, no re-derived instructions), then splits the response back into the unchanged per-unit gates/manifest/store path. A `stop_reason == max_tokens` / missing-unit / unparseable envelope triggers **bisection** — split the group and retry halves down to singletons, so no unit is silently dropped.
- **Implementation (TDD).** New `build_group.py` + `build_group_prompt.py`; `review.review_group`/`revise_group` (batch within each lens; r1/r2 stay independent); `build_cli --group`. Caught and fixed a test-isolation bug where a wrongly-targeted mock let the real gate flag skeleton items and shell out to a live `claude` subprocess (the 120s hang) — the fix was patching the name `build_cli` actually binds (`build_cli.run_all`).
- **A/B on PHP-S2 (real Opus).** Ran per-unit vs group arms with telemetry. Result: **34 → 9 calls (3.8×)**, **input tokens 1.51M → 0.60M (−60%)**, output −18%, quality comparable at n=1 (group r1/r2 fail rate 11.7% vs 20%, and 0 gate-repair rounds vs 4). Corrected an initial token miscount — `claude -p` reports only *uncached* input, so the real volume lives in the cache fields. Key finding: the **draft** stage omitted units at 6-per-call and bisected to 5 calls, eating most of the draft savings.
- **Comparison page.** Built via the repo's own `compare_html.build_model` (resolve-override), two columns = the two arms, per-unit × dimension with gate flags, r1/r2 verdicts, citation highlighting, and briefs.
- **Experiment integration.** Added config `"execution": "group"` routing an experiment through `group_run`, writing the same per-unit artifacts **and gate traces** so `report.json` metrics are comparable to a `per_unit` run. This required **aligning the group review-on flow to the per-unit gate point** (draft → review → revise → gate **once** after revise), removing an earlier double-gate that would have inflated `first_pass_gate_rate` — so the inconsistency fix was a prerequisite, not a separate follow-up. (When the user later asked to "fix the inconsistency," it was already done in this commit; verified against the code.)
- **Draft-batch cap.** `--draft-batch-size` / config `draft_batch_size` (default **4**), draft-stage only, to keep each draft call reliable and off the bisection guard. Draft-only because the draft envelope has no cross-unit dependency (each unit drafts from its own brief), unlike the section brief.
- **Docs + merge.** Refreshed spec follow-ups (marked done), CLAUDE.md, terminology, usage docs, and project memory. Opened/updated PR #39 and merged it to `main`.

## Artifacts
- **New:** `content_bank/author/build_group.py`, `content_bank/author/build_group_prompt.py`; tests `content_bank/tests/test_build_group.py`, `test_build_group_prompt.py`, `test_review_group.py`.
- **Modified:** `content_bank/author/review.py` (`review_group`/`revise_group`), `build_cli.py` (`--group`, `--draft-batch-size`), `experiment_cli.py` (execution dispatch), `experiment_config.py` (validate `execution`, `draft_batch_size`); tests `test_experiment_config.py`, `test_experiment_runner.py`.
- **Configs:** `experiments/php_s2_per_unit.json`, `experiments/php_s2_group.json` (matched A/B pair).
- **Specs / plan:** `docs/superpowers/specs/2026-08-07-group-batched-content-build-design.md`, `docs/superpowers/specs/2026-08-07-draft-batch-size-cap-design.md`, `docs/superpowers/plans/2026-08-07-group-batched-content-build.md`.
- **Docs:** `docs/content_builder_usage.md`, `docs/content_experiment_usage.md`, `docs/content_build_terminology.md`, `CLAUDE.md`.
- **Review page (git-ignored):** `work/content_bank_build/PHP/review-ab-per-unit-vs-group.html`; A/B run tree under the session scratchpad.

## Outcome
Merged to `main` (PR #39, `8f4422e`). Full content-bank suite green at merge: **`Ran 477 tests … OK`**. Group mode ships with the bisection guard, the draft-batch cap (default 4), the experiment `execution: "group"` path with comparable gate metrics, and complete docs. A/B validated the core premise (3.8× fewer calls, −60% input tokens, no quality regression at n=1).

## Follow-ups
- **K-trial A/B** (repeat the per-unit vs group comparison over several trials) before adopting group mode as the **default** authoring path — the single-trial quality edge is suggestive, not conclusive.
- Re-measure with the draft-batch cap in place: PHP-S2 draft should drop from the bisected 5 calls to ~2 chunk calls (`[4,2]`), moving the realized win from 3.8× toward ~6×.
