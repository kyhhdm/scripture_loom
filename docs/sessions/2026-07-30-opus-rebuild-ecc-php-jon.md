# Opus rebuild of ECC, PHP, JON (+ JON translation)

- **Date:** 2026-07-30
- **Branch / commits:** work performed on `feature/builder-concurrency` (PR #33's `--concurrency`), then the tree was switched to `feature/gemini-quality-evaluator` mid-run; no commits made — all output is untracked draft/translation artifacts under `work/content_bank_build/`.
- **Summary:** Rebuilt Ecclesiastes, Philippians, and Jonah from scratch with the current opus pipeline settings at `--concurrency 4`, then ran Jonah through the translator and generated its Chinese review page. All three books reached full draft coverage; the run surfaced a concrete subscription usage-window limit on the largest book.

## Request
`/goal` — "rebuild ECC, PHP and JON with the latest settings, set concurrency to 4, until done." Then, mid-run: "go on the pipeline of translator, review webpage on JON"; later "finish those 4 units" (the ECC stragglers) and "export this session."

## What we did
- **Confirmed scope and cleared prior runs.** Unit counts: ECC 24, PHP 14, JON 8 (46 total). PHP had a partial older opus run (6 drafted / 8 pending) and JON a complete older run; both predated the current gate/citation settings, so "rebuild" meant fresh full builds. Moved the existing PHP/JON `runs/opus/` dirs to a scratchpad backup (non-destructive) so a bare `--book` run would seed a fresh all-pending manifest.
- **Ran books sequentially, each at `--concurrency 4`.** Chose sequential-per-book (not all three at once) because the `claude` backend's parallel `claude -p` invocations share one subscription usage window — three books at concurrency 4 would mean 12 concurrent opus calls. Driver script: JON → PHP → ECC, `--backend claude --model opus`.
- **JON and PHP built cleanly** at concurrency 4 (8/8 and 14/14, 0 failures).
- **ECC hit the usage window.** As the third and largest book, ECC failed 17 of 24 units in a single burst (`claude -p failed (exit 1)`, empty stderr — the burst-failure signature of window exhaustion). Retried the 17 at `--concurrency 2` → 13 recovered, 4 still failed (again the first units dispatched, before the window recovered). A `--concurrency 1` retry then errored on argument parsing because the tree had been switched to `feature/gemini-quality-evaluator`, which lacks PR #33's flag; re-ran those 4 sequentially with no flag → all 4 drafted.
- **JON translation + review page.** Translated JON's opus drafts with the default flash translator, `--drift-model deepseek-v4-pro`, suggest-fixes on, concurrency 4 (118/118 proposals). Generated the translation review page via `translate_compare_html`.

## Artifacts
- `work/content_bank_build/JON/runs/opus/drafts/` — 8 units, 118 items.
- `work/content_bank_build/PHP/runs/opus/drafts/` — 14 units, 200 items.
- `work/content_bank_build/ECC/runs/opus/drafts/` — 24 units, 363 items.
- `work/content_bank_build/JON/runs/opus/translations/deepseek-v4-flash/` — 118 translation proposals.
- `work/content_bank_build/JON/runs/opus/translations/review.html` — self-contained JON translation review page.
- Scratchpad backup of the pre-rebuild PHP/JON opus runs (session scratchpad, `opus-run-backup/`).
- All items are `review_status: draft`; nothing was promoted to the store.

## Outcome
- **Full draft coverage:** JON 8/8 (118 items), PHP 14/14 (200), ECC 24/24 (363). Rebuild goal met.
- **JON translation:** 118/118. Of 118 items — 30 gate-flagged (25%, almost all citation-tag mechanics: `added_tag`, `verse_mismatch`, `untagged_quote`, driven by the flash translator over-tagging verse refs the opus draft left untagged), 25 drift=true (deepseek-v4-pro reviewer), resolving into 11 changed suggested-fixes + 14 CUV-inherent `cuv_note`s, 0 uncertain. All drift items resolved into exactly one outcome; none doctrinal — all are the mechanical class the review page exists to surface.

## Follow-ups
- **PHP + ECC translation and review pages** not yet run (only JON translated).
- **Human review** of the JON translation review page (30 gate-flagged items to adjudicate).
- **Concurrency guidance confirmed empirically:** for a whole-book opus run keep `--concurrency` at 2 tops; the tail of a large book is where the subscription window bites. Worth folding into `docs/content_builder_usage.md` if not already precise there.
- PR #33 (`--concurrency`) still open/unmerged; the active `feature/gemini-quality-evaluator` branch lacks the flag, so builds there must run sequentially.
