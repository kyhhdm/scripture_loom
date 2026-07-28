# seed_sections — LLM-proposed, validator-guaranteed section maps

- **Date:** 2026-07-28
- **Status:** design (approved shape; pending spec review → plan)

## Problem

A book becomes buildable only after it has both a **pericope** map and a
**section** map (`corpus/canon/structure/{pericopes,sections}/<book>.json`).
Pericopes are semi-automatically seeded from BSB `\s` headings by
`corpus/ingest/seed_pericopes.py`. **Sections have no generator** — the three
existing maps (MAT/PHP/ECC) were hand-authored in the 2026-07-19 book-arc
session and are only *validated* by `corpus/lib/sections.py:validate_data`. That
manual step is the pacing item blocking scale-out to many books.

This tool closes the gap: it **proposes** a section partition with an LLM,
**guarantees** it with the existing deterministic validator, **verifies** any
machine markers, and stages the result for **human confirmation**. It mirrors
the citation-tags principle — *the model proposes, a deterministic gate
guarantees, a human confirms* — and mirrors `seed_pericopes` as the sibling
seeder.

## Non-goals

- Not part of the corpus's deterministic, offline, no-network rebuild. This tool
  needs an LLM call, so it is a **separate authoring tool**; its committed output
  file is treated as a corpus source, exactly as a hand-authored map would be.
- Does not confirm or publish anything. Output lands in staging with
  `status: "seeded"`; a human reviews and promotes it into canon.
- Does not author Chinese titles (`title_zh` stays `""`, as in `seed_pericopes`).
- Does not generate pericopes or content items.

## Inputs (gathered deterministically, before any LLM call)

1. **Pericope spine** — the ordered pericopes from
   `corpus/canon/structure/pericopes/<book>.json`: `id`, `range`, `title_en`.
   This is the ground truth the partition must tile exactly.
2. **Commentary grounding** — for each pericope's verse range, the aligned
   public-domain commentary block(s), so movement boundaries are defensible
   rather than invented:
   - **JFB first** (`corpus/canon/lampposts/jfb/<book>.json`, terser), **Matthew
     Henry fallback** (`.../mhc/<book>.json`) when JFB has no overlapping block.
   - Each block snippet **truncated (~200 chars)** to bound the prompt even for
     Matthew (153 pericopes). Alignment is by verse-range overlap between the
     pericope range and the commentary block `range`.
   - Both are `role: lamppost`, `license: public-domain`, all 66 books present.
3. **Book meta** — `name_en` etc. from `corpus/canon/structure/books.json`.

## LLM proposal

The prompt (fully rendered, self-contained — the seam runs a single-shot
completion with tools disabled) presents the ordered pericope list with titles
and the aligned commentary snippets, and asks the model to partition the
pericopes into contiguous named movements — **scaled to the book's length and
structure (roughly 3–12; more for long narrative books like Genesis)**. This is
soft guidance only; the validator enforces coverage and contiguity, never count,
so the model is free to exceed it when the book's arc warrants.

Required strict-JSON output per section:

- `title_en` — dual convention: `"Label: Description"` (e.g.
  `"Book One: The Sermon on the Mount"`), matching the existing maps.
- `first_pericope`, `last_pericope` — pericope ids from the spine.
- `marker` — a canonical `BOOK.CH.V` ref **only** where a clear repeating
  textual formula hinges the movement (e.g. Matthew's "when Jesus had finished"
  at `MAT.7.28`); otherwise `null`.
- `rationale` — one line, grounded in the commentary, explaining the boundary.

## Deterministic guarantees (the gate)

1. **Partition validation** — parse the JSON, then run the *existing*
   `sections.validate_data(proposal, pericope_order)`: required fields,
   first/last resolve, `first ≤ last`, contiguity (no gap/overlap), full coverage
   of every pericope, marker format. On any error, feed the error list back to
   the model for up to `--max-repair` rounds (default 2). If still invalid after
   the budget, **write nothing and exit non-zero** — a broken partition is never
   emitted.
2. **Marker verification** — for each non-null proposed `marker`, verify via
   `corpus_bridge` that (a) the ref resolves to a real verse, and (b) it falls
   **within the section's own verse-range span** (the union of `first_pericope`
   through `last_pericope` ranges). This matches the real data: `MAT-S2`
   ("Book One") carries marker `MAT.7.28`, the discourse-ending formula, which
   sits inside S2's own span (MAT-007→033). **Drop** any marker that fails either
   check; never hard-fail on it (markers are optional — Matthew's
   Prologue/Epilogue legitimately have `null`). This stops the model inventing a
   plausible-but-false anchor.

## Output

- **Default target: staging**, not canon —
  `work/section_seeds/<book>.json` (override with `--out PATH`). The tool never
  writes `corpus/canon/structure/sections/` unless `--out` is explicitly aimed
  there. A human reviews the staged file and promotes it by hand (a plain copy).
- **File shape** matches the section schema, plus a new **optional additive**
  field `status: "seeded"` on each section (signals human-unconfirmed, like
  pericopes). `title_zh: ""`. The field is additive: `validate_data` and the
  manifest compile ignore unknown keys, so nothing downstream breaks. `rationale`
  is **not** stored in the JSON (keeps canon schema-clean).
- **Human-facing report to stdout**: the section table (id · range span · title ·
  marker) with the per-boundary rationale, so a reviewer can judge the proposal
  without opening the file. Optional `--rationale-file PATH` writes the same as a
  sidecar `.md`.

## Seam / CLI

- Module `content_bank/author/seed_sections.py`, run as
  `python -m content_bank.author.seed_sections --book <BOOK>`.
- Reuses the existing `content_bank/author/llm.py:llm(prompt, model)` seam and
  `corpus_bridge` for corpus reads — no new LLM plumbing.
- Flags mirror `build_cli`:
  - `--book` (required)
  - `--backend {claude,llm_core}` — default **`claude`** (sets
    `SCRIPTURE_LOOM_LLM_BACKEND`)
  - `--model` — default **`opus`** (whole-book arc reasoning; sets
    `SCRIPTURE_LOOM_LLM_MODEL`)
  - `--max-repair N` — default 2
  - `--out PATH` — default `work/section_seeds/<book>.json`
  - `--rationale-file PATH` — optional sidecar
- Refuses before any network call if no credential is configured (same guard as
  the builder).

## Testing (network-free, seam mocked)

Same pattern as the translate/citation tests — patch `llm()` to return canned
completions:

1. A valid proposal passes the gate unchanged and writes a file that
   `validate_data` accepts.
2. An invalid partition (gap/overlap) triggers a repair round, then succeeds.
3. A proposal still invalid after `--max-repair` writes nothing and exits
   non-zero.
4. A non-null marker that doesn't resolve is dropped; a valid one is kept.
5. Default output goes to `work/section_seeds/<book>.json`; canon is untouched.
6. `status: "seeded"` and `title_zh: ""` are present; `rationale` is absent from
   the JSON but present in the stdout report / sidecar.
7. Commentary alignment prefers JFB and falls back to MHC when JFB lacks an
   overlapping block.

## Design principles honored

- **Propose → validate → confirm** — the model's freedom is fenced by the
  deterministic partition validator and marker verification; a human makes the
  final call (`status: "seeded"`, staged not canon).
- **Corpus rebuild determinism intact** — the offline rebuild never runs this
  tool; its output is committed source.
- **Grounded in trusted, public-domain sources** — boundaries anchored to JFB/MHC
  commentary; markers verified against the corpus, not trusted from the model.
