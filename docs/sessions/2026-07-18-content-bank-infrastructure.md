# Building the Scripture Loom content bank (infrastructure layer)

- **Date:** 2026-07-18
- **Branch / commits:** `content-bank-infra` (12 commits, `710fe49`..`e6c6491`), branched from `main` at `13552e5`; pushed to `origin` and opened as **PR #1** (https://github.com/kyhhdm/scripture_loom/pull/1).
- **Summary:** Designed and built the *infrastructure* for Scripture Loom's content bank — the static, human-reviewed study-content library that sits above the corpus and feeds the kit generator. Shipped complete: gated bilingual store, validation, an offline authoring harness, prototype migration + rewire; content_bank 48 tests + prototype 17 + corpus 63 all green; whole-branch review verdict "ready to merge."

## Request

The user opened by asking what the corpus is, then said "let's start a new task to build the content bank." Through brainstorming this was scoped to the **infrastructure** (the machinery), not authoring a book's worth of content — with the explicit follow-on that content authoring at scale is a later cycle. The session ended with an explanation of how the authoring harness generates content and a session export.

## What we did

Ran the full superpowers flow: brainstorming → writing the spec → writing the plan → subagent-driven execution → final review → finishing the branch.

**Design decisions settled during brainstorming (all binding):**

- **Infrastructure first** — deliver the machinery plus small seed content, not authored content at scale.
- **Prompt-harness, no live API** — the repo assembles a per-pericope prompt pack; a human/Claude runs it out-of-band and pastes back draft JSON, which the tooling validates. Preserves the corpus's stdlib-only/offline invariant and keeps unreviewed theological content out of the tree.
- **New top-level `content_bank/`** — a sibling of `corpus/` and `prototype/`; it consumes the corpus as a dependency and never duplicates corpus-owned data (pericope boundaries, book names).
- **One JSON file per book** — `content_bank/store/mat.json` (review is logically per-pericope even though storage is per-book).
- **Migrate + rewire the prototype** — seed the store from the prototype's 3 pericopes' items, re-keyed to corpus pericope IDs, and repoint the prototype's loader; this also completed the design's deferred "migrate string pericope keys to stable IDs" follow-up.
- **Full bilingual now**, with the **one-item / `text:{en,zh}`** model — one logical item owns one id; only language-specific strings vary; one id in the member record regardless of render language.
- **Enforcement model "Approach A"** — the *gate* is mechanical (product mode serves published-only, the license-gate analog); the Westminster *guardrail* is assembled by the machine into every draft prompt and its review is *recorded* as a publish precondition, but conformity is *judged by a human*, never linted by keyword heuristics. The software proves an item was reviewed, not that it is doctrinally sound.

**A concrete boundary reconciliation surfaced during planning:** the prototype's "Matthew 5:1–12 (Beatitudes)" is not a single corpus pericope — the corpus splits it into `MAT-013` (5:1–2 setup) and `MAT-014` (5:3–12 proper). The two "crowds/mountain" setup items were mapped to `MAT-013`; the rest to `MAT-014`. `MAT-013` was deliberately kept out of the sample family's reading sequence so the prototype's linear 3-passage demo (MAT-009 → MAT-014 → MAT-015) is preserved.

**Execution** followed the subagent-driven-development loop: a fresh implementer subagent per task (cheap model for complete-code transcription, standard model for integration/content tasks), a spec+quality task review after each, and a final whole-branch opus review. Progress tracked in `.superpowers/sdd/progress.md` (the stale corpus-build ledger was reset to this plan's scope first).

**Two plan bugs caught and fixed mid-flight:**

- A **tautological test** in the plan (Task 3's WCF assertion passed regardless of content) — fixed in the plan before dispatch (pre-flight scan).
- A **store-filename inconsistency**: `load_book_store` derives the filename via `book.lower()` → `mat.json`, but the plan named the file `matthew.json`. The Task 2 implementer surfaced it; the plan was corrected to `mat.json` throughout (also fixing Task 4's latent fixture bug).

**Final whole-branch review** (opus) returned **ready to merge**, no Critical/Important. Two of its five Minor findings were applied immediately (guarding the `sys.path` insert in `corpus_bridge.passage_text`; a test enforcing the dimension single-source `set(dimensions.TEMPLATES) == schema.DIMENSIONS`); three were deferred.

The session closed with a walkthrough of how content is generated: `build_draft_prompt.py` compiles a pack (passage text + WCF ch.1 guardrail + D1–D8 menu + schema) → a human runs it through Claude → `validate.py` gates structure → `review_checklist.py` gates substance → provenance is stamped and `review_status` set to `published`; only then does `get_content(mode="product")` serve it.

## Artifacts

- **Design/spec/plan:** `docs/superpowers/specs/2026-07-18-content-bank-design.md`, `docs/superpowers/plans/2026-07-18-content-bank-infra.md`
- **Library:** `content_bank/lib/{schema,content,corpus_bridge,validate,prototype_bank}.py`
- **Authoring harness:** `content_bank/author/{dimensions,build_draft_prompt,review_checklist}.py`
- **Store + provenance:** `content_bank/store/mat.json` (25 migrated items, corpus-keyed, bilingual-capable), `content_bank/PROVENANCE.md`
- **Tests:** `content_bank/tests/` (7 files, 48 tests)
- **Docs:** `content_bank/README.md`
- **Prototype rewire:** `prototype/{generate_kit,test_selector,family,sample_output}` modified; `prototype/content_bank.json` deleted; `prototype/selector.py` untouched
- **PR:** #1 (`content-bank-infra` → `main`)

## Outcome

- All 8 plan tasks complete; every task review and the final whole-branch review resolved.
- Suites: **content_bank 48**, **prototype 17** (rewired), **corpus 63** (no regression) — all passing.
- Content gate verified end-to-end: `get_content(mode="product")` serves only `published`; the single draft item is provably excluded; the publish invariant fails validation for a `published` item lacking `WCF-1` review provenance.
- Layering verified: all corpus access routed through `corpus_bridge`; vocabularies single-sourced in `schema.py`.
- Branch pushed; PR #1 open (worktree/branch preserved for PR iteration).

## Follow-ups

- **Deferred Minor items** (recorded in the SDD ledger): `display_ref` robustness for hypothetical cross-chapter pericope ranges (none exist in the corpus today); caching `corpus_bridge._load` (negligible now, worth it as more books are added).
- **Bilingual review gap:** the draft pack requests `text:{en,zh}` but `review_checklist.py` is English-centric — a distinct Chinese-conformity review step is a natural addition for the authoring cycle.
- **The natural next cycle:** authoring a real book's worth of content on top of this infrastructure (its own brainstorm → spec → plan → build), driving `build_draft_prompt.py` over a Gospel's pericopes.
- **Untracked pre-existing files** noted during the PR push (`docs/bible_licenses.md`, `docs/chinese_resource_licenses.md`, prior corpus-session docs, a stray `.swp`) predate this work and were left untouched.
