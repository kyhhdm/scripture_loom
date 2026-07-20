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

## Follow-up (same day): the ceiling is the model — proven

Because the `llm()` seam is the pipeline's only LLM touchpoint, we added a `claude`
backend (`build_cli --backend claude`) that routes the *identical* Python pipeline to
Claude Opus via the Claude Code **subscription** (`claude -p`, no API credits). Rebuilt
PHP-002 with it and compared the same pericope across all three backends:

| PHP-002 build | Items | D2 (Sequence) | Dimension spread | Gate defects |
|---|---|---|---|---|
| Claude workflow (subscription) | 18 | 1 | 3/1/3/2/3/1/3/2 | 0 |
| Python + deepseek (API) | 31 | 7 | 4/7/4/4/3/3/3/3 | 0 |
| **Python + Opus (subscription)** | **16** | **2** | **2/2/2/2/2/2/3/1** | **0** |

**Finding:** swapping *only the model* (same gates, same repair loop, same prompts)
collapsed the padding — 31→16 items, D2 7→2 — to essentially the Claude-workflow
shape. The flat "3-per-dimension" deepseek signature disappeared; Opus honored *"only
the dimensions the passage genuinely supports."* Spot-checking the items, the surviving
D2 questions are real sequence work ("trace the chain of effects: Paul's chains → the
gospel's advance"), quotes are verbatim and grounded, and tiers are spread. This is
workflow-parity quality from the standalone program.

**Conclusion:** the standalone Python builder was never the quality limiter — the cheap
model was. `--backend claude` gives the best of both: the cheap/controllable/testable
deterministic pipeline **and** a strong model at subscription cost when quality matters.
Recommended default for real library builds; keep `--backend llm_core` for cheap bulk
drafts a human will heavily rewrite anyway. (Cost of the win: Opus is slower — one
`claude` process per call, no `--bare` — and draws down subscription usage windows.)

## Second follow-up: does `deepseek-v4-pro` close the gap? No.

Ran the same PHP-002 unit with `--backend llm_core --model deepseek-v4-pro --review`
(the `--model` flag added this session), to test whether a stronger *deepseek* buys the
padding discipline without Opus. Four-way:

| PHP-002 build | Items | D2 | Refs | Defects | Cost/unit |
|---|---|---|---|---|---|
| Claude workflow | 18 | 1 | 16/16 | 0 | subscription |
| llm_core flash | 31 | 7 | 0/29\* | 0 | ~$0.03 |
| llm_core **pro** | **31** | 4 | 30/30 | 0 | **$1.03** |
| claude Opus (sub) | 16 | 2 | 0/14\* | 0 | subscription |

\* flash/Opus PHP-002 predate the leader-reference fix; pro postdates it (30/30) — a
timing artifact, not a model effect.

**Finding:** pro does **not** solve over-generation. Still 31 items (~2× workflow/Opus);
it merely *redistributes* the padding (D2 7→4, but D7→6 and D3→5). And it costs **$1.03
and 6.7 min per pericope** (5 calls incl. a revise) — ~30× flash, in Opus's cost/latency
territory but without Opus's discipline. References with pro are good (grounded, correct
verses), confirming the reference fix is model-agnostic. **Verdict:** pro earns no slot
between flash (cheap bulk) and Opus (quality). The over-generation is a model-judgment
gap that only the strong model (Opus/workflow) closes; the deterministic anti-padding
heuristic remains the way to move it into the gate layer.

## Third follow-up (#19): deterministic anti-padding gate

Before building the "brief-aware" signal (flag items in dimensions the *brief* marks
unsupported), verified whether a cheap model can even judge dimension support. It can't
reliably: flash on PHP-002, 5 samples, correctly rated D2 (sequence in an epistle) as
`incidental`/`none` every time — but rated **D1, D5, D6 as `primary`** where Opus said
`incidental`. The cheap model's dimension declaration inherits the same inflation that
makes it pad the draft; the ceiling just moves from draft to brief. So **brief-aware was
dropped** in favour of two model-independent signals:

- **thread-span** (hard): a `thread` on a single-pericope section is invalid.
- **dimension cap** (soft): flag any dimension a unit emits `> cap` of (default 3); fed
  to the repair loop to prune, then *logged* if still over — never hard-fails, since a
  rich passage may legitimately exceed.

**Effectiveness — PHP-002 on flash, cap=3 vs uncapped:**

| PHP-002 | Items | Max items in one dim |
|---|---|---|
| Claude workflow | 18 | 3 |
| flash uncapped | 31 | 7 |
| **flash cap=3** | **21** | **4** |
| Opus (subscription) | 16 | 3 |

The deterministic cap pulled flash **31→21 items** and **max/dim 7→4** — a large move
toward workflow/Opus shape, on the cheap model, no brief change and no LLM judgment in
the gate. (D2 landed at 4, 1 over cap after the repair budget — correctly logged as
advisory, not blocked.) Not all the way to Opus's 16, but the deterministic lever does
real work where the cheap model's self-judgment (brief-aware, pro) does not.
