---
name: export-session
description: Use when the user asks to export, save, archive, or write up the current session/conversation as a durable file in the repo — e.g. "export this session", "save this conversation to docs", "write up what we did today".
---

# Export Session

## Overview

Export the current session as **two paired files** in `docs/sessions/`, sharing one
`<slug>` that represents the **whole** session:

1. **Summary** — `YYYY-MM-DD-<slug>.md` — a structured, readable write-up you compose
   from the conversation.
2. **Transcript** — `YYYY-MM-DD-<slug>-transcript.md` — the verbatim conversation,
   rendered from Claude Code's on-disk session log by `scripts/render_transcript.py`.

The transcript is generated from the JSONL Claude Code writes as the conversation
happens, so it is a true verbatim record (more reliable than reconstructing from
context, and it survives compaction). The built-in `/export` command is a manual
alternative, but this skill does not depend on it — a skill cannot invoke `/export`.

## The output contract

Produce exactly two files, same directory, same `<slug>`:

- **Directory:** `docs/sessions/` (create it if missing).
- **Summary file:** `YYYY-MM-DD-<slug>.md`
- **Transcript file:** `YYYY-MM-DD-<slug>-transcript.md`
- `YYYY-MM-DD` = the current date (today). If you can tell from context that the
  session clearly began on an earlier day, use that start date instead.
- `<slug>` = kebab-case, 2–5 words, naming the session's **overarching theme or
  outcome**, not just the last thing worked on. If the session covered several
  threads, name it for the dominant one, or use an umbrella term that covers them.

Representative-name examples:

| Session | ✅ Good slug | ❌ Weak slug |
|---|---|---|
| Designed + built two HS courses, wrote an alignment report | `shormann-hs-math-courses` | `fix-tests` (last step only) |
| Debugged a flaky CI job, then documented the fix | `flaky-ci-timeout-fix` | `session-2` (meaningless) |
| Several unrelated small fixes | `misc-cleanup-and-fixes` | `dark-mode` (one thread of many) |

## File structure

Fill this skeleton. Keep each section proportional to what actually happened. If a
section genuinely has no content, remove its heading entirely — do not keep the
heading with a "none" placeholder under it. (`Follow-ups` is the usual candidate.)

```markdown
# <Human-readable session title>

- **Date:** YYYY-MM-DD
- **Branch / commits:** <branch, key commit SHAs, PR numbers — if any>
- **Summary:** <one or two sentences: what the session set out to do and the result>

## Request
<what the user asked for, in your words>

## What we did
<the key steps, decisions, and turning points — chronological, bulleted or short prose.
Include the WHY behind non-obvious choices, not just the what.>

## Artifacts
<files created/changed, commits, PRs, docs — with paths. Be specific and verifiable.>

## Outcome
<end state: what works, test results, what shipped/merged>

## Follow-ups
<open items, known gaps, deferred work — omit if none>
```

## Steps

1. Pick the date and a representative `<slug>` per the contract above.
2. Create `docs/sessions/` if it does not exist.
3. Write the **summary** file, filling the skeleton faithfully from the conversation.
   Reflect what actually happened; do not invent details, and mark anything uncertain
   as uncertain rather than guessing.
4. Generate the **transcript** file by running the renderer (it resolves the current
   session from `$CLAUDE_CODE_SESSION_ID` automatically):

   ```bash
   python3 .claude/skills/export-session/scripts/render_transcript.py \
     docs/sessions/YYYY-MM-DD-<slug>-transcript.md
   ```

   Use the same `YYYY-MM-DD-<slug>` you chose in step 1. If the script reports it
   can't find the session, pass the JSONL path as a second argument.
5. Tell the user both exact paths you wrote.

## Common mistakes

- **Naming for the last task instead of the whole session.** The slug must capture
  the session's overall arc. Re-read the contract's examples.
- **Producing only one of the two files.** Both the summary and the transcript are
  required, and they must share the same `YYYY-MM-DD-<slug>` base name.
- **Hand-writing the transcript instead of running the script.** The verbatim log
  comes from `render_transcript.py`, not from you retyping the conversation.
- **Forgetting to create `docs/sessions/`**, or writing to `docs/` root instead.
- **Padding the summary with invented specifics.** If a commit SHA, test count, or
  file path isn't in your context, say so instead of fabricating it.
