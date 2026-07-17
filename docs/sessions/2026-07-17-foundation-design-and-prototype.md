# Scripture Loom: foundation design docs and first working prototype

- **Date:** 2026-07-17
- **Branch / commits:** `main` — `737622b` (design docs + CLAUDE.md), `faa9f66` (kit generator design), `f07b01c` (active-reading principle), `1bc40aa` (governing conviction + Westminster guardrail), `0c3b89d` (sample kit), `86c25d0` (prototype), `6da2918` (.gitignore), `d503b39` (skill relocation)
- **Summary:** Took the repo from three loose design documents to a committed design foundation (principles, dimension model, kit-generator architecture), two rendered sample kits (English and Chinese), and a tested working prototype of the content-bank → selector → kit pipeline.

## Request

Starting from `/init`, the session evolved through the owner's successive design ideas: initialize CLAUDE.md; give an opinion on the founding docs and distill core principles; design the kit generator (fluency dimensions, static-vs-generated content); incorporate the active-reading insight; incorporate the spiritual dimension (leader's faith, confessional guardrail); produce sample kits; and finally build the pipeline for real.

## What we did

- **Initialized `CLAUDE.md`** for a pre-code repo: captured the three-phase constraint (prepare/gather/reflect), design invariants, privacy rules, and mainland-China locale assumptions instead of build commands that don't exist.
- **Recorded the owner's decision that audio transcription is low priority** — the unplugged paper workflow must stand alone. Saved to CLAUDE.md and persistent memory.
- **Distilled `docs/core_principles.md`** from the three founding docs; it wins where documents disagree. Identified "designed evidence moments" as the load-bearing product insight.
- **Designed the kit generator** (`docs/design-kit_generator.md`): froze eight fluency dimensions (D1–D8) as the product's stable schema, each a full profile. Key decision, proposed by the owner and confirmed: **content is static like a book (human-reviewed library, pericope × dimension × age tier); personalization is selection/scheduling, never generation at session time** — the Anki model. Six in-session evidence codes (Q A R C U P) stay separate from the eight dimensions; mapping happens at reflect time.
- **Added the active-reading principle** (owner's insight: social media trains passive scroll-mode; fluency requires active reading): pre-reading quests, the read-twice moment, a four-stage activation scaffold that fades as a member's *unprompted* questions appear, and a `prompted` flag on evidence. The prompted→unprompted ratio is the per-member success metric.
- **Added the governing conviction** (owner's insight: worship, not academy): the app trains fluency, only the Spirit gives revelation, the leader's faith is the unautomatable factor. Two consequences: heart preparation physically precedes logistics in the leader guide, and all content is anchored to the Westminster Confession (esp. ch. 1) as a fixed guardrail at both AI-drafting and human-review stages. Noted that WCF 1.9 ("Scripture interprets Scripture") is dimension D5 stated confessionally.
- **Produced sample kits for Matthew 5:1–12**: a markdown spec example (`docs/sample-kit-matthew_5_1-12.md`), an English HTML artifact (rubric-red liturgical treatment, print CSS), and a Chinese version (和合本 text, 正-character tallies, hanzi evidence codes 问答忆连疑行, CUV names 亚居拉/百基拉 + children 恩恩/立立). The Chinese version surfaced a design finding: quests sometimes need per-language re-authoring, not translation, because they point at features of the translation's text (「有福了」 falls at clause end).
- **Clarified honestly that the samples were hand-authored mockups** — no bank or selector existed — then built them for real.
- **Built the prototype** (`prototype/`, stdlib Python, tests first): `content_bank.json` (three Matthew pericopes, design-doc schema, one draft item to prove the published-only gate), `family.json` (evidence history), `selector.py` (deterministic: spaced review from weak dimensions, observation targets from weakness+staleness, activation-stage quest scaling), `generate_kit.py` (markdown composer). 17 tests pass, including the acceptance test: changing the member record changes the generated kit.
- Housekeeping: `.gitignore` for `__pycache__`; moved a user-placed `export-session` skill from `docs/.claude/` to `.claude/`.

## Artifacts

- `CLAUDE.md` — repo guidance incl. transcription deprioritization and Westminster guardrail
- `docs/core_principles.md` — governing conviction + 7 principles + methods + MVP orientation
- `docs/design-kit_generator.md` — D1–D8 dimension model; bank/selector/composer architecture; theological guardrail
- `docs/sample-kit-matthew_5_1-12.md` — worked four-page kit example with design notes
- HTML artifacts (claude.ai): English kit `d921018f-7d4c-47d6-a7c1-ec824979558e`, Chinese kit `d1569c0d-4c84-4b1f-8600-d9a9042c09b2`
- `prototype/` — `content_bank.json`, `family.json`, `selector.py`, `generate_kit.py`, `test_selector.py` (17 tests), `sample_output.md`, `README.md`
- Persistent memory: `transcription-low-priority.md`

## Outcome

All work committed on `main`, working tree clean. Tests: 17/17 passing (`python3 -m unittest test_selector -v` in `prototype/`). The design docs and the prototype agree — the schemas from the design doc were implemented without modification. The generated kit demonstrably responds to member-record changes (Grace's quest slip fades from category-mode to "write your own" as unprompted questions accumulate).

## Follow-ups

- Open questions in `design-kit_generator.md`: starting book for the library, age-tier boundaries, bilingual authoring strategy (per-language re-authoring finding from the Chinese kit should feed this), notebook-page interaction with the kit.
- Prototype's deliberate gaps: reflect-phase capture (marks/photos → EvidenceItem), `used_item_ids` persistence, real content bank beyond three pericopes, print layout integration.
- Kit-composer layout concern from the sample: observation sheet + exit card + quest slip may be too much paper per member; consider merging.
