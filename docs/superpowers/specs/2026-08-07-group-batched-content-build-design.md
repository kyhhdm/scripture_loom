# Group-batched content build mode — design

**Date:** 2026-08-07
**Status:** approved for planning
**Owner decision driving it:** minimize the *number* of LLM calls (not just tokens) when
drafting on the `claude`/Opus subscription backend, whose usage windows meter both
request count and tokens.

## Problem

The standalone builder (`content_bank/author/build_cli.py`) drives the pipeline
**one unit at a time**: brief → draft → (gates + repair) → review r1/r2 → revise, per
pericope and per section. For a section spanning N pericopes (a *group* of N+1 units)
that is roughly `4(N+1)+` LLM calls. On the `claude` backend (Claude Code headless,
Opus, subscription auth) every request counts against a usage window, so a per-unit
walk exhausts the window far faster than necessary — even though the section and its
pericopes share almost all of their context.

## Goal

Add a **`group` execution mode** that batches all units of one section-group into
**one LLM call per stage**, splits the batched response back into per-unit artifacts
immediately, and keeps every downstream stage (gates, manifest, store writer,
provenance) operating per-unit and byte-for-byte as today. For a 6-unit group this
turns ~24 calls into ~5.

Non-goals (explicit): this does **not** reduce output tokens (the same items are
produced), does **not** change item quality expectations (human review is still the
gate), and does **not** wire into the experiment runner's per-stage routing in v1
(clean follow-up).

## Key facts grounding the design (verified in code)

- `content_bank/author/llm.py` — `LLMResult.stop_reason` is populated from the
  `claude -p` JSON payload (`"max_tokens"` on truncation) and is `None` for
  `llm_core`. Group mode is designed for the `claude` path, so truncation is
  **deterministically detectable**, not guessed.
- Sections carry `first_pericope` / `last_pericope`; `build_cli._section_text`
  already walks a section's pericope span. `groups_for_book` reuses that logic.
- Gates (`gates.run_all`, `dimension_cap_check`) and the repair loop
  (`build_cli._repair_to_clean`) are **per-unit and deterministic**; only the repair
  LLM call costs a request.
- Review (`review.py:review`) already issues exactly **two** LLM calls per unit
  (r1, r2) and `revise` re-sends **only the failed items**. Group mode batches
  *within* each lens; it never folds drafting and review into one call.
- The manifest (`manifest.py`) tracks stage **per unit**; group mode marks each unit
  `briefed`/`drafted` as its slice is split out.

## Design

### 1. Group definition

A **group** = one section + the pericopes in its span. Sections partition the book
(from `seed_sections`), so every pericope belongs to exactly one group. New helper:

```
groups_for_book(book) -> list[(section_id, [pericope_id, ...])]
```

reading `corpus.lib.sections` (`first_pericope`/`last_pericope`) the same way
`build_cli._section_text` does. A single-pericope section (`PHP-S1`) is a group of
two units (the section + its one pericope); its `thread_span_check` behavior is
unchanged (threads remain invalid on a single-pericope section).

### 2. Module layout

New module **`content_bank/author/build_group.py`**. It does **not** enlarge the
already-large `build_cli.py`; it imports and reuses `build_cli`'s helpers
(`_parse_items`, `_repair_to_clean`, `_regate`, `_stamp_draft_provenance`,
`_write_json`, `_run_layout`, `_load_run_manifest`, `_effective_model`,
`_run_slug`, `_passage_text`, `_section_text`) and `gates`/`manifest`/`routing`.
Group mode changes **only the LLM I/O batching**; everything downstream is the
existing per-unit code.

CLI: a `--group` flag on `build_cli.main()` dispatches to `build_group.group_run(...)`.
`--group` is **orthogonal to `--backend`** — it works with any backend and does not
warn on `llm_core` (the user drives Opus with `--group --backend claude --model opus`).

### 3. Batched prompt builders and the envelope

Each stage sends **one** prompt covering the whole group and requests a JSON
envelope:

```json
{ "units": { "PHP-002": <payload>, "PHP-003": <payload>, ... } }
```

- **Group brief prompt** (`build_group_brief_prompt.build(group, book)`): one header +
  per-unit blocks (section arc block + each pericope block), reusing the substance of
  `build_brief_prompt` / `build_section_brief_prompt`. Payload per unit = the brief
  markdown string.
- **Group draft prompt** (`build_group_draft_prompt.build(group, book, briefs)`): one
  header + per-unit brief + per-unit passage, reusing the per-unit *shape* specs from
  `build_draft_prompt` / `build_section_draft_prompt`. Payload per unit = the item
  array.

The prompt builders compose the existing single-unit prompt substance so the tuned
authoring instructions (citation tags, item shapes, dimension rules) are preserved;
the only new text is the group header and the envelope output-format spec.

Envelope parsing: `_parse_units(text, expected_ids) -> dict[str, payload]`. A missing
id, an unparseable envelope, or a truncated body is **not** a silent partial — it
triggers the bisection guard (§5).

### 4. The per-group flow (one call per stage)

For a group `(section_id, pericope_ids)`:

1. **brief** — 1 call → split → write each `briefs/<unit>.md`; each unit → `briefed`.
2. **draft** — 1 call → `{unit: [items]}`; each unit's items run the existing per-unit
   gates (`run_all` + `dimension_cap_check`).
3. **repair** — the flagged units **only**, batched into **1 call per round**
   (up to `--max-repair`), via the same `{"units": {...}}` envelope. Remaining HARD
   flags fail *that unit only* (isolated, does not fail the group); SOFT flags warn.
4. **review r1** — 1 call over all units' items → per-unit verdicts; **r2** — 1 call.
   Two calls, lenses independent.
5. **revise** — the failed units **only**, batched into 1 call → split → re-gate each
   revised unit (`_regate`).
6. Write `drafts/<unit>.json` + `verdicts/<unit>.json`; each unit → `drafted`.

`--no-review` skips 4–5 and uses draft + batched repair only.

Batched review/revise are new group-aware functions in `review.py`
(`review_group`, `revise_group`) that take `{unit: items}` / `{unit: verdicts}` and
return per-unit results; they mirror `review`/`revise` exactly except for the envelope
and prompt shape. Single-unit `review`/`revise` are untouched.

### 5. Truncation / oversize guard (bisection)

After **any** group call, if `stop_reason == "max_tokens"` OR an expected unit id is
missing from the envelope OR the envelope will not parse:

- **Bisect the group's unit list and retry each half** as its own group call,
  recursing until halves succeed or reach a **singleton**.
- A singleton that still truncates/omits raises a per-unit failure, isolated to that
  unit (recorded in the `failed` map like any per-unit `GateError`); the rest of the
  group proceeds.

Two half-calls still beat N per-unit calls, and no unit is ever silently dropped. The
guard applies uniformly to brief, draft, repair, review, and revise calls.

### 6. What stays identical

Manifest (per-unit stages), gates and their allowlists (`pericope_allowed` /
`section_allowed`), repair loop semantics, `revise`'s byte-identical-passing-items
guarantee, provenance stamping, per-model run layout
(`runs/<slug>/{manifest,briefs,drafts,verdicts,raw_drafts}`), and `raw_drafts`
persistence. `compare_html` reads the same per-unit files and is unaffected.

### 7. Telemetry (the one accepted tradeoff)

Batched calls are recorded via the existing `record_call` with
`unit_id = <section_id>` and `kind = "group"`. Per-**call** counts and stop reasons
are retained (the metric that matters here); per-**unit** token attribution is lost
for batched stages. This is documented, not hidden. Bisected sub-calls are recorded
individually (so a truncation shows up as extra calls in telemetry).

### 8. Error handling and resumability

- A group is the failure unit for the *batched call*, but per-unit isolation is
  preserved for gate/parse outcomes: one unit failing its gates raises for that unit
  only; other units in the group are still written and marked `drafted`.
- The manifest is saved after each unit's stage advance, so a crash mid-group resumes
  at the first not-yet-`drafted` unit; `group_run` recomputes the group's remaining
  work from the manifest (units already `drafted` are skipped when re-run).
- `--limit` in group mode limits the number of **groups**, not units.

## CLI surface

```
uv run python -m content_bank.author.build_cli \
    --book PHP --group --backend claude --model opus [--no-review] \
    [--max-repair N] [--limit N_GROUPS] [--dim-cap N]
```

`--units` in group mode selects groups by section id (a section id names its whole
group). Omitting `--units` walks all groups with any unit not yet `drafted`.

## Testing (TDD, `llm` seam mocked — network-free)

1. `groups_for_book` returns the correct section→pericope partition for a fixture book.
2. `_parse_units`: valid envelope; missing-unit; truncated/unparseable → each surfaces
   the bisection signal (not a silent partial).
3. Batched **draft** happy path: one mocked call yields a `{units}` envelope → every
   unit gated, written to `drafts/`, and marked `drafted`; manifest correct.
4. **Bisection recovery**: mock returns `max_tokens` on the full group but a valid
   envelope on each half → all units end up drafted; telemetry shows the extra calls.
5. **Failed-units-only** repair and revise: given per-unit gate/verdict fixtures, only
   the flagged units appear in the repair/revise prompt; passing units are byte-identical.
6. **Call-count assertion** (the core value metric): a group of N+1 units drafts in the
   batched call count (~1 draft call + bounded repair), asserted strictly less than the
   per-unit `4(N+1)` baseline via a counting mock.
7. `--no-review` path: draft + batched repair only, no review/revise calls.

## Follow-ups (out of scope for v1)

- Wire group mode into `experiment_cli.py` per-stage routing (so a hybrid experiment
  can batch on one route and review on another).
- A/B measurement (Opus per-unit vs Opus group-batched) on cost **and** quality
  (gate pass rate, r1/r2 fail rate, dropped-item count) on a real section, per the
  nondeterministic-system verification discipline — recommended before adopting group
  mode as the default authoring path.
