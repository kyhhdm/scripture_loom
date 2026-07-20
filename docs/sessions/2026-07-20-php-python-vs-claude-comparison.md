# Philippians: standalone Python builder vs Claude Code workflow

Date: 2026-07-20
Issue: #16 — standalone Python content-bank builder
Compared builds:
- **Claude** — `work/content_bank_build/PHP/drafts/` (built by the Claude Code
  `build_book_full` / `build_sections` workflow fan-out).
- **Python** — `work/content_bank_build/PHP/drafts_py/` (built by
  `content_bank/author/build_cli.py --review`, deepseek-v4-flash via `llm_core`).

Both cover the same 14 units (10 pericopes PHP-001..010 + 4 sections PHP-S1..S4).
Both ran a two-lens adversarial review + the deterministic quote/schema gates; the
Python run additionally ran the new `refs_in_range` gate.

## Quantitative

| | Claude | Python |
|---|---|---|
| Units | 14 | 14 |
| Items | 210 | 262 |
| Items/unit (avg, range) | 15.0 (3–23) | 18.7 (6–31) |
| Gate defects (committed gates) | 0 | 0 |
| Build cost | subscription (not itemized) | ~$0.41 API credits |
| Wall time | — | ~17 min LLM time (single-threaded) |
| Avg LLM call | — | $0.007, 19 s |

Per-dimension spread (item counts):

| Dim | Claude | Python | Note |
|---|---|---|---|
| D1 Recall | 26 | 36 | |
| **D2 Sequence** | **7** | **38** | **Python over-generates; Philippians (epistle) has little narrative sequence** |
| D3 Vocabulary | 32 | 29 | |
| D4 Setting | 31 | 29 | |
| D5 Connections | 27 | 25 | |
| D6 Questioning | 20 | 30 | |
| D7 Interpretation | 45 | 40 | |
| D8 Application | 22 | 35 | |

## Qualitative findings

**1. Uniform padding — the predicted core weakness.** The Python/deepseek build tends
toward an even per-dimension spread regardless of genre. The clearest tell is **D2
(Sequence): 38 vs 7**. Philippians is a letter, not a narrative; the Claude build
correctly produced few sequence items because the passages do not support them, while
the Python build manufactured sequence items to fill the dimension. The draft prompt
explicitly says *"ONLY THE DIMENSIONS THIS PASSAGE GENUINELY SUPPORTS … Do not pad,"*
but that is a judgment the mechanical gates cannot enforce — and the two-lens
adversarial reviewer, run by the same cheap model, did not catch it either. This is
exactly the "no exploratory self-correction" tradeoff issue #16 anticipated.

**2. Section threads invented on a single-pericope section.** PHP-S1 spans only one
pericope (PHP-001, PHP.1.1-11). A "thread" is defined as a motif that **recurs across
2+ pericopes**. Claude produced **0 threads** for PHP-S1 (correct). The Python build
produced **2 threads** ("Partnership in grace", "The day of Christ Jesus") whose refs
are in-range (so `refs_in_range` passes) but which cannot satisfy the cross-pericope
definition. Another genre/scope judgment the gates cannot see.

**3. Both are gate-clean, including the new gate.** The committed gates
(quote + schema + `refs_in_range`) flag **0 defects in either build**. Notably the new
`refs_in_range` gate found no scope drift in the *Claude* PHP build either — so on
this book the gate's value is preventive, not a caught-in-the-act win. (Its designed
catch, the historical MAT-035 Matthew-15-in-Matthew-8 drift, is covered by a unit
test.)

**4. Where the Python build is genuinely competitive.** On in-genre dimensions
(D3/D4/D5/D7) the spreads are close, and the section throughlines read well and stay
in the text's own terms (PHP-S1 throughline: *"Paul gives thanks for the Philippians'
partnership in the gospel from the first day, prays…"*). For a *first draft a human
reviews anyway*, the mechanical accuracy (verbatim quotes, valid schema, in-range
refs) is solid and the coverage is generous.

## Interpretation vs issue #16's "net" claim

Issue #16 argued that for a draft library a human reviews anyway, the standalone
program is *"cheaper, more controllable, more testable, and with the ref-in-range gate
catches a class of error the agents missed."* This build bears that out with one
important caveat:

- **Cheaper / controllable / testable: confirmed.** ~$0.41 for 14 units, fully
  scripted, resumable, per-unit isolated, zero manual reconciliation, 0 gate defects.
- **Catches a class of error: confirmed in principle** (`refs_in_range` + the MAT-035
  test), though this particular book had no such drift to catch.
- **Caveat — quality ceiling is the model, not the harness.** The weaknesses here
  (dimension padding, threads on a one-pericope section) are *pedagogical/genre
  judgments*, precisely the class the issue says "gates only catch mechanical
  wrongness" leaves to the human review gate. The cheaper model padding more makes the
  human review pass *more* necessary, not less. Green gates must not be read as "ready."

## Recommendation

Adopt `build_cli.py` as the default draft-library builder — it is cheaper, scriptable,
and mechanically at least as safe as the workflow (strictly safer via `refs_in_range`).
Keep two guardrails on top:

1. **Human review remains mandatory** and should explicitly watch for dimension padding
   and off-genre items — the model's failure mode, not the workflow's.
2. **Consider a cheap deterministic anti-padding heuristic** as a follow-up (e.g. warn
   when a single pericope emits > N items in a dimension the brief's "reading moves"
   marked "standard/omit", or when a single-pericope section emits threads). This would
   move the most common quality miss from human-only into the gate layer — a natural
   next issue, not part of #16.

For genre-sensitive, pedagogy-heavy books, a stronger drafting model (or keeping the
Claude workflow for those) is worth it until such heuristics exist.
