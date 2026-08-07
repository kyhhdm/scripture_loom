# Citation Tags Foundation — design, build, verify, ship

- **Date:** 2026-07-23 – 2026-07-28
- **Branch / commits:** `feature/citation-tags-foundation` (base `main`) → **PR #25 MERGED** (merge commit `1a0fcd1`). Key commits: `4d4fbc5` spec, `bf82b5a` plan, `d550c14`/`6200546`/`ed6032f`/`5afc76c`/`162e31f`/`f9a8480` (tasks 1–6), `50fd839` section-tagging fix, `409122e`/`a52cbcd` review-page highlighting, `04d1b62` nested ZH form + ZH recall net, `3fec007` shortest-CUV-span fix, `cacea12` docs.
- **Summary:** Designed and built a foundation where the authoring LLM **declares** Scripture/doctrine citations as inline `<verse>`/`<doctrine>` tags and a deterministic gate **verifies** them; then verified it against live generation + translation, fixed the real problems that surfaced, documented it, and merged.

## Request

Continued from a compacted session that had just approved (via "go ahead") writing the citation-tags foundation spec. The session then ran the full brainstorm → spec → plan → subagent-driven build, followed by a series of user-driven requests: run an end-to-end verification, compare runs side by side, make the review pages distinguish tagged text, translate tagged drafts, diagnose a bad translation, capture the effective config in the docs, and finally finish + merge the branch.

## What we did

- **Design + plan (brainstorming → writing-plans).** Locked two recommendations: distinct `<verse>`/`<doctrine>` elements (different verification semantics), and `<doctrine>` authored in English and carried through translation. Wrote the spec (`docs/superpowers/specs/2026-07-23-citation-tags-foundation-design.md`) and a 6-task TDD plan, verifying corpus facts (ref grammar, `CUV`/`BSB` version strings, canon-lamppost shapes) so the plan carried exact code.
- **Built it (subagent-driven-development).** Six tasks, each a fresh implementer + independent spec/quality review: (1) `citation_tags` parser/stripper, (2) `standards` resolver, (3) `citation_check` two-mode gate wired into `run_all`, (4) ZH translation gate, (5) prompt tagging instructions, (6) strip-at-render. One real regression caught in review (a tagging block tripped a pre-existing prompt-size budget) and fixed. Final whole-branch review (opus) empirically confirmed backward compatibility against all three real stores — the `untagged_quote` hits were all true positives, not noise.
- **End-to-end verification.** Ran a live claude/opus generation over PHP-001/002/003 + PHP-S1/S2. PHP-S2 hard-failed — the **section prompt enforced the citation gate without instructing tagging**, so quote-dense threads came out untagged. Fixed the section prompt + added a tag-aware repair hint (`50fd839`); re-ran → all green.
- **Review-page usability.** The comparison pages *stripped* tags, so a reviewer couldn't see citations. Made both the English (`compare_html`, client-side JS) and Chinese (`translate_compare_html`, server-side via a new `citation_tags.highlight_html`) review instruments **highlight** tags (green verse + ref, amber doctrine), while the family-facing kit still strips.
- **The two-marker finding (user-spotted).** In Chinese, dropped `<verse>` tags left correct `「」` CUV brackets — the tag and the brackets were competing. Decided (via AskUserQuestion) to **nest both** and **enforce**: ZH Scripture is `<verse ref>「…CUV…」</verse>`; `citation_check` now ignores `「」` when verifying, and a **ZH recall net** flags a bare verbatim-CUV `「…」` outside a tag. Tag preservation across a flash re-translation jumped **2 → 14**.
- **The fluency regression (user-spotted).** The nested prompt had licensed widening a quote to "the whole verse"; the cheap model took it and produced broken prose that the gate still passed (a whole verse is trivially verbatim). Fixed the prompt to demand the shortest apt CUV span (`3fec007`); re-translation restored fluent short quotes with tags intact. Surfaced the general lesson: **the gate guarantees citation correctness, not fluency** — highlighted review + human review remain the backstop.
- **Docs + merge.** Wrote the recommended config (Opus for EN generation, deepseek-v4-flash for ZH translation, tags on) into `content_builder_usage.md`, created `content_translator_usage.md`, and updated the terminology glossary. Pushed, updated the PR body (via REST API — `gh pr edit` kept aborting on a GitHub Projects-classic GraphQL deprecation), and **merged PR #25** with a merge commit; branch deleted.

## Artifacts

- **New code:** `content_bank/lib/citation_tags.py` (parser, `strip_tags`, `highlight_html`), `content_bank/lib/standards.py`, `gates.citation_check` + `_untagged_zh_quote_flags`.
- **Modified:** `gates.py` (`_norm` strips `「」`; `run_all`), `translate.py` (zh gate + repair hint), `build_draft_prompt.py`, `build_section_draft_prompt.py`, `build_translate_prompt.py` (tagging + nested form + shortest-span), `compare_html.py` + `translate_compare_html.py` (highlighting), `prototype_bank.py` (strip on render).
- **Docs:** `docs/superpowers/specs/2026-07-23-citation-tags-foundation-design.md`, `docs/superpowers/plans/2026-07-23-citation-tags-foundation.md`, `docs/content_builder_usage.md`, `docs/content_translator_usage.md` (new), `docs/content_build_terminology.md`, `CLAUDE.md`.
- **Verification artifacts (untracked, local):** `work/content_bank_build_tagtest/` — tagged draft run, three translation runs (v1/v2/v3), and the highlighted comparison pages.
- **Memory:** `citation-tags-foundation.md` written to the auto-memory index.

## Outcome

PR #25 **merged to `main`** (`1a0fcd1`). Suites green on merged main: content_bank **300**, corpus **67**, prototype **34**. The feature is live: LLM-declared citations, deterministically verified in both languages, highlighted for reviewers, stripped for families. Validated by live generation + translation runs, not only unit tests.

## Follow-ups

- Three follow-on specs ride on this foundation: content-type style rules (both languages), the blind ZH fluency-editor pass, and editor-facing glossary explanations.
- Known migration edge: a full rebuild of existing PHP/ECC through `run_all` will hard-fail legacy items that carry genuine untagged verbatim quotes until they are re-tagged (documented in the spec).
- Cheap-model translation (`deepseek-v4-flash`) still drops/mis-tags some citations; these are gate-flagged for review rather than silent. A stronger translator would flag fewer.
