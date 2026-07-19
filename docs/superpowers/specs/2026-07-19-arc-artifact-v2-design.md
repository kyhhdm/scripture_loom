# Arc artifact (v2) — authored interpretive arc content

**Date:** 2026-07-19
**Status:** design, pending review
**Origin:** `docs/2026-07-19-cross-pericope-probe-findings.md` (the probe) and
`docs/superpowers/specs/2026-07-19-book-arc-layer-design.md` (the MVP, now shipped).

## Background

The book-arc-layer MVP shipped a *derived-only* layer: a per-book section map, a
"story so far" recap on every kit, and a zoom-out consolidation session that fires at
each section boundary. The zoom-out exercises cross-pericope **sequence** comprehension
(fully derivable) but leaves its **interpretation** to a *generic* prompt — *"In one
sentence, what was [section] about?"* — with no authored content behind it. The probe's
headline orphan examples (the Philippians *phroneo* thread, Matthew's fulfilment-
quotation refrain, the joy thread) are exactly the authored interpretive content the MVP
deferred.

v2 supplies that content: a section-scoped tier of **authored** arc content — throughlines,
threads, and arc questions — that the zoom-out consumes, WCF-1-guarded and leader-confirmed
like the rest of the content bank.

## Scope & key decisions (taken during design)

- **Full content scope:** per-section **throughlines**, cross-pericope **threads**, and
  section **questions**.
- **Modeled as section-scoped `ContentItem`s** — the content bank's `ContentItem` gains a
  `section` scope *alongside* `passage` (an item carries exactly one). This **refines**
  probe decision D-B (which rejected *overloading `passage`* to span pericopes) rather than
  violating it: a parallel `section` scope never makes `passage` multi-pericope, and it
  reuses the entire content-bank pipeline (`review_status`, `leader_reference`, WCF-1
  provenance, `age_tier`, bilingual `text`).
- **Threads are scoped at their *anchor* section.** A thread spans multiple sections, but
  its `section` field names its **anchor** (the section at whose zoom-out it surfaces — its
  payoff); the thread's true span lives in its `refs` list. This keeps scope binary
  (`passage` xor `section`) instead of adding a third `book` scope.

### Non-goals (explicit)

- **The context-scoped D2 authoring reshape is RETIRED (YAGNI).** Only D2 carries an
  anti-span rule (`dimensions.py`: "avoid sequence spanning other pericopes"); v2's
  interpretive content is **D7/D3/D5**, which the authoring rules already permit, and the
  MVP's *derived* sequence exercise already covers cross-pericope D2. **`dimensions.py` is
  not modified.** (This formally closes the third piece the probe named.)
- **No new dimension (no D9); no new evidence field.** Arc content is scored under existing
  dimensions via the MVP's `kind`-based derive-don't-store — unchanged.
- **No multi-pericope `passage`** — D-B's actual invariant is preserved.
- **Leader-adjustable section boundaries** — still deferred (a later, orthogonal change).

## Data model

### `section` scope on `ContentItem` (`content_bank/lib/schema.py`)

Today `_REQUIRED` includes `passage`. Change:

- Remove `passage` from the unconditional `_REQUIRED`; add a rule: **exactly one of
  `passage` / `section` is present** (mutual exclusivity; one is mandatory).
- `section`, when present, matches a section-id shape (`^[A-Z0-9]{3}-S\d+$`, e.g.
  `MAT-S1`); store-level validation resolves it against the corpus section map.
- New `TYPES`: **`throughline`**, **`thread`** (added to the existing set). `question`,
  `activity`, etc. are unchanged and may now be `section`-scoped as well.
- **`refs`** — a new optional field, **required and non-empty for `type: thread`**, a list
  of verse refs (`"MAT.1.22"`, OSIS-style, book must match the item's section book).
  Forbidden on non-thread items.
- Type/scope rules: `throughline` and `thread` **must** be `section`-scoped (never
  `passage`). A `throughline` is **D7**. A `thread` is **D3 or D7** (the existing
  `leader_reference` closed/open rule then applies automatically: a D3 thread carries an
  `answer_key`, a D7 thread a `leader_note`).

`leader_reference`, `provenance` (WCF-1), `age_tier`, `difficulty`, `review_status`,
`text` (bilingual), `version` are **unchanged** and reused verbatim.

### Content shapes (concrete)

**Throughline** — one authored per section, replaces the MVP's generic prompt:

```json
{
  "id": "mat-s1-throughline",
  "section": "MAT-S1",
  "type": "throughline",
  "dimension": "D7",
  "age_tier": "all",
  "difficulty": 2,
  "review_status": "published",
  "text": {"en": "Matthew opens by proving Jesus is the promised King — son of David, son of Abraham — whose very infancy already fulfils what the prophets said.", "zh": ""},
  "version": 1,
  "leader_reference": {
    "kind": "leader_note",
    "text": {"en": "Anchor to 1:1 and 1:17; the fulfilment quotations (1:22; 2:15; 2:17; 2:23) make the point across the section, not in any one scene.", "zh": ""},
    "provenance": {"reviewed_by": "…", "reviewed_date": "2026-07-…", "guardrail": "WCF-1"}
  }
}
```

**Thread** — book-spanning, anchored at its payoff section, carrying its member refs:

```json
{
  "id": "mat-thread-fulfilment-refrain",
  "section": "MAT-S1",
  "type": "thread",
  "dimension": "D7",
  "refs": ["MAT.1.22", "MAT.2.15", "MAT.2.17", "MAT.2.23"],
  "age_tier": "youth",
  "difficulty": 3,
  "review_status": "published",
  "text": {"en": "Matthew keeps stopping the story to say an event happened 'to fulfil what the Lord had said through the prophet.' Follow the refrain across chapters 1–2: what is he teaching about who Jesus is?", "zh": ""},
  "version": 1,
  "leader_reference": {
    "kind": "leader_note",
    "text": {"en": "The formula (narrator's, distinct from the scribes' citation at 2:5) frames the whole infancy as prophecy fulfilled; it is Matthew's running claim that Jesus is the promised one. Keep to what the text states.", "zh": ""},
    "provenance": {"reviewed_by": "…", "reviewed_date": "2026-07-…", "guardrail": "WCF-1"}
  }
}
```

**Section question** — an arc discussion question for the zoom-out (reuses `type:
question`, `section`-scoped, existing `leader_reference` rules).

## Authoring pipeline

Reuse `content_bank/author/` (`build_brief_prompt` → `build_draft_prompt` →
`build_reference_prompt`) with a **section-scope brief**. Where a pericope brief presents
one passage, the section brief presents the section's span — its pericope titles and the
served text ranges (via the license gate) — and asks the author to draft: the one
throughline, the named threads with their `refs`, and the arc questions, all under WCF-1
and confirmed by a human/leader before `review_status: published`. `dimensions.py` guidance
is reused as-is (no D2 change). The Stage-1/2/3 prompt builders gain a section-scope mode;
no new authoring concepts beyond scope.

## Selector / zoom-out integration

`build_zoom_out_kit` (from the MVP) gains authored content when present and **degrades to
the derived MVP behavior when absent**:

- **Throughline** — if a published `throughline` exists for the section, the kit prints it
  (and its `leader_note`) in place of the generic *"In one sentence…"* prompt. No
  throughline → the generic prompt (MVP behavior) stands.
- **Threads** — the kit includes every published `thread` whose `section` (anchor) is this
  section: it prints the thread's `text`, its `refs` for the family to look up, and the
  `leader_reference` as the leader's exercise.
- **Section questions** — a section analogue of `select_discussion_questions` pulls
  published `section`-scoped `question` items for the discussion round.

All Prepare-authored onto paper; scored under existing dimensions at arc scope
(derive-don't-store from the session `kind`, unchanged). The recap micro-segment and the
zoom-out trigger are untouched.

## Validation & store

Section-scoped items live in the same `content_bank/store/<book>.json`. `validate.py`
(store-level) gains:

- `section` resolves to a real id in the corpus section map for the item's book.
- every `thread`'s `refs` parse and fall within the item's book.
- **at most one published `throughline` per section.**
- `passage`/`section` mutual exclusivity (structural, in `schema.py`); a `thread`'s anchor
  section exists.

## Testing

- **Schema** (`content_bank/tests/test_schema.py`): `passage` xor `section` (both/neither
  fail); `throughline`/`thread` require `section` and reject `passage`; `thread` requires a
  non-empty well-formed `refs`; `refs` forbidden on non-threads; `throughline` is D7;
  `leader_reference` closed/open rule holds for D3 vs D7 threads.
- **Store validation** (`content_bank/tests/test_validate.py`): unresolved `section`
  fails; a `thread` ref outside the book fails; two published throughlines for one section
  fail.
- **Selector** (`prototype/test_selector.py`): a zoom-out prints an authored throughline
  when one exists (else the generic prompt); includes threads anchored to the section with
  their refs; includes section questions; **back-compat** — with no arc content authored,
  the zoom-out is byte-for-byte the MVP zoom-out.
- **Authoring** (`content_bank/tests/test_author.py`): the section-scope brief renders the
  section span and asks for throughline/threads/questions.

Commands: `python3 -m unittest discover -s content_bank/tests -v`;
`cd prototype && python3 -m unittest test_selector -v`;
`python3 -m unittest discover -s corpus/tests -v`.

## Success criteria

A family reaching a section's zoom-out sees an **authored** throughline and, at the
section that pays it off, an authored thread (with its verse refs) drawn from the content
bank — all WCF-1-guarded and leader-confirmed — while a book with no arc content authored
yet behaves exactly like the shipped MVP. No new dimension, no `dimensions.py` change, no
multi-pericope `passage`, and no change to the pericope-authoring path.
