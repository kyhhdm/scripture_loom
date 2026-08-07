# Section Discovery Questions — design, build, and Jonah pilot

- **Date:** 2026-07-29
- **Branch / commits:** `feature/section-discovery-questions` → PR #28 (merged to `main` as `c86ff33`). Also merged PR #27 (`a4f34dc`, multi-pericope section steering) at the start of the session.
- **Summary:** Turned a pedagogy question — should section throughline/thread content be *discovered* rather than handed over? — into a shipped feature: section-level `throughline` and `thread` items are now drafted as discovery questions whose traced answer is revealed via a `leader_reference`. Designed, spec'd, planned, built via subagent-driven development (with a real cross-task regression caught and fixed), merged, then piloted end-to-end by rebuilding Jonah's JON-S2 and updating its bilingual review page.

## Request

A sequence of connected asks:
1. Merge PR #27 (multi-pericope section steering + Jonah re-seed).
2. Explain how `thread` and `throughline` item types — which aren't questions — are actually used.
3. Explore converting them into questions that let a leader *discover* the result rather than being shown it. Decision: do it for **both** the leader (during Prepare) and the family (during Gather), from one item.
4. Take the idea into a written spec → implementation plan → build it (subagent-driven) → merge.
5. Rebuild JON-S2 under the new format and update `review.html`.
6. Merge the feature.
7. Export the session.

## What we did

- **Merged PR #27** (`a4f34dc`): `seed_sections` steered toward multi-pericope movements; Jonah re-seeded to a 2-panel section map.
- **Explained throughline/thread** against the real pipeline (`docs/content_build_terminology.md`, `build_section_draft_prompt.py`): both are *statement content* at the section (book-arc) layer — the throughline is the section spine (one, D7); threads are motifs recurring across 2+ pericopes (D3 tracked-word or D7 interpretive), the only item type carrying `refs`. Both are leader-facing prep material with no `leader_reference`.
- **Brainstormed** the discovery-question idea (superpowers:brainstorming). Surfaced the pivotal fork — *who* discovers: the leader (their own fluency, the "unautomatable factor") vs. the family (a ready-made prompt for the table). User chose **both**, from one item.
- **Key schema discovery:** `leader_reference` is banned only on `memory_verse`; the "no reveal on throughline/thread" rule lived only in the drafting prompt. And the reveal *kind* maps one-to-one onto the dimension already assigned — D3 (closed) → `answer_key`, D7 (open) → `leader_note` — reusing the validator's existing rule. So the feature needs **no `schema.py` change**.
- **Wrote spec + plan**, committed to the branch. Four bite-sized tasks.
- **Built via subagent-driven development:** fresh implementer + reviewer per task, final opus whole-branch review.
  - Task 1: `section_reveal_check` HARD gate (enforces the dimension→kind pairing), wired into `run_all`.
  - Task 2: schema regression guard (test-only — proves the shape already validates).
  - Task 3: drafting prompt emits question stems + dimension-matched reveals; removed the old "need NO leader_reference" line.
  - Task 4: surfaced the new gate on the review page (range-independent pass; reveal text already rendered by the type-agnostic `_leader_ref`).
- **Caught a cross-task regression the subagents misdiagnosed:** `section_reveal_check` in `run_all` flagged `SectionBuildTest`'s mock throughline (no reveal), driving an extra repair-loop `llm` call past the mock's `side_effect` → `StopIteration`. The implementers had called it "pre-existing" because their `git stash` reproduction was a no-op (the change was already committed). Verified by commit bisect (base OK, Task-1 commit FAILED) and fixed the fixture to the new contract. Full suite went green (345 OK).
- **Merged PR #28** to `main`.
- **Piloted the feature on Jonah's JON-S2:** rebuilt it (claude/opus) under the new prompt — the throughline and two threads now read as genuine discovery questions with the traced result in the reveal; gates CLEAN. Re-translated the 6 new items (flash), deleted 5 stale proposals for dropped/renamed items, and regenerated the en▸zh▸CUV `review.html` (116 items). Two translations carry the usual flash CUV-quote-fidelity flags for human review (unrelated to the restructure).

## Artifacts

- **Spec:** `docs/superpowers/specs/2026-07-29-section-discovery-questions-design.md`
- **Plan:** `docs/superpowers/plans/2026-07-29-section-discovery-questions.md`
- **Production:** `content_bank/author/gates.py` (`section_reveal_check` + `run_all` wiring), `content_bank/author/build_section_draft_prompt.py` (prompt rewrite), `content_bank/author/compare_html.py` (review-page surface).
- **Tests:** `test_gates.py`, `test_schema.py`, `test_section_prompt.py`, `test_compare_html.py`, `test_build_cli.py` (fixture fix).
- **Pilot (untracked, in `work/`):** rebuilt `runs/opus/drafts/JON-S2.json`, re-translated proposals under `runs/opus/translations/deepseek-v4-flash/`, regenerated `runs/opus/translations/review.html`; old draft backed up as `JON-S2.json.pre-discovery.bak`.
- **PRs:** #27 (merged, `a4f34dc`), #28 (merged, `c86ff33`).

## Outcome

- Feature shipped on `main`. Section throughline/thread items are now discovery questions with dimension-matched reveals, enforced by a HARD gate. No `schema.py` change (guarded by a regression test).
- Suites green: content_bank **345 OK**, corpus **67 OK**.
- JON-S2 rebuilt and its bilingual review page updated — the feature demonstrated end-to-end on real content.
- All Jonah pilot artifacts remain review-stage (untracked in `work/`); nothing promoted to the served store, honoring the "AI proposes, the leader confirms" invariant.

## Follow-ups

- Human review of the updated JON-S2 `review.html`, including the 2 flash CUV-quote-fidelity flags.
- Forward-only by design: existing statement-form section items (elsewhere in the bank) are not migrated; re-seeding them under the new prompt is a later choice.
- Process lesson (recorded in the SDD ledger): verify "pre-existing failure" claims against the **base commit**, not `git stash`, when the change is already committed.
