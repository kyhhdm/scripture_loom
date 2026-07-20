"""llm_core — scripture_loom's in-process LLM capability.

A minimal synchronous LLM path vendored from the mxlens service (see
PROVENANCE.md): ``build_chat(model).batch_llm(msgs)`` behind a small seam. No
FastAPI, no Celery, no Redis, no REST server. Default model: deepseek-v4-flash
(Volcengine via LiteLLM), keyed by ARK_API_KEY loaded from the configured .env.

Public seam:
    run_sync_llm(system_prompt, user_message) -> str
    run_batch_llm([(system, user), ...])      -> list[str]
    llm_configured()                          -> bool
"""
from llm_core.sync import llm_configured, run_batch_llm, run_sync_llm

__all__ = ["run_sync_llm", "run_batch_llm", "llm_configured"]
