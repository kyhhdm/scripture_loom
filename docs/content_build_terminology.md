# Content build pipeline — terminology

A reference for the vocabulary used across the content-bank authoring pipeline
(`content_bank/author/`, `corpus/`, and the comparison tooling). Definitions are
grounded in the code and specs; file pointers are given so each term can be checked
at source. See also `docs/design-kit_generator.md` (the D1–D8 schema) and
`docs/superpowers/specs/2026-07-21-model-aware-run-directories-design.md` (the run
layout).

---

## Source-text layer

**Pericope** — a single, self-contained passage unit (e.g. `PHP-001` = Philippians
1:1–11). Pericopes are the base unit of authoring; their ids and ranges come from the
corpus (`corpus.lib`, via `content_bank/lib/corpus_bridge.py`).

**Section** — a *cross-pericope* grouping that spans one or more consecutive
pericopes (e.g. `PHP-S2` spans `PHP-002`..`PHP-006`). Sections carry the book-arc
content — the material for the "zoom-out" reflection that looks at the whole arc
rather than one passage. A section may span a single pericope (`PHP-S1` = just
`PHP-001`); that constraint matters for threads (below).

**Unit** — the generic term for "a pericope or a section." The builder walks a
manifest of units; each has a `kind` of `pericope` or `section`.

**Passage / range** — the verse span, written as `PHP.1.1-11`. The single read path
for Bible text is `corpus/lib/passage.py:get_passage()` (enforces the license gate).

---

## The eight fluency dimensions (D1–D8)

The product's schema. Every content item is tagged with exactly one. Defined in
`docs/design-kit_generator.md`.

| Dim | Name | In one line |
|-----|------|-------------|
| **D1** | People & Places | Who and where — the passage's named actors and settings. |
| **D2** | Event Sequence | What happens, in order. |
| **D3** | Vocabulary | Key words/phrases and the sense the text gives them. |
| **D4** | Memory | Holding the text itself (memory verses). |
| **D5** | Connections | How this passage links to other Scripture (the one dimension that legitimately cross-references). |
| **D6** | Questions | Open wondering the passage invites. |
| **D7** | Interpretation | What the text *means* — observing what it says, then why. |
| **D8** | Application | Living it out (observable, doable on paper). |

D1–D5 are the **closed** dimensions (a question has a correct answer); D6–D8 are the
**open** dimensions (no single right answer). This split drives which kind of leader
reference an item carries (below).

---

## Item anatomy

A **content item** is one JSON object — a question, activity, memory verse, etc. Its
schema lives in `content_bank/lib/schema.py`.

**type** — the shape of the item. Valid types: `question`, `activity`, `vocab_list`,
`memory_verse`, `key_facts`, `narration_prompt`, `pre_reading_quest`, and two
section-only types:

- **throughline** — *exactly one per section*, dimension D7. A one-or-two-sentence
  statement of what the whole section is about, in the text's own terms — the section
  spine printed at the zoom-out. It is *statement content, not a question*, so it
  carries **no** leader reference (there is nothing to answer). Spec:
  `content_bank/author/build_section_draft_prompt.py` (`_SHAPE`).
- **thread** — *zero or more per section*, dimension D3 or D7. A word, phrase, or
  motif that **recurs across two or more of the section's pericopes** and carries the
  section's argument. A thread has a name, its member verse **`refs`** (the only item
  type that carries `refs`), and a one-or-two-sentence note on what the recurrence
  teaches. Also statement content — no leader reference. Tagged **D3** when the
  recurrence is primarily a tracked key word, **D7** when it is an interpretive
  movement (both are permitted; models differ here — a real review judgment call).

**age_tier** — `pre_reader`, `child`, `youth`, `adult`, or `all`.

**difficulty** — `1`, `2`, or `3` (shown as `diff 1/2/3` on the comparison page, to
avoid visual collision with the `D1`/`D2` dimension labels).

**review_status** — `draft` → `reviewed` → `published`. The builder writes items as
`draft`; product mode (`content_bank/lib/content.py:get_content`) serves **only**
`published` items. Advancing a draft past `draft` is a human-gated step, never done by
the builder.

**leader_reference** — leader-only material attached to a question, judged separately
from the item it rides on. Two kinds:

- **answer_key** — for closed questions (**D5**): the concise, correct expected
  response plus the verse it comes from. (Pericope closed dims D1–D5 also use this.)
- **leader_note** — for open questions (**D6–D8**): points where the text leads and
  flags common misreadings, but keeps the question open — never a canned answer.

`throughline`, `thread`, and `memory_verse` items carry **no** leader reference (the
first two are statements; a memory verse *is* its own reference).

---

## Pipeline stages (the manifest ledger)

Each unit's progress is tracked per model run in a `manifest.json`
(`content_bank/author/manifest.py`). The stages the builder uses:

**pending** → **briefed** → **drafted** → (human) **reviewed** → **published**

- **pending** — unit exists, nothing produced yet.
- **briefed** — the theological/arc brief has been written to `briefs/<unit>.md`.
- **drafted** — items have been drafted, gated, and written to `drafts/<unit>.json`.
- **reviewed / published** — human-gated; not produced by the builder.

---

## Artifacts (per model run)

Each model gets its own run directory:
`work/content_bank_build/<BOOK>/runs/<model-id>/` containing `manifest.json`,
`briefs/`, `drafts/`, `verdicts/`.

**Brief** — a compact distillation the items are drafted *from* (Stage 1). Two kinds,
both model-dependent:

- **Pericope brief** — ~250 words: passage emphasis, key terms, doctrinal anchors,
  cross-references, reading moves (`build_brief_prompt.py`).
- **Section (arc) brief** — the arc spine, recurring motifs with member refs,
  cross-pericope connections, doctrinal anchors (`build_section_brief_prompt.py`).

**Draft** — the JSON array of items for a unit (`drafts/<unit>.json`), all
`review_status: "draft"`.

**Verdict file** — the adversarial review's output, item-keyed
(`verdicts/<unit>.json`): `{item_id: [{reviewer, verdict, notes}, ...]}`.

---

## Gates (deterministic pre-filters)

Pure functions in `content_bank/author/gates.py` that catch *mechanical* wrongness
before a human looks. Two tiers:

**HARD** (bundled in `run_all`; a remaining flag fails the unit after the repair
budget):

- **quote_check** — every quoted span (≥3 words) must appear verbatim in the BSB.
- **schema_check** — controlled vocabulary, scope, reference rules per item.
- **refs_in_range** — a stated verse ref must fall in the unit's own range (catches
  scope drift). D5 pericope items are exempt (they legitimately cross-reference).
- **thread_span_check** — a `thread` must recur across 2+ pericopes, so it is invalid
  on a single-pericope section. (This is why `PHP-S1` has no threads.)

**SOFT** (advisory only — logged, never blocks):

- **dimension_cap_check** — flags any dimension a unit emits more than `--dim-cap`
  of (default 3). Anti-padding: fed to the repair loop to prune over-generation, then
  logged if still over — a rich passage may legitimately exceed.

**Repair loop** — when gates flag, the problems are fed back to the model to fix, up
to `--max-repair` rounds (`build_cli.py:_repair_to_clean`). Remaining HARD flags then
raise `GateError`; remaining SOFT flags only warn.

Gates catch mechanical wrongness only. Genre fit, pedagogy, and theology are **not**
gate-checkable — that is what human review is for.

---

## Adversarial review (r1 / r2)

An optional-but-default LLM pass (`content_bank/author/review.py`, `--review` /
`--no-review`) that judges the draft against the seven-axis rubric
(`content_bank/author/rubric.py`) through **two complementary lenses**:

- **r1** — accuracy, WCF-1 (Westminster) conformity, answerability from *this* passage.
- **r2** — evidence-not-judgment, age fitness, dimension fit, pedagogy, leader-
  reference correctness.

Each lens returns `pass` or `fail` + a note per item. A **`fail` from either lens**:

1. **Triggers a targeted revise pass** — only the failed items are sent back to be
   fixed (retag dimension, switch answer_key↔leader_note, reground, reframe judgment
   to behavior) or, if unfixable, **dropped** (`review.py:revise`). Passing items are
   left byte-identical. The revised items are then re-gated.
2. **Is recorded as a badge** on the comparison page. Verdicts are saved *before* the
   revise runs, so `r1:fail`/`r2:fail` describes the **original** draft — a signal
   that this item was already rewritten because the review caught something. It is
   where a human reviewer should look hardest.

What a `fail` does **not** do: it does not fail the build (only HARD gates do), and it
does not confer human review — as the module says, it *"sharpens the draft, it does
not confer human review."*

---

## Model / run / provenance

**backend** — which LLM path runs: `llm_core` (deepseek via API credits, default) or
`claude` (Claude Code headless via subscription).

**model** — the effective model id (e.g. `deepseek-v4-flash`, `deepseek-v4-pro`,
`opus`).

**run / slug** — the run directory name, = the full model id
(`runs/deepseek-v4-flash/`). Each model run is a self-contained pipeline (own brief,
draft, verdict).

**provenance** — stamped onto each item: at draft time
`{model, backend, run}` (which model produced it); at publish time
`drafted_by`, `reviewed_by`, `reviewed_date`, `guardrail` (always `WCF-1`),
`confirmed_by`. The draft-time model/run identity is preserved into the store
(`content_bank/author/publish.py`), so a published item records which model drafted
it.

---

## Comparison tooling

**compare_html** (`content_bank/author/compare_html.py`) — a static generator that
emits one self-contained HTML page comparing several model runs side by side per
unit × dimension, with gate/verdict badges, the seven-axis rubric, per-run briefs,
and per-item accept → `decisions.json` export. It is a review *instrument*: it never
writes the store; promoting accepted items stays a separate human-gated step.

**decisions.json** — the reviewer's export from the comparison page: which item ids
were accepted / rejected. Consuming it to promote items is a future, human-gated step.
