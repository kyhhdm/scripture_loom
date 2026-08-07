# Evaluating issue #36 (multi-unit draft packing) against measured evidence

- **Date:** 2026-07-31
- **Branch / commits:** `feature/gemini-quality-evaluator` (no commits — analysis + one GitHub issue comment)
- **Summary:** Assessed whether issue #36 (pack multiple content units into one `claude -p` drafting call) is a good idea. Measured the shared-preamble size and investigated how the subscription quota is metered; found the cost/quota motivation weak because the quota is usage-metered, not invocation-count-metered. Summarized the findings as a comment on #36.

## Request
The user asked, in sequence: (1) read issue #36 and judge whether it's a good idea; (2) check whether the shared draft preamble is large relative to per-unit inputs; (3) find evidence for whether the subscription quota depends on `claude -p` invocation count; (4) post a comment on #36 summarizing all findings.

## What we did
- **Read #36 via the API** (`gh issue view` failed on the classic-projects GraphQL deprecation, so used `gh api repos/{owner}/{repo}/issues/36`). The issue proposes bounded, per-unit-isolated packing for draft generation: strict unit-ID envelope, per-unit gate/repair/persist, deterministic fallback to `pack_size: 1`, default `1`, evaluation-gated via #35.
- **Initial assessment:** the engineering design is sound and defensive (failure isolation, fallback, opt-in default, invariants preserved), but the *premise* deserved scrutiny. Flagged that #36 is unmeasurable until #35 (experiment framework) lands, and that the benefit hinges on whether the bottleneck is invocation count or tokens.
- **Measured shared vs. per-unit prompt sizes** on real PHP-001 artifacts (`build_draft_prompt.build`, `store/php.json` as the output proxy):
  - Shared preamble ~8,000 chars / ~2,000 tok (2.2× the per-unit input) — large in isolation.
  - Per-unit input ~3,600 chars / ~900 tok; per-unit output ~16,500 chars / ~4,100 tok (unchanged by packing).
  - Total-token saving from packing: ~14% (N=2), ~21% (N=4); usage-weighted (Opus output ~5× input): ~4–6%.
- **Investigated quota metering.** `content_bank/author/llm.py` shells out to `claude -p` against the logged-in subscription. The decisive evidence was the prior session doc `docs/sessions/2026-07-30-opus-rebuild-ecc-php-jon.md`: Opus builds at `--concurrency 4` ran JON (8) and PHP (14) cleanly, but ECC (24, the largest) failed 17/24 in a burst; lowering concurrency and waiting for the window to recover fixed it. Three signatures (bit on cumulative volume at the tail, recovers on a clock, fixed by lowering concurrency not call count) show a **rolling usage window metered by token/usage (Opus-weighted)**, not a per-invocation counter.
- **Conclusion:** packing optimizes the invocation-count axis the quota does not charge for; saves only ~6% usage-weighted; and does not reduce burstiness (it enlarges per-call output). The real failure mode — bursting into the rolling window — is already handled by the `--concurrency` throttle (PR #33). This confirms #36's own listed non-goal ("fewer calls ≠ proportionally lower token-metered usage").
- **Posted the summary** as a comment on #36.

## Artifacts
- GitHub comment on issue #36: https://github.com/kyhhdm/scripture_loom/issues/36#issuecomment-5139068155
- Scratchpad: `.../scratchpad/issue36_comment.md` (comment body).
- No code changes; no commits.
- Files inspected: `content_bank/author/build_draft_prompt.py`, `content_bank/author/llm.py`, `content_bank/author/build_cli.py`, `content_bank/store/php.json`, `docs/sessions/2026-07-30-opus-rebuild-ecc-php-jon.md`.

## Outcome
- Delivered a grounded verdict: #36's engineering design is sound, but its cost/quota motivation is weak because the subscription is usage-metered, not call-metered. Recommended #35 precede #36 and that the default never move off `pack_size: 1` without quality parity. Decision captured on the issue.

## Follow-ups
- Optional: fold the empirical concurrency guidance (keep `--concurrency ≤2` for whole-book Opus runs) into `docs/content_builder_usage.md` — a pending follow-up already noted in the 2026-07-30 session doc.
- #35 (named experiments framework) remains the prerequisite for any measurable #36 evaluation.
