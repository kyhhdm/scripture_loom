"""Generic LLM batch service.

Backs POST /api/v1/llm/batch and POST /api/v1/llm/batch/estimate. Submits the
run_llm_batch Celery task without any datasource coupling — `AnnotateRunner`
and the `mxapi.datasource` layer are NOT used here. For batched row-packed
labeling, use the existing enrichment / llm_labeling path.
"""

import hashlib
import json
import time
from typing import Any

import structlog

from llm_core.config import settings
from llm_core.schemas import (
    LLMBatchEstimateRequest,
    LLMBatchEstimateResponse,
    LLMBatchRequest,
)
from llm_core.errors import ValidationError

logger = structlog.get_logger(__name__)

_CACHE_PREFIX = "llm:cmpl:"


def _completion_key(model: str, msgs: list, overrides: dict) -> str:
    """Stable cache key over the semantics that determine the output:
    model + full message list + completion overrides (NOT api_base/api_key)."""
    canonical = json.dumps([model, msgs, overrides], sort_keys=True,
                           ensure_ascii=False, default=str)
    return _CACHE_PREFIX + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class _CachedAI:
    """Minimal stand-in for a batch_llm result, reconstructed from cache."""
    __slots__ = ("content", "additional_kwargs")

    def __init__(self, content: str, tool_calls):
        self.content = content
        self.additional_kwargs = {"tool_calls": tool_calls} if tool_calls else {}


def _cache_client(cache):
    """Resolve the `cache` arg to a redis-like client (or None). True -> the
    shared sync Redis; a client with mget/setex -> used as-is (injection/tests)."""
    if cache is True:
        # The shared-Redis completion cache was NOT vendored into llm_core
        # (scripture_loom's sync path defaults cache off). Passing a redis-like
        # client explicitly still works via the branch below; `cache=True`
        # degrades to no-cache rather than pulling a Redis dependency.
        logger.warning("llm.cache.unavailable", error="redis cache not vendored in llm_core")
        return None
    if cache and hasattr(cache, "mget"):
        return cache
    return None


# Pass shape: convert pydantic ChatMessage models to plain dicts before
# handing them to Celery (JSON-only serialization). Carries tool-calling
# fields through so the worker can forward them to the LLM.
def _serialize_prompts(prompts: list) -> list:
    out: list = []
    for p in prompts:
        if isinstance(p, str):
            out.append(p)
            continue
        serialized: list[dict] = []
        for m in p:
            turn: dict = {"role": m.role}
            if m.content is not None:
                turn["content"] = m.content
            if m.tool_calls:
                turn["tool_calls"] = m.tool_calls
            if m.tool_call_id:
                turn["tool_call_id"] = m.tool_call_id
            if m.name:
                turn["name"] = m.name
            serialized.append(turn)
        out.append(serialized)
    return out


def _resolve_model_or_raise(model: str | None):
    """Build the LLM client at submit time so a bad model surfaces as 400."""
    from llm_core import chatmodels

    resolved = model or settings.llm_default_model
    model_obj, errmsg = chatmodels.build_chat(modelId=resolved)
    if errmsg or model_obj is None:
        raise ValidationError(
            f"Unknown LLM model: {resolved}",
            details={"resource_type": "llm_model", "resource_id": resolved, "reason": errmsg},
        )
    return resolved, model_obj


class LLMService:
    """Submit and estimate generic LLM batches."""

    @staticmethod
    def run_batch_sync(prompts: list, model: str | None = None,
                       config: dict | None = None,
                       build_overrides: dict | None = None,
                       progress=None, cache=False) -> dict:
        """Synchronous LLM batch execution — the shared core of the run_llm_batch
        Celery task AND the mxlens-analyst in-recipe seam. OpenAI-format prompts
        in, ``{generations, summary}`` out (with per-prompt + total token/cost).

        Args:
            prompts: list where each item is a str (single user message) or a
                list of ``{role, content, tool_calls?, tool_call_id?, name?}``
                turns (OpenAI/LiteLLM format; carries tool-calling fields).
            model: chatmodels.menu id; defaults to settings.llm_default_model.
            config: LiteLLM completion overrides forwarded per call.
            build_overrides: kwargs forwarded to ``build_chat`` (e.g.
                ``api_base``/``api_key`` for a self-hosted endpoint).
            progress: optional ``(fraction: float, step: str) -> None`` callback
                (the Celery task passes its ``update_progress``).
            cache: completion cache. ``False`` = off; ``True`` = the shared sync
                Redis (keyed by model+messages+config, TTL
                ``settings.llm_completion_cache_ttl_s``); a redis-like client is
                used as-is. Only cache MISSES hit the LLM; cached prompts are
                marked ``cached=True`` and contribute 0 to the usage/cost totals.
                Degrades to no-cache if Redis is unavailable.
        """
        from llm_core import chatmodels

        prog = progress or (lambda *_a: None)
        start = time.time()
        resolved_model = model or settings.llm_default_model
        overrides = dict(config) if config else {}

        prog(0.02, f"Resolving model: {resolved_model}")
        model_obj, errmsg = chatmodels.build_chat(modelId=resolved_model, **(build_overrides or {}))
        if errmsg or model_obj is None:
            raise ValueError(f"Failed to build LLM client for model={resolved_model}: {errmsg}")

        def _to_messages(item) -> list:
            """str -> [{'user'}]; list -> plain dicts carrying tool-call fields."""
            if isinstance(item, str):
                return [{"role": "user", "content": item}]
            if isinstance(item, list):
                out: list[dict] = []
                for turn in item:
                    msg: dict = {"role": turn.get("role", "user")}
                    content = turn.get("content")
                    msg["content"] = "" if content is None else content
                    if turn.get("tool_calls"):
                        msg["tool_calls"] = turn["tool_calls"]
                    if turn.get("tool_call_id"):
                        msg["tool_call_id"] = turn["tool_call_id"]
                    if turn.get("name"):
                        msg["name"] = turn["name"]
                    out.append(msg)
                return out
            raise ValueError(f"Unsupported prompt item type: {type(item).__name__}")

        prog(0.05, f"Preparing {len(prompts)} prompts...")
        msgs_list = [_to_messages(p) for p in prompts]

        # Cache lookup (opt-in) — only MISSES are dispatched to the LLM.
        n = len(prompts)
        rc = _cache_client(cache)
        keys = [_completion_key(resolved_model, m, overrides) for m in msgs_list] if rc else [None] * n
        hits: list[dict | None] = [None] * n
        if rc:
            try:
                for i, x in enumerate(rc.mget(keys) if keys else []):
                    if x:
                        hits[i] = json.loads(x.decode() if isinstance(x, (bytes, bytearray)) else x)
            except Exception as exc:
                logger.warning("llm.cache.read_failed", error=str(exc)[:120])
                rc = None

        miss_pos = [i for i in range(n) if hits[i] is None]
        prog(0.10, f"Dispatching {len(miss_pos)}/{n} calls to {resolved_model}...")
        ai_by_pos: list = [None] * n
        if miss_pos:
            ai_miss = model_obj.batch_llm(msgs=[msgs_list[i] for i in miss_pos], **overrides)
            if len(ai_miss) < len(miss_pos):  # batch_llm short-list padding
                ai_miss = list(ai_miss) + [
                    type(ai_miss[0])("{}") if ai_miss else None
                    for _ in range(len(miss_pos) - len(ai_miss))
                ]
            for local_i, pos in enumerate(miss_pos):
                ai_by_pos[pos] = ai_miss[local_i]
        for i in range(n):  # reconstruct cached hits as AI-like objects
            if hits[i] is not None:
                ai_by_pos[i] = _CachedAI(hits[i].get("generation", ""), hits[i].get("tool_calls"))

        prog(0.92, "Computing usage stats...")
        generations: list[dict] = []
        tokens_in_total = tokens_out_total = success_count = cache_hit_count = 0
        ttl = settings.llm_completion_cache_ttl_s
        for idx, (item_msgs, ai) in enumerate(zip(msgs_list, ai_by_pos)):
            cached = hits[idx] is not None
            try:
                tokens_in = sum(model_obj.get_num_tokens(m.get("content") or "")
                                for m in item_msgs)
            except Exception:
                tokens_in = 0
            generation = getattr(ai, "content", "") if ai is not None else ""
            tool_calls = None
            if ai is not None:
                raw_calls = (getattr(ai, "additional_kwargs", None) or {}).get("tool_calls")
                if raw_calls:
                    tool_calls = raw_calls
            try:
                tokens_out = model_obj.get_num_tokens(generation) if generation else 0
            except Exception:
                tokens_out = 0
            # A tool-call-only response (empty content) is NOT a failure.
            is_failure = not (bool(generation) and generation != "{}") and not tool_calls
            if not is_failure:
                success_count += 1
            if cached:
                cache_hit_count += 1
            elif rc and not is_failure:  # store fresh successes
                try:
                    rc.setex(keys[idx], ttl, json.dumps(
                        {"generation": generation, "tool_calls": tool_calls}, ensure_ascii=False))
                except Exception as exc:
                    logger.warning("llm.cache.write_failed", error=str(exc)[:120])
            generations.append({
                "prompt_id": idx, "generation": generation, "tool_calls": tool_calls,
                "error": "model_returned_empty" if is_failure else None,
                "cached": cached, "tokens_in": tokens_in, "tokens_out": tokens_out,
            })
            if not cached:  # totals reflect only the fresh LLM calls
                tokens_in_total += tokens_in
                tokens_out_total += tokens_out

        input_price = getattr(model_obj, "input_price", 0.0) or 0.0
        output_price = getattr(model_obj, "output_price", 0.0) or 0.0
        currency = getattr(model_obj, "currency_code", "USD") or "USD"
        cost = input_price * tokens_in_total + output_price * tokens_out_total
        prog(1.0, "Completed")
        return {
            "generations": generations,
            "summary": {
                "model": resolved_model, "total": len(prompts), "success": success_count,
                "error_count": len(prompts) - success_count,
                "cache_hits": cache_hit_count,
                "tokens_in_total": tokens_in_total, "tokens_out_total": tokens_out_total,
                "cost": cost, "currency_code": currency,
                "elapsed_s": round(time.time() - start, 2),
            },
        }

    # NOTE: mxlens's async `submit_batch` (Celery run_llm_batch + task_service +
    # queue_load) was intentionally NOT vendored — scripture_loom uses the
    # synchronous `run_batch_sync` path directly (see llm_core.sync), so there is
    # no Celery/Redis/REST task layer here.

    def estimate(self, request: LLMBatchEstimateRequest) -> LLMBatchEstimateResponse:
        """Synchronous token / cost estimate. No LLM call.

        Counts input tokens by tokenizing each rendered prompt with the
        model's own tokenizer. Output tokens are estimated from a fixed
        per-prompt assumption (server config or per-request override).
        """
        n = len(request.prompts)
        cap = settings.llm_batch_max_prompts
        if n > cap:
            raise ValidationError(
                f"Too many prompts: {n} > {cap}. Use llm_labeling on a datasource for larger workloads.",
                details={"limit": cap, "received": n},
            )

        resolved_model, model_obj = _resolve_model_or_raise(request.model)
        output_per_prompt = (
            request.output_tokens_per_prompt
            if request.output_tokens_per_prompt is not None
            else settings.llm_batch_estimate_output_tokens
        )

        input_token_total = 0
        for p in request.prompts:
            if isinstance(p, str):
                input_token_total += _safe_token_count(model_obj, p)
            else:
                for m in p:
                    # content may be None on tool-calling assistant turns;
                    # _safe_token_count tolerates None.
                    input_token_total += _safe_token_count(model_obj, m.content)
                    # tool_calls / tool_call_id / name also consume input
                    # tokens via the serialized JSON. Tokenize the
                    # serialized blob so the estimate stays meaningful for
                    # multi-turn tool-calling conversations.
                    if m.tool_calls:
                        import json
                        input_token_total += _safe_token_count(
                            model_obj, json.dumps(m.tool_calls, ensure_ascii=False)
                        )

        # Tools (function definitions) are sent once per call and contribute
        # to every prompt's input tokens. Tokenize the JSON blob and
        # multiply by the number of calls.
        if request.tools:
            import json
            tools_tokens = _safe_token_count(
                model_obj, json.dumps(request.tools, ensure_ascii=False)
            )
            input_token_total += tools_tokens * n

        input_price = getattr(model_obj, "input_price", 0.0) or 0.0
        output_price = getattr(model_obj, "output_price", 0.0) or 0.0
        currency = getattr(model_obj, "currency_code", "USD") or "USD"
        output_token_total = output_per_prompt * n
        cost = input_price * input_token_total + output_price * output_token_total

        return LLMBatchEstimateResponse(
            model=resolved_model,
            num_calls=n,
            input_token_total=input_token_total,
            output_token_total_assumed=output_token_total,
            input_price_per_token=float(input_price),
            output_price_per_token=float(output_price),
            estimated_cost=float(cost),
            currency_code=currency,
        )


def _safe_token_count(model_obj, text: str) -> int:
    try:
        return int(model_obj.get_num_tokens(text or ""))
    except Exception:
        # Fallback: rough character-based estimate, matching the one inside
        # LiteLLM2Chat.get_num_tokens for tokenizer failures.
        return max(1, len(text or "") // 2)
