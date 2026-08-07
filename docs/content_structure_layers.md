# How pericopes and sections are built

Scripture Loom stacks two structural layers on top of Bible text. They are
produced by **two sibling seeders with deliberately different trust models**:

- **Pericopes** — deterministic, rebuilt from the source text (`corpus/`).
- **Sections** — LLM-proposed, validator-guaranteed, human-gated
  (`content_bank/author/`).

A **section-group** binds them: a section plus the pericopes in its span. The
split follows the corpus principle in `corpus/README.md`: `ingest/` scripts are
deterministic (`sources/ → canon/`, rerunnable); `canon/` is the normalized
store and the only thing consumers read.

See also: `docs/content_build_terminology.md` (glossary),
`docs/content_section_seeder_usage.md` (running the section seeder),
`docs/content_builder_usage.md` (§"Group mode").

---

## 1. Pericopes — deterministic, from the source text

A **pericope** is the base authoring unit: a single self-contained passage
(e.g. `PHP-001` = Philippians 1:1–11).

- **Built by:** `corpus/ingest/seed_pericopes.py` (part of the corpus rebuild).
- **Source of truth:** the `\s` section headings in a USFM source file. Each
  heading starts a new pericope at the *next* verse after the heading; each
  pericope ends at the verse before the next one begins. Any text before the
  first heading becomes pericope `001` (an "Opening").
- **Fully deterministic and rerunnable** — no LLM, no human gate.
  `python3 corpus/ingest/seed_pericopes.py MAT` regenerates it from committed
  sources.
- **Stored at:** `corpus/canon/structure/pericopes/<book>.json`.

Record shape:

```json
{"id": "PSA-001", "range": "PSA.1.1-6", "title_en": "The Two Paths", "title_zh": "", "status": "seeded"}
```

File wrapper: `{"book": "PSA", "pericopes": [...]}`. IDs are `<BOOK>-NNN`
(3-digit, 1-based); `range` is a canonical verse span (`BOOK.CH.V-V`, or
cross-chapter `BOOK.C1.V1-BOOK.C2.V2`).

---

## 2. Sections — LLM-proposed, validator-guaranteed, human-gated

A **section** is a *cross-pericope* grouping spanning one or more consecutive
pericopes (e.g. `MAT-S1` spans `MAT-001..MAT-006`). Sections carry the book-arc
/ "zoom-out" reflection content. There is no textual heading signal for these,
so they cannot be derived deterministically — they are **proposed**. (A section
may span a single pericope, which matters for `thread` items that need 2+
pericopes.)

- **Built by:** `content_bank/author/seed_sections.py`.
- **The pipeline** (`seed`):
  1. **Gather** — the book's pericopes in order, each grounded with a
     public-domain commentary snippet (JFB preferred, Matthew-Henry fallback;
     `_GROUNDING_WORKS = ("jfb", "mhc")`).
  2. **Prompt the LLM** to propose "as few, broad movements as the book's
     structure supports — roughly 2–12": a contiguous partition with every
     pericope in exactly one section, no gaps or overlaps, full coverage.
  3. **Validate** against `corpus/lib/sections.py` (contiguity + coverage). On
     failure it builds a **repair prompt** and retries up to `max_repair`
     (default 2); still-invalid raises.
  4. **Verify markers** — an optional `marker` (a canonical verse ref for a
     repeating textual formula, e.g. Matthew's "when Jesus had finished") must
     parse and fall inside the section span, else it is dropped to null and
     recorded in `dropped`.
  5. **Stage** the output to `work/section_seeds/<book>.json` and print an
     instruction to review, then manually copy into
     `corpus/canon/structure/sections/<book>.json`.
- **Not part of the deterministic corpus rebuild** — its committed output is
  treated as a *source*. The copy into canon is a **manual human step**.
- Backends: `claude` (Claude Code CLI, default) or `llm_core` (deepseek).
- **Stored at:** `corpus/canon/structure/sections/<book>.json`.

Record shape:

```json
{"id": "MAT-S1", "title_en": "Prologue: The Infancy", "title_zh": "",
 "first_pericope": "MAT-001", "last_pericope": "MAT-006", "marker": null}
```

IDs are `<BOOK>-S<n>`. A section is a *span* — `first_pericope`..`last_pericope`
(inclusive), not an explicit list. `marker` is an optional canonical verse ref,
else null.

---

## 3. The section-group

Because sections partition the book, **every pericope belongs to exactly one
section**. A **section-group** is a section plus the pericopes in its span
(e.g. `PHP-S2` + `PHP-002..PHP-006`).

The join happens in `content_bank/author/build_group.py` (`groups_for_book`) —
it loads the ordered pericope IDs and slices between the section's boundaries:

```python
i, j = ids.index(sec["first_pericope"]), ids.index(sec["last_pericope"])
out.append((sec["id"], ids[i:j + 1]))
```

The batched unit list puts the section first, then its pericopes
(`unit_ids_for_group`).

**Group build mode** (`build_cli --group`) uses this to batch all of a group's
units into **one LLM call per stage** (brief, draft, repair, review r1/r2,
revise), each returning a `{"units": {unit_id: payload}}` envelope split back
into per-unit artifacts. Motivation: the `claude`/Opus subscription backend
meters request count, so a group of N+1 units drops from ~4(N+1) calls to ~5.
Downstream gates/manifest/store stay per-unit and byte-identical. A
`stop_reason == max_tokens`, missing-unit, or unparseable envelope triggers
**bisection** — split and retry down to singletons.

---

## Trust-model summary

|                    | Pericopes                                    | Sections                                            |
| ------------------ | -------------------------------------------- | --------------------------------------------------- |
| Script             | `corpus/ingest/seed_pericopes.py`            | `content_bank/author/seed_sections.py`              |
| Source of truth    | USFM `\s` headings                           | LLM proposal + validator                            |
| Determinism        | Fully deterministic, rerunnable              | LLM-proposed, non-deterministic                     |
| In corpus rebuild? | Yes                                          | No — treated as a committed source                  |
| Human gate         | None (mechanical)                            | Staged to `work/section_seeds/`, manual copy to canon |
| Storage            | `corpus/canon/structure/pericopes/<book>.json` | `corpus/canon/structure/sections/<book>.json`     |
| ID form            | `<BOOK>-NNN`                                  | `<BOOK>-S<n>`                                        |
| Span model         | `range` (verse span)                         | `first_pericope`..`last_pericope` (+ optional `marker`) |

Both emit `status: "seeded"` and the same `{"book": ..., [layer]: [...]}`
wrapper, formatted `indent=1, ensure_ascii=False`.

> **Current gap:** `psa.json` exists for pericopes but not yet for sections —
> Psalms has base units but no book-arc partition seeded into canon yet.
