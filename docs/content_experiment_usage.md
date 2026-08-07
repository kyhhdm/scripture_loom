# Content-pipeline experiments (`experiment_cli.py`)

A **named experiment** runs the real content-build pipeline (same deterministic
gates and two-lens review as the standalone builder) with an explicit
**per-stage model route**, retains normalized per-call token/timing telemetry and
gate traces, runs the D1–D8 fit evaluator on a fixed evaluator route, and writes a
self-contained, immutable result tree you can compare against other experiments.

The **experiment name is the identity** — not a single model slug — so hybrid
pipelines (e.g. Gemini brief/review, Opus draft, Sonnet repair) are first-class.

Built per issue #35; design: `docs/superpowers/specs/2026-07-31-content-pipeline-experiments-design.md`.

## Configuration

An experiment is a JSON file under `experiments/` (see `experiments/example.json`):

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

- Every LLM **stage** (`brief`, `draft`, `repair`, `review_r1`, `review_r2`,
  `revise`) gets its own `{backend, model, settings?}` route.
- `evaluator` is the **D1–D8 fit** route, fixed independently of `draft`.
- `units: null` (or omit) ⇒ every pending/briefed unit of the book.
- `"execution"` (optional, default `"per_unit"`) selects how units are batched — see
  below.

### Execution mode: `per_unit` vs `group`

```json
{ "...": "...", "execution": "group", "units": ["PHP-S2"] }
```

- **`per_unit`** (default) — one LLM call per stage **per unit**, the standard walk.
- **`group`** — batch a **section-group** (a section + its pericopes) into **one call
  per stage**, cutting request count on the `claude`/Opus subscription backend
  (~`4(N+1)` → ~5 calls for a group of `N+1` units). It runs the *same* stages, gates,
  and review semantics and writes the *same* per-unit artifacts (drafts, verdicts,
  briefs, and **gate traces**), so `report.json` metrics — `first_pass_gate_rate`,
  `final_gate_rate`, tokens, `calls_by_stage` — are computed identically and are
  directly comparable to a `per_unit` experiment. Group mode gates at the same point
  the per-unit builder does (after revise when review is on), so the gate rates mean
  the same thing across modes.
- In `group` mode, **`units` selects groups by section id** (e.g. `"PHP-S2"` builds its
  whole group); omit `units` to build every group in the book. A batched call that
  truncates or omits a unit is split and retried down to singletons (the bisection
  guard), so no unit is dropped.
- **Not supported with `--reuse-drafts`** (group mode does not persist reusable
  per-unit raw drafts) — run `per_unit` to reuse frozen drafts.

To A/B group vs per-unit fairly: run two experiments with identical routes that differ
only in `"execution"`, then `compare --experiments per_unit_name,group_name`.

### Single-book vs cross-book

- **Single-book:** set `"book"` and (optionally) `"units"` within it — as above.
- **Cross-book:** **omit `"book"`** and list `"units"` spanning books; each unit's
  book is derived from its `BOOK-` prefix. The runner groups units by book, builds
  each group, and merges telemetry, gate traces, and the evaluator report under the
  one experiment name. Useful for a genre-spread probe (`experiments/genre_probe.json`):

  ```json
  {
    "schema_version": 1,
    "name": "genre_probe",
    "units": ["PSA-003", "PHP-002", "JON-002", "ECC-018"],
    "routes": { "...": "one route per stage" },
    "evaluator": {"backend": "claude", "model": "opus"}
  }
  ```

  ```bash
  uv run python -m content_bank.author.experiment_cli run experiments/genre_probe.json
  ```

  Results still land under one `experiments-out/genre_probe/`, with drafts nested
  per book (`experiments-out/genre_probe/<BOOK>/runs/genre_probe/`), one shared
  `calls.jsonl`, and `manifest.json`/`report.json` carrying a `books` list. The
  comparison page is per-book, so view one genre at a time:
  `compare --book JON --experiments genre_probe`.
- **No credentials in the config** — provider keys live in the environment
  (`ARK_API_KEY`, `GEMINI_API_KEY`/`GOOGLE_API_KEY`, or the Claude subscription
  login). Validation rejects any `api_key`/`token`-like field.

The config is **immutable per name**: a `config_hash` folds in the config, the
corpus revision (`git rev-parse HEAD:corpus/canon`), and a prompt-builder version.
Re-running a name whose hash changed is refused; an identical hash resumes.

## Commands

```bash
# Check a config (structure + credential-leak scan)
uv run python -m content_bank.author.experiment_cli validate experiments/NAME.json

# Run it — writes experiments-out/NAME/
uv run python -m content_bank.author.experiment_cli run experiments/NAME.json

# Resume an interrupted run (identical config only; completed units are skipped)
uv run python -m content_bank.author.experiment_cli run experiments/NAME.json --resume

# Reuse a source experiment's frozen drafts: skip brief+draft (no opus calls) and
# run only the downstream review/revise/repair stages with THIS config's routes.
uv run python -m content_bank.author.experiment_cli run experiments/NAME.json --reuse-drafts SOURCE

# Rebuild the metrics report from an existing run (no new LLM calls)
uv run python -m content_bank.author.experiment_cli evaluate NAME

# Run the D1-D8 classification-fit evaluator with an INDEPENDENT judge (LLM calls).
# Use this to fit-score an imported baseline with the same judge as another
# experiment, for a fair classification-error comparison.
uv run python -m content_bank.author.experiment_cli evaluate NAME \
    --fit --fit-model gemini-3.6-flash --units PHP-002

# Translate an experiment's English drafts to CUV-aligned Chinese proposals
uv run python -m content_bank.author.experiment_cli translate NAME [--concurrency N]

# Draft comparison, one column per experiment. --book optional: omit to include
# every book found across the experiments. Writes ONE file named from the inputs
# (e.g. compare_NAME_A__NAME_B.html), each book's units gated against its own book.
uv run python -m content_bank.author.experiment_cli compare --experiments NAME_A,NAME_B
uv run python -m content_bank.author.experiment_cli compare --book PHP --experiments NAME_A,NAME_B --out review.html

# ZH translation comparison: English ▸ CUV ▸ one zh column per experiment (one file)
uv run python -m content_bank.author.experiment_cli compare-translations --experiments NAME_A,NAME_B
```

## Translation step

`translate NAME` translates an experiment's English drafts into CUV-aligned Chinese
proposals (same gates + back-translation drift review as the standalone
`translate_cli`), per book, appending per-call telemetry (stages `translate`,
`translate_repair`, `drift`, `translate_fix`, `translate_note`) to the experiment's
`calls.jsonl`. The translator model comes from the config's optional `translate`
route (default `llm_core`/`deepseek-v4-flash`), with an optional separate `drift`
route for the back-translation reviewer:

```json
  "translate": {"backend": "llm_core", "model": "deepseek-v4-flash"},
  "drift":     {"backend": "llm_core", "model": "deepseek-v4-pro"}
```

Proposals land at `experiments-out/NAME/<BOOK>/runs/NAME/translations/<translate-slug>/`
and stay draft-only — promotion to the store is a separate, human-gated step.

## Result tree

```
experiments-out/NAME/
  manifest.json            frozen config + config_hash + corpus_rev + route matrix
                           + before/after subscription snapshots + aggregate telemetry
  calls.jsonl              append-only, one CallRecord per LLM attempt
  gate_traces/UNIT.json    initial flags, each repair round (route + tokens),
                           item drops, first-pass vs final status
  report.json              deterministic + D1-D8 fit metrics, extended (below)
  PHP/runs/NAME/           drafts/  raw_drafts/  briefs/  verdicts/
```

`raw_drafts/` holds each unit's **pre-review** draft (the raw draft-model output,
before review/revise). It's what `--reuse-drafts` reads.

## Reuse a frozen draft (iterate cheap stages without re-paying opus)

The draft stage is the expensive, quality-defining one (often opus). To test
whether *cheaper* models can do the downstream review/revise/repair stages without
hurting quality, draft **once**, then run many experiments that reuse that frozen
draft and vary only the ops routes:

```bash
uv run python -m content_bank.author.experiment_cli run experiments/genre_probe.json
uv run python -m content_bank.author.experiment_cli run experiments/hybrid_A.json --reuse-drafts genre_probe
uv run python -m content_bank.author.experiment_cli run experiments/hybrid_B.json --reuse-drafts genre_probe
```

Each `--reuse-drafts` run reads the source's `raw_drafts/` and `briefs/`, makes
**no brief or draft LLM calls** (so no opus cost or latency, and the draft route's
credential isn't required), and runs only review→revise→re-gate→evaluate with the
reusing config's routes. Because every reuse run starts from an *identical* draft,
the comparison cleanly isolates the ops stages.

Note: `raw_drafts/` is captured going forward — an experiment built before this
shipped has none, so **re-run the source once** to freeze its drafts before
reusing them. The manifest records `reused_drafts_from`.

### Telemetry honesty

Each `CallRecord` carries a `usage_source`:

- **`provider`** — real per-call usage from `claude -p --output-format json`
  (input/output plus cache-creation/cache-read tokens).
- **`local_estimate`** — llm_core's locally-tokenized token counts (no
  cache/thinking breakdown). Cost there is derived from a price table; for the
  subscription `claude` path cost is `null` (marginal cost ≈ 0 — raw tokens are the
  truth).

Records never contain credentials or prompt/response bodies — only a
`prompt_hash`.

### Subscription snapshot

The individual Claude CLI exposes per-call usage but **no documented
machine-readable remaining-allowance endpoint**, so account snapshots are
best-effort and record an explicit `available: false` reason rather than scraping
interactive output. (The quota is usage-metered, not call-count-metered; throttle a
whole-book Opus run with build concurrency, not by reducing call count.)

### Extended metrics (`report.json`)

Calls and tokens by stage/backend/model; Claude calls specifically; tokens, time,
and estimated cost per completed unit and per accepted item; first-pass and final
gate rates; repairs and tokens per repaired unit; D1–D8 fit mismatch and
missing/padded-dimension counts; and `evaluator_is_drafter` — whether the fit
judge is the same model as the drafter.

## Fair-comparison recipe

To make a comparison measure the **pipeline routes** rather than noise, hold these
identical across the experiments you compare:

1. **Same units** — the exact same `units` list.
2. **Same corpus revision** — run them at the same `HEAD:corpus/canon` (the
   `config_hash` records it; a differing `corpus_rev` means they are not
   comparable).
3. **Same prompts and gates** — same `PROMPT_VERSION`, `max_repair`, and `dim_cap`.
4. **Same evaluator route** — fix the `evaluator` block to one model across all
   experiments, so quality deltas reflect the routes under test, not the judge.
   Watch `evaluator_is_drafter`: a judge that is also the drafter is not
   independent. For a **classification-error** comparison of two drafters (e.g.
   sonnet vs opus), the evaluator must be a *third* model independent of both —
   `evaluate <baseline> --fit --fit-model <judge> --units <ids>` fit-scores an
   already-built experiment/baseline with that shared judge.

Then vary only the one thing you are testing (e.g. the `draft` route).

Product note: generated items are **draft-only**, WCF-1 constrained, and
evidence-not-judgment; nothing here publishes to the store. Staging remains a
separate, human-gated step.
