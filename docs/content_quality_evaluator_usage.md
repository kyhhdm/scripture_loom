# Content-build quality evaluator

`content_bank/author/quality_eval.py` evaluates one or more model-run draft
directories without changing the drafts or publishing anything. It writes a
machine-readable JSON report and prints one compact row per run/unit.

It has two deliberately separate layers:

1. **Deterministic metrics and gates** — reproducible, no LLM judgment.
2. **Semantic dimension-fit review** — one configurable LLM call per run/unit,
   using the canonical D1–D8 definitions and sharp boundary tests.

## Recommended command

Evaluate the same unit from Gemini and Opus with an independent Sonnet reviewer:

```bash
uv run python -m content_bank.author.quality_eval \
  --book PHP \
  --runs gemini-3.6-flash,opus \
  --units PHP-002 \
  --fit-backend claude \
  --fit-model sonnet
```

The default reviewer is `gemini-3.6-flash` through `llm_core`:

```bash
uv run python -m content_bank.author.quality_eval \
  --book PHP --runs gemini-3.6-flash,opus --units PHP-002
```

That default is inexpensive/free-tier-friendly, but the JSON field
`reviewer_is_draft_model` will be `true` when Gemini reviews its own Gemini draft.
Treat that result as a correlated self-review, not independent confirmation.

For deterministic metrics only, with no network call:

```bash
uv run python -m content_bank.author.quality_eval \
  --book PHP --runs gemini-3.6-flash,opus --units PHP-002 \
  --no-dimension-fit
```

The default report path is
`work/content_bank_build/<BOOK>/quality_eval.json`. Override it with `--out PATH`;
override the build root with `--base DIR`.

## Deterministic metrics

Each run/unit records:

- item count;
- D1–D8 counts, numerical coverage, and missing dimensions;
- largest per-dimension count;
- hard-gate flagged items/problems and their exact flags;
- soft anti-padding flags;
- item-text and leader-reference word counts;
- leader-reference count;
- `<verse>` and `<doctrine>` tag counts;
- difficulty, type, and age-tier distributions;
- difficulty-3 count;
- saved r1/r2 failure count and details.

Saved review verdicts describe the **pre-revision draft**, because the builder
persists verdicts before revising items. The evaluator names these fields
`saved_review_*` so they are not mistaken for defects in the final gated draft.

Build token usage, elapsed time, and provider charges are not in the draft files,
so this evaluator does not invent them. They remain available only from captured
builder logs until build-run telemetry is persisted separately.

## Dimension-fit review

The reviewer classifies every item as:

- `accurate` — assigned dimension is clearly the dominant learner skill;
- `mixed` — assigned skill is real, but another dimension is equally or more
  prominent;
- `misclassified` — assigned skill is not genuinely exercised.

Each result contains the suggested dominant dimension, confidence, and a concrete
reason. The evaluator then reports both numerical assigned coverage and
`adjusted_coverage`/`adjusted_missing_dimensions` based on the semantic retags.
This catches false coverage such as a model-written why-question tagged D6: D6
requires the learner to formulate the question.

Dimension-fit results are proposals, not publication authority. A human reviewer
still confirms classification, especially for `mixed` items and when
`reviewer_is_draft_model` is true.

## Flags

| Flag | Default | Meaning |
|---|---|---|
| `--book BOOK` | required | Canonical book code. |
| `--runs A,B` | required | Comma-separated build-run slugs. |
| `--units ID ...` | all units | Restrict the report to named units. |
| `--fit-backend {llm_core,claude}` | `llm_core` | Semantic reviewer backend. |
| `--fit-model MODEL` | `gemini-3.6-flash` | Semantic reviewer model. |
| `--no-dimension-fit` | off | Skip semantic review and make no LLM call. |
| `--dim-cap N` | `3` | Soft anti-padding threshold. |
| `--base DIR` | `work/content_bank_build` | Build root. |
| `--out PATH` | `<base>/<BOOK>/quality_eval.json` | JSON output path. |

Gemini free-tier privacy and regional cautions from
`docs/content_builder_usage.md` apply equally to evaluator prompts. The evaluator
sends draft items, leader references, and the unit's theological brief to the
selected reviewer.
