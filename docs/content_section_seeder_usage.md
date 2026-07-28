# Using the section seeder

`content_bank/author/seed_sections.py` proposes a book's **section map** — the
book-arc movement layer that groups a book's ordered pericopes into contiguous,
named movements (`docs/content_build_terminology.md` § Section). It is the LLM-based
sibling of `corpus/ingest/seed_pericopes.py` (which seeds pericopes deterministically
from USFM `\s` headings): sections have no such textual signal, so an LLM **proposes**
a partition, the existing `corpus/lib/sections.py` validator **guarantees** it's a
valid contiguous partition, proposed boundary markers are **verified** against the
corpus, and the result is **staged** for a human to confirm before it becomes part of
the corpus.

For the vocabulary used below (pericope, section, unit), see
`docs/content_build_terminology.md`.

---

## What it does

1. **Propose.** For each of the book's pericopes (in order), gather a short public-domain
   commentary snippet — Jamieson-Fausset-Brown (JFB) preferred, falling back to Matthew
   Henry's Commentary (MHC) when JFB has no overlapping block — and send the whole book
   to the model in one prompt, asking it to group the pericopes into contiguous named
   sections (roughly 3–12, more for long narrative books), each with a `title_en`, an
   optional `marker` (a canonical verse ref, only where a clear repeating textual formula
   hinges the movement — e.g. Matthew's "when Jesus had finished"), and a one-line
   `rationale` grounded in the commentary.
2. **Validate.** The proposal is checked against `corpus/lib/sections.py:validate_data()`
   — full coverage, no gaps, no overlaps, exactly one section per pericope range. If it
   fails, the errors are fed back to the model as a repair prompt, up to `--max-repair`
   times; if it's still invalid after that, the run fails outright (nothing is staged).
3. **Verify markers.** Each proposed `marker` is checked: it must parse as a canonical
   ref and fall within its section's own pericope span. Any marker that fails either
   check is dropped (set to `null`) and recorded in the report — the tool never invents
   or keeps an unverifiable marker.
4. **Confirm (human).** The result is written to a **staging** file, not the corpus.
   Nothing is promoted automatically.

---

## The command

```bash
uv run python -m content_bank.author.seed_sections --book JON
```

Run everything under `uv` (`uv run …` or an activated `.venv`; `uv sync` first).

A provider credential is required for the chosen backend — the tool refuses before any
network call if it's missing:

- **`--backend claude`** (default) → the `claude` CLI (Claude Code headless) must be on
  `PATH`; it uses your subscription, not API credits.
- **`--backend llm_core`** → deepseek via `ARK_API_KEY`. Put it in the repo `.env`
  (git-ignored; see `.env.example`). Check: `llm_configured()` must be true.

---

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| `--book` | *(required)* | Book code, e.g. `JON`, `PHP`, `MAT`. |
| `--backend {claude,llm_core}` | `claude` | `claude` = Claude Code headless via subscription; `llm_core` = deepseek via API credits. |
| `--model MODEL` | `opus` for `claude`, `deepseek-v4-flash` for `llm_core` | Override the model. |
| `--max-repair N` | `2` | Repair rounds fed back to the model when the proposal fails partition validation, before giving up. |
| `--out PATH` | `work/section_seeds/<book>.json` | Output path for the staged section map. |
| `--rationale-file PATH` | — | Also write the human-readable report (per-section rationale + dropped markers) to this path. |
| `--force` | off | Overwrite `--out` if it already exists (without it, an existing file aborts the run). |

---

## Output: staged, not promoted

The tool writes the canonical section-map shape — `{"book": ..., "sections": [...]}`
with each section's `id`, `title_en`, `title_zh` (empty, filled in later), `first_pericope`,
`last_pericope`, `marker`, and `status` — to `work/section_seeds/<book>.json` by
default. Every section's `status` is `"seeded"`: this is a proposal, not a confirmed
canon entry. `rationale` is intentionally **dropped** from the staged JSON (it lives
only in the printed/`--rationale-file` report) — it's grounding for the human reviewer,
not a field the corpus schema carries.

`main()` prints the human-readable report (per-section span, marker, title, rationale,
and any dropped markers) followed by:

```
Staged → work/section_seeds/jon.json  (review, then copy to corpus/canon/structure/sections/jon.json)
```

**A human must review the staged file and copy it into
`corpus/canon/structure/sections/<book>.json`** — the seeder never writes there
directly, and there's no automated promotion step. Until that copy happens, the book
has no section map.

**This tool is NOT part of the corpus deterministic rebuild.** Unlike
`corpus/ingest/seed_pericopes.py` and the rest of `corpus/ingest/`, which read only
committed `sources/` and are re-run to reproduce the canon deterministically
(`corpus/README.md`), `seed_sections.py` calls an LLM and its staged output is a
proposal a human must accept. Once accepted and copied into
`corpus/canon/structure/sections/<book>.json`, that committed file — like other
`corpus/canon/` content — is treated as a source of truth going forward, not
regenerated by the rebuild.

---

## Practical notes

- **Re-running requires `--force`** if the default (or given) `--out` already exists —
  this guards against silently clobbering a staged proposal you haven't reviewed yet.
- **JFB-first grounding.** Commentary snippets prefer JFB (terser, better fits the
  prompt) and fall back to MHC only when JFB has no block overlapping a pericope's
  range; if neither has one, the pericope goes into the prompt with no grounding text.
- **Dropped markers are not a failure.** A section with a dropped marker still stages
  normally with `marker: null`; check the report/`--rationale-file` output to see what
  was dropped and why (`marker outside section span` / `marker unresolvable (...)`).
- **Section ids** are assigned downstream as `<BOOK>-S<n>` in proposal array order —
  the model does not supply an `id` field.
