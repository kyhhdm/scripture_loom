# Matthew draft-library generation (batches 1–11) and the standalone-builder proposal

- **Date:** 2026-07-20
- **Branch / PRs:** `feature/content-bank-matthew` (PR #15, merged to `main` as `f94b99a`) · GitHub issue #16 opened
- **Summary:** Resumed the paused Matthew first-draft content library, generating and staging 54 of 153 pericopes (MAT-001–057 minus the 4 published pilots) in eleven batches of five, then pushed and merged PR #15. Closed with a design discussion — how to rebuild the agent-driven pipeline as a standalone Python program — captured as issue #16.

## Request
"Go on with Matthew." Continue the honest `reviewed` first-draft library for Matthew, resuming from where the prior session stopped. Mid-session the user asked to stop after a batch, then to commit/push/open a PR and merge it. Finally: "how can I run the library building in a standalone python program? … give your critics," followed by "create a new issue for this proposal."

## What we did
- **State check.** Confirmed the Matthew build state: 153 pericopes total, 4 already `published` (MAT-009/013/014/015), 149 pending + 7 arc sections in `work/content_bank_build/MAT/manifest.json`. Batch 1's briefs (mat-001..005) existed from the prior stop but nothing was staged (drafts dir empty), so re-ran cleanly.
- **Batched generation.** Ran the lean `build_book_draft.workflow.js` (brief → draft → deterministic quote+schema gates; no AI self-review, no publish) in batches of five pericopes (~10 agents each) to stay under the account session limit — the batch size proven in the prior session. After each batch: verified gates, staged with `stage_book.py` as `review_status: reviewed`, committed periodically.
- **Transient failures, absorbed by the gates.** Three single-agent failures across the run: MAT-027 (session limit — draft had landed and passed gates, staged as-is), MAT-035 (server error → incomplete draft that *failed* the quote gate with a cross-pericope Matthew-15 quote; deleted and re-run clean in the next batch), MAT-043 (server error → draft never wrote; re-run clean). The refold-into-next-batch pattern lost no data.
- **Stopped on request** after batch 11 (54 pericopes), staged and committed.
- **Test fix before PR.** The pilot-era guard `test_only_scoped_pericopes_present` hard-coded the store to the 4 published pilots and now failed. Rewrote it to check store passages for *membership* in the corpus pericope structure (`corpus/canon/structure/pericopes/mat.json`) rather than an exact set — preserving its real intent (no orphan/misnamed scopes).
- **PR #15** opened and merged to `main`; feature branch deleted.
- **Standalone-builder discussion.** Investigated the agent workflow's actual calls and established that the pipeline is ~90% deterministic Python already — every agent shell-out (`build_brief_prompt`, `build_draft_prompt`, `corpus_bridge.passage_text`, the gates, `store_writer.upsert_items`) is a pure function. The LLM's real job reduces to two templated calls (brief, draft) + a repair loop; no tools/agent framework needed. Delivered a critique (gains: cheaper/faster/portable/testable; losses: no exploratory self-correction, API-billing wallet change, gates only catch mechanical wrongness, no adversarial review — all parity or mitigable) and a recommended new deterministic `refs_in_range` gate that would have mechanically caught the MAT-035 drift.
- **Issue #16** created capturing the proposal, critique, open questions (stdlib-`urllib` vs `anthropic` SDK; pericope-only vs sections), and acceptance criteria.

## Artifacts
- **Store:** `content_bank/store/mat.json` — 1,106 items (1,044 `reviewed` draft + 62 `published` pilots); validates with 0 errors; serves 0 reviewed items in product mode.
- **Briefs:** `content_bank/author/briefs/mat-001.md` … `mat-057.md` (for the drafted pericopes).
- **Manifest:** `work/content_bank_build/MAT/manifest.json` (stage tracking).
- **Test:** `content_bank/tests/test_store_matthew.py` — scope check now membership-based against corpus structure.
- **Commits on `feature/content-bank-matthew`:** batches 1–3, 4–5, 6–7, 8–9, 10–11, plus the test fix (7 commits total), merged via PR #15.
- **Issue:** https://github.com/kyhhdm/scripture_loom/issues/16

## Outcome
- **Matthew:** 54 of 153 pericopes staged as a `reviewed` first-draft library, merged to `main`. Joins the completed Philippians (210) and Ecclesiastes (421) draft libraries.
- All content passed verbatim-BSB quote and schema gates; provenance honest (`drafted_by: claude`, no `confirmed_by`).
- Tests green: `content_bank` 128, `corpus` 67.

## Follow-ups
- **Matthew remaining:** MAT-058–153 (95 pericopes) + 7 arc sections (MAT-S1–S7, via `build_sections_draft.workflow.js`). Next batch would be MAT-058–062, branch fresh from `main`.
- **Human review** and promotion of the ~1,044 Matthew reviewed items (plus PHP/ECC) to `published` — the deferred non-negotiable step.
- **Issue #16** — implement the standalone Python builder (with the `refs_in_range` gate) if pursued; decide stdlib-only vs `anthropic` SDK first.
