# Psalms 1–10 full-pipeline run — findings

- **Date:** 2026-07-29
- **Purpose:** Run the whole content pipeline on Psalms 1–10 and evaluate output quality.
  Psalms is the first sustained test of **Hebrew poetry** and its hardest sub-genres —
  wisdom, penitential lament, imprecatory lament, royal/messianic, creation praise — with
  the theological cruxes those carry (the Psalm 2:7 "today I have begotten you" adoptionism
  trap, the Psalm 8 / Hebrews 2 man-vs-Christ reading, imprecation, the Sheol/afterlife
  question). It follows the OT-narrative pilot (`docs/2026-07-28-jonah-pilot-findings.md`).

## What ran

| Stage | Tool | Config | Result |
|-------|------|--------|--------|
| 1. Pericopes | `seed_pericopes.py PSA` | deterministic (BSB `\s`) | 150 pericopes; **chs 1–10 = one psalm each** (PSA-001…010), clean |
| 2. Sections | — (out of scope) | — | The section layer is **whole-book** by construction — see finding 7 |
| 3. Pericope drafts | `build_cli --units PSA-001…010` | claude/opus, review ON | **ok=9, fail=1** first pass; PSA-007 clean on a plain retry → **10/10, 187 items, full D1–D8** |
| 4. Translation | `translate_cli` | deepseek-v4-flash | 187 proposals, **25 gate-flagged (13%)**, 9 drift-flagged |
| 5. Review pages | `compare_html`, `translate_compare_html` | — | `runs/opus/../review.html` (EN) + `translations/review.html` (EN▸ZH▸CUV) |

Total generation wall-clock: well under two hours of background runtime (opus is headless-CLI
per call, the slow leg; flash translation of all 187 items ran in ~8 minutes).

## Findings

### 1. Psalms genre needed ZERO prompt fixes
This was the open question — only narrative (Jonah), gospel (Matthew), epistle (Philippians),
and wisdom-prose (Ecclesiastes) had been exercised; sustained **Hebrew poetry** had not. The
genre-aware prompts (the brief's "reading moves: poetry → image → referent" hint plus the
corpus lampposts) handled all ten psalms with **no hard-gate failures and no prompt edits**.
Every psalm drafted with full D1–D8 coverage and passed gates + two-lens review.

### 2. Poetry is read *as* poetry
The drafts consistently treat images as images, not as data to decode: chaff and tree in
Ps 1 ("answer from the image, not a dictionary definition"), the three predator pictures in
Ps 10:8-10 read as "one portrait of predatory cunning, not a sequence of three crimes,"
the lion simile in Ps 7:2 ("the word 'like' is the handle"). Metaphor shifts are flagged
(Ps 1 leaves "the orchard for the threshing floor" at v4), and the argument-carrying
connectives of poetry are surfaced (the "For" of Ps 1:6, the "Therefore" of Ps 2:10). This
is exactly the poetry reading-move the brief prompt asks for, executed well.

### 3. The hard theological cruxes are handled with real care
The genre's danger is not exegetical but doctrinal, and the tuned opus drafts navigate the
classic traps correctly, anchored to the Standards:
- **Ps 2:7 "today I have become Your Father"** — the adoptionism trap — is answered with the
  historic caution verbatim: the resurrection/enthronement *manifested and installed in
  office* a Sonship already true, "not a Son newly made" (anchored `<doctrine std="WCF"
  ref="8.1">`). The Acts 4 fulfilment (Herod/Pilate/Gentiles/Israel) is correctly identified
  and tied to `WCF 1.9` (Scripture interprets Scripture).
- **Ps 8:4-6** is held across *both* Genesis 1:28 (the creation charter, "now only in modified
  remains" post-fall) and Hebrews 2:6-9 (Christ) — "the psalm speaks truly of man as created,
  and finds its fulfilment in the exaltation of Christ's human nature." Neither over- nor
  under-christologized.
- **Ps 6:5 (Sheol)** is framed as "an argument from God's glory, not a denial of life after
  death" — avoiding a real proof-texting trap.
- **Imprecation/lament** (Ps 7, 10) is drawn as a *type* ("do not push the family toward
  identifying a particular person"), and the unanswered "why" of Ps 10:1 is "answered not
  with an explanation but with a Person" — pastorally and doctrinally sound.

### 4. Evidence-not-judgment discipline is visibly enforced in the drafts
The leader-notes repeatedly steer away from character verdicts: "keep answers at the level of
action, not of the heart — what a person would do, not what kind of person they are"; the Ps 1
index-card activity explicitly says "do not turn the two sides into a self-assessment of which
kind of person anyone is." The product's core invariant is being honored *in the content*, not
just the schema.

### 5. Gates were clean; one transient JSON failure is the only reliability wrinkle
All 187 items pass the HARD gate tier with **0 flags** (quote-fidelity, schema, ref-range,
citation). 120 `<verse>` and 10 `<doctrine>` citation tags all verify. The single failure —
**PSA-007 on the first pass** — was a malformed-JSON parse error at the draft stage (an
unescaped delimiter in the model's output), **not** a gate or content failure; a plain retry
produced a clean 22-item draft. Reliability read: ~1-in-10 opus drafts may need a no-change
retry for JSON well-formedness. The per-unit isolation handled it correctly (the other nine
were unaffected and the run exited non-zero to flag it).

### 6. Cheap-model translation flags are lower than narrative, and split into two kinds
25/187 proposals came back `gate_ok=false` (**13%**, vs Jonah's 30%), dominated by
`citation.untagged_quote` (14) and `citation.verse_mismatch` (13) — the documented flash
weakness, surfaced not shipped. The flag messages show flash *is* emitting verbatim CUV spans
(e.g. Ps 1:1-2, Ps 2:1); it just sometimes leaves them untagged or mis-refs them. The 9 drift
flags separate into two categories a human must adjudicate differently:
- **Real translator errors** — e.g. Ps 2 flash *inserted* 「受膏者说：我要传圣旨」 into the
  quote. Fixable; reject the proposal.
- **CUV-vs-BSB translation-philosophy divergence** — e.g. CUV renders Ps 1:6 "guards" (shomer)
  as 知道 ("knows"). That is the CUV's own choice, not a flash error; the translator cannot
  "fix" it without leaving the CUV. The drift review flags it anyway (correct), but the human
  resolves it by accepting the CUV rendering, not by re-translating.

For quote-dense poetry, an opus translation pass would cut the flag count; whether it is worth
the cost is a per-book review-budget call.

### 7. The section (book-arc) layer is whole-book — out of scope for a 10-chapter slice
`corpus/lib/sections.py:validate_data` requires a section map to **partition every pericope in
the book** (150 psalms), so a valid `sections/psa.json` cannot cover only chapters 1–10. The
section layer is therefore a book-level task, not a chapter-slice task, and was deliberately not
run here. (This is stricter than the Jonah pilot, where the whole short book was in scope.) When
Psalms is built at book scale, decide the section-granularity policy up front — Psalms has
natural multi-psalm movements, e.g. the Ps 1–2 paired prologue, that the thread-bearing arc
layer wants.

### 8. Coverage and minor content notes
Every psalm hits all 8 dimensions (avg ~19 items/psalm). Type mix is varied: 110 questions, 26
activities, 22 pre-reading quests, 19 memory verses, 10 narration prompts. Age tiers spread
child 52 / youth 60 / adult 31 / all 42, but **`pre_reader` as a distinct tier is thin (2)** —
pre-reader accommodation mostly appears as inline variants inside child/all items rather than as
its own tier. One representative content looseness that human review is meant to catch:
PSA-006-012's answer key cites a fourth reference (Ps 118:17) while the question named only
Ps 115:17 and 30:9 — accurate content, slightly conflated framing.

### 9. Human review remains the throughput bottleneck (as predicted)
The run produced 187 English items + 187 Chinese proposals (25 gate-flagged, 9 drift-flagged)
for ten psalms in under two hours of background time. Review capacity, not generation, governs
scale-out. Everything sits at draft/proposal stage — **nothing promoted to the served store**.

## Overall assessment

The pipeline handles Psalms 1–10 at **production quality**. On the tuned opus config it clears
the genre's exegetical demands (poetry read as poetry) and — more importantly — its doctrinal
ones (the Psalm 2:7, Psalm 8, and Sheol cruxes handled with confessional care), with clean gates
and correct evidence-not-judgment discipline in the content itself. The two real wrinkles are
operational, not qualitative: a ~10% chance an opus draft needs a no-change retry for JSON
well-formedness, and the expected cheap-translation flag load (lower here than for narrative).
This is the strongest genre showing of the pilots so far.

## Artifacts (untracked, review-stage)

- Corpus structure (new, staged): `corpus/canon/structure/pericopes/psa.json` (150 pericopes, `status:"seeded"`).
- Canonical build manifest: `work/content_bank_build/PSA/manifest.json` (units PSA-001…010).
- Drafts: `work/content_bank_build/PSA/runs/opus/drafts/` (10 psalms, 187 items) + briefs + verdicts.
- Translations: `work/content_bank_build/PSA/runs/opus/translations/deepseek-v4-flash/` (187 proposals).
- Review pages: `work/content_bank_build/PSA/review.html` (EN) and
  `work/content_bank_build/PSA/runs/opus/translations/review.html` (EN▸ZH▸CUV).

## Recommendation

The pipeline is ready for poetry/Psalms at scale with the current prompts. Before a book-scale
Psalms run: (a) settle the section-granularity policy for the Psalter's multi-psalm movements;
(b) budget human-review capacity to the ~13% translation flag rate (or spend on opus translation
for the most quote-dense psalms); (c) optionally add a one-shot JSON-repair retry inside the
builder so a malformed-JSON draft self-recovers instead of failing the unit.

## Addendum (2026-07-30) — model settings and later PSA-003 reruns

The run above used the tuned config: **English build `--backend claude --model opus`**
(review on) and **translation `deepseek-v4-flash`** (the recommended settings, documented in
`docs/content_builder_usage.md` and `docs/content_translator_usage.md`). Its 9 drift flags were
from the **flash** back-translation review — all there was at the time.

Investigating the PSA-003 proposals afterward drove a batch of translation-pipeline fixes (PRs
#29/#30/#31: badge tooltips, drift suggested-fixes, the `_norm` CUV em-dash bug, en↔zh tag
correspondence, CUV-inherent drift notes). The later **PSA-003 reruns** therefore used an extra
setting not available for the original build: **`--drift-model deepseek-v4-pro`**, which runs the
back-translation drift review on the stronger model while translation stays on flash. It caught
drift flash gave false negatives on (e.g. the Ps 3:3 over-copy and the Ps 3:5 CUV-inherent
divergence), so for quote-dense books the recommended translation config is now
`deepseek-v4-flash` **+ `--drift-model deepseek-v4-pro`**.
