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

# Rebuild the metrics report from an existing run (no new LLM calls)
uv run python -m content_bank.author.experiment_cli evaluate NAME

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
  PHP/runs/NAME/           drafts/  briefs/  verdicts/  (the built content)
```

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
   independent.

Then vary only the one thing you are testing (e.g. the `draft` route).

Product note: generated items are **draft-only**, WCF-1 constrained, and
evidence-not-judgment; nothing here publishes to the store. Staging remains a
separate, human-gated step.
