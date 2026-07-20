# Standalone Python content-bank builder (issue #16)

Date: 2026-07-20
Issue: #16 — "Standalone Python content-bank builder (replace agent workflow with an API-call program)"
Branch: feature/llm-core-vendor (continues here)

## Goal

Replace the Claude Code **Workflow** fan-out that builds the draft content library
(`work/content_bank_build/build_book_draft.workflow.js`,
`build_sections_draft.workflow.js`) with a committed, standalone Python program that
drives the same deterministic pipeline directly and calls an LLM through the already-
vendored `llm_core` seam. Then extend it with an optional **adversarial-review** step
(the lens the *full* workflow had, `build_book_full.workflow.js`), build the
Philippians (PHP) draft library with it, and compare quality against the existing
Claude-Code-built PHP library.

## Why this is now tractable

The pipeline is already ~90% deterministic Python; every non-LLM step is a pure
function that already exists:

| Step | Callable |
|---|---|
| brief prompt | `content_bank.author.build_brief_prompt.build(pid, book)` |
| write brief | **LLM** via `content_bank.author.llm.llm(prompt)` |
| draft prompt | `content_bank.author.build_draft_prompt.build(pid, book, brief)` |
| section prompt | `content_bank.author.build_section_brief_prompt.build(sid, book)` |
| draft items | **LLM** |
| quote gate | `work/content_bank_build/quote_check.py` (to be promoted) |
| schema gate | `content_bank.lib.schema.validate_item` |
| ref-range gate | **new** `refs_in_range` |
| stage draft | write JSON to `work/content_bank_build/<book>/drafts/<id>.json` |

The `llm()` seam (`content_bank/author/llm.py`) is **already done and wired to
`llm_core`** (default model deepseek-v4-flash). This resolves issue #16's open
question (a)/(b): the repo is no longer stdlib-only (dropped when `llm_core` was
vendored), so there is no `anthropic`-SDK-vs-`urllib` decision — the builder uses the
existing seam. This spec records that resolution so the issue's checkbox closes
honestly.

## Decisions (locked with the owner)

1. **Scope:** pericopes **and** sections, both in this work.
2. **Review status:** items are written `review_status: "draft"` (matching the
   current draft workflows), not `reviewed`. Human review remains the true gate; a
   separate deliberate step (`stage_book.py` / `restage_library.py`) promotes drafts
   into the store later. The builder never writes the committed store and never
   self-publishes.
3. **Output target:** the builder is a faithful drop-in for the two draft workflows —
   its only product is gated draft JSON files in the untracked
   `work/content_bank_build/<book>/drafts/`. It does not touch the committed store.
4. **Adversarial review** (added by the session goal): an **optional** step behind a
   `--review` flag. Default off = issue-#16 lean parity (matches
   `build_book_draft`). `--review` on = the two-lens adversarial pass + one revise
   pass (matches `build_book_full`), inserted before the final mechanical gates.

## Architecture

### New / changed files

| File | Status | Purpose |
|---|---|---|
| `content_bank/author/build_cli.py` | new, committed | orchestrator + `python -m` entry point |
| `content_bank/author/gates.py` | new, committed | the three deterministic gates as importable, tested functions |
| `content_bank/author/review.py` | new, committed | the adversarial-review + revise LLM step (used only with `--review`) |
| `content_bank/author/build_section_brief_prompt.py` | edit | fold the concrete JSON item-shape (currently only in the workflow JS) into `build()` so the section path is self-contained |
| `content_bank/author/tests/test_gates.py` | new | gate unit tests incl. the MAT-035 repro |
| `content_bank/author/tests/test_build_cli.py` | new | orchestrator tests with `llm()` mocked |
| `content_bank/author/tests/test_review.py` | new | adversarial-review tests with `llm()` mocked |

The untracked `work/content_bank_build/quote_check.py` and the `*.workflow.js` files
become dead once this lands; they are already git-ignored scaffolding and are left in
place (not deleted) as reference.

### `gates.py` — three pure functions

Each returns `{item_id: [problems]}` (empty dict = clean).

1. **`quote_check(book, items)`** — promoted verbatim from
   `work/content_bank_build/quote_check.py`: flags any quoted span (≥3 words) in an
   item's `text` / `leader_reference.text` / `leader_reference.verse` that is not
   verbatim (quote-mark- and whitespace-insensitive) anywhere in the whole BSB. The
   whole-Bible haystack means legitimate D5 cross-reference quotes still validate.
2. **`schema_check(items)`** — thin wrapper mapping ids to non-empty
   `schema.validate_item(item)` results.
3. **`refs_in_range(items, unit)`** — **new.** `unit` carries the allowed range(s):
   a pericope's own `range`, or a section's `first_pericope..last_pericope` span.
   - **Sections:** every `thread.refs` entry (already validated *well-formed* by
     `schema._check_scope`, but never validated *in-span*) must fall within the
     section span. This is the missing membership check on top of the existing
     shape check.
   - **Pericopes:** the item's structured `passage` field is always the right
     pericope, so drift shows up in a *stated verse reference* inside the item —
     e.g. a `leader_reference.verse` reference or an explicit chapter:verse token in
     text. The gate extracts stated verse references and flags any whose
     chapter·verse falls outside the pericope range and is not a cross-reference the
     brief names. (Prose paraphrase without a stated reference is left to
     `quote_check`; this gate polices *stated locations*.)
   - **Anchor test (drives the design test-first):** reconstruct the historical
     MAT-035 drift — a Matthew-15 quote/reference inside the Matthew-8 pericope
     MAT-035 — and assert `refs_in_range` flags it. The exact set of fields scanned
     and the D5-cross-ref exemption are pinned down by making that test (plus a
     legitimate-D5 non-false-positive test) pass.
   - **Primitives:** reuse `corpus_bridge._parse_range` and a chapter-aware
     containment (note: the existing `_overlaps` requires same chapter, so section
     spans that cross chapters need a multi-chapter comparison — a small helper in
     `gates.py`, not `_overlaps`).

`gates.py` exposes a convenience `run_all(book, items, unit, *, extra=())` that runs
the standard three and returns a merged `{item_id: [problems]}`.

### `build_section_brief_prompt.py` edit

The section draft's exact JSON item schema (throughline / thread / question object
shapes, id conventions, the leader_reference rules, "exactly one throughline")
currently lives only in the workflow JS prompt string. Fold it into `build()` as an
output-schema block (mirroring `build_draft_prompt._SCHEMA_BLOCK` / `_TYPE_BLOCK`) so
`build(sid, book)` yields a fully self-contained prompt. Pericope prompts already are
self-contained, so no change there.

### `review.py` — adversarial review + revise (optional)

Used only when `--review` is set. Mirrors `build_book_full` S3–S4, single-sourced
against `rubric.py`:

- **`review(items, context) -> list[verdict]`**: two reviewer `llm()` calls with
  complementary lenses, each fed the drafted items + the passage text + the brief +
  the shared rubric text (`rubric.build()` for r1's accuracy/WCF-1/answerability lens;
  `rubric.build()` + `rubric.reference_criteria()` for r2's
  evidence-not-judgment/age/dimension/pedagogy/leader-reference lens). Each returns
  strict JSON `{item_id: {"reviewer","verdict":"pass"|"fail","notes"}}`. Parsed via
  the shared JSON-extraction helper.
- **`revise(items, verdicts, context) -> items`**: one `llm()` call that revises only
  the items any reviewer failed (fix fact/quote; retag dimension and switch
  answer_key↔leader_note to match; reframe judgment→observable behavior;
  make answerable/grounded), leaving passing items untouched, and returns the full
  array. Irreparable items may be dropped (documented in the run log).
- Output then flows into the same mechanical gates + repair loop as the lean path, so
  `--review` never bypasses the deterministic gates.

Items still land `review_status: "draft"`; the adversarial pass sharpens the draft, it
does not confer human review or publish.

### `build_cli.py` — the orchestrator

Entry point: `python -m content_bank.author.build_cli`.

Flags:
- `--book BOOK` (required)
- `--units ID [ID ...]` — explicit override of the work queue
- `--kind {pericope,section,all}` (default `all`)
- `--review / --no-review` (default `--no-review`)
- `--max-repair N` (default 2)
- `--limit N` — cap units processed this run
- `--manifest PATH` (default `work/content_bank_build/<book>/manifest.json`)

Work queue: units in the manifest at stage `pending` (for the brief step) /
`briefed` (for the draft step), filtered by `--kind`, or the explicit `--units`.

Per-unit flow (each wrapped in try/except for **failure isolation**):

Pericope:
1. If stage `pending`: `build_brief_prompt.build(pid, book)` → `llm()` (with
   backoff) → write `content_bank/author/briefs/<pid>.md`; manifest stage → `briefed`.
2. `build_draft_prompt.build(pid, book, brief)` → `_draft_with_repair(...)` →
   (if `--review`: `review.review` → `review.revise`) → final gates + repair →
   write `drafts/<pid>.json`; manifest stage → `drafted`.

Section:
1. `build_section_brief_prompt.build(sid, book)` → `_draft_with_repair(...)` →
   (if `--review`: review + revise) → final gates + repair → write
   `drafts/<sid>.json`; manifest stage → `drafted`.

On any unit failure (LLM error after backoff, or gates still dirty after
`--max-repair` rounds): log the reason, **leave the manifest stage unchanged**,
continue to the next unit. Re-running retries only the stragglers. No half-written
drafts land.

### Shared helpers (in `build_cli.py` or a small `_util`)

- **`_draft_with_repair(prompt, book, unit, *, max_repair)`**: `llm()` → parse JSON
  array → `gates.run_all` → if flagged, build a repair prompt (previous array + the
  specific gate problems + "return the full corrected array") and re-`llm()`; ≤
  `max_repair` rounds, else raise `GateError`.
- **`_parse_items(text)`**: strip ```json fences / surrounding prose and locate the
  JSON array; raise a clear error on unparseable output (counts as a unit failure).
- **`_llm_with_backoff(prompt)`**: wraps `llm()` with a bounded sleep-backoff (with
  jitter) on transient `RuntimeError` (rate-limit-shaped). `llm_core` already retries
  twice internally; this adds the outer pacing, then gives up → unit failure.
- **Errors:** `GateError`, `LLMUnavailable` (raised once up front if
  `llm_configured()` is false, so the run fails fast rather than per-unit).

## Data flow

```
manifest (work queue)
   └─ per unit ─────────────────────────────────────────────
        build_*_prompt.build()  ── deterministic ──► prompt
        llm()  (backoff)                          ─► brief / draft text
        _parse_items()                            ─► items[]
        [--review] review() + revise()            ─► items[]  (sharpened)
        gates.run_all() + repair loop             ─► items[]  (gate-clean)
        write drafts/<id>.json ; manifest stage → drafted
   ────────────────────────────────────────────────────────
(separate, later, human-gated: stage_book.py → store ; human review → published)
```

## Error handling

- **No LLM credential:** `llm_configured()` false → fail fast at startup with a clear
  message (do not attempt any unit).
- **Rate limit / transient LLM error:** bounded backoff in `_llm_with_backoff`; on
  exhaustion the unit is skipped (isolated), the run continues.
- **Unparseable LLM output:** unit skipped, logged.
- **Gates never clean after repair:** unit skipped, logged; manifest stage unchanged.
- **Per-unit isolation is the invariant:** one bad pericope never aborts the batch and
  never leaves a partial draft file (write only after gates pass).

## Testing (no network — `llm()` mocked in every test)

- `test_gates.py`:
  - `quote_check` flags a non-verbatim quote, passes a verbatim one and a legit
    cross-book quote.
  - `schema_check` surfaces `validate_item` errors by id.
  - `refs_in_range`: **MAT-035 repro** (Matthew-15 reference in the Matthew-8
    pericope) is flagged; an in-range pericope item and a legitimately-named D5
    cross-reference are **not** flagged; a section thread ref outside the span is
    flagged; one inside the span passes.
- `test_build_cli.py` (fake `llm()` returning canned brief + draft JSON):
  - pericope path writes brief + draft to the right paths and bumps manifest stages;
  - section path writes the section draft and bumps the stage;
  - the repair loop drives a dirty→clean draft (fake `llm()` returns dirty first,
    clean on repair) and stops after `--max-repair`;
  - an `llm()` exception isolates to one unit — the batch completes the others and
    the failed unit's manifest stage is unchanged.
- `test_review.py` (fake `llm()`):
  - `review` parses two reviewers' verdicts; `revise` edits only failed items and
    leaves passing ones byte-identical; a failed item that cannot be fixed is
    dropped.

Run: `uv run python -m unittest discover -s content_bank/tests -v` (and/or the
author tests dir, matching the repo's existing test discovery).

## Acceptance criteria (issue #16 + goal)

- [x] `build_cli.py` produces the same `draft` items the workflow does, gated on
      quote + schema **+ new ref-in-range** checks.
- [x] LLM access stays behind the single `llm()` seam (already done; mockable).
- [x] Rate-limit backoff + per-unit failure isolation.
- [x] Unit tests with the LLM seam mocked (no network).
- [x] Stdlib-only-vs-SDK decision recorded (resolved: use vendored `llm_core`).
- [x] Optional `--review` adversarial step (two lenses + revise), single-sourced
      against `rubric.py`, never bypassing the mechanical gates.
- [x] PHP draft library built with `build_cli.py --review`, and a written quality
      comparison against the existing Claude-Code-built PHP library
      (`docs/sessions/2026-07-20-php-python-vs-claude-comparison.md`).

## Out of scope

- Writing to / publishing the committed store (stays a separate, human-gated step).
- Auto-`reviewed`/auto-`published` status (owner decision: human review is the gate).
- Reworking the corpus, prompt-builder content, or the schema itself.
- Deleting the now-dead workflow JS / `work/quote_check.py` scaffolding.
