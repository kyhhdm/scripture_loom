# Psalms 1–10 evaluation → translation drift & CUV-fidelity hardening

- **Date:** 2026-07-30
- **Branches / PRs:** #29 `feature/review-page-flag-tooltips` (merged `a0af337`); #30 `feature/translation-drift-suggested-fixes` (merged `031e459`); #31 `fix/citation-tag-correspondence` (merged `0e20425`). All on `main`.
- **Summary:** Set out to run the whole content pipeline on Psalms 1–10 and judge quality. The evaluation was strong on its own, but inspecting the PSA-003 translation proposals kept surfacing real gaps in the drift/CUV-fidelity path — each of which turned into a shipped fix. Net result: the Psalms genre is validated at production quality, and the Chinese-translation drift/citation machinery is substantially hardened (three PRs).

## Request

A `/goal`: "run the whole pipeline on Psalms first 10 chapters, evaluate the result quality." Then a chain of follow-ups, each triggered by looking at the output:
- surface the gate/drift badge *reasons* on the review page;
- when we have detailed gate/drift info, feed it back to fix the issue;
- why does the translator prompt not fix the over-copy;
- the PSA-003-i05 extra-verse-tag observation;
- the PSA-003-i13 suggested-fix not carrying the triggering notes;
- "I don't see the suggested fix on the notes" (i14);
- how to deal with CUV-inherent drift (i09) — a note beside the CUV;
- merge/rebase orchestration between the PRs.

## What we did

**1. Psalms 1–10 full-pipeline evaluation.**
- `seed_pericopes PSA` (chs 1–10 = one psalm each) → built all 10 with the tuned config (`claude/opus`, review on): 9/10 first pass, PSA-007 clean on a plain retry → **187 items, full D1–D8, 0 hard-gate flags**.
- Translated with flash → review page. Findings: **strongest genre showing yet** — poetry read *as* poetry, and the hard doctrinal cruxes handled with confessional care (Ps 2:7 adoptionism → WCF 8.1 "not a Son newly made"; Ps 8 held across Gen 1:28 *and* Heb 2; Ps 6:5 Sheol as "argument from God's glory, not a denial of afterlife"; imprecatory Ps 7/10 drawn as a *type*). Write-up: `docs/2026-07-29-psalms-1-10-pipeline-findings.md`.

**2. Review-page badge tooltips (PR #29).** The page showed only `gate`/`drift` badges; the explanations were discarded at render. Added hover `title=` tooltips carrying the full `gate_flags` / `drift.notes`.

**3. Drift suggested-fixes (PR #30).** Realised the *gate*-repair loop already feeds flags back to the LLM; the new part was **drift**. Built (brainstorm → spec → plan → subagent-driven, opus final review) a **CUV-safe, suggest-and-confirm** drift fixer: on a drift-flagged proposal, one extra LLM call proposes a revised zh recorded as `suggested_fix` (never replacing the original), re-gated and re-drift-checked. Added `--drift-model` (run the drift review on `deepseek-v4-pro`, which catches drift flash misses). Also, while investigating why the *prompt* couldn't stop a full-verse over-copy, found the **real root cause**: `gates._norm` didn't strip the CUV em-dash `—` (Ps 3:3 `但你—耶和华…`), so the citation gate was unsatisfiable for that verse and the repair loop thrashed into over-copies. Fixed `_norm` (drop em/en-dash touching CJK); the prompt was never the blocker. Kept a coherence rewrite of the prompt's CUV-extent rule as no-regression polish.

**4. Tag correspondence + CUV-inherent drift (PR #31).**
- **Tag correspondence gate:** `citation_check` validated each language independently and never compared the zh `<verse>`/`<doctrine>` tag set to the en set — so a translator that *invented* a tag (with verbatim CUV content) slipped through. 42/187 PSA proposals had a mismatched tag set (systematic flash fabrication). Added `citation.added_tag`/`dropped_tag` (multiset), en-only draft items untouched; fixed 8 pre-existing fixtures that had used a zh tag with no en counterpart.
- **Suggested-fix review fidelity:** carry the triggering drift notes (`addresses`); render the revised **leader-note** (fixes often land in the answer, which was invisible before).
- **CUV-inherent drift (i09):** some drift can't be fixed — the CUV itself diverges in emphasis from the English, and it must ship verbatim. Final rule: **accept a drift fix only if it kept the CUV *and* the re-drift confirms it's resolved; otherwise keep the CUV and emit a leader-prep divergence note** (`cuv_note`). This subsumes all three observed cheap-model behaviours (keep CUV / leave CUV → `verse_mismatch` / inject a prose gloss) into one outcome.

## Artifacts

- **Evaluation:** `docs/2026-07-29-psalms-1-10-pipeline-findings.md`; corpus `corpus/canon/structure/pericopes/psa.json` (150 pericopes, seeded); PSA build/translation artifacts under `work/content_bank_build/PSA/` (review-stage).
- **Spec/plan (PR #30):** `docs/superpowers/specs/2026-07-30-translation-drift-suggested-fixes-design.md`, `docs/superpowers/plans/2026-07-30-translation-drift-suggested-fixes.md`.
- **Production code:** `content_bank/author/gates.py` (`_norm` dash fix; `citation_check` tag correspondence), `content_bank/author/translate.py` (`suggest_drift_fix` + CUV-inherent handling, `--drift-model` threading), `content_bank/author/translate_cli.py` (`--suggest-fixes`, `--drift-model`), `content_bank/author/translate_compare_html.py` (badge tooltips, suggested-fix block, `addresses`, revised leader-note, `cuv_note`), `content_bank/author/build_translate_prompt.py` (CUV-extent rule).
- **Docs:** `docs/content_translator_usage.md` (drift fixes, `--drift-model`, tag correspondence).
- **Memory (feedback):** `verify-diagnosis-on-nondeterministic-systems.md` — don't trust n=1/n=2 on a cheap LLM; K-trial A/B + probe the deterministic gate directly.
- **PRs:** #29 (`a0af337`), #30 (`031e459`), #31 (`0e20425`) — all merged.

## Outcome

- Psalms 1–10 evaluated at production quality; three PRs merged to `main`; suites green (**content_bank 379, corpus 67**).
- The translation drift/citation path now handles: resolvable drift (suggested fix), reliable drift detection (`--drift-model`), CUV-inherent drift (leader note, CUV kept verbatim), tag fabrication (correspondence gate), and the CUV em-dash normalization bug. The review page faithfully shows each.
- All PSA content remains review-stage in `work/` — nothing promoted to the served store.

## Follow-ups

- Human review of the PSA-003 review page (the `added_tag` flags are real fabrications; the i09 `cuv_note` is a teaching aid to confirm).
- Promotion of a suggested fix into the store (`translate.promote --use-suggested`) is still a manual edit — deferred.
- Broader audit for other CUV typographic separators beyond the em-dash, if any surface.
- Process lesson: three separate iterations of the same underlying pattern — the suggested-fix *logic* was sound, but its *review surface* kept under-showing what happened (dropped `uncertain`, missing triggering notes, invisible leader-note). Check the render surface, not just the data, when shipping a review tool.
