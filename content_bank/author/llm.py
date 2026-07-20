"""The single LLM seam for content-bank authoring.

Rendered prompt in, completion text out. This is the swappable/mockable ``llm()``
seam issue #16's standalone builder (``build_cli.py``) calls after
``build_brief_prompt.build(...)`` and ``build_draft_prompt.build(...)``.

Two backends, selected by ``SCRIPTURE_LOOM_LLM_BACKEND`` (default ``llm_core``):

- ``llm_core`` — the vendored synchronous mxlens path (default model
  deepseek-v4-flash, billed to API credits). Cheap and fast; the quality ceiling
  is the model.
- ``claude`` — shells out to the Claude Code CLI in headless print mode
  (``claude -p``), billing against the logged-in **subscription** (no
  ``ANTHROPIC_API_KEY`` in the environment ⇒ the CLI uses the OAuth login). Gets a
  strong model (default ``opus``) at no marginal per-token cost, at the price of
  per-call process spawn + subscription usage windows.

Both are pure "prompt in, text out" and raise ``RuntimeError`` on failure, so the
builder's backoff + per-unit isolation handle either identically.
"""
import os
import subprocess

# Built-in tools disabled for a pure single-shot completion (the prompts are
# fully self-contained; the model must not shell out or read files). NOTE: do
# NOT add ``--bare`` — it skips the credential source and breaks subscription
# auth ("Not logged in").
_CLAUDE_NO_TOOLS = ["Bash", "Read", "Edit", "Write", "Glob", "Grep",
                    "WebFetch", "WebSearch", "Task", "NotebookEdit"]
_CLAUDE_TIMEOUT_S = 900


def llm(prompt: str, model: str | None = None) -> str:
    """Send one fully-rendered prompt, return the completion text.

    Backend from ``SCRIPTURE_LOOM_LLM_BACKEND`` (``llm_core`` default, or
    ``claude``). Raises ``RuntimeError`` on failure.
    """
    if os.environ.get("SCRIPTURE_LOOM_LLM_BACKEND") == "claude":
        return _claude_cli_llm(prompt, model)
    from llm_core import run_sync_llm

    return run_sync_llm("", prompt, caller="content_bank", model=model)


def _claude_cli_llm(prompt: str, model: str | None = None) -> str:
    """One headless Claude Code completion via ``claude -p`` (subscription auth).

    Prompt goes on stdin (so it never collides with the variadic tool flags).
    """
    argv = ["claude", "-p", "--model", model or "opus",
            "--output-format", "text",
            "--disallowed-tools", *_CLAUDE_NO_TOOLS]
    proc = subprocess.run(argv, input=prompt, capture_output=True, text=True,
                          timeout=_CLAUDE_TIMEOUT_S)
    if proc.returncode != 0:
        raise RuntimeError(
            f"claude -p failed (exit {proc.returncode}): {proc.stderr[:500]}")
    out = (proc.stdout or "").strip()
    if not out:
        raise RuntimeError("claude -p returned empty output")
    return out
