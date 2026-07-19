# Cross-pericope Fluency Probe — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run an empirical, hand-authored probe of book-arc fluency (timeline, event
chains, argument progression across pericopes) and produce a findings doc that either
green-lights the full content-bank build or names the minimal cheap changes it needs.

**Architecture:** This is a *probe*, not a build. There is no shipped code and no
schema change. The work is: pull real passage text through the license gate, hand-
author a small set of *cross-pericope* content items across D1–D8 for one narrative
span and one epistle span, judge which dimension houses each item (and whether any
load-bearing skill is orphaned), then resolve four decisions (D-A..D-D) into a
recommendation. The single committed artifact is the findings document. Method and
format deliberately copy the genre probe
(`docs/2026-07-19-genre-dimension-probe-findings.md`) so the two compose.

**Tech Stack:** Python 3 standard library only (used solely to call
`corpus/lib/passage.py: get_passage` for reference text). Markdown for all authored
artifacts. Git for the final commit.

## Global Constraints

- **Python 3 standard library only** — no third-party packages. (The probe barely
  touches code; this governs any helper snippet.)
- **All Bible text via the license gate.** Read only through
  `get_passage(version, range_str, mode="product")`; use **BSB** (public-domain,
  `role: displayable`). Never paste from another source.
- **WCF-1 guardrail on every authored item.** Content must conform to the Westminster
  Confession, esp. Ch. 1 on Scripture; Scripture interprets Scripture. State
  observable behavior, never character/spiritual judgment.
- **Author-harness standing rule:** *"ONLY THE DIMENSIONS THIS PASSAGE GENUINELY
  SUPPORTS… Do not pad."* An honest ✗ ("no home") is a valid, valuable verdict.
- **No code, no schema, no selector changes are written during the probe.** Any such
  change is *proposed* by the findings, not implemented here. `schema.py`,
  `dimensions.py`, `selector.py` are read-only for this plan.
- **Nothing committed but the findings doc.** Authored items are illustrative/
  unreviewed scratch (mirrors the genre probe's "No content committed" status). Scratch
  lives in `work/` (untracked); the deliverable lives in `docs/`.
- **Paper-kit constraint on the session-shape finding (D-C).** Any cross-pericope
  form proposed must live in Prepare (authored into the printable kit) or Reflect —
  never live-session computing (`docs/unplug_assitant.md` §16 denylist).

**Spec:** `docs/superpowers/specs/2026-07-19-cross-pericope-probe-design.md`.
Decisions the findings must resolve: **D-A** (does a pericope need a new authoring
hook now? — the only build blocker), **D-B** (where arc content lives), **D-C**
(session shape — a finding), **D-D** (does the corpus need a mid-level section
grouping?).

---

### Task 1: Materials — served text + provisional spans

Establish the two spans and confirm every verse range is servable through the gate,
so authoring in Tasks 2–3 works from real text. Matthew infancy pericopes already
exist; Philippians must be divided provisionally (probe-local, **not** committed to
the corpus).

**Files:**
- Create: `work/content_bank_quality/cross-pericope-probe/materials.md` (scratch,
  untracked)
- Read only: `corpus/canon/structure/pericopes/mat.json`, `corpus/lib/passage.py`

**Interfaces:**
- Consumes: `get_passage(version, range_str, mode="product") -> Passage`; verse text
  is in `.verses` (a dict) — the dataclass has **no** `.text` attribute. Cross-chapter
  ranges need the full book prefix on **both** ends, e.g. `PHP.3.1-PHP.4.1` (a bare
  `PHP.3.1-4.1` raises "malformed ref"). From `corpus/lib/passage.py`.
- Produces: the ordered pericope list for each span (id, range, working title) that
  Tasks 2–3 author against, and a confirmation that each range serves in product mode.

- [ ] **Step 1: Record the narrative span (already seeded).**

Copy the eight infancy pericopes verbatim from `pericopes/mat.json` into
`materials.md` as a table: `MAT-001` MAT.1.1-17 Genealogy · `MAT-002` MAT.1.18-25
Birth · `MAT-003` MAT.2.1-12 Magi · `MAT-004` MAT.2.13-15 Flight to Egypt · `MAT-005`
MAT.2.16-18 Weeping in Ramah · `MAT-006` MAT.2.19-23 Return to Nazareth · `MAT-007`
MAT.3.1-12 John the Baptist · `MAT-008` MAT.3.13-17 Baptism of Jesus.

- [ ] **Step 2: Draw a provisional Philippians division (probe-local).**

Philippians has no seeded pericopes. Divide the letter into ~7 working units and record
them in `materials.md` under a heading that flags them **PROVISIONAL — not for corpus
commit**. A reasonable division (adjust to the text as you read it):

```
PHP-p1  PHP.1.1-11    Greeting, thanksgiving, prayer (partnership in the gospel)
PHP-p2  PHP.1.12-26   Paul's imprisonment advances the gospel
PHP-p3  PHP.1.27-PHP.2.4  Stand firm; be of one mind; humility toward one another
PHP-p4  PHP.2.5-11    The Christ-hymn (have this mind)
PHP-p5  PHP.2.12-30   Work out salvation; Timothy and Epaphroditus as examples
PHP-p6  PHP.3.1-PHP.4.1   Righteousness through Christ, not the flesh; press on
PHP-p7  PHP.4.2-23    Rejoice, be anxious for nothing, contentment, final thanks
```

Note the joy/rejoicing thread spans p1→p7 and the 2:5-11 hymn (p4) sits inside the
humility exhortation (p3) — these are the cross-pericope seams the probe targets.

- [ ] **Step 3: Verify every range serves through the gate.**

Run (BSB is the displayable public-domain version):

```bash
cd /media/pb/data/pjllc/scripture_loom && python3 -c "
from corpus.lib import passage
for r in ['MAT.1.1-17','MAT.1.18-25','MAT.2.1-12','MAT.2.13-15','MAT.2.16-18','MAT.2.19-23','MAT.3.1-12','MAT.3.13-17',
          'PHP.1.1-11','PHP.1.12-26','PHP.1.27-PHP.2.4','PHP.2.5-11','PHP.2.12-30','PHP.3.1-PHP.4.1','PHP.4.2-23']:
    p = passage.get_passage('BSB', r, mode='product')
    print(r, 'OK', len(p.verses), 'verses')
"
```

Expected: each line prints `<range> OK <n> verses` with n > 0 and **no** license-gate
exception. If `BSB` is not the correct version key, list `corpus/canon/bibles/` and
use the public-domain displayable one (e.g. `WEB`); record the version used in
`materials.md`.

- [ ] **Step 4: Review gate.**

`materials.md` contains both ordered spans, the PROVISIONAL flag on Philippians, and
the confirmed serving version. No commit (scratch file). Deliverable: a reviewer can
see exactly what will be authored against and that the text is real and gated.

---

### Task 2: Author the narrative cross-pericope item set (Matthew infancy)

Hand-author *cross-pericope* items spanning MAT-001..008 across D1–D8, then judge each
item's dimensional home. The point is not polished content — it is the housing verdict
and the orphan hunt.

**Files:**
- Create: `work/content_bank_quality/cross-pericope-probe/narrative-matthew.md`
  (scratch, untracked)
- Read only: `content_bank/author/dimensions.py` (the D1–D8 templates, to test each
  item against its dimension's stated rule)

**Interfaces:**
- Consumes: the eight-pericope list and served text from Task 1.
- Produces: the Matthew dimension table (rows D1–D8: representative cross-pericope
  item · verdict ✓ load-bearing / △ forced / ✗ no home) and an explicit orphan-skill
  note. Tasks 4–5 consume this table.

- [ ] **Step 1: Draft one cross-pericope item per dimension.**

For each of D1–D8, write one item that *only makes sense across two or more of the
infancy pericopes* (not answerable from a single pericope). Seed items (extend/replace
as the text warrants):

- **D1 People/Places (arc):** "Trace where Jesus is from MAT-002 to MAT-006:
  Bethlehem → Egypt → Nazareth. Who moves the family each time?"
- **D2 Event Sequence (arc):** "Put the infancy events in order across these
  pericopes, then name the cause→effect link between Herod's decree (MAT-005) and the
  flight to Egypt (MAT-004)." *(Test directly against the D2 template's rule 'Avoid
  sequence spanning other pericopes' — does book-timeline fit D2 or is it refused?)*
- **D3 Vocabulary (arc):** a term that recurs across the span (e.g. "fulfil what the
  Lord had said" formula repeated in MAT-002/004/006) — "what does this repeated
  phrase do across the infancy story?"
- **D4 Memory (arc):** "Recall the three Old-Testament fulfilment quotations Matthew
  strings through chapters 1–2."
- **D5 Connections (arc):** "How does the flight to Egypt and the return (MAT-004,
  MAT-006) echo Israel's own exodus? (Hosea 11:1)."
- **D6 Questions (arc):** "What do you wonder about why Matthew opens a book about
  Jesus with a genealogy before any events?"
- **D7 Interpretation (arc):** "Why does Matthew open with the genealogy (MAT-001) —
  how does it set up the whole Gospel's claim that Jesus is the promised King?"
- **D8 Application (arc):** an observable response drawing on the arc (e.g. "name one
  way your family's story has 'chapters' the way Jesus' beginning did").

Record the exact BSB wording you relied on beside each item.

- [ ] **Step 2: Judge each item's dimensional home.**

For each item write a one-line verdict — **✓ load-bearing** (the dimension houses it
cleanly), **△ forced** (constructable but really another dimension wearing this hat,
per the genre-probe pattern), or **✗ no home** — with a sentence of reasoning tied to
that dimension's `dimensions.py` template. Be especially rigorous on **D2**: if the
item is only expressible by *violating* the "avoid cross-pericope sequence" rule, that
is evidence D2 refuses to house book-timeline.

- [ ] **Step 3: Name the orphan skill(s).**

State plainly whether a load-bearing *cross-pericope narrative skill* (arc/plot
memory, "where are we in the story") has **no native dimension** — the way metaphor
and argument-connective came out orphaned in the genre probe — or whether D2/D5/D7
stretched to book scale house everything. Write it as a labeled finding.

- [ ] **Step 4: Review gate.**

`narrative-matthew.md` holds the D1–D8 table with verdicts and the orphan note. No
commit. Deliverable: a reviewer can see, per dimension, whether book-arc narrative
content has a home.

---

### Task 3: Author the epistle cross-pericope item set (Philippians)

Same procedure for the logic-progression case. Philippians tests whether argument-
thread tracing across chapters lives in a dimension or strains outside all of them.

**Files:**
- Create: `work/content_bank_quality/cross-pericope-probe/epistle-philippians.md`
  (scratch, untracked)
- Read only: `content_bank/author/dimensions.py`

**Interfaces:**
- Consumes: the provisional Philippians division and served text from Task 1.
- Produces: the Philippians dimension table (D1–D8 · item · verdict) and its orphan-
  skill note. Tasks 4–5 consume it.

- [ ] **Step 1: Draft one cross-pericope item per dimension.**

Each item must span two or more provisional pericopes. Seed items:

- **D1 People/Places (arc):** "Who are the named people across the letter (Timothy,
  Epaphroditus, Euodia, Syntyche) and where does each appear?" *(Likely △ — argument-
  subject ID, not cast-and-map; note it.)*
- **D2 Event Sequence / logic (arc):** "Trace the argument chain: 1:27 'conduct
  worthy' → 2:1-4 'be of one mind, in humility' → 2:5-11 'have this mind, which was in
  Christ.' What does each step license the next to say?" *(Is a logical 'therefore'
  chain a D2 'sequence'? Test against D2's template.)*
- **D3 Vocabulary (arc):** a term recurring across pericopes (e.g. *phroneo* /
  "mind"/"think" threaded 1:7, 2:2, 2:5, 3:15, 4:2) — "what does this repeated word do
  across the letter?"
- **D4 Memory (arc):** "Recall the letter's rejoicing bookends (1:18; 4:4) — where does
  joy recur?"
- **D5 Connections (arc):** internal echo vs. external cross-ref — "the hymn's every
  knee/tongue (2:10-11) quotes Isaiah 45:23; where else does the letter reach back?"
- **D6 Questions (arc):** "What question does the letter's insistence on joy *from
  prison* raise across chapters 1 and 4?"
- **D7 Interpretation (arc):** "Where does the 2:5-11 hymn sit in Paul's argument —
  how does the humility example serve the 1:27–2:4 exhortation?"
- **D8 Application (arc):** an observable response drawn from the argument's arc.

- [ ] **Step 2: Judge each item's dimensional home.**

Same verdict scheme (✓/△/✗) with reasoning tied to each `dimensions.py` template. Be
rigorous on **D2 and D7**: does *argument-connective / thread tracing* fit D7
("interpretation"), overload it, or fall outside every dimension?

- [ ] **Step 3: Name the orphan skill(s).**

State whether a load-bearing *cross-pericope argument skill* (thread/therefore tracing
across chapters) has no native dimension, or is housed by D7-at-book-scale. Cross-check
against the genre probe's finding that intra-pericope argument-connective was already
an orphan — is the *cross*-pericope version the same orphan at larger scale, or a new
one?

- [ ] **Step 4: Review gate.**

`epistle-philippians.md` holds the D1–D8 table with verdicts and the orphan note. No
commit.

---

### Task 4: Cross-cut analysis — resolve D-A..D-D

Turn the two tables into decisions. This is the analytical core: the probe wins by
*breaking* the starting thesis H1 (no new dimension, no new stored unit, selector
derives book moves from ordering + cross-refs), not by confirming it.

**Files:**
- Create: `work/content_bank_quality/cross-pericope-probe/analysis.md` (scratch,
  untracked)
- Read only: `content_bank/lib/schema.py` (to judge whether any proposal touches the
  data model), `prototype/selector.py` (to judge D-B "selector composes at kit-build"
  feasibility), `corpus/canon/structure/pericopes/mat.json` (ordering-is-free basis)

**Interfaces:**
- Consumes: the two dimension tables + orphan notes (Tasks 2, 3).
- Produces: an explicit resolution paragraph for each of D-A, D-B, D-C, D-D, and a
  single recommendation (green light **or** scoped cheap-changes list). Task 5
  consumes these.

- [ ] **Step 1: Consolidate the orphan finding.**

Across both spans, list every load-bearing cross-pericope skill and whether it has a
native dimension. Decide: is H1 confirmed (all housed by D2/D5/D7 at book scale) or
broken (a genuine orphan, or D2 actively refusing book-timeline)?

- [ ] **Step 2: Resolve D-A (the only blocker).**

Answer yes/no with evidence: **does a pericope need a new authoring-time hook now**
(an arc-role note in the brief, a section tag on the item) for a future arc layer to
attach — or can the arc layer attach later using only corpus ordering + cross-refs +
existing objectives? Tie the answer to concrete items from Tasks 2–3: could each
cross-pericope item have been authored *without* any new per-pericope field?

- [ ] **Step 3: Resolve D-B, D-C, D-D.**

- **D-B (where content lives):** derived-only / span-scoped ContentItem / separate arc
  artifact — pick one, with the evidence. Sanity-check the "selector derives at
  kit-build" option against what `selector.py` already has access to (pericope order,
  objectives, cross-refs).
- **D-C (session shape):** state which paper-kit form the authored items naturally took
  — recurring micro-segment, periodic zoom-out session, or both. This is a finding
  from how the items read on paper, constrained to Prepare/Reflect.
- **D-D (mid-level grouping):** does the corpus need a stored section/movement layer,
  or is section membership derivable from ordering + ranges? If stored is required,
  that is a corpus change and must be called out as (potentially) blocking.

- [ ] **Step 4: Write the recommendation.**

One of: **(a) green light** — "D-A: no; full pericope build and the arc layer proceed
independently; arc layer is a later additive spec" — or **(b) cheap-changes list** —
a short enumerated set of scoped changes (genre-probe style), including the minimal
per-pericope hook *iff* D-A is yes, and the minimal corpus section layer *iff* D-D
requires stored grouping.

- [ ] **Step 5: Review gate.**

`analysis.md` resolves all four decisions with evidence and lands one recommendation.
No commit. Deliverable: the reviewer can see the build is either unblocked or blocked
on a named, minimal change.

---

### Task 5: Assemble and commit the findings doc

Fold Tasks 1–4 into the single committed deliverable, in the genre-probe format so the
two probes read as a set.

**Files:**
- Create: `docs/2026-07-19-cross-pericope-probe-findings.md` (committed)
- Read only: `docs/2026-07-19-genre-dimension-probe-findings.md` (format to mirror),
  all four `work/…/cross-pericope-probe/*.md` scratch files

**Interfaces:**
- Consumes: everything from Tasks 1–4.
- Produces: the committed findings document (the probe's sole tracked artifact).

- [ ] **Step 1: Draft the findings doc mirroring the genre format.**

Sections, in order:

1. Header — title, `**Date:** 2026-07-19`, `**Question:**` (the cross-pericope
   question), `**Method:**` (hand-author cross-pericope items across D1–D8 for a
   narrative span and an epistle span; observe housing and orphans).
2. `## Starting thesis (H1, being pressure-tested)` — the no-new-dimension /
   no-new-unit / selector-derives thesis, verbatim intent from the spec.
3. `## Result — Matthew infancy (narrative timeline)` — the D1–D8 verdict table from
   Task 2 + the orphan callout.
4. `## Result — Philippians (epistle argument)` — the table from Task 3 + orphan
   callout.
5. `## Decisions` — D-A, D-B, D-C, D-D each resolved (from Task 4).
6. `## Implications for design` — the recommendation (green light or cheap-changes
   list), matching the genre findings' closing shape.
7. `## Status` — "Exploratory probe. No content committed; no schema changed. Drafted
   items illustrative, not reviewed or published. Provisional Philippians pericope
   division is probe-local and NOT committed to the corpus. Input to a possible future
   spec / to the go/no-go on the full content-bank build."

- [ ] **Step 2: Self-review against the spec's success criteria.**

Confirm the doc states a defensible **yes/no for D-A with evidence**, resolves
D-B/D-C/D-D, and ends in a green light or a scoped cheap-changes list. Confirm no item
smuggled in non-public-domain text and every authored item respected WCF-1. Fix inline.

- [ ] **Step 3: Verify the referenced ranges one more time.**

Re-run the Task 1 Step 3 serving check to confirm nothing in the write-up cites a range
that does not serve through the gate. Expected: all `OK`.

- [ ] **Step 4: Commit the findings doc only.**

```bash
cd /media/pb/data/pjllc/scripture_loom
git add docs/2026-07-19-cross-pericope-probe-findings.md
git commit -m "docs: cross-pericope fluency probe findings

Hand-authored cross-pericope items across D1-D8 for Matthew's infancy
arc and the whole of Philippians. Resolves D-A (does the full build need
a per-pericope authoring hook now), D-B/C/D, and lands a go/no-go
recommendation for the content-bank scale-out.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

Do **not** `git add` anything under `work/` — scratch stays untracked, per the
genre-probe "no content committed" precedent.

- [ ] **Step 5: Review gate.**

`git log --oneline -1` shows the findings commit; `git status` shows `work/` still
untracked and no schema/code files staged. Deliverable: the committed findings doc,
ready to feed either the scale-out plan or a follow-up cheap-changes spec.

---

## Self-Review (author's check against the spec)

- **Spec coverage:** D-A → Task 4 Step 2 + Task 5. D-B/C/D → Task 4 Step 3. Method
  (hand-author across D1–D8, both spans, orphan hunt) → Tasks 2–3. Materials (Matthew
  infancy + whole Philippians, BSB via gate) → Task 1. Deliverable (findings doc,
  genre format) → Task 5. Non-goals (no build, no schema, no during-session, not the
  scale-out plan) → Global Constraints + Task 5 Step 4. All spec sections mapped.
- **Placeholder scan:** no TBD/TODO; each authoring step lists concrete seed items and
  each verdict step names the scheme. Seed items are explicitly "extend/replace as the
  text warrants," which is direction, not a placeholder.
- **Type/format consistency:** the verdict scheme (✓ load-bearing / △ forced / ✗ no
  home) is identical across Tasks 2, 3, 5; the four decision labels D-A..D-D are used
  identically in the spec, Task 4, and Task 5; the findings filename
  `docs/2026-07-19-cross-pericope-probe-findings.md` matches the spec's deliverable.
- **Note on TDD:** a probe has no red/green cycle; "review gates" replace test steps,
  and the only executable checks (Task 1 Step 3, Task 5 Step 3) verify the text truly
  serves through the license gate. This is the honest analog of "run it to make sure
  it passes" for an investigation.
