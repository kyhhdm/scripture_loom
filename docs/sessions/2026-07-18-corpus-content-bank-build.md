# Building the Scripture Loom corpus (content-bank source layer)

- **Date:** 2026-07-18
- **Branch / commits:** `main`, `cf99dfe` (design spec) → `13552e5` (CLAUDE.md update); pushed to `origin/main` (`78edd96..13552e5`). ~19 commits from the design spec through the finished build.
- **Summary:** Designed and built the corpus layer beneath Scripture Loom's content bank — public-domain Bibles, reference structure, and Westminster/commentary "lamppost" documents normalized into a diff-able JSON canon store with a license gate as the single read path. Shipped complete: 63 tests green, Python-3-stdlib-only, reproducible from committed sources.

## Request

Design how to build the content bank: (1) acquire "lamppost documents" (Bible, confession, catechism, optional commentary) that shape content but are never shown directly; (2) organize Bible text by books, pericopes, and cross-references, in multiple versions (English: ESV, NKJV, KJV, NIV, NLT; Chinese: CUV 和合本, CNV 新译本); (3) decide how to get, store, and organize these assets. Then write the spec, write the plan, and execute it via subagent-driven development. Finally, export the session.

## What we did

The design phase (in an earlier, compacted portion of the session) settled four binding decisions:

- **Hybrid licensing.** Only public-domain / openly-licensed texts are stored and committed. Copyrighted translations (ESV/NKJV/NIV/NLT/CNV) live in a git-ignored `sources/private/` now and behind a licensed API adapter later — never committed, never shipped. This is why the stored English layer is KJV/WEB/BSB and the stored Chinese layer is CUV only.
- **Seed pericopes, then canonicalize.** Pericope boundaries are seeded from open-dataset section markers, then editorially adjusted during content authoring; stable opaque IDs (`MAT-001`) with the verse range as mutable data.
- **Matthew Henry as the devotional voice + JFB for facts** — both public domain, both lampposts.
- **Normalized JSON as the canonical store** — diff-able, stdlib-only, consistent with the existing prototype.

Execution followed the superpowers subagent-driven-development loop: a fresh implementer subagent per task, a task reviewer per task, fix subagents for review findings, then a final whole-branch review. The progress ledger (`.superpowers/sdd/progress.md`) tracked each task's commits and findings across a context compaction.

Ten tasks: (1) scaffold + 66-book table, (2) canonical ref parsing, (3) fetch open Bible sources, (4) USFM parser, (5) Bible ingestion with auto-derived versification exceptions, (6) Matthew pericope seeding, (7) OpenBible cross-references, (8) Westminster standards, (9) MHC + JFB commentaries, (10) passage adapter + license gate + README.

**Where review caught real defects that passed their own tests:**

- **Task 9 (opus review) — 77 JFB commentary blocks silently mis-anchored.** All of Psalms 70–144 and 2 Samuel 22–23 were served under the wrong scripture reference (e.g. Psalm 121's commentary shipped under `PSA.119`). Root cause: the upstream HelloAO source mis-numbers prose-only chapters, and the original code only recognized the handful of books the implementer hand-inspected, then *trusted the bad source number* by default. Fix: flip the default to drop-when-unconfirmed, add a generic 66-book self-citation resolver, and backfill.
- **Task 9 — MHC missing 23 chapters** including all of Matthew 19–28 (the Passion/Resurrection), because coverage was only checked at the file/book level. Fix: backfill from CCEL ThML and add chapter-level coverage tests against KJV with a `KNOWN_ABSENT` allowlist.
- **Task 10 — path-traversal in the private-file loader** (`version` interpolated into a path unvalidated; in personal mode an arbitrary-file read). Fixed with a regex guard + regression test.
- **Final whole-branch review — latent `CC-BY` token mismatch.** The gate allowed `"CC-BY"` but crossrefs wrote `"CC-BY (openbible.info)"`, so the gate could never match its own displayable asset. Fixed by making `license` a controlled vocabulary (bare token + `license_note`). Also: extracted the duplicated OSIS book-code map to `corpus/lib/osis.py`, and pinned the "dropped by design" counts so a parser regression can't silently drop more refs.

Non-obvious empirical findings recorded in `corpus/PROVENANCE.md`: WEB's `engwebp` Matthew has zero `\s` section headings, so BSB was chosen as the pericope seed source; `refs.parse_range` is same-book-only, so cross-book and whole-chapter cross-reference/proof-text cites are dropped by design (counted and documented).

## Artifacts

- **Design/spec/plan:** `docs/superpowers/specs/2026-07-17-corpus-assets-design.md`, `docs/superpowers/plans/2026-07-17-corpus-assets.md`
- **Library:** `corpus/lib/{books,refs,usfm,passage,osis}.py`
- **Ingest scripts:** `corpus/ingest/{fetch,build_books,ingest_bible,seed_pericopes,ingest_crossrefs,ingest_westminster,ingest_commentary,fetch_commentary_sources}.py`
- **Canon store:** `corpus/canon/bibles/{kjv,web,cuv-simp,bsb}.json`; `corpus/canon/structure/{books.json,pericopes/mat.json,crossrefs.json}`; `corpus/canon/lampposts/{wcf,wsc,wlc}.json` and `mhc/`, `jfb/` (66 books each)
- **Committed sources + provenance:** `corpus/sources/` (public-domain only), `corpus/PROVENANCE.md`, `corpus/README.md`
- **Tests:** `corpus/tests/` (10 files, 63 tests)
- **Docs:** `CLAUDE.md` "Repository state" updated to describe the corpus and its commands.

## Outcome

- All 10 tasks complete; every task review and the final whole-branch review resolved.
- Full suite: **63 tests, all passing.** Canon rebuilds deterministically from committed sources (no network at ingest time).
- License gate verified airtight: `sources/private/` git-ignored, private versions personal-mode-only and never displayable, path traversal closed, all committed canon licenses are bare gate-valid tokens.
- Pushed to `origin/main`.

## Follow-ups

- **Documented, test-guarded content gaps** (secondary "facts" lamppost, fillable later by re-ingesting a cleaner edition with zero consumer changes): MHC lacks Jonah 2–4; JFB lacks 2 Samuel 22, Matthew 24/26, Mark 3/5/15, several Psalms, and parts of Song of Solomon.
- **Deferred by design:** TSK public-domain cross-reference base layer (the `sources` field keeps the merge path open); the `api` passage provider (stub only); traditional-script CUV; Chinese commentary lampposts; SQLite as a possible future derived build artifact.
- **Accumulated minor notes** for a future pass (in the ledger): CCEL-sourced MHC blocks embed inline KJV verse text while HelloAO blocks are commentary-only; `LicenseError` doesn't distinguish cause; `books.load()` isn't cached.
- **Not done (per spec §8):** migrating the prototype's string pericope keys to the new stable pericope IDs — happens when the prototype next changes.
