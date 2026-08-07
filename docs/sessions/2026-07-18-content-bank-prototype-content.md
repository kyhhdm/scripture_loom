# Generating and quality-tuning the prototype content bank

- **Date:** 2026-07-18 (spanned into 2026-07-19)
- **Branch / commits:** `content-bank-infra` (this cycle's work, ~22 commits `186337e`..`6864e59`) merged to `main` via **PR #1** (merge commit `98c7103`), then the branch deleted. Follow-up design recorded on `docs/heart-prep-gate-followup` (`39574ac`). Two GitHub issues opened: **#2** (content) and **#3** (gate).
- **Summary:** Built a two-stage, corpus-grounded authoring harness and used it to generate, adversarially review, and publish **62 leader-facing study items** across four Matthew pericopes for the kit-generator prototype — with the review loop tuning the authoring machinery. Then designed (and filed issues for) the next increment: leader references behind a heart-prep gate.

## Request

"Check the quality of content generated, and tune the quality. With corpus and content infrastructure ready, generate content bank for prototype first." Later in the session: add answers/notes to items for the leader, decide how a leader accesses them (a heart-prep gate), and file the work as issues.

## What we did

Ran the full superpowers flow: brainstorming → spec → plan → subagent-driven execution → finish → merge.

**Design decisions settled in brainstorming (all binding for the cycle):**
- **Content is the test case; tuning the machinery is the durable outcome.** Regenerate all four prototype pericopes (replace the 25 hand-migrated seed items). Adversarial reviewer agents are the quality signal. English-only.
- **MAT-013 joined the reading sequence** (`009 → 013 → 014 → 015`) so the Beatitudes' "crowds/mountain" People-&-Places setup has an answerable home in its own pericope.
- **`reviewed` → confirmation digest → `published`** — a human gate honors "AI proposes, the leader confirms."

**A pivotal mid-brainstorm question — "how are corpus assets used?"** — surfaced that the drafting pack only used Bible text + WCF ch.1; commentary, cross-references, and the catechisms were unused, and there is no lexicon. This drove the **two-stage, passage-first design** (the key architectural decision), because the lampposts for the Beatitudes run ~80× the passage length:
- **Stage 1 (brief):** `build_brief_prompt.py` distils passage + full WCF-1 + JFB/MHC commentary + cross-references + WCF/WLC/WSC statements (selected by **proof-text reverse-lookup**) into a compact (~250-word), fidelity-reviewed, committed **theological brief**.
- **Stage 2 (items):** `build_draft_prompt.py` drafts from a passage-first pack (foregrounded passage + brief + compact WCF-1), never the raw lampposts.
- A concrete **proof-text safeguard** was validated on the Beatitudes: WLC Q172 (a Lord's-Supper Q&A) cites 5:3-4, so the brief uses only its reading of the poor/mourning heart and sets the sacramentology aside as off-agenda.

**Execution** was subagent-driven (14 tasks): implementer subagents for the code/TDD tasks (rubric, corpus_bridge accessors, brief/draft packs, checklist, dimensions), and the controller directly orchestrated the per-pericope generation (drafter subagent + ≥2 parallel adversarial reviewers) since those require dispatching reviewer agents.

**The quality loop did real work.** Adversarial review caught genuine defects, each triaged into an item fix or a **machinery** fix so it wouldn't recur:
- A **verse-ordering bug** in `corpus_bridge.passage_text` (string order: 4.1, 4.10, 4.11, 4.2…) that misled the drafter about who led Jesus to the wilderness → fixed to canonical order + regression test.
- Two doctrinal drifts — a Christological overstatement (Temptation) and WCF 19.6 mis-attached with its covenant-of-works qualifier dropped (Beatitudes, a works-righteousness risk) → item fixes + brief-builder guards ("preserve the commentary's nuance"; "cite confessional statements faithfully").
- `pre_reading_quest` dimension mismatches, an out-of-scope `vocab_list` item, and self-display framing in application items (good deeds without v.16's God-glory purpose) → item + machinery fixes.

The store was assembled (62 items), the human approved publishing, and the prototype family fixture + selector acceptance tests were re-coordinated to the new content without weakening their intent. Final whole-branch review returned **merge-ready**; two Minor findings (a duplicated PROVENANCE line; a test class below the `__main__` guard) and a stray committed vim swap file were fixed. Merged to `main`.

**After the cycle**, we discussed adding leader-facing answers/notes. This evolved through dialogue into: **typed references** (answer keys for closed items, keep-open notes for open ones), then a **heart-prep gate** on *access* — never printed, unlocked only after (1) read-as-hearer + pray (a conviction, default-on) and (2) attempting each selected question with a light phrase; verifies attempt, not correctness; before or after the gathering, never during. Recognizing content and access are **orthogonal**, we filed them as separate issues.

## Artifacts

- **Spec / plan:** `docs/superpowers/specs/2026-07-18-content-bank-prototype-content-design.md`, `docs/superpowers/plans/2026-07-18-content-bank-prototype-content.md`.
- **Authoring harness:** `content_bank/author/{rubric,dimensions,review_checklist,build_brief_prompt,build_draft_prompt}.py`.
- **Corpus access:** `content_bank/lib/corpus_bridge.py` — new `commentary()`, `crossrefs()`, `confessional_refs()`; `passage_text` verse-ordering fix.
- **Content:** `content_bank/store/mat.json` (62 published items); four briefs `content_bank/author/briefs/mat-009,013,014,015.md`; `content_bank/PROVENANCE.md`.
- **Quality writeup + review aid:** `docs/superpowers/notes/2026-07-18-content-tuning-log.md`, `docs/superpowers/notes/2026-07-18-mat-content-review.md`.
- **Prototype:** `prototype/family.json` (reading sequence + fixture), `prototype/test_selector.py`; `selector.py` untouched.
- **Follow-up design:** heart-prep-gate section in the spec, on branch `docs/heart-prep-gate-followup`.
- **Issues:** [#2](https://github.com/kyhhdm/scripture_loom/issues/2) (leader references — content), [#3](https://github.com/kyhhdm/scripture_loom/issues/3) (heart-prep gate — access).

## Outcome

- **Merged to `main`** (PR #1). All three suites green (content_bank, prototype, corpus); the Beatitudes demo kit generates end-to-end from the new content.
- 62 items, all `review_status: published`, provenance complete (drafted_by claude, reviewed_by claude-adversarial, confirmed_by kyhhdm, brief path).
- `content-bank-infra` branch deleted (merged).

## Follow-ups

- **Issue #2** — build the typed leader references (buildable now on content_bank + prototype).
- **Issue #3** — the heart-prep gate; a Prepare-phase product-flow feature needing an interactive layer the repo doesn't have yet (prototype is a non-interactive CLI); depends on #2.
- `docs/heart-prep-gate-followup` branch is pushed but not merged — fold into #2/#3's own spec or merge to `main`.
- Deferred from the content cycle: Chinese (`zh`) text + a distinct zh-conformity review; a corpus lexicon for D3 vocabulary.
