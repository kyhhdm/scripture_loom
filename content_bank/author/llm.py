"""The single LLM seam for content-bank authoring.

Rendered prompt + an explicit ``Route`` in, completion text out. This is the
swappable/mockable ``llm()`` seam the standalone builder (``build_cli.py``) and
the experiment runner (#35) call after the prompt builders. Routing is now
**explicit per call** (a ``Route``) instead of process-wide
``SCRIPTURE_LOOM_LLM_BACKEND``/``SCRIPTURE_LOOM_LLM_MODEL`` env vars, so one build
can draft on one model and review on another.

Two backends, chosen by ``route.backend``:

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

``route_from_env(model)`` is a transitional bridge for call sites not yet
rethreaded onto an explicit RouteConfig; it also serves as the documented "env as
a default source" for a single-model run.
"""
import json
import os
import subprocess
import time

from .routing import Route
from .telemetry import LLMResult, TokenUsage

# Built-in tools disabled for a pure single-shot completion (the prompts are
# fully self-contained; the model must not shell out or read files). NOTE: do
# NOT add ``--bare`` — it skips the credential source and breaks subscription
# auth ("Not logged in").
_CLAUDE_NO_TOOLS = ["Bash", "Read", "Edit", "Write", "Glob", "Grep",
                    "WebFetch", "WebSearch", "Task", "NotebookEdit"]
_CLAUDE_TIMEOUT_S = 900


def route_from_env(model: str | None = None) -> Route:
    """Build a Route from the legacy env vars (transitional bridge / single-model
    default source). ``model`` overrides ``SCRIPTURE_LOOM_LLM_MODEL``."""
    backend = os.environ.get("SCRIPTURE_LOOM_LLM_BACKEND") or "llm_core"
    return Route(backend, model or os.environ.get("SCRIPTURE_LOOM_LLM_MODEL") or None)


def llm(prompt: str, route: Route) -> LLMResult:
    """Send one fully-rendered prompt via ``route``; return a structured
    ``LLMResult`` (text + normalized usage + metadata). Raises ``RuntimeError`` on
    failure. Use ``llm_text()`` where only the completion string is wanted."""
    if route.backend == "claude":
        return _claude_cli_llm(prompt, route.model, route.settings)
    from llm_core import run_sync_llm_result

    t0 = time.time()
    text, summary = run_sync_llm_result("", prompt, caller="content_bank",
                                        model=route.model)
    return LLMResult(
        text=text,
        usage=TokenUsage(input=summary.get("tokens_in_total"),
                         output=summary.get("tokens_out_total")),
        requested_model=route.model, actual_model=summary.get("model"),
        stop_reason=None, duration_ms=int((time.time() - t0) * 1000),
        usage_source="local_estimate", cost_estimate=summary.get("cost"))


def llm_text(prompt: str, route: Route) -> str:
    """The text-only contract for callers that don't need telemetry."""
    return llm(prompt, route).text


def _claude_cli_llm(prompt: str, model: str | None = None,
                    settings: dict | None = None) -> LLMResult:
    """One headless Claude Code completion via ``claude -p`` (subscription auth),
    using structured JSON output so per-call provider usage is retained.

    Prompt goes on stdin (so it never collides with the variadic tool flags).
    """
    settings = settings or {}
    argv = ["claude", "-p", "--model", model or "opus",
            "--output-format", "json",
            "--disallowed-tools", *_CLAUDE_NO_TOOLS]
    t0 = time.time()
    proc = subprocess.run(argv, input=prompt, capture_output=True, text=True,
                          timeout=_CLAUDE_TIMEOUT_S)
    dur = int((time.time() - t0) * 1000)
    if proc.returncode != 0:
        raise RuntimeError(
            f"claude -p failed (exit {proc.returncode}): {proc.stderr[:500]}")
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"claude -p returned non-JSON: {(proc.stdout or '')[:300]!r}") from exc
    text = (payload.get("result") or "").strip()
    if not text:
        raise RuntimeError("claude -p returned empty result")
    u = payload.get("usage") or {}
    return LLMResult(
        text=text,
        usage=TokenUsage(input=u.get("input_tokens"), output=u.get("output_tokens"),
                         cache_creation=u.get("cache_creation_input_tokens"),
                         cache_read=u.get("cache_read_input_tokens")),
        requested_model=model, actual_model=payload.get("model"),
        stop_reason=payload.get("stop_reason"), duration_ms=dur,
        usage_source="provider", cost_estimate=None)
