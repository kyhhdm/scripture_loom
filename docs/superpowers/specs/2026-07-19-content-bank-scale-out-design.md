# Content-bank scale-out — batching & review pipeline

**Date:** 2026-07-19
**Status:** design, pending review
**Origin:** the cross-pericope probe's explicit non-goal
(`docs/sessions/2026-07-19-cross-pericope-book-arc-layer.md`): *"The full multi-book
content-bank scale-out plan (tooling / batching / review throughput) — the probe's explicit
non-goal, now unblocked."*

## Background

The content-bank machinery is complete and green (107/107 tests): closed vocabularies, a
two-tier validator (`content_bank/lib/schema.py`, `validate.py`), a single published-only
content gate (`content_bank/lib/content.py`), and the two-stage offline authoring harness
(`build_brief_prompt.py` → `build_draft_prompt.py`, plus `build_section_brief_prompt.py`
and `build_reference_prompt.py`). The arc tier (section-scoped throughlines / threads / arc
questions) shipped in arc-artifact-v2, proven against fixtures.

What does **not** exist is the throughput to author at book scale. The store holds only
**62 items across 4 of Matthew's 153 pericopes**, all English, **zero** section/arc content
committed. The 4-pericope pilot was run by hand: drafter subagent, then ≥2 parallel
adversarial reviewer subagents, then human confirmation. This spec formalizes that pattern
into a repeatable, resumable pipeline and carries three books — Philippians, Ecclesiastes,
Matthew — from "text + commentary exist" to "full published content bank," without
weakening the WCF-1 human-confirmation invariant.

## Goal

A repeatable pipeline producing, per book: the per-pericope tier (D1–D8 items, all age
tiers, leader references) **and** the section/arc tier (throughlines, threads, arc
questions), at ~170-pericope total scale, gated by a human review model sized to the real
bottleneck — human confirmation, not AI drafting.

## Scope & key decisions (taken during design)

- **Tiered-by-risk human review.** The confirmation unit is split by doctrinal risk, not
  applied uniformly:
  - **D1–D5 (closed / factual):** confirmed as a compact **per-pericope digest** — all
    items + answer keys + adversarial verdicts reviewed together, batch confirm/reject with
    inline spot-edits.
  - **D6–D8 + throughlines / threads / arc questions (interpretive):** surfaced
    **item-by-item** for individual human confirmation, each with its adversarial-review
    notes and WCF-1 rationale.
  This concentrates the human's scarce attention where doctrinal risk is highest while
  keeping factual content moving.
- **Claude Code workflow fan-out** is the orchestration. A resumable workflow runs the
  brief → draft → adversarial-review chain per pericope (and per section for the arc tier),
  concurrently across units, emitting review-ready digests into a queue. It formalizes the
  proven pilot pattern; it does not invent a new authoring method.
- **Drafting is out-of-band and out-of-tree.** All orchestration and draft artifacts live
  in untracked `work/` (like the existing `work/content_bank_quality/`). Nothing touches
  `content_bank/store/` or `corpus/` until a human confirms. This preserves the stdlib-only
  / offline invariant of the committed trees: the orchestration is build-time scaffolding,
  not shipped code.
- **Phase 0 (corpus structure for PHP & ECC) is part of this spec**, not a separate one —
  the build cannot start without it and it is small.
- **Philippians is the end-to-end proof book**, run in full (including arc content) before
  Ecclesiastes, then Matthew.
- **The 4 existing Matthew pilot pericopes (MAT-009/013/014/015) are grandfathered** as-is —
  already `published` with provenance; they are not re-run under the formal pipeline. The
  Matthew build (Phase 3) authors the remaining 149 pericopes and reconciles section
  membership around the grandfathered four.

### Non-goals (explicit YAGNI)

- **Chinese (`zh`) content and its separate conformity review.** English-first; deferred in
  every prior cycle and deferred here. `title_zh` left blank in new corpus structure,
  consistent with `sections/mat.json`.
- **The D3 corpus lexicon.** Does not exist; not built here.
- **The interactive heart-prep gate** (issue #3, `docs/heart-prep-gate-followup`). Needs a
  product layer the repo lacks; out of scope.
- **Leader-adjustable section boundaries.** Deferred through all arc increments; still
  deferred.
- **No `dimensions.py` change.** arc-artifact-v2 retired the D2 authoring reshape as YAGNI;
  this spec adds no dimension work.

## Sequencing — four phases with approval gates

Do not start Phase N+1 until Phase N's book is fully published and a short pipeline
retrospective is done.

1. **Phase 0 — Corpus structure (PHP + ECC).** Author `pericopes/php.json`,
   `pericopes/ecc.json`, then `sections/php.json`, `sections/ecc.json`. Human editorial
   boundary work; the partition validator (`corpus/lib/sections.py`) requires the pericope
   layer first. **MHC (Matthew Henry) is the primary authority for pericope and section
   boundaries**; JFB and the passage text inform but do not override it where they disagree.
2. **Phase 1 — Philippians proof.** Run the entire pipeline on Philippians end-to-end,
   including the arc tier. This is where throughput and review ergonomics are shaken out at
   small scale before volume.
3. **Phase 2 — Ecclesiastes.** Genre stress-test (wisdom literature; exercises the recent
   genre-awareness work) at mid size.
4. **Phase 3 — Matthew.** The 149 remaining pericopes plus the full section/arc tier,
   authored section by section, reconciling around the grandfathered pilot four.

## Components

### 1. Corpus-structure prerequisite (Phase 0)

Mirrors the existing Matthew artifacts exactly:

- `corpus/canon/structure/pericopes/<book>.json` — ordered array; each entry `range`,
  `title_en`, `title_zh` (blank), `status`.
- `corpus/canon/structure/sections/<book>.json` — contiguous partition
  (`first_pericope`/`last_pericope`/`marker`), validated by `corpus/lib/sections.py`.

PHP → a handful of pericopes, 2–4 sections. ECC → larger, sections along its structural
movements. No fan-out; this is human editorial work. **MHC is the primary boundary
authority**; JFB and the text inform but do not override it on disagreement.

### 2. Per-pericope fan-out (Tier 1 — the batching core)

A Claude Code workflow. For each pericope in the target book:

1. **Stage-1 brief** — assemble the `build_brief_prompt` pack → drafter subagent →
   fidelity-reviewed brief committed to `content_bank/author/briefs/<pericope>.md`.
2. **Stage-2 draft** — `build_draft_prompt` pack (passage + brief + compact WCF-1 +
   dimensions + rubric) → D1–D8 items with leader references, as draft JSON.
3. **Adversarial review** — ≥2 parallel reviewer subagents, prompted to refute /
   WCF-1-check each item.
4. **Structural gate** — `validate.py` structural checks on the draft.
5. **Emit digest** — write a review-ready digest for this pericope into the queue.

Pericopes run concurrently (capped), resumable from the manifest (§5).

### 3. Per-section arc fan-out (Tier 2)

Fires for a section only once all its pericopes are drafted (Tier 1 complete for the
section). Uses `build_section_brief_prompt` → one throughline (D7) + threads (D3/D7 with
verse `refs`) + arc questions → adversarial review → digest. Depends on Tier 1 output +
corpus ordering + `crossrefs.json`; adds nothing to per-pericope data (consistent with
probe decision D-A).

### 4. Tiered review queue + digest tooling

The workflow's output is a **queue of digests**, not published content. Review tooling
(extend `review_checklist.py` or a sibling module) renders per unit:

- **D1–D5:** a compact per-pericope digest — items + answer keys + adversarial verdicts —
  for batch confirm/reject with inline spot-edits.
- **D6–D8 + throughline / thread / arc question:** item-by-item, each with adversarial
  notes and WCF-1 rationale.

Human confirmation stamps provenance (`drafted_by: claude`, `reviewed_by:
claude-adversarial`, `confirmed_by: kyhhdm`, `guardrail: WCF-1`), flips `review_status` to
`published`, and commits into `content_bank/store/<book>.json`. `validate.py` runs on the
committed store as the final gate.

### 5. State manifest & resumability

A per-book manifest in `work/` records each pericope/section's stage:
`pending → briefed → drafted → reviewed → in-queue → confirmed → published`. The workflow
reads it to skip completed units and resume after interruption; the review tooling reads it
to show what is awaiting the human. This ledger makes a 153-pericope build survivable across
many sessions.

## Data flow

```
Phase 0: human authors pericopes/<book>.json → sections/<book>.json  (corpus, validated)
   │
Tier 1 (per pericope, fanned out, → work/):
   brief pack → drafter → brief.md
             → draft pack → draft JSON → ≥2 adversarial reviewers → validate.py → digest
   │
Tier 2 (per section, after its pericopes drafted, → work/):
   section-brief pack → throughline/threads/arc-Q → adversarial review → digest
   │
Review queue (work/):  digests, tiered by risk
   │  human: D1–D5 batch-confirm per pericope; D6–D8 + arc item-by-item
   ▼
content_bank/store/<book>.json  (published, provenance-stamped) → validate.py final gate
```

## Testing

- New tooling (queue generator, manifest, digest renderer) gets unit tests under
  `content_bank/tests`, keeping the 107/107-green bar.
- Existing gates — `schema.py`, `validate.py`, `review_checklist.py`, corpus
  `sections.py` — are reused, not bypassed; the workflow feeds them.
- Phase 0 corpus files are validated by the existing partition validator and a
  `test_store_validates_clean`-style check per new book once content lands.
- Stdlib-only holds for all committed code; the workflow orchestration is build-time
  scaffolding in `work/`, never imported by shipped modules.

## Open risks / watch-items (non-blocking)

- **Human review is the real throughput ceiling.** The fan-out can outrun confirmation; the
  tiered model exists to keep the interpretive queue small enough to clear. If the D6–D8
  queue still backs up on Philippians, that is the signal to revisit the tiering before
  scaling to Matthew.
- **Adversarial review quality is not mechanically provable.** As stated in the
  infrastructure session, the software proves an item was reviewed, not that it is
  doctrinally sound. WCF-1 conformity remains a human judgment.
- **Matthew section reconciliation.** The grandfathered four pericopes sit inside sections
  that Phase 3 must author around; verify their section membership when the Matthew arc tier
  is built.
