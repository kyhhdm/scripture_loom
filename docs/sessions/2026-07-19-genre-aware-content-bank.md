# Genre-aware content bank: probe → spec → ship

- **Date:** 2026-07-19
- **Branch / commits:** `feature/genre-aware-content-bank` → merged to `main` via **PR #5** (merge commit `dafb026`). Task commits: `34bcb45` (selector), `8fd6827` (author prompts), `93b6712` (D7 docs); design docs `51b153b`/`90bd89c`/`3a714e3`/`8122eed`/`01b65ac`.
- **Summary:** Starting from an open design question about how biblical genre affects the content bank, we ran an empirical probe that killed the "systematic genre" idea, specced three cheap changes instead, built them with subagent-driven TDD, and merged.

## Request
The user asked how the genre of a book or pericope (history, poetry, prophecy, epistle, etc.) influences its content bank, and wanted a genuine design opinion — then, in turn: pressure-test the thesis, run a probe, write it up, spec the surviving changes, resolve the deferred open question, write the plan, execute it, and merge.

## What we did
- **Brainstormed a thesis** (grounded in the real code): genre should *not* add a ninth dimension or a "poetry mode"; the eight fluency dimensions (D1–D8) stay universal, and genre merely reweights which are load-bearing per pericope and reshapes the templates inside a dimension.
- **Pressure-tested it** and found three cracks — chiefly that D1/D2 are themselves narrative-shaped, that genre doesn't partition cleanly per pericope, and that the selector's real constraint is content-availability, not genre.
- **Ran an empirical probe**: authored content across all D1–D8 for Psalm 23 (poetry) and Philippians 2:1–11 (epistle + embedded hymn), using real BSB text through the corpus license gate plus the WCF-1 guardrail. Result: every passage stayed authorable within D1–D8; D1/D2 went forced; each non-narrative genre had a load-bearing reading move (poetry: image→referent; epistle: trace the "therefore") that D7/D3 absorb silently. Philippians 2 confirmed genre is sub-pericope (D2 dead in v1–4, alive in v6–11), **killing the `genre → dimension-profile` table** before it was built.
- **Specced two cheap changes** the probe left standing, then **dug into the deferred D7-sub-label question** and decided it *against* on derive-don't-store grounds (every evidence record already carries its passage) — which promoted a real residual (a narrative-shaped assessment standard) into a third docs-only change.
- **Wrote a TDD implementation plan** and **executed it subagent-driven**: fresh implementer + task reviewer per task (all spec ✅, quality Approved), one plan-wording correction adjudicated mid-flight, then an Opus whole-branch review (Ready to merge = Yes, no Critical/Important, constraints grep-verified).

## Artifacts
- **Design docs:** `docs/2026-07-19-genre-dimension-probe-findings.md`; `docs/superpowers/specs/2026-07-19-genre-aware-content-bank-design.md`; `docs/superpowers/plans/2026-07-19-genre-aware-content-bank.md`.
- **Change 1 — availability-driven observation targets:** `prototype/selector.py` (`available_dimensions()` helper, threaded into `select_observation_targets`/`build_kit`), `prototype/test_selector.py`.
- **Change 2 — genre-aware D3/D7 authoring guidance:** `content_bank/author/build_brief_prompt.py` (fifth "Reading moves" brief part), `content_bank/author/build_draft_prompt.py` (D3/D7 pointer), `content_bank/tests/test_author.py`.
- **Change 3 — genre-general D7 progression language:** `docs/design-kit_generator.md` (D7 top rung).
- **Ledger:** `.superpowers/sdd/progress.md` (git-ignored scratch).

## Outcome
Merged to `main`. Suites green: selector 19/19, content-bank 91/91, corpus unchanged. Binding constraints held and were grep-verified: Python-3-stdlib-only, no new dimension, no `genre` field, no `schema.py` change, no dimension-profile table, no D7/D3 evidence sub-labels. Local and remote feature branches deleted.

## Follow-ups
Four Minor, non-blocking items (in PR #5 body): empty-availability path not directly asserted in the selector test; the D3/D7 pointer test asserts `count == 2` but not per-line placement; the new D7 rung covers epistle implicitly under "book's argument" (could name it "book's or letter's argument"); and (already scoped out in the spec) backfilling the four Matthew briefs with a "standard" Reading-moves note to exercise the `(if present)` degrade path.
