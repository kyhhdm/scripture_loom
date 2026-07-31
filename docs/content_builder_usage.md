# Using the Python content builder

`content_bank/author/build_cli.py` is the standalone draft builder: it walks a book's
units and, per unit, runs the deterministic pipeline
**brief → draft → gates (+ repair) → optional adversarial review → gated draft file**.
Everything a model produces lands under a per-model run directory as
`review_status: "draft"`; the builder **never writes the store** and never
self-publishes. Promotion to the store is a separate, human-gated step.

For the vocabulary used below (pericope, section, brief, gate, r1/r2, provenance,
citation tags), see `docs/content_build_terminology.md`.

To run the pipeline with a **different model per stage** (a hybrid experiment) and
capture per-call token/cost telemetry, gate traces, and a comparison page, use the
named experiment runner instead — see `docs/content_experiment_usage.md`. Model
selection is now driven by an explicit **route** (`--backend/--model` builds a
single-model route for every stage; an experiment config assigns one per stage);
the old `SCRIPTURE_LOOM_LLM_BACKEND`/`SCRIPTURE_LOOM_LLM_MODEL` mid-pipeline
switching is gone.

---

## Recommended configuration (from this project's experiments)

| Stage | Setting | Why |
|-------|---------|-----|
| **English generation** | `--backend claude --model opus` | Opus produces the strongest drafts and reliably emits well-formed `<verse>`/`<doctrine>` **citation tags**; cheaper models pad dimensions and mis-tag more, leaning harder on repair + human review. |
| **Chinese translation** | `deepseek-v4-flash` (translator default) | Fast and cheap, and good enough for the *reviewed-draft* library — the CUV/citation gates + human review are the backstop. See `docs/content_translator_usage.md`. |
| **Citation tags** | on by default | The drafting prompt emits `<verse>`/`<doctrine>` tags and the `citation_check` gate verifies them. No flag to toggle — tagging is part of the draft/section prompts. |

This is the config the pipeline is tuned for; the flags below let you deviate (e.g. a
cheap comparison build, or a section retried with a bigger repair budget).

---

## Prerequisites

Run everything under `uv` (`uv run …` or an activated `.venv`; `uv sync` first).

A provider credential is required — the builder refuses before any network call if
none is configured:

- **`--backend llm_core`** (default) → deepseek via `ARK_API_KEY`. Put it in the repo
  `.env` (git-ignored; see `.env.example`). The same backend supports the Google
  Gemini Developer API via `GEMINI_API_KEY` (or `GOOGLE_API_KEY`). Check:
  `llm_configured()` must be true.
- **`--backend claude`** → the `claude` CLI (Claude Code headless) must be on `PATH`;
  it uses your subscription, not API credits.

---

## The output layout

By default the builder writes into a **per-model run directory** keyed by the
resolved model id:

```
work/content_bank_build/<BOOK>/
  manifest.json                     # canonical unit list (model-agnostic)
  runs/<model-id>/
    manifest.json                   # this run's stage ledger (pending→…→drafted)
    briefs/<unit>.md                # per-model briefs (pericope AND section)
    drafts/<unit>.json              # the drafted items
    verdicts/<unit>.json            # adversarial r1/r2 verdicts (when --review)
```

The `<model-id>` slug is the full effective model: `deepseek-v4-flash`,
`deepseek-v4-pro`, `opus`, `sonnet`. The canonical `<BOOK>/manifest.json` supplies the
unit list; each run's `manifest.json` is seeded from it (all `pending`) on first use,
so every model tracks its own progress independently.

---

## Common commands

Build a whole book (every unit still at `pending`/`briefed`), default backend, review on:

```bash
uv run python -m content_bank.author.build_cli --book PHP
```

Build specific units (works even if they're already drafted — it re-drafts):

```bash
uv run python -m content_bank.author.build_cli --book PHP --units PHP-001 PHP-002
```

Build only sections (or only pericopes):

```bash
uv run python -m content_bank.author.build_cli --book PHP --kind section
```

**Produce a comparison run with a different model** — pick the backend/model; output
auto-routes to `runs/<model-id>/`, so runs never overwrite each other:

```bash
# deepseek pro
uv run python -m content_bank.author.build_cli --book PHP --units PHP-001 PHP-002 \
    --model deepseek-v4-pro

# Gemini 3.6 Flash (Google AI Studio/API; separate comparison run)
uv run python -m content_bank.author.build_cli --book PHP --units PHP-002 \
    --backend llm_core --model gemini-3.6-flash

# Claude Opus (subscription)
uv run python -m content_bank.author.build_cli --book PHP --units PHP-001 PHP-002 \
    --backend claude --model opus
```

Skip the adversarial review (faster/cheaper, no r1/r2 verdicts):

```bash
uv run python -m content_bank.author.build_cli --book PHP --no-review
```

---

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| `--book` | *(required)* | Book code, e.g. `PHP`, `MAT`, `ECC`. |
| `--units [ID ...]` | — | Explicit unit ids to build. When given, builds exactly these regardless of stage; when omitted, builds all units at `pending`/`briefed`. |
| `--kind {pericope,section,all}` | `all` | Restrict to one unit kind (only applies when `--units` is omitted). |
| `--review` / `--no-review` | **review ON** | Run (or skip) the two-lens adversarial review + revise pass. |
| `--max-repair N` | `2` | Gate-repair rounds before a HARD-gate failure aborts the unit. |
| `--limit N` | — | Cap how many units are built this run. |
| `--dim-cap N` | `3` | Soft anti-padding cap per dimension (over-cap dims feed the repair loop, then log; never hard-fail). |
| `--backend {llm_core,claude}` | `llm_core` | `llm_core` = registered API models (Volcengine DeepSeek or Google Gemini); `claude` = Claude Code headless via subscription. |
| `--model MODEL` | backend's default | Override the model (`deepseek-v4-pro`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`; or `opus`/`sonnet` with the Claude backend). Determines the run slug. |
| `--run-root DIR` | `work/content_bank_build` | Build root holding `runs/<model>/`. |
| `--manifest` / `--drafts-dir` / `--briefs-dir` / `--verdicts-dir` | derived | Explicit-path overrides (advanced / legacy). Passing `--manifest` or `--drafts-dir` switches off the automatic run layout. |

Gemini free-tier requests may be used by Google to improve its products. Use the
free tier only for corpus-based authoring material: never send family records,
children's data, recordings, photos, or private reflection artifacts. Free-tier
quotas are project-specific, so start with a single-unit build. Google also enforces
Gemini API regional availability; the Developer API is not currently listed as
available in mainland China.

---

## How a unit is built

1. **Brief.** If the unit is `pending` (or its brief file is missing), the model writes
   the brief to `runs/<slug>/briefs/<unit>.md` and the stage advances to `briefed`.
   Otherwise the existing brief is reused. Pericopes use `build_brief_prompt`; sections
   use `build_section_brief_prompt` (arc distillation).
2. **Draft.** The draft prompt (passage + brief + D1–D8 schema, anchored to WCF-1, plus
   the **citation-tagging** instructions) is sent; the JSON item array is parsed. The
   model wraps each quoted verse in `<verse ref="…">…</verse>` and each Standards-based
   claim in `<doctrine std="…" ref="…">…</doctrine>`.
3. **Gates + repair.** HARD gates (quote-fidelity, schema, ref-range, thread-span, and
   **citation_check** for the tags) and the SOFT anti-padding cap run. Flags are fed
   back to the model for up to `--max-repair` rounds. Remaining HARD flags **fail the
   unit**; remaining SOFT flags only log `[warn] padding remains`.
4. **Review (if on).** The two lenses (r1 accuracy/WCF-1/answerability; r2 evidence/age/
   dimension/pedagogy) judge the draft; failed items are revised (or dropped) and
   re-gated. Verdicts are saved to `runs/<slug>/verdicts/<unit>.json`.
5. **Write.** Items are stamped with provenance `{model, backend, run}` and written to
   `runs/<slug>/drafts/<unit>.json`; the stage advances to `drafted`.

Failures are isolated per unit — a unit that raises is recorded in the run's `failed`
list and the others continue. The command exits non-zero if any unit failed.

---

## Reading the output

`stdout` prints one line per unit (`[ok] PHP-001` / `[FAIL] PHP-005: …`) and a final
`Done. ok=N failed=M`. Note that `stdout` is **buffered** when not attached to a TTY
(e.g. a background run) — to gauge progress mid-run, inspect the run directory instead:

```bash
# stages so far
python3 -c "import json;m=json.load(open('work/content_bank_build/PHP/runs/opus/manifest.json'));print({k:v['stage'] for k,v in m['units'].items()})"
# what's been written
ls work/content_bank_build/PHP/runs/opus/{briefs,drafts,verdicts}
```

---

## Then compare

Once two or more runs exist, generate the side-by-side review page (run names are the
model slugs):

```bash
uv run python -m content_bank.author.compare_html PHP \
    --runs deepseek-v4-flash,opus
# → work/content_bank_build/PHP/review.html  (self-contained; open in a browser)
```

The page shows the runs per unit × dimension with gate/verdict badges, the rubric,
per-run briefs, and answer-key / leader-note blocks, and lets a human accept items and
export `decisions.json`. **Citation tags are highlighted** on the page — `<verse>`
spans in green with the ref, `<doctrine>` in amber — so a reviewer can see and verify
each citation (the tags are stripped only on the family-facing kit, never here). See
the comparison-page design spec for details.

For a machine-readable quality report with deterministic metrics plus a semantic
D1–D8 dimension-fit audit, see `docs/content_quality_evaluator_usage.md`.

**To translate the drafts into Chinese**, see the companion guide
`docs/content_translator_usage.md` (the `translate_cli` tool and its own highlighted
review page).

---

## Practical notes

- **Runs are self-contained.** To rebuild one run from scratch, delete its
  `runs/<slug>/` directory (or just the unit files) and re-run; other models are
  untouched.
- **A bare `--book X` run only picks up `pending`/`briefed` units.** Once a book is
  drafted, name units with `--units` to redo them.
- **Sections spanning a single pericope carry no threads** — the thread-span HARD gate
  rejects them; this is expected, not an error.
- **Cost/latency.** `llm_core` flash is cheap and fast (a full PHP book with review ran
  ~$0.15 in this project's tests). The `claude` backend is slower per call (each is a
  headless CLI invocation) and billed to the subscription.
- **If a unit hard-fails on a stubborn gate**, retry it alone with a larger budget:
  `--units PHP-S1 --max-repair 4`. (Opus once failed a section on an invalid
  `leader_reference.kind`; the extra budget cleared it.)
- **Model runs are independent**, so two different models can build the same units
  concurrently (separate run dirs, separate manifests) — useful for parallel
  comparison builds.
- Draft items are `review_status: "draft"` and are **not** served in product mode;
  only human-`published` items are. The builder deliberately stops at `drafted`.
