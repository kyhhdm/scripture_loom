# Content-bank prototype content: generate, judge, tune

- **Date:** 2026-07-18
- **Depends on:** the content-bank *infrastructure* (`content_bank/`, PR #1) and the
  corpus (`corpus/`). Both are treated as fixed dependencies here.
- **Status:** design approved; ready for an implementation plan.

## Goal

Generate the first real, harness-produced content bank for the kit-generator
prototype's passages, judge its quality with independent adversarial review, and
feed recurring defects back into the authoring machinery. **The content is the
test case; tuning the machinery is the durable outcome.**

This is the "author a real slice on top of the infrastructure" cycle named as a
follow-up in `docs/sessions/2026-07-18-content-bank-infrastructure.md`, scoped
down to exactly what the prototype exercises.

## Scope

**In scope** — regenerate content for the prototype's reading-sequence pericopes,
replacing the 25 hand-migrated seed items:

- `MAT-009` The Temptation of Jesus (4:1-11)
- `MAT-013` The Sermon on the Mount — setup (5:1-2)
- `MAT-014` The Beatitudes (5:3-12)
- `MAT-015` Salt and Light (5:13-16)

Also in scope — **wire the corpus lampposts into authoring as a two-stage,
passage-first process** so accuracy against them is real, not merely asserted, and
the passage is never buried under reference:

- Extend `corpus_bridge` to serve commentary (JFB, MHC), cross-references, and
  **confessional references** (WCF + WLC + WSC selected by proof-text lookup).
- **Stage 1 — distill a theological brief.** From passage + WCF-1 + commentary +
  cross-references + confessional references, produce a compact (~250-word),
  reviewed, committed per-pericope brief that is the theological base.
- **Stage 2 — draft from passage + brief.** The drafting pack carries the
  foregrounded passage + the short brief (+ a compact WCF-1 guardrail + the
  cross-reference targets), never the raw ~11k words of lampposts.
- Give the adversarial reviewers the brief (and, at Stage 1, the raw lampposts)
  as ground truth (see "Corpus assets in authoring" and "Two-stage authoring").

**Out of scope** (explicit, so the plan does not drift):

- Chinese text. English-only this cycle; a `zh` pass and a distinct
  zh-conformity review are a later cycle (the design already flags
  `review_checklist.py` as English-centric).
- The `vocab_list` and `key_facts` item types. They exist in the schema but the
  prototype selector does not render them.
- Any other Matthew pericope. 149 of the 153 stay empty.
- Changing the corpus, the store schema/vocabularies (`schema.py`), the gate
  (`content.py`), or the selector logic (`selector.py`).

(Note: the catechisms WLC/WSC, previously deferred, are **now in scope** — the
proof-text lookup makes their relevant Q&As cheap and precise to include.)

## Locked decisions

1. **Content + tune the machinery.** Effort lands on producing good content *and*
   improving `author/` from what the content teaches us.
2. **Regenerate all, replace seed.** The hand-migrated items are discarded; the
   harness output becomes the store. (No head-to-head merge.)
3. **Adversarial reviewer agents** are the quality signal — independent of the
   drafter, one lens per risk axis, prompted to *break* each item. Substance is
   judged, never keyword-linted (preserves the infrastructure invariant that the
   software proves an item was *reviewed*, not that it is *sound*).
4. **English-only.**
5. **MAT-013 joins the reading sequence** → `MAT-009 → MAT-013 → MAT-014 →
   MAT-015`. This gives the Beatitudes their "crowds / mountain / disciples"
   People-&-Places (D1) setup a real, *answerable-from-its-own-text* home.
6. **`reviewed` + confirmation digest.** Adversarial pass advances items to
   `review_status: "reviewed"`; a human confirms before anything is stamped
   `"published"`. Honors "AI proposes, the leader confirms."

## The quality rubric

A single written standard, derived from the design invariants
(`docs/core_principles.md`, `CLAUDE.md`), that **both** the adversarial reviewers
and `author/review_checklist.py` score against. Seven axes:

1. **Confessional conformity (WCF-1).** Affirms — and never hedges on —
   Scripture's inspiration, infallibility, inerrancy, sufficiency, clarity.
   Scripture interprets Scripture (WCF 1.9); no private novelty.
2. **Accuracy & answerability.** Every factual claim is correct against the
   passage and the corpus lampposts; names, places, sequence, and quotations
   match. **New, sharpened rule:** the item must be *answerable from this
   pericope's own text* — a question whose answer lives only in an adjacent
   pericope is a defect, not a cross-reference. (D5 "Connections" is the sole
   exception and must name where it reaches.)
3. **Evidence, never judgment.** Prompts elicit observable behavior; they never
   ask for or imply assessments of faith, character, or spiritual state.
4. **Age fitness.** Language and difficulty match the item's `age_tier`;
   activities are doable on paper with ordinary materials.
5. **Dimension fit.** The item genuinely exercises its tagged dimension (a D2
   item is about sequence, not vocabulary wearing a D2 label).
6. **Worship, not academy.** Serves fluency and the heart, not academic trivia;
   nothing that belongs to the denied during-session category (live scoring,
   gamification, etc.).
7. **Pedagogical strength.** A genuinely good prompt: open where it should be
   open, not leading, not trivially yes/no unless deliberately a warm-up.

**Coverage principle (falls out of MAT-013):** cover every dimension the passage
*genuinely supports*, at the tiers the selector needs — no more. Forcing a
dimension a thin text cannot carry (e.g. D7 interpretation on the 2-verse 5:1-2
setup) violates axis 1's "meaning from the text, not speculation." **Under-covering
a thin passage is correct, not a gap.** Target per rich pericope: questions across
the supported dimensions at mixed tiers/difficulties (~8-10), one child-or-youth
activity + one `pre_reader` variant, pre-reading quests at child/youth/adult, one
`memory_verse`, one `narration_prompt`.

## Corpus assets in authoring

What the corpus holds, and how each asset is used when drafting a pericope. Today
(before this cycle) only the first two are wired in; this cycle adds commentary
and cross-references.

| Asset | Corpus location | Role in authoring |
|---|---|---|
| **Bible text** (BSB/KJV/WEB/CUV) | `canon/bibles/` via `corpus/lib/passage.py` gate | The pericope's verses — the text every non-D5 item must be answerable from. *Already wired* (`passage_text`, BSB). |
| **Confession** (WCF ch.1) | `canon/lampposts/wcf.json` | The hard doctrinal guardrail injected into every pack. *Already wired* (`wcf_chapter1_text`). |
| **Commentary** (JFB, MHC) | `canon/lampposts/{jfb,mhc}/<book>.json` | **Exegesis** — what the text says. Grounds the brief (axes 1, 2, 5, 7). **Wired this cycle (Stage 1).** |
| **Cross-references** | `canon/structure/crossrefs.json` | **Scripture interprets Scripture** — the vetted, real targets for D5. Grounds the brief; the top refs also carry into the draft pack. **Wired this cycle.** |
| **Confession** (WCF 2-33) + **Catechisms** (WLC/WSC) | `canon/lampposts/{wcf,wlc,wsc}.json` | **Doctrine** — what the church confesses this passage teaches. Selected per pericope by **proof-text reverse-lookup**; grounds the brief. **Wired this cycle (Stage 1).** |
| Dictionary / lexicon | — | **Does not exist.** D3 (Vocabulary) leans on the commentary; a lexicon is a possible future corpus asset, out of scope here. |

**The two roles of the confessional material.** WCF **chapter 1** is the *method*
guardrail — how any content must treat Scripture (inspired, inerrant, sufficient,
Scripture-interprets-Scripture). It is *standing*: it applies to every item on
every passage, so a **compact** form of it rides in every draft pack, and its full
text grounds the brief stage. The **rest of WCF plus WLC/WSC** is the *doctrinal
map* — passage-specific, selected by proof-text lookup, and folded into the brief.

**Data shapes (verified):**

- Commentary: `{work, book, license, role, blocks: [{range: "MAT.4.1-11", text}]}`,
  keyed by `BOOK.CH.V-V`. Keying differs by work: **MHC is per-pericope**
  (`MAT.5.1-2`, `MAT.5.3-12`), **JFB is per-verse** (`MAT.5.3`, `MAT.5.4`, …), and
  neither always aligns to pericope boundaries. The reader returns blocks whose
  range **overlaps** the pericope range (not only exact matches) and gracefully
  returns an empty list when nothing overlaps. All four in-scope pericopes have
  commentary in both works.
- Cross-references: `{role, refs: [{from: "MAT.5.3", to: "PSA.37.11", weight,
  sources}]}`, ~344k entries. The per-pericope reader returns refs whose `from`
  falls within the pericope's verse span, ranked by `weight` (descending), capped
  (e.g. top 15) to keep the pack bounded.
- Confessional standards: `wcf.json` = `{chapters: [{n, title, sections: [{n,
  text, proof_texts: [...]}]}]}`; `wlc.json` / `wsc.json` = `{questions: [{n, q,
  a, proof_texts: [...]}]}`. Each `proof_texts` entry is a Scripture ref
  (`ROM.11.36`, `MAT.5.5`, …). The per-pericope reader returns the WCF sections
  and WLC/WSC Q&As whose proof-texts overlap the pericope, each carrying its text
  and the citing verse. Output is naturally small (0-11 hits/pericope, verified);
  MAT-013 has zero — coverage restraint applies (omit, don't force).

**License note:** JFB, MHC, and the Westminster standards (WCF/WLC/WSC) are public
domain; all are used as *authoring-time grounding only* — they inform the drafter,
the brief, and the reviewers but are never copied into shipped items (verbatim
quotations come from the gated Bible text). No new license surface enters the
store. Cross-references are CC-BY (openbible.info); if any shipped product later
surfaces them, attribution is required — not triggered by this cycle, which uses
them only during authoring.

## Two-stage authoring

The problem this solves: for the Beatitudes the lampposts run ~10,900 words
(WCF-1 977 + MHC 5,973 + JFB 3,957) against a ~130-word passage — roughly **80×**.
Injected raw, the passage drowns and the drafter is tempted to write *about the
commentary*. So authoring splits into distill → draft.

**Stage 1 — the theological brief.** `build_brief_prompt.py` assembles a
distillation pack (the passage + full WCF-1 + commentary + top cross-references +
the confessional proof-text hits). Here length is fine — the task is synthesis,
not generation. The drafter produces a compact **~250-word brief** with a fixed
shape: the passage's own emphasis (primary); key terms grounded in the commentary;
the doctrinal anchors (which WCF/WLC/WSC statements bear, and the method from
WCF-1); the vetted cross-references, each with a one-phrase note. The brief is
**adversarially reviewed for fidelity** — faithfully represents the lampposts,
adds no private novelty, keeps the passage's emphasis primary — then **committed**
as `content_bank/author/briefs/<pericope>.md`. It *is* the theological base.

**The proof-text safeguard (load-bearing, not theoretical).** A proof-text link
means "the divines grounded doctrine X partly here," *not* "this passage is a
treatise on X." Verified example: the Beatitudes hit **WLC Q172**, whose subject
is the Lord's Supper; the brief must extract only Q172's reading of "poor in
spirit / mourn" as the humble, needy heart and drop the sacramentology as
off-agenda. The fidelity review enforces exactly this discernment.

**Stage 2 — drafting items.** `build_draft_prompt.py` carries the **foregrounded
passage + the committed brief + a compact WCF-1 guardrail + the cross-reference
targets** (+ the rules/types/rubric). Passage-to-base is now ~1:2, not 1:80. The
quality reviewers get the brief + passage as ground truth, with the full lampposts
available only if a reviewer wants to dig.

## Workflow (per pericope)

```
STAGE 1 — brief
passage + full WCF-1 + commentary(JFB/MHC) + crossrefs + confessional_refs
                    │
                    ▼
build_brief_prompt.py ──▶ drafter ──▶ ~250-word brief
                                          │
                                          ▼
                  adversarial FIDELITY review (faithful? no novelty?
                  passage-emphasis primary? loose proof-texts handled?)
                                          │ clean
                                          ▼
                  commit  content_bank/author/briefs/<pericope>.md

STAGE 2 — items
passage (foregrounded) + brief + compact WCF-1 + crossref targets
                    │
                    ▼
build_draft_prompt.py ──▶ drafter ──▶ draft items
                                          │
                          ┌───────────────┘
                          ▼
        adversarial QUALITY reviewers (seven rubric axes;
        handed the brief + passage as ground truth)
                          │  verdicts + defects
                          ▼
                    triage each defect
                    ├── fix the item ──────────────┐
                    └── fix the machinery           │
                         (brief-builder, draft pack,│
                          dimensions, or checklist)  │
                          │                          │
              apply machinery fix, regenerate/repair │
                          └───────────► re-review ◀──┘
                                          │ clean
                                          ▼
                         review_status: "reviewed" (+ provenance)
```

After all four pericopes are clean → **confirmation digest** → human approval →
stamp `"published"` → write `store/mat.json`.

**Triage rule.** A defect is a *machinery* fix (not just an item fix) when it
recurs across items or pericopes, or when it traces to a missing instruction the
drafter could not have known — a gap in the drafting prompt, the per-dimension
guidance, or the checklist. One-off content mistakes are item fixes. Every
machinery change is recorded with the defect that motivated it.

## Components changed

- **New — the rubric artifact.** The seven axes above, in a form the reviewer
  agents are handed and `review_checklist.py` mirrors. Location:
  `content_bank/author/rubric.py` (a `build()` returning the text, matching the
  existing `review_checklist.py` / `dimensions.py` shape), so it is single-sourced
  and importable by both the checklist and the drafting pack.
- **`lib/corpus_bridge.py`** — add three read-only accessors: `commentary(range_str,
  book="MAT", works=("mhc","jfb"))` returning the overlapping commentary blocks per
  work; `crossrefs(range_str, limit=15)` returning the top-weighted cross-references
  whose `from` falls in the range; and `confessional_refs(range_str)` returning the
  WCF sections and WLC/WSC Q&As whose proof-texts overlap the range (each with its
  text and citing verse). Read directly from the corpus JSON canon like the
  existing accessors; no corpus dependency on `sys.path`.
- **New — `author/build_brief_prompt.py`.** Assembles the Stage-1 distillation
  pack (passage + full WCF-1 + commentary + crossrefs + confessional_refs) and the
  instruction to produce the fixed-shape ~250-word brief, including the proof-text
  safeguard. Offline, stdlib-only, no API.
- **New — `author/briefs/<pericope>.md`.** The committed, fidelity-reviewed
  theological briefs — the durable theological base and part of provenance.
- **`author/dimensions.py`** — expand each one-line template into drafting
  guidance rich enough to prevent the recurring dimension-fit and answerability
  defects the review surfaces. Meaning still sourced from
  `docs/design-kit_generator.md` Part 1.
- **`author/build_draft_prompt.py`** — becomes the Stage-2 pack: **foreground the
  passage**, then carry the committed **brief**, a **compact WCF-1 guardrail** (not
  the full 977-word chapter — that lives in the brief stage), and the
  **cross-reference targets** for D5; plus the answerable-from-this-pericope rule,
  coverage-per-supported-dimension guidance, per-type expectations,
  tier/difficulty calibration, and the evidence-not-judgment constraint. Keep it
  offline, stdlib-only, no API.
- **The adversarial reviewer prompts** — two flavors: a Stage-1 **fidelity**
  reviewer (brief faithful to lampposts, no novelty, passage-emphasis primary,
  loose proof-texts handled) and the Stage-2 **quality** reviewer (seven rubric
  axes), the latter handed the brief + passage as ground truth.
- **`author/review_checklist.py`** — realign to the seven rubric axes (adds
  dimension-fit, answerability, pedagogical-strength; today it has conformity /
  accuracy / age-fitness / evidence).
- **`content_bank/store/mat.json`** — regenerated: seed replaced by
  harness-produced, adversarially-reviewed items for the four pericopes.
- **`content_bank/PROVENANCE.md`** — record this authoring cycle (incl. the briefs
  and the lampposts each was distilled from).
- **`prototype/family.json`** — `reading_sequence` gains `MAT-013`.

Not changed: `schema.py`, `content.py`, `validate.py`, `prototype_bank.py`,
`selector.py`, the corpus itself (read-only). `corpus_bridge.py` gains three
read-only accessors but its existing surface is untouched.

## Provenance model

- Drafted items: `provenance.drafted_by = "claude"`.
- After adversarial pass: `review_status = "reviewed"`,
  `provenance.reviewed_by` records the AI adversarial review, `guardrail = "WCF-1"`,
  `reviewed_date` set. (`validate_item` already requires `reviewed_by`,
  `reviewed_date`, `guardrail ∈ {WCF-1}` once status ≠ draft.)
- After human confirmation: `review_status = "published"`;
  `provenance.confirmed_by = "kyhhdm"` (human of record).

## Verification

- `content_bank` suite, `prototype` suite, `corpus` suite all green.
- `validate_store("MAT")` passes (referential integrity, id uniqueness, bilingual
  counts) on the regenerated store.
- The gate holds: `get_content(mode="product")` serves only `published`; any item
  left `reviewed`/`draft` is provably excluded.
- `generate_kit.py` runs end-to-end against the new store and produces a coherent
  kit.
- **Demo-passage check (flagged, resolved at verification):** adding MAT-013 makes
  it the *next* passage, so the default demo kit would feature the thin 5:1-2
  setup rather than the flagship Beatitudes. Resolve during verification —
  preferred: mark MAT-013 as a studied session in `family.json` so the demo kit
  remains MAT-014, while the sequence still teaches the setup first for real
  families. Decide against the generated output, not in the abstract.

## Deliverables

1. Regenerated, adversarially-reviewed `store/mat.json` (four pericopes).
2. Four committed, fidelity-reviewed theological briefs
   (`author/briefs/mat-009,013,014,015.md`) — the theological base.
3. Tuned authoring harness: new `rubric.py` and `build_brief_prompt.py`; tuned
   `dimensions.py`, `build_draft_prompt.py` (Stage 2, passage-first + brief +
   compact WCF-1), `review_checklist.py`; `corpus_bridge.py` commentary +
   cross-reference + confessional-reference accessors.
4. Updated `family.json`, `PROVENANCE.md`.
5. A quality/tuning writeup: the defects found (both stages), the machinery
   changes each motivated, and the residual known limitations.
6. All suites green; kit verified end-to-end.
