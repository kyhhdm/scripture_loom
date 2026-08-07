# Named content-pipeline experiments with per-stage routing and telemetry

- **Issue:** #35
- **Date:** 2026-07-31
- **Status:** Design approved; ready for implementation plan.
- **Related:** #36 (packed multi-unit drafting) is a *consumer* of this framework and is
  sequenced strictly after it — its evaluation plan depends on the runner and telemetry
  built here. The owner's #36 pre-implementation analysis established that #35 must land
  first.

## Problem

Content-build comparisons are organized around a single draft-model slug. That no longer
fits hybrid pipelines where brief, draft, repair, review, revise, and D1–D8-fit evaluation
may each use a different backend/model. Three concrete gaps in the current tree:

1. **Model selection is process-wide, not per-stage.** `build_cli.run()` sets
   `os.environ["SCRIPTURE_LOOM_LLM_BACKEND"]` / `SCRIPTURE_LOOM_LLM_MODEL` once
   (`build_cli.py:300–304`), and every stage calls the same `llm(prompt)` seam
   (`llm.py:33`). It is currently impossible to draft on opus but review on deepseek.
2. **Telemetry exists but is discarded.** `llm_core` already computes per-call
   `tokens_in_total`, `tokens_out_total`, `cost`, `elapsed_s` inside `run_batch_sync`
   (`service.py:243–250`) and only logs them; `run_sync_llm` returns text alone
   (`sync.py`). The `claude -p` seam uses `--output-format text` and drops the JSON usage
   the CLI can emit.
3. **No single reproducible experiment artifact.** There is no named, immutable
   configuration that fixes every stage's route, executes the real pipeline, retains cost
   and quality telemetry, runs the evaluator, and feeds a human comparison page.

## Goal

Add a named, reproducible experiment runner around the **existing** content-building
pipeline. An experiment configuration selects a backend/model for every LLM stage, executes
the whole pipeline with the same deterministic gates and review semantics as the production
builder, retains normalized cost/quality telemetry, runs the existing evaluator, and
generates the reviewer comparison page. The **experiment name**, not a model slug, is the
primary identity.

## Non-goals

- Publishing drafts without human confirmation.
- Replacing deterministic gates with LLM judgment.
- Depending on undocumented Claude account endpoints, or scraping interactive CLI output.
- Putting provider credentials in experiment configuration or results.
- Packed multi-unit drafting (#36) — a separate, later, evaluation-gated feature.

## Product constraints (unchanged)

Generated material stays draft-only, WCF-1 constrained, evidence-not-judgment, and subject
to leader review before publication. This is **prepare-time authoring only** and introduces
**no during-gathering computation**. Gates remain deterministic and local.

## Key architectural decisions

1. **One pipeline, route-driven.** Rather than build a parallel runner, `build_cli`'s core
   is refactored to take an explicit per-stage `RouteConfig`. The normal
   `--backend/--model` CLI and the experiment runner both become thin callers of the same
   route-driven core — a single source of pipeline truth. The env-var switching is deleted.
2. **Structured return + explicit sink for telemetry.** The seam returns an `LLMResult`
   (text + usage + metadata); callers (which know stage/unit/attempt) record a `CallRecord`
   to a `TelemetrySink`. A thin `llm_text()` preserves the current text-only API. No hidden
   ambient state; fully testable network-free.
3. **Telemetry is tagged by source and honest about what each backend provides.** Only
   `claude -p --output-format json` yields provider-reported usage (including cache tokens);
   `llm_core`'s numbers are locally-tokenized *estimates* with no cache/thinking breakdown.
   Every token record carries a `usage_source` (`"provider"` | `"local_estimate"`) and
   cache/thinking fields are nullable. Cost is a clearly-derived estimate — from
   `llm_core`'s price table, or `null` for the subscription `claude` path (marginal cost
   ≈ 0; raw tokens are the truth).
4. **`dimension_fit` is the evaluator route, not a builder stage.** The issue lists
   `dimension_fit` among the routes, but that classification lives in `quality_eval.py`,
   not the builder. It is modeled as the config's separate `evaluator` block, fixed
   independently of `draft`.

## Module layout

```
content_bank/author/
  routing.py             NEW  — Route, RouteConfig; single() + from_experiment() builders
  telemetry.py           NEW  — LLMResult, CallRecord, TelemetrySink (append-only JSONL)
  experiment_config.py   NEW  — load/validate JSON, canonical config_hash, immutability guard
  experiment_cli.py      NEW  — validate / run / evaluate / compare subcommands
  experiment_report.py   NEW  — extend quality report with experiment metrics
  llm.py                 EDIT — llm(prompt, route) -> LLMResult; llm_text() legacy shim;
                                claude backend uses --output-format json
  build_cli.py           EDIT — thread RouteConfig + TelemetrySink through the pipeline;
                                delete env-var switching
  quality_eval.py        EDIT — accept an explicit evaluator Route + sink (currently uses
                                the same env-driven llm seam)
experiments/             NEW dir — checked-in NAME.json experiment configs
llm_core/
  sync.py                EDIT — add run_sync_llm_result() returning (text, summary)
```

`experiments-out/` (run outputs) is git-ignored, like `work/content_bank_build/`.

## Part A — Route-driven pipeline

### Types (`routing.py`)

```python
@dataclass(frozen=True)
class Route:
    backend: str                    # "llm_core" | "claude"
    model: str | None = None        # None -> backend default
    settings: dict = field(default_factory=dict)   # e.g. {"effort": "high"} for claude

@dataclass(frozen=True)
class RouteConfig:
    brief: Route
    draft: Route
    repair: Route
    review_r1: Route
    review_r2: Route
    revise: Route

    @classmethod
    def single(cls, backend, model=None) -> "RouteConfig": ...
        # every stage -> the same Route. Behaviour-identical to today's single-model run.

    @classmethod
    def from_experiment(cls, routes_json: dict) -> "RouteConfig": ...
```

### Threading

- `build_pericope`/`build_section` gain a `routes: RouteConfig` parameter (replacing the
  implicit env-var model) and a `sink: TelemetrySink` parameter. Each call uses its stage's
  route: brief → `routes.brief`; first draft → `routes.draft`; repair loop
  (`_repair_to_clean`) → `routes.repair`; review lenses → `routes.review_r1` /
  `routes.review_r2`; revise → `routes.revise`.
- `_llm_with_backoff` and the review helpers take a `route` (and `sink` + attribution)
  argument instead of relying on ambient env.
- `run()` builds `RouteConfig.single(backend, model)` from the existing
  `--backend/--model` flags and passes it down. The
  `os.environ["SCRIPTURE_LOOM_LLM_BACKEND"] = backend` block is **removed**. The LLM
  availability check (`llm_configured` / `claude` on PATH) moves to operate over the routes
  actually present in the `RouteConfig`.

**Backward compatibility:** the normal builder's observable behaviour is unchanged — the
same single model runs every stage, the per-model run layout (`runs/<slug>/`) is unchanged,
and `SCRIPTURE_LOOM_LLM_MODEL`/`SCRIPTURE_LOOM_LLM_BACKEND` may remain as a *default source*
for `RouteConfig.single()` for existing muscle-memory, but are no longer read mid-pipeline.

## Part B — Telemetry seam

### Seam (`llm.py`)

```python
@dataclass
class LLMResult:
    text: str
    usage: TokenUsage           # nullable fields; see below
    requested_model: str | None
    actual_model: str | None    # when the backend exposes it (claude json does; llm_core: resolved)
    stop_reason: str | None
    duration_ms: int
    usage_source: str           # "provider" | "local_estimate"

def llm(prompt: str, route: Route) -> LLMResult: ...
def llm_text(prompt: str, route: Route) -> str:  # legacy shim
    return llm(prompt, route).text
```

`TokenUsage` fields: `input`, `output`, `cache_creation`, `cache_read`, `thinking` — all
`int | None`. Only what the backend authentically reports is populated.

- **claude backend:** invoke `claude -p --output-format json …` (keep `--disallowed-tools`
  and the no-`--bare` note from the current seam). Parse the JSON envelope for `usage`
  (input/output/cache-creation/cache-read tokens), `stop_reason`, and `model`.
  `usage_source="provider"`. On non-zero exit or empty result, raise `RuntimeError` (same
  contract as today, so backoff + per-unit isolation are unchanged).
- **llm_core backend:** add `run_sync_llm_result(system, user, caller, model) ->
  (text, summary)` returning the existing `summary` alongside the completion. Map
  `summary` → `TokenUsage(input=tokens_in_total, output=tokens_out_total, cache_*=None,
  thinking=None)`, `cost_estimate=summary["cost"]`, `actual_model=summary["model"]`,
  `usage_source="local_estimate"`.

### Sink (`telemetry.py`)

```python
@dataclass
class CallRecord:
    experiment: str | None
    stage: str                  # brief | draft | repair | review_r1 | review_r2 | revise | evaluate
    unit_id: str | None
    kind: str | None            # pericope | section
    attempt: int
    backend: str
    requested_model: str | None
    actual_model: str | None
    usage: dict                 # TokenUsage as a dict (nullable fields preserved)
    usage_source: str
    cost_estimate: float | None
    duration_ms: int
    stop_reason: str | None
    success: bool
    error: str | None
    prompt_hash: str            # sha256 of the rendered prompt; NEVER the prompt text or creds

class TelemetrySink:
    def add(self, record: CallRecord) -> None: ...   # append one JSONL line
```

- Append-only JSONL; one line per LLM attempt (including failed/retried attempts).
- **Never** logs credentials or full prompt/response bodies — only a `prompt_hash`.
- For the **normal builder**, the sink is a no-op (or an optional simple per-run log), so
  telemetry adds zero required configuration to ordinary builds.

## Part C — Experiment runner

### Configuration (`experiments/NAME.json`)

```json
{
  "schema_version": 1,
  "name": "php_hybrid_v1",
  "book": "PHP",
  "units": ["PHP-001", "PHP-002"],
  "routes": {
    "brief":     {"backend": "llm_core", "model": "gemini-3.6-flash"},
    "draft":     {"backend": "claude",   "model": "opus", "settings": {"effort": "high"}},
    "repair":    {"backend": "claude",   "model": "sonnet"},
    "review_r1": {"backend": "llm_core", "model": "gemini-3.6-flash"},
    "review_r2": {"backend": "llm_core", "model": "gemini-3.6-flash"},
    "revise":    {"backend": "claude",   "model": "sonnet"}
  },
  "gates": {"max_repair": 2, "dim_cap": 6},
  "evaluator": {"backend": "claude", "model": "sonnet"}
}
```

- `units: null` ⇒ whole book (all pending/briefed units of every kind).
- `name` is the identity; results land under `experiments-out/NAME/`.
- `evaluator` is the `dimension_fit` route, fixed independently of `draft`.

### Validation & immutability (`experiment_config.py`)

- `validate(path)` — schema check: required keys, known backends, known stages, `dim_cap`
  and `max_repair` in range, and **rejection of any credential-like field** (`api_key`,
  `token`, `authorization`, …) anywhere in the config.
- `config_hash` — sha256 over the canonicalized config: JSON with sorted keys, plus a folded
  **prompt-builder version string** (a constant bumped when
  `build_brief_prompt`/`build_draft_prompt`/rubric change) and the **corpus revision** (git
  SHA of `corpus/canon`). This makes "identical configuration" precise.
- **Overwrite guard:** on `run`, if `experiments-out/NAME/manifest.json` exists with a
  *different* `config_hash`, refuse with a clear diff (which fields changed). Identical hash
  ⇒ resume.

### Runner (`experiment_cli.py`)

`run experiments/NAME.json [--resume]`:

1. Load + validate; build `RouteConfig.from_experiment(config["routes"])`.
2. Availability check over exactly the routes present (claude on PATH if any claude route;
   `llm_configured(model)` for each llm_core route).
3. Freeze `manifest.json`: `config_hash`, corpus revision, prompt-builder version,
   `created_at` (the **CLI** supplies the timestamp — scripts cannot call `Date.now()`, but
   the CLI can), and the resolved route matrix.
4. **Subscription snapshot (before)** — pluggable, best-effort. If no reliable source is
   configured, record `{"available": false, "reason": "<why>"}`. Never scrapes interactive
   output or undocumented endpoints; never adds a model request.
5. Walk units through the **same** `build_pericope`/`build_section` (route-driven, sink
   active). Per-unit failure isolation is already present; `--resume` skips units the
   run manifest already marks `drafted`.
6. **Subscription snapshot (after).**
7. Run `quality_eval` on the fixed `evaluator` route (sink active, `stage="evaluate"`).
8. Write the self-contained result tree.

### Results tree

```
experiments-out/NAME/
  manifest.json      frozen config + config_hash + env + route matrix + before/after snapshots
  calls.jsonl        append-only CallRecords (the sink output)
  briefs/  drafts/  verdicts/
  gate_traces/UNIT.json   initial gate flags; each repair round (route + tokens); item drops;
                          first-pass vs final pass status
  report.json        deterministic + D1-D8 fit metrics, extended (below)
```

### Extended metrics (`experiment_report.py`, on top of `quality_eval`)

- Calls and tokens by stage / backend / model; Claude calls specifically.
- Tokens, time, and estimated cost per completed unit and per accepted item.
- First-pass and final gate rates.
- Repairs and tokens per repaired unit.
- r1/r2 pass rates.
- D1–D8 fit mismatch and missing/padded-dimension metrics (from the existing evaluator).
- `evaluator_is_drafter` (bool) — the honesty flag: is the fit evaluator the same
  model/backend as the drafter?

## Part D — Human comparison

Extend the existing `compare_html.py` (already renders per-model columns) so **a column
represents an experiment**, sourced from `experiments-out/NAME/` instead of a run dir:

- Column header shows the full **route matrix** (stage → backend/model) and aggregate
  telemetry (tokens, estimated cost, first-pass/final gate rates).
- **Preserved unchanged:** per-unit item rendering, citation highlighting, leader
  references, verdict badges, and human acceptance/export behaviour.

`experiment_cli compare --book PHP --experiments NAME_A,NAME_B` → one HTML page with those
experiment columns.

## Suggested commands

```bash
uv run python -m content_bank.author.experiment_cli validate experiments/NAME.json
uv run python -m content_bank.author.experiment_cli run experiments/NAME.json
uv run python -m content_bank.author.experiment_cli run experiments/NAME.json --resume
uv run python -m content_bank.author.experiment_cli evaluate NAME
uv run python -m content_bank.author.experiment_cli compare --book PHP --experiments NAME_A,NAME_B
```

## Implementation phasing (single spec, staged build)

Each phase is independently testable and network-free (the seam is mocked).

1. **Phase A — routing.** `routing.py` + route-driven `build_cli`. Env-var switching
   deleted. Observable behaviour of the normal builder unchanged; existing tests stay green.
2. **Phase B — telemetry.** `telemetry.py` + `LLMResult` seam + `llm_text()` shim +
   `claude -p --output-format json` + `run_sync_llm_result()`. Normal builder wires a no-op
   (or optional) sink.
3. **Phase C — runner.** `experiment_config.py`, `experiment_cli.py` (validate/run/evaluate),
   results tree, gate traces, `experiment_report.py`. `quality_eval` accepts an explicit
   evaluator route.
4. **Phase D — comparison.** `compare_html.py` experiment columns + `compare` subcommand.

## Testing (all network-free; seam mocked)

- **Config validation** — required keys, unknown backend/stage rejected, credential-like
  field rejected, `dim_cap`/`max_repair` bounds.
- **Config hash / immutability / resume** — identical config resumes; changed config is
  refused with a diff; resume skips completed units and does not re-draft them.
- **Routing** — each stage calls its configured model (assert via a mock seam that records
  `(stage, route)`); a single-model `RouteConfig.single` reproduces today's behaviour.
- **Telemetry normalization** — both backends map to the normalized schema; nullable cache/
  thinking fields stay `None` for llm_core; `usage_source` correct; failed attempts recorded;
  no credentials or prompt bodies in the record.
- **Failure isolation** — a malformed/gate-failing unit does not discard successful siblings;
  the per-unit manifest advances independently.
- **Gate-trace persistence** — initial flags, repair rounds with route+tokens, item drops,
  first-pass vs final status all recorded.
- **Comparison rendering** — an experiment column renders route matrix + telemetry and
  preserves citation highlighting / leader references / verdict badges / accept-export.

## Documentation

- `docs/content_experiment_usage.md` — how to write a config, run/resume, evaluate, compare;
  and a **fair-comparison recipe**: identical units, identical corpus revision, identical
  prompts/gates, and a **fixed evaluator route** across the experiments being compared
  (so quality deltas reflect the pipeline routes under test, not the judge).
- Cross-links from `docs/content_builder_usage.md` and `docs/content_build_terminology.md`
  (add "experiment", "route", "route matrix", "telemetry/CallRecord").

## Acceptance criteria (from #35)

- [ ] A checked configuration can assign a different backend/model to every LLM stage.
- [ ] A named experiment executes the same gates and review semantics as the production builder.
- [ ] Each provider call produces normalized stage-attributed token and timing telemetry when
      the provider exposes it.
- [ ] Claude per-call usage is captured; unsupported subscription-level snapshots are reported
      honestly and do not add a model request.
- [ ] Gate state and every repair attempt are persisted per unit.
- [ ] Interrupted experiments resume without repeating completed units or accepting a changed
      configuration.
- [ ] The existing deterministic metrics and D1–D8 fit evaluator produce a report for the
      experiment.
- [ ] The HTML comparison accepts experiment names and displays route, efficiency, quality, and
      reviewer-facing content.
- [ ] Network-free tests cover configuration validation, routing, telemetry normalization,
      resume behavior, failure isolation, and comparison rendering.
- [ ] Documentation includes a fair-comparison recipe using identical units, corpus revision,
      prompts, gates, and evaluator route.
