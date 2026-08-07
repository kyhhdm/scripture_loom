# Cross-pericope fluency → book-arc layer (probe, MVP, v2, safety sweep)

- **Date:** 2026-07-19
- **Branches / PRs:** `feature/cross-pericope-probe` (#6), `feature/book-arc-layer` (#8, superseding auto-closed #7), `feature/arc-artifact-v2` (#9), `fix/passage-subscript-safety` (#10) — all merged to `main` (final `b63e28d`).
- **Summary:** Starting from "is it time to build the whole content bank, and how do we handle fluency across pericopes?", we ran an empirical probe (green-lit the build, found the cross-pericope orphan), then shipped the book-arc layer in three merged increments — derived MVP, authored v2 arc artifact, and a safety sweep — each brainstormed → spec → plan → subagent-executed with review gates.

## Request

Two questions to open: (1) with the recent content-bank infrastructure MRs, is it time to build the whole content bank? (2) The bank is built on the smallest unit (the pericope) — how do we work the fluency of timeline, events, and logic progressions that cross pericopes within a book? The session then proceeded through each follow-on piece the work surfaced.

## What we did

- **Framed the tension.** The pericope pipeline was production-ready, but the model *actively walls off* cross-pericope structure (D2's "avoid sequence spanning other pericopes" rule; D5 is pairwise) while the D7 assessment ladder already aspires to book-scale interpretation. So scaling now risked baking a gap into a large bank.
- **Cross-pericope probe (#6).** Copied the genre-probe method: hand-authored cross-pericope items across D1–D8 for a narrative span (Matthew infancy MAT-001..008) and an epistle span (whole of Philippians), each WCF-1-reviewed by a subagent gate.
  - Result: both spans orphan the **same** skill — *cross-pericope structural comprehension* (D2 refuses it by rule; D4/D5/D7 house only its products). Matthew 5✓/2△/1✗; Philippians 3✓/4△/1✗ (D5 corrected ✓→△ on review).
  - Decisions: **D-A = no** (no per-pericope authoring hook needed) → **GREEN LIGHT** for the full build; D-B derived spine + arc artifact; D-C session shape is a finding; D-D no stored section layer required. Orphan handled by a scheduling/reshape move over D2/D5/D7, **not a new dimension D9**.
- **Book-arc layer MVP (#8).** Brainstormed to a *derived-only* MVP with one deliberate step up (the user chose "meaningful boundaries," which forced a minimal section map). Shipped: a per-book **section map** (`structure/sections/mat.json`, Matthew's 7 discourse-marker sections, validated contiguous partition of 153 pericopes), a derived **recap micro-segment** on every kit, and a **zoom-out session** firing at each section boundary (replaces the session; derived sequence-reconstruction cards + memory recall + open throughline prompt). Scored via derive-don't-store (session `kind`), no D9.
- **Arc artifact v2 (#9).** Brainstormed the authored interpretive tier. Chose full content scope (throughlines + threads + questions), modeled as **section-scoped ContentItems** (`passage` xor `section`, refining probe D-B rather than violating it), threads scoped at an **anchor section** carrying member `refs`. Formally **retired the D2 authoring reshape as YAGNI** (only D2 has an anti-span rule; arc content is D7/D3/D5). Shipped schema + store validation + a section-scope authoring brief + zoom-out integration that degrades to exact MVP behavior when no arc content exists.
- **Passage-subscript safety sweep (#10).** Both the MVP and v2 whole-branch reviews had caught the same class of Critical (a selector helper subscripting `passage` and dying on the new scoped item/session). Audited every `passage`/`section` subscript; found one remaining latent bug and fixed it.
- **Process throughout:** each increment followed brainstorming → written spec → written plan → subagent-driven execution with per-task spec+code-quality gates and an opus whole-branch review. The whole-branch review earned its cost twice, catching a Critical in both #8 and #9 that per-task reviews structurally couldn't see.

## Artifacts

- **Specs:** `docs/superpowers/specs/2026-07-19-cross-pericope-probe-design.md`, `…-book-arc-layer-design.md`, `…-arc-artifact-v2-design.md`.
- **Plans:** `docs/superpowers/plans/2026-07-19-cross-pericope-probe.md`, `…-book-arc-layer.md`, `…-arc-artifact-v2.md`.
- **Probe findings:** `docs/2026-07-19-cross-pericope-probe-findings.md`.
- **Corpus:** `corpus/canon/structure/sections/mat.json`, `corpus/lib/sections.py` (+ `corpus/tests/test_sections.py`).
- **Content bank:** `content_bank/lib/schema.py` (section scope, throughline/thread, refs), `content_bank/lib/validate.py` + `corpus_bridge.section_ids`, `content_bank/author/build_section_brief_prompt.py`.
- **Prototype selector:** `prototype/selector.py` (`arc_recap`, `due_zoom_out`, `build_zoom_out_kit`, `_published_section`, section-scope integration, the two review fixes + the sweep fix), `prototype/generate_kit.py` (recap + zoom-out rendering).
- **Key fix commits:** `d6eca39` (MVP `select_review_questions` KeyError), `a91e64d` (v2 `_published` KeyError), `7c724ee` (sweep: `build_zoom_out_kit` memory_recall KeyError).
- **PRs:** #6, #8 (#7 auto-closed by a stacked-base branch deletion), #9, #10 — all merged.

## Outcome

All four increments merged to `main` (`b63e28d`); local and remote in sync. Final suites green: **selector 33 / content_bank 107 / corpus 67**, smoke render exit 0. The full content-bank build is unblocked, and the book-arc layer is complete through authored content, with the `passage`-subscript failure family closed out.

## Follow-ups

- Author real WCF-1-reviewed section content (throughlines/threads/questions) into `store/mat.json` — the v2 machinery ships proven with fixtures; committing reviewed content is separate authoring work.
- Leader-adjustable section boundaries (deferred through all three increments).
- The full multi-book content-bank scale-out plan (tooling / batching / review throughput) — the probe's explicit non-goal, now unblocked.
