"""Synchronous in-recipe LLM for the analyst shape engine (Phase 2).

The vendored SOFT primitives (detect_anomaly caption, identify_actors caption,
decompose_drivers bucket-resolve) and the shape-level VerifyStep call
`_run_claude_no_tools(system, user, caller)` for *fail-open* captions/verify.
Phase-1 stubbed it (raise → primitives degrade). Here we route it to MxLens's
own synchronous `chatmodels` client — the same path `LLMService` builds.

Design:
- **Auto-gated on configuration** (no new flag): if no LLM credential is set,
  raise fast so the caller's fail-open path degrades to Phase-1 behavior without
  a slow network attempt. Envs with `llm_api_key`/`llm_api_base` configured get
  the real call.
- **C0 discipline**: bounded retry + a structured audit record per attempt.
  Output validation + the fail-open decision stay in the primitives (they
  `parse_llm_json(...)` and drop to a degraded result on any failure).
- Stateless: a fresh model per call (clean buffer), mirroring LLMService.
"""
from __future__ import annotations

import os
import time

import structlog

from llm_core.config import settings

_log = structlog.get_logger("mxlens.analyst.llm")
_MAX_ATTEMPTS = 2
# Provider credentials `chatmodels` reads straight from the environment. The
# analyst model (deepseek-v4-flash) is a Volcengine model keyed by ARK_API_KEY,
# so the gate must recognize these — not just the settings.llm_* override.
_PROVIDER_KEY_ENV = ("ARK_API_KEY", "VOLCENGINE_API_KEY", "OPENAI_API_KEY",
                     "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY")


def llm_configured() -> bool:
    """True when an in-recipe LLM call can actually reach a model — via an
    explicit endpoint override (settings.llm_api_base/key, e.g. a self-hosted
    server) OR a provider key `chatmodels` picks up from the environment."""
    if settings.llm_api_key or settings.llm_api_base:
        return True
    return any(os.environ.get(k) for k in _PROVIDER_KEY_ENV)


def run_sync_llm(system_prompt: str, user_message: str, caller: str = "",
                 model: str | None = None) -> str:
    """One synchronous completion via the SHARED LLM path (`LLMService.
    run_batch_sync`) — the same OpenAI-format, usage-tracked core that backs the
    run_llm_batch task / POST /api/v1/llm/batch. Raises on unconfigured/unknown
    model or after bounded retry; callers (SOFT sites) catch and degrade
    fail-open."""
    if not llm_configured():
        raise RuntimeError(
            "analyst in-recipe LLM not configured (set llm_api_key/llm_api_base "
            "or a provider key like ARK_API_KEY); SOFT sites degrade fail-open")

    from llm_core.service import LLMService

    resolved = model or settings.analyst_llm_model
    # Proper OpenAI messages (system + user turns), not a concatenated blob.
    messages = ([{"role": "system", "content": system_prompt}] if system_prompt else []) \
        + [{"role": "user", "content": user_message}]
    # Endpoint override for a self-hosted / non-default endpoint; when unset the
    # model self-configures its provider endpoint + key from the environment.
    build_overrides = _build_overrides()

    last_err = "empty"
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        t0 = time.time()
        try:
            out = LLMService.run_batch_sync(
                [messages], model=resolved, build_overrides=build_overrides,
                cache=settings.analyst_llm_cache_enabled)
        except ValueError as exc:  # unbuildable model — not transient
            raise RuntimeError(f"analyst LLM: unknown model {resolved!r}: {exc}") from exc
        gen = out["generations"][0]
        summary = out["summary"]
        elapsed = int((time.time() - t0) * 1000)
        if not gen.get("error") and gen.get("generation"):
            _log.info("analyst.llm.ok", caller=caller, model=resolved, attempt=attempt,
                      elapsed_ms=elapsed, tokens_out=summary.get("tokens_out_total"),
                      cost=summary.get("cost"))
            return gen["generation"]
        last_err = gen.get("error") or "empty"
        _log.warning("analyst.llm.retry", caller=caller, model=resolved,
                     attempt=attempt, elapsed_ms=elapsed, error=str(last_err)[:200])
    raise RuntimeError(
        f"analyst LLM failed after {_MAX_ATTEMPTS} attempts "
        f"(caller={caller}, model={resolved}): {last_err}")


def _build_overrides() -> dict:
    o = {}
    if settings.llm_api_base:
        o["api_base"] = settings.llm_api_base
    if settings.llm_api_key:
        o["api_key"] = settings.llm_api_key
    return o


def run_batch_llm(prompts: list[tuple[str, str]], caller: str = "",
                  model: str | None = None) -> list[str]:
    """Batch variant of run_sync_llm: N ``(system, user)`` prompts → N generations
    in ONE concurrent (``async_limit``) + cached ``run_batch_sync`` call. Per-item
    failures return ``""`` so callers can fail-open per item (no whole-batch
    retry). ``[]`` in → ``[]`` out. Configured on the same gate + model + cache as
    run_sync_llm; use it wherever a site holds several independent prompts.
    """
    if not prompts:
        return []
    if not llm_configured():
        raise RuntimeError(
            "analyst in-recipe LLM not configured (set llm_api_key/llm_api_base "
            "or a provider key like ARK_API_KEY); SOFT sites degrade fail-open")

    from llm_core.service import LLMService

    resolved = model or settings.analyst_llm_model
    messages = [
        ([{"role": "system", "content": s}] if s else []) + [{"role": "user", "content": u}]
        for s, u in prompts
    ]
    out = LLMService.run_batch_sync(
        messages, model=resolved, build_overrides=_build_overrides(),
        cache=settings.analyst_llm_cache_enabled)
    s = out["summary"]
    _log.info("analyst.llm.batch", caller=caller, model=resolved, n=len(prompts),
              cache_hits=s.get("cache_hits"), tokens_out=s.get("tokens_out_total"),
              cost=s.get("cost"))
    return [g["generation"] if not g.get("error") else "" for g in out["generations"]]
