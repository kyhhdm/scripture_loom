# Jonah full-pipeline pilot — findings

- **Date:** 2026-07-28
- **Purpose:** First end-to-end run of the content pipeline using the new `seed_sections`
  tool, on an untested genre (OT narrative). Answers the question posed before scale-out:
  *how much correction does a new genre need, and does the section seeder work in practice?*

## What ran

| Stage | Tool | Config | Result |
|-------|------|--------|--------|
| 1. Pericopes | `seed_pericopes.py JON` | deterministic (BSB `\s`) | 6 pericopes, clean narrative arc |
| 2. Sections | **`seed_sections` (new)** | claude/opus | 4-movement partition, validated, promoted |
| 3. Pericope drafts | `build_cli --kind pericope` | claude/opus, review ON | **ok=6 failed=0**, 101 items, full D1–D8 |
| 4. Section arc | `build_cli --units JON-S1` | claude/opus | ok=1 (S1), 7 items (throughline/threads/questions) |
| 5. Translation | `translate_cli` | deepseek-v4-flash | 108 proposals, 33 flagged, 4 drift |
| 6. Review page | `translate_compare_html` | — | `runs/opus/translations/review.html` |

## Findings

### 1. The section seeder works on first real use
`seed_sections --book JON` proposed a valid, commentary-grounded 4-movement partition
(one per chapter: Flight/Pursuit → Prayer from the Depths → Second Commission/Repentance
→ Anger/Compassion). All markers correctly `null` (Jonah has no repeating textual formula,
so none were invented — the verify-and-drop guard did its job). The partition validated
clean against `sections.validate_data` and was staged for review, then promoted.

### 2. OT narrative needed ZERO prompt fixes
This was the open risk (only wisdom/gospel/epistle had been exercised). The genre-aware
draft prompts handled Jonah narrative with **no hard-gate failures and no prompt edits** —
all 6 pericopes drafted with full D1–D8 coverage and passed gates + two-lens review.
Narrative is not a genre that needs prompt work; that risk did not materialize here.

### 3. Section granularity is the one real tuning finding
The seeder's chapter-aligned partition left **3 of 4 sections spanning a single pericope**
(chapters 2/3/4). Single-pericope sections cannot carry cross-pericope threads (the
thread-span gate rejects them by design), so only **JON-S1** (chapter 1's 3 pericopes)
produced arc content. For short narrative books, a coarser partition (e.g. the classic
2-panel Jonah: chs 1–2 / chs 3–4) would yield more thread-bearing movements. This is a
**seeder-granularity consideration, not a bug** — the partition is theologically valid;
it just interacts with the arc layer's multi-pericope requirement. Options for scale-out:
(a) accept fine partitions and only build arc content for multi-pericope sections, or
(b) steer the seeder toward coarser movements for short books.

### 4. Cheap-model translation flags concentrate in quote-dense text
33/108 proposals came back `gate_ok=false`, dominated by `citation.verse_mismatch` (11)
and `citation.untagged_quote` (6), **concentrated in JON-004 (Jonah's psalm)** — a chapter
woven from Scripture where verbatim-CUV alignment is hardest. This is the documented
flash weakness working as designed: the gate surfaces them for review rather than shipping
silently. A stronger translator (opus) would flag fewer. 4 items drew doctrinal-drift
flags for review.

### 5. Human review remains the bottleneck (as predicted)
The run produced 108 English items + 108 Chinese proposals (33 flagged) for a single short
book in well under an hour of wall-clock. Review capacity, not generation, governs
scale-out throughput. All content sits at draft/proposal stage — nothing promoted to the
served store.

## Artifacts (untracked, review-stage)

- Corpus structure (new, staged for human confirmation): `corpus/canon/structure/pericopes/jon.json`, `corpus/canon/structure/sections/jon.json` (both `status:"seeded"`).
- Drafts: `work/content_bank_build/JON/runs/opus/drafts/` (6 pericopes + JON-S1).
- Translations: `work/content_bank_build/JON/runs/opus/translations/deepseek-v4-flash/` (108).
- Review page: `work/content_bank_build/JON/runs/opus/translations/review.html`.

## Recommendation for scale-out

The pipeline is ready for more narrative books with the current prompts. Before a broad
run, decide the section-granularity policy (fine vs coarse for short books) and budget
review capacity to match generation. Consider opus translation for quote-dense chapters
(psalms, prayers) to cut the review flag count.
