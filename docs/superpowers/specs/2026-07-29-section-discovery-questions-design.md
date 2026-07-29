# Section Discovery Questions — Design

- **Date:** 2026-07-29
- **Status:** design (approved in brainstorming; pending spec review)
- **Author:** pairing session (kyhhdm + Claude)

## Problem

At the section (book-arc "movement") layer, two item types carry the
cross-pericope argument: `throughline` (exactly one per section, D7) and
`thread` (zero or more, D3 or D7). Today both are **statement content** — the
traced result is handed to the leader pre-digested, and the drafting prompt
explicitly forbids them a `leader_reference`
(`content_bank/author/build_section_draft_prompt.py:68`).

Handing the leader a finished spine and finished motif-traces works against the
pedagogy. The Bible Fluency Method treats the leader's own fluency as the
"unautomatable factor" (`docs/motto.md`, `docs/core_principles.md`): a leader who
reads a throughline aloud has not internalized the arc; a leader who *traces the
motif themselves* builds the fluency the product exists to grow. The same is true
one level out — a pre-traced motif is a weaker family exercise than a question the
family discovers together.

## Goal

Convert `throughline` and `thread` items from statements into **discovery
questions with a revealed answer**: the `text` field poses a question ("trace the
word *great* through this section — where does it recur, and what does its final
use reveal?"), and the traced result — the statement we ship today — moves into a
`leader_reference` that renders collapsed beneath the stem.

One item, two discoveries (the "both" decision):

- **Prepare (leader's own fluency):** the leader answers the stem themselves, then
  checks against the revealed `leader_reference`.
- **Gather (family discovery, ready-made prompt):** the leader re-asks that same
  stem at the table, using the reveal as their guide.

This is deliberately additive to leader effort in Prepare — a chosen trade in
favour of formation — but it produces a *ready-to-ask* family prompt, so it does
not add table-time burden and does not make the leader a data-entry clerk.

## Scope decisions (settled in brainstorming)

- **Both types convert.** Every section-level `throughline` and `thread` becomes a
  discovery question. The throughline loses its role as a pre-digested spine
  handed to the leader; its spine statement survives as the reveal.
- **Forward-only.** The change applies to future builds. Existing statement-form
  items (e.g. Jonah's `work/` drafts) are left as-is; re-seeding them under the new
  prompt is a manual choice, not a required migration. No migration tooling ships.

## Why the schema already fits

The change rides machinery that already exists; **`content_bank/lib/schema.py`
needs no change**.

1. `leader_reference` is banned on exactly one type — `memory_verse`
   (`schema.py:51-52`). Threads and throughlines are **not** banned from carrying
   one. The "no leader_reference" rule lives only in the drafting prompt
   (`build_section_draft_prompt.py:68`), so this is a prompt change, not a schema
   change.

2. The reveal *kind* is decided by the dimension the item already carries, via
   rules already in the validator:

   | Item | Dimension | Closed/Open | Reveal kind | Why it fits |
   |---|---|---|---|---|
   | `thread` (tracked key word) | D3 | closed (`schema.py:56`) | `answer_key` | concrete recurrence has a correct answer; `answer_key` is the only kind allowed a `verse` field (`schema.py:65-69`), and a D3 thread's answer *is* verses |
   | `thread` (interpretive movement) | D7 | open (`schema.py:60`) | `leader_note` | keeps the question open; points where the text leads |
   | `throughline` | D7 | open | `leader_note` | the spine, framed as guidance not a canned answer |

   The D3/D7 axis threads already carry maps one-to-one onto the
   `answer_key`/`leader_note` axis leader_references already carry. Nothing new is
   invented; two existing axes are lined up.

## Relationship to existing "arc questions"

The section-draft prompt already emits 2–4 free-standing **arc questions**
(`type:"question"` with a `leader_reference`, `build_section_draft_prompt.py:65-67`).
Those are unaffected and remain. After this change a section carries three kinds of
discovery content, with distinct jobs:

- **throughline question** — the section's *headline* discovery question (one, D7).
- **thread questions** — *motif-tracing* discovery questions (zero or more; each
  keeps its `refs`, the verse chain being traced).
- **arc questions** — free-standing coverage questions for dimensions the
  throughline and threads do not touch (unchanged mechanism).

No arc question is removed or auto-derived from a thread; the change only gives the
throughline and threads a stem + reveal of their own.

## Design

### Data shape (per item)

`throughline` — was a statement; now a D7 question with a `leader_note` reveal:

```json
{"id":"<sid>-throughline","section":"<SID>","dimension":"D7","type":"throughline",
 "age_tier":"all","difficulty":2,"review_status":"draft",
 "text":{"en":"<question stem: what is this whole movement driving at? how do you see it move from X to Y?>"},
 "leader_reference":{"kind":"leader_note",
   "text":{"en":"<the spine statement we ship today — the arc in the text's own terms>"},
   "provenance":{"reviewed_by":"...","reviewed_date":"...","guardrail":"WCF-1"}},
 "version":1}
```

`thread` (D7 shown; D3 uses `kind:"answer_key"` and may add a `verse`):

```json
{"id":"<sid>-thread-<slug>","section":"<SID>","dimension":"D7","type":"thread",
 "age_tier":"all","difficulty":2,"review_status":"draft",
 "text":{"en":"<question stem naming the motif to trace and asking what its recurrence reveals>"},
 "refs":["<BOOK>.C.V","..."],
 "leader_reference":{"kind":"leader_note",
   "text":{"en":"<the traced result we ship today — name + what the recurrence teaches>"},
   "provenance":{"reviewed_by":"...","reviewed_date":"...","guardrail":"WCF-1"}},
 "version":1}
```

Invariants preserved: `text` is still the only field a reader sees first; `refs`
stay on threads only (`schema.py:97`); one throughline per section; citation tags
still allowed inside both `text` and `leader_reference.text`
(`gates.py:288-289`).

### Drafting prompt (`build_section_draft_prompt.py`)

- `_SHAPE`: change the throughline and thread example objects (lines 55-58) so
  `text` is a **question stem** and each carries a `leader_reference` whose `kind`
  is dictated by its dimension (D3→`answer_key`, D7→`leader_note`).
- Replace line 68 ("throughline and thread items need NO leader_reference") with the
  inverse requirement, stating the dimension→kind rule explicitly.
- Add drafting guidance: the stem must be answerable *from the text* (not opinion),
  must name the motif/arc concretely enough to trace, and must not embed its own
  answer. The reveal must be the same traced content produced today.

### Gates (`content_bank/author/gates.py`)

Add one deterministic gate (the "AI proposes, deterministic guarantee, human
confirms" pattern):

- **`section_reveal_check`** (HARD): every `throughline` and `thread` item must
  carry a `leader_reference` whose `kind` matches its dimension
  (D3→`answer_key`, D7→`leader_note`). Flags a missing reveal or a mismatched kind.
  Wire it into the HARD tier alongside `thread_span_check` (`gates.py:446-451`).

Unchanged: `thread_span_check` (still keys on `type=="thread"`, still requires 2+
pericope span); `citation_check` / quote gates (already read
`leader_reference.text`/`.verse`, `gates.py:288-289`).

### Rendering / kit

The kit already renders `type:"question"` items with a collapsible
`leader_reference`. Route throughline/thread items through that same renderer so
the stem prints as a discovery prompt with the reveal collapsed beneath. This is
what makes one item serve both Prepare (leader self-checks) and Gather (leader
re-asks the family) — no second stem is authored.

## Testing

- **schema:** a throughline/thread *with* a dimension-appropriate `leader_reference`
  validates; unchanged, but add a regression asserting it (guards against a future
  re-ban).
- **`section_reveal_check`:** throughline/thread missing a reveal → flagged;
  wrong-kind reveal (D3 with `leader_note`, D7 with `answer_key`) → flagged;
  correct pairing → passes; `question`/other types → untouched.
- **prompt:** `_SHAPE` example objects carry `leader_reference` with the correct
  kind per dimension; the old "need NO leader_reference" line is gone.
- **thread_span_check:** unchanged behaviour under the new item shape (a single-
  pericope thread still flagged).

## Out of scope

- Migrating existing statement-form items (forward-only).
- Changing the free-standing arc-question mechanism.
- Any change to `content_bank/lib/schema.py` (it already permits the shape).
- Chinese-translation prompt changes — the zh pass already translates
  `text` and `leader_reference.text`; no structural change is introduced.
