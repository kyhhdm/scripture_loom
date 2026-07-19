# Book-arc layer (MVP) — design

**Date:** 2026-07-19
**Status:** design, pending review
**Origin:** `docs/2026-07-19-cross-pericope-probe-findings.md` (the cross-pericope probe).

## Background

The probe established that book-arc fluency — *cross-pericope structural comprehension*
(the plot/timeline spine in narrative, the argument/"therefore"-chain in an epistle) — is
a load-bearing skill that **no dimension scores**: D2 (Event Sequence) refuses it by its
own rule "avoid sequence spanning other pericopes," while D4/D5/D7 house only the
*products* of arc comprehension, never the comprehension itself. The probe's decisions
that bound this spec:

- **D-A = no per-pericope authoring hook** — the full pericope build is unblocked and the
  arc layer is additive; nothing here changes pericope authoring.
- **D-B** — a *derived* spine (selector composes arc moves at kit-build) plus, for
  interpretive content, a separate lamppost-like *arc artifact*. **Not** span-scoped
  ContentItems.
- **D-C** — session shape is *both* a recurring recap micro-segment and a periodic
  dedicated zoom-out session, all Prepare-authored onto paper (no live computing).
- **D-D** — no stored section layer is *required*, but if named "meaningful" boundaries
  are wanted they belong **additive to `corpus/canon/structure/`, not as a per-pericope
  field**.
- **No new dimension (D9).** Arc comprehension is scored via existing dimensions at arc
  scope; D9 is reserved behind an explicit empirical trigger.

## Scope of this spec (decisions taken during design)

A **derived-only MVP**, with one deliberate, minimal step beyond "zero new data":

1. **Derived-only** for all session content — no authored arc content, no interpretive
   threads, no authoring-pipeline change.
2. **Meaningful boundaries, so a minimal section map.** The zoom-out fires at
   *meaningful* section boundaries (owner decision), which the probe found are **not**
   derivable from ordering alone. The MVP therefore adds a tiny **per-book section map**
   — named boundaries only, drawn from each book's **own structural markers** (for
   Matthew, the five-discourse "when Jesus had finished these sayings" formula). This is
   D-D's "additive to `structure/`" boundary layer, and **only** that — no interpretive
   threads.
3. **Zoom-out replaces the session** (a consolidation week; the reading does not advance
   to a new pericope that session).
4. **Throughline prompt included** as an open, no-answer-key prompt (carries no authored
   interpretation).

Deferred to a **v2 arc artifact** (explicitly out of scope): authored interpretive
threads (e.g. the Philippians *phroneo* thread), the context-scoped D2 *authoring*
reshape those would require, and leader-adjustable section boundaries.

## Architecture overview

Three additive components; the first is corpus data, the other two live in the prototype
selector (where kit generation lives, per `prototype/selector.py`).

| Component | Where | New data? |
|---|---|---|
| 1. Section map | `corpus/canon/structure/sections/<book>.json` + a loader/validator | Yes — tiny, per book |
| 2. Recap micro-segment | `prototype/selector.py` (new fn + kit field) | No — pure derived |
| 3. Zoom-out session | `prototype/selector.py` (`build_kit` branch) + session record model | No content; two record fields |

`content_bank/` is **untouched** — the arc sequence exercise is *generated* by the
selector, not authored as a ContentItem, so `dimensions.py`'s D2 rule stays as-is.

---

## Component 1 — the section map

### Location & shape

`corpus/canon/structure/sections/mat.json`, beside `pericopes/`:

```json
{
  "book": "MAT",
  "sections": [
    {"id": "MAT-S1", "title_en": "Prologue: The Infancy", "title_zh": "",
     "first_pericope": "MAT-001", "last_pericope": "MAT-006", "marker": null},
    {"id": "MAT-S2", "title_en": "Book One: Discipleship (Sermon on the Mount)",
     "title_zh": "", "first_pericope": "MAT-007", "last_pericope": "MAT-0NN",
     "marker": "MAT.7.28"}
  ]
}
```

- **Contiguous partition.** Sections cover the book's ordered pericopes with no gaps and
  no overlaps; every pericope belongs to exactly one section; `first_pericope` /
  `last_pericope` resolve to real ids and are correctly ordered.
- **`marker`** — the textual formula justifying the boundary (e.g. `MAT.7.28`, "when
  Jesus had finished these sayings"), or `null` for prologue. Provenance and WCF-1
  safety: boundaries follow structure the text itself signals, not imposed themes.
- **Bilingual titles** (`title_en` / `title_zh`), matching the pericope schema; `title_zh`
  may be empty pending translation.

### Matthew's authored sections (the structural-marker division)

Seven sections — Baconian five-book structure (each = narrative + its discourse, ending
at the formula) plus prologue and Passion epilogue:

| id | title | chapters | marker |
|---|---|---|---|
| MAT-S1 | Prologue: The Infancy | 1–2 | — |
| MAT-S2 | Book One: The Sermon on the Mount | 3–7 | 7:28 |
| MAT-S3 | Book Two: The Mission Discourse | 8–10 | 11:1 |
| MAT-S4 | Book Three: The Parables of the Kingdom | 11–13 | 13:53 |
| MAT-S5 | Book Four: The Community Discourse | 14–18 | 19:1 |
| MAT-S6 | Book Five: The Olivet Discourse | 19–25 | 26:1 |
| MAT-S7 | Epilogue: Passion & Resurrection | 26–28 | — |

Only MAT-S1 (`MAT-001..MAT-006`) is fully pinned here; the remaining `first/last_pericope`
ids are resolved against `pericopes/mat.json` at authoring time. Exact pericope ids, not
chapter numbers, are stored.

### Validation

A `validate_sections(book)` check (mirroring `corpus`'s existing validation style):
partition integrity (contiguous, no gap/overlap, complete cover of the book's pericopes),
id resolution, ordering, `marker` well-formed if present. Runs in the corpus test suite.

### Loading

`load_sections(book) -> list[Section]` in the corpus structure layer; `build_kit` receives
the loaded `sections` list as an argument, parallel to how it already receives `bank`.

---

## Component 2 — recap micro-segment (derived, every normal kit)

New selector function:

```python
def arc_recap(sections, bank, family):
    """The 'story so far' within the current section: the section title and the
    ordered titles of pericopes studied so far in it. Pure derived; no new data."""
```

- Finds the current section (the one containing `next_passage`'s pericope).
- Lists, in reading order, the titles of pericopes in that section the family has already
  studied (from `family["sessions"]`, normal sessions only).
- Returns e.g. `{"section": "Prologue: The Infancy", "studied": ["The Genealogy of
  Jesus", "The Birth of Jesus", "The Pilgrimage of the Magi"], "position": "3 of 6"}`.
- Empty `studied` before any pericope of the section is done → recap still names the
  section ("Beginning *Prologue: The Infancy*").

`build_kit` adds `"arc_recap": arc_recap(sections, bank, family)` to the kit dict; the kit
renderer prints it as a one-line breadcrumb.

---

## Component 3 — the zoom-out session

### Record-model additions (personal record, not corpus)

Sessions gain a `kind`; zoom-out sessions carry a `section` and **no** `passage`:

```json
{"date": "…", "kind": "normal",   "passage": "MAT-003", "evidence": []}
{"date": "…", "kind": "zoom_out", "section": "MAT-S1",  "evidence": []}
```

`kind` defaults to `"normal"` when absent (back-compatible with existing fixtures). These
are the only new record fields — no new evidence field.

### Trigger detection

```python
def due_zoom_out(sections, family):
    """Return the Section to zoom out on, or None.
    Fires when the most-recently-studied pericope is a section's last_pericope AND no
    zoom_out session already exists for that section."""
```

- "Most-recently-studied pericope" = the `passage` of the last **normal** session.
- "Already zoomed" = any session with `kind == "zoom_out"` and that `section`.
- Fires **once** per section, exactly at completion; never mid-section.

### `build_kit` branch

```python
def build_kit(bank, family, sections):
    section = due_zoom_out(sections, family)
    if section:
        return build_zoom_out_kit(bank, family, sections, section)   # replaces the session; no passage advance
    passage = next_passage(bank, family)
    ...
    kit["arc_recap"] = arc_recap(sections, bank, family)
    return kit
```

A zoom-out **replaces** the new-passage session: `next_passage` is not consulted, so
reading does not advance that session. `next_passage`'s `studied` set is computed from
normal sessions' `passage` only (guard against zoom-out sessions having no `passage`).

### Zoom-out kit contents (all derived over the completed section)

`build_zoom_out_kit` returns a kit of `kind: "zoom_out"` containing:

1. **Sequence reconstruction (D2, arc-scope)** — the section's pericopes as a scrambled
   set of title cards, to be put back into reading order. *This is the orphaned skill
   itself, fully derivable from ordered titles + ranges.* Kit field: `sequence_cards`
   (the section's pericopes) + the correct order for the leader's reference sheet.
2. **Memory recall (D4)** — the memory verses the family met in this section, derived
   from studied `memory_verse` items whose `passage` falls in the section. Kit field:
   `memory_recall`.
3. **Throughline prompt (D6/D7, open, no answer key)** — a generically-templated open
   prompt: *"In one sentence, what was* [section title] *about?"* No authored
   interpretation and no answer key (an open dimension), so nothing is fabricated;
   deferred v2 supplies an authored throughline.

Reuses existing scaffolding: `assign_roles` and the recorder/notebook page apply
unchanged.

---

## Component 4 — evidence & scoring (no D9)

Zoom-out marks file under **existing** dimensions: the sequence exercise → D2, memory
recall → D4, the throughline → D6/D7. "**Arc-scope** D2" is distinguished from
pericope-scope D2 **not** by a new field but by the session being `kind: "zoom_out"` —
*derive-don't-store*, the identical principle the genre probe used (context is a derived
attribute of the session, computable at read time).

The existing weakness/staleness signals (`weak_dimensions`, `select_observation_targets`)
consume zoom-out evidence like any other — a child who repeatedly can't reorder a section
accrues D2 weakness, which is correct and desired. If, once this ships, the record still
cannot distinguish "reconstructs the plot" from "memorized the facts" under arc-scope D2,
that is the probe's stated empirical trigger to revisit D9 — future evidence, not a reason
to complicate this MVP.

---

## Interfaces (summary)

- `load_sections(book) -> list[Section]` and `validate_sections(book) -> list[str]`
  (corpus structure layer).
- `arc_recap(sections, bank, family) -> dict` (selector).
- `due_zoom_out(sections, family) -> Section | None` (selector).
- `build_zoom_out_kit(bank, family, sections, section) -> dict` (selector).
- `build_kit(bank, family, sections) -> dict` — **signature change**: gains `sections`;
  returns either a normal kit (now with `arc_recap`) or a zoom-out kit.

`next_passage`'s `studied` derivation changes to count normal sessions only. All other
existing selector functions are unchanged.

## Non-goals (explicit — preserve probe consistency)

- **`content_bank/author/dimensions.py` unchanged.** The D2 "avoid cross-pericope
  sequence" rule stays; the arc sequence exercise is selector-generated, not authored.
- **No interpretive/thread arc content** (e.g. *phroneo*) — v2 arc artifact.
- **No context-scoped D2 authoring reshape** — only needed when arc content is *authored*
  (v2).
- **No per-pericope field; D-A stays no.** The full pericope build remains unblocked.
- **No D9**, no new evidence field, no new dimension vocabulary.
- **No leader-adjustable sections** — ship the authored structural-marker default; a
  per-family override is v2.
- **Nothing during the gathering** — recap and zoom-out are Prepare-authored onto paper
  (`unplug_assitant.md` §16).

## Testing

- **Corpus:** `validate_sections("MAT")` — partition is contiguous/complete/non-overlapping,
  ids resolve and are ordered, markers well-formed; a fixture with a gap/overlap fails.
- **Selector:**
  - `arc_recap` names the correct section and lists studied pericope titles in reading
    order; empty-studied names the section only.
  - `due_zoom_out` fires exactly at a section's `last_pericope`, not mid-section, and not
    twice for the same section (a prior `zoom_out` session for it suppresses re-firing).
  - `build_kit` returns a zoom-out kit on a completion boundary and does **not** advance
    the passage; returns a normal kit (with `arc_recap`) otherwise.
  - `build_zoom_out_kit`: `sequence_cards` = exactly the section's pericopes; correct
    order recorded for the leader; `memory_recall` = studied memory verses in-section only;
    throughline prompt present with no answer key.
  - Back-compat: existing fixtures without `kind`/`sections` still build a normal kit.

Commands: `python3 -m unittest discover -s corpus/tests -v` and
`cd prototype && python3 -m unittest test_selector -v`.

## Success criteria

A family reading Matthew gets a "story so far" line on every kit, and on finishing each of
Matthew's seven sections gets one derived zoom-out session that exercises and lets the
leader observe cross-pericope sequence comprehension — with those marks scored under
arc-scope D2/D4/D6/D7, no new dimension, no authored arc content, and no change to pericope
authoring or the corpus pericope build.
