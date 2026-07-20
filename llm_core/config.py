"""Trimmed settings for llm_core's synchronous LLM path.

Replaces the full ``mxlens.config.settings`` (hundreds of platform fields) with
only the handful the vendored sync path reads. Defaults target scripture_loom's
choice of ``deepseek-v4-flash`` (Volcengine via LiteLLM) and keep the Redis
completion cache OFF so no Redis dependency is ever touched.

Credential loading gotcha
-------------------------
``chatmodels.LiteLLM2Chat`` reads provider keys (``ARK_API_KEY`` /
``VOLCENGINE_API_KEY`` / ...) **straight from** ``os.environ``. A pydantic
``BaseSettings`` object does NOT populate ``os.environ`` — so we explicitly load
the ``.env`` file into the real process environment at import time. By default we
load this repo's own ``.env`` (git-ignored; see ``.env.example``); override the
path with ``SCRIPTURE_LOOM_LLM_ENV``.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo-local .env by default (see .env.example); override with SCRIPTURE_LOOM_LLM_ENV.
_DEFAULT_ENV = str(Path(__file__).resolve().parents[1] / ".env")
_ENV_PATH = os.environ.get("SCRIPTURE_LOOM_LLM_ENV", _DEFAULT_ENV)

# Load provider credentials into the real environment (override=False so an
# already-exported ARK_API_KEY wins). This is what makes chatmodels' direct
# os.environ reads see the key — see module docstring.
load_dotenv(_ENV_PATH, override=False)


class Settings(BaseSettings):
    """Only the fields llm_core.service / llm_core.sync actually reference."""

    model_config = SettingsConfigDict(env_file=_ENV_PATH, extra="ignore")

    # Model selection — default to the owner's choice.
    llm_default_model: str = "deepseek-v4-flash"
    analyst_llm_model: str = "deepseek-v4-flash"

    # Optional explicit endpoint override (unset -> provider self-configures from
    # env). When set, forwarded to build_chat as api_base/api_key.
    llm_api_key: str | None = None
    llm_api_base: str | None = None

    # Completion cache: OFF by default (no Redis in llm_core).
    analyst_llm_cache_enabled: bool = False
    llm_completion_cache_ttl_s: int = 604800  # 7 days (unused while cache off)

    # Batch guards (kept for parity with run_batch_sync / estimate).
    llm_batch_max_prompts: int = 500
    llm_batch_estimate_output_tokens: int = 512


settings = Settings()
