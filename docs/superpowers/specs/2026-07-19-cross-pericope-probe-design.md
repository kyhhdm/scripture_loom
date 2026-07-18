# Cross-pericope fluency — empirical probe

**Date:** 2026-07-19
**Status:** design, pending review
**Kind:** probe (investigation → findings), not a build
**Origin:** strategic question — with the pericope-level pipeline now mature
(brief → draft → leader-reference → genre-aware → selector, all green against
Matthew), is it time to mass-produce the content bank? And: the bank is built on
the smallest unit (the pericope); how do we work the fluency of *timeline, events,
and logic progressions that cross pericopes* within a book?

## Why a probe, not a build

The pericope-level machinery is production-ready. But the model **actively walls off
cross-pericope structure**, so scaling now would bake that wall into every authored
unit:

- `content_bank/author/dimensions.py` — **D2 (Event Sequence)** instructs *"Avoid
  sequence spanning other pericopes."*
- **D5 (Connections)** is the only dimension allowed to reach outside the pericope —
  but it is **pairwise and names a specific text**, not the arc of a book.
- Yet the **D7 assessment ladder's top rung** (`docs/design-kit_generator.md`, as
  revised in the genre MR) is *"explains the passage within the book's argument… the
  psalm's movement."*

So the *fluency goal* already includes book-scale competence (timeline, event
chains, argument progression), but **no content unit and no scheduling move
represents a book's arc.** The selector walks pericope by pericope with nothing
carrying "the story so far" or "where this exhortation sits in Paul's argument."

This is cheap to design now and expensive to retrofit across a large authored bank.
The genre probe (`docs/2026-07-19-genre-dimension-probe-findings.md`) established the
house method for exactly this situation: rather than design a system up front,
hand-author against hard cases and let the evidence kill or keep it. That probe
**killed** the systematic option (no `genre` field, no `genre → dimension-profile`
table) and kept two cheap changes. This probe runs the same play for the
cross-pericope question.

## What the corpus already gives us

- **Ordering is free.** Pericopes are an ordered array per book with verse ranges
  (`corpus/canon/structure/pericopes/mat.json`: `MAT-001` … `MAT-NNN`, each with a
  `range` and title). "Story so far" and "put these events in order" are **derivable
  today** with no new data.
- **Cross-references exist** (`corpus/canon/structure/crossrefs.json`) — pairwise,
  the engine behind D5.
- **No mid-level grouping.** There is `book`, and there is `pericope`, and *nothing
  between*: no "Sermon on the Mount" span, no "Philippians argument sections." If
  book-level fluency needs named movements/acts, that grouping is the one piece that
  might have to be authored or stored — and deciding that is a probe goal (D-D).

## The question the probe must answer

The probe exists to **de-risk the full build** with one hard yes/no:

> Does authoring a pericope need any new hook *now* for a book-arc layer to attach to
> later — or is the book-arc layer purely additive and derivable, so full pericope
> production and the arc layer can proceed independently?

It resolves four decisions:

- **D-A — the only legitimate blocker.** Does each pericope brief/item need a new
  field or authored note (an "arc role," a "section" tag) baked in *at authoring
  time*? If **no**, mass build starts now and the arc layer is built in parallel. If
  **yes**, define that minimal hook before scaling — that is the sole thing worth
  blocking the build on.
- **D-B — where cross-pericope content lives.** Derived-only (selector composes book
  moves at kit-build from corpus order + cross-refs + existing pericope objectives);
  span-scoped `ContentItem`s (a `passage` that spans several pericopes); or a
  separate "arc" artifact (a book/section outline, lamppost-like).
- **D-C — session shape.** Recurring micro-segment appended to each pericope kit vs.
  a periodic dedicated "zoom out" review session vs. both. This is a **finding**, not
  an input — the authored items reveal their natural form on paper.
- **D-D — mid-level grouping.** Does the corpus need a section/movement structure it
  lacks, and if so is that a *blocking corpus change* or *derivable* from ordering +
  cross-refs?

## Method — copy the genre probe exactly

Hand-author a small set of *cross-pericope* items across D1–D8 against real
public-domain text (BSB, served through `corpus/lib/passage.py` license gate; drafted
under the **WCF-1** guardrail and the author harness's standing rule *"ONLY THE
DIMENSIONS THIS PASSAGE GENUINELY SUPPORTS… Do not pad"*). Then observe, per item:

1. **Which dimension houses it** — D2 at book-timeline scale, D5 at arc-connection
   scale, D7 at book-argument scale — or none cleanly.
2. **Whether a load-bearing cross-pericope skill has no native dimension** — the
   genre-probe pattern, where metaphor-structure and argument-connective tracing came
   out orphaned into D3/D7.
3. **Whether the item is authorable from corpus-derived material alone** (ordering,
   cross-refs, existing objectives) **or requires a mid-level section grouping** the
   corpus does not have.

### Starting thesis to try to break (H1)

Cross-pericope fluency needs **no new dimension and no new stored unit**. It is:

- **D2 stretched to book-timeline** ("order events across pericopes"),
- **D5 stretched to arc-connection** ("how this pericope echoes / sets up another"),
- **D7 stretched to book-argument** ("where this sits in the book's flow"),

and the **selector composes the book-level moves at kit-build time** from corpus
ordering + cross-refs + already-authored pericope objectives. Under H1, D-A is *no*
(no per-pericope hook), D-B is *derived-only*, D-D is *derivable*, and the full build
proceeds immediately.

**The probe wins by breaking H1**, not confirming it. Two specific orphans to hunt:

- **Narrative-arc / plot memory.** Does *"put the infancy events in order across
  MAT-001..008"* genuinely live in D2 — whose template currently **forbids**
  cross-pericope sequence — or is book-timeline a skill D2 refuses to house?
- **Argument-thread tracing across chapters.** Does Philippians' joy / partnership /
  humility thread and its "therefore" chain live in D7, or strain outside every
  dimension the way argument-connective tracing did in the genre probe?

If either orphan is real, or if D-D comes back "needs a stored section grouping," H1
is broken and the findings carry a concrete, minimal proposal (in the genre-probe
spirit: the smallest change that houses the skill, preferring derive-don't-store and
no data-model expansion).

## Materials

- **Narrative — Matthew infancy, MAT-001..008** (genealogy → birth of Jesus → the
  Magi → flight to Egypt → weeping in Ramah → return to Nazareth → John the Baptist →
  baptism of Jesus). Already built as pericopes, so the probe also stresses the
  **seam between authored units**. Representative cross-pericope items to draft:
  - *(D2-arc)* order the infancy events across these eight pericopes; identify
    cause→effect chains that cross pericope boundaries (e.g. Herod's decree → flight).
  - *(D7-arc)* why does Matthew open with a genealogy — how does it set up the whole
    Gospel's claim that Jesus is the promised King?
  - *(D5-arc)* how does the flight to Egypt and return echo Israel's own story
    (Hosea 11:1, already a cross-ref)?
  - *(recap)* a "story so far" prompt built only from the ordered pericope titles /
    objectives — the derive-only baseline.
- **Epistle — whole of Philippians** (extends the genre probe's Phil 2:1–11 to the
  book's full argument across its pericopes). Representative items:
  - *(D7-arc)* trace the joy / partnership / humility threads across chapters 1–4;
    where does the 2:1–11 hymn sit in the letter's argument?
  - *(D2-arc / logic)* the "therefore" and consequence chain — how 1:27's "conduct
    worthy" leads into 2:1–4's exhortation leads into the 2:5–11 example.
  - *(D5-arc)* internal echoes (e.g. rejoicing bracketed 1:18 / 4:4) vs. external
    cross-refs.

Small N, hand-authored — enough to see housing and orphans, **not** a content
deliverable. No code, no schema, no selector changes are written during the probe;
those (if any) are proposed by the findings.

## Deliverable

`docs/2026-07-19-cross-pericope-probe-findings.md`, mirroring the genre-probe findings
format:

- per-span dimension tables (representative item · verdict: ✓ load-bearing / △ forced
  / ✗ no home), matching the genre findings' layout;
- explicit callout of any load-bearing cross-pericope skill with no native dimension;
- resolution of D-A, D-B, D-C, D-D each stated as a decision with its evidence;
- a closing recommendation that is **one of**:
  - **green light** — "no per-pericope hook needed (D-A: no); full pericope build and
    the arc layer proceed independently; arc layer is a later, additive spec"; or
  - **cheap-changes spec** — a short list of scoped changes (the genre-probe
    outcome), including the minimal per-pericope hook if and only if D-A is *yes*.

## Non-goals (explicit)

- **Not building the arc layer.** The probe decides *whether and how*; it does not
  implement selector moves, span-scoped items, or a section structure.
- **Not a new dimension by default.** D1–D8 stand unless the probe produces an orphan
  that genuinely fits none — and even then the genre-probe precedent is to reshape/
  reweight before adding.
- **Not a during-session feature.** Any cross-pericope work must live in Prepare
  (authored into the paper kit) or Reflect, never as live-session computing
  (`docs/unplug_assitant.md` §16 denylist). The session-shape finding (D-C) is
  constrained to paper-kit forms.
- **Not the scale-out plan.** Tooling / batching / review-throughput for the full
  multi-book build is a separate spec, unblocked (or scoped) by this probe's D-A
  result.

## Success criteria

The probe is done when the findings doc states a defensible yes/no for **D-A** with
evidence, resolves D-B/D-C/D-D, and ends in either a green light or a scoped
cheap-changes list — such that the team can start (or consciously defer) the full
content-bank build without fear of a cross-pericope retrofit.
