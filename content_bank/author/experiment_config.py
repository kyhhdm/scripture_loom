"""Load, validate, and hash a named experiment configuration (#35).

The config assigns a backend/model Route to every LLM stage plus a fixed
evaluator route. The experiment NAME is the identity; a ``config_hash`` over the
canonicalized config (+ corpus revision + prompt version) makes "identical
configuration" precise, so a run resumes only when nothing changed and refuses to
silently overwrite a name whose configuration differs.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

from .routing import STAGES

KNOWN_BACKENDS = frozenset({"llm_core", "claude"})
CREDENTIAL_KEYS = frozenset({"api_key", "apikey", "token", "authorization",
                             "secret", "password", "ark_api_key", "anthropic_api_key",
                             "gemini_api_key", "google_api_key"})
# Bump when brief/draft prompt builders or the rubric change so that a config
# reusing a name is not treated as identical across a prompt change.
PROMPT_VERSION = "1"


def load(path) -> dict:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def _scan_credentials(obj, where="config"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in CREDENTIAL_KEYS:
                raise ValueError(
                    f"credential-like field {k!r} is not allowed in {where}; "
                    "keep provider credentials in the environment, never in config")
            _scan_credentials(v, f"{where}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _scan_credentials(v, f"{where}[{i}]")


def validate(config: dict) -> None:
    """Raise ValueError on any structural problem or credential leak."""
    _scan_credentials(config)
    for key in ("schema_version", "name", "book", "routes", "evaluator"):
        if key not in config:
            raise ValueError(f"config missing required key: {key}")
    routes = config["routes"]
    missing = [s for s in STAGES if s not in routes]
    if missing:
        raise ValueError(f"routes missing stages: {missing}")
    for name, route in list(routes.items()) + [("evaluator", config["evaluator"])]:
        if route.get("backend") not in KNOWN_BACKENDS:
            raise ValueError(
                f"route {name}: unknown backend {route.get('backend')!r} "
                f"(known: {sorted(KNOWN_BACKENDS)})")
    gates = config.get("gates") or {}
    if not (0 <= int(gates.get("max_repair", 2)) <= 10):
        raise ValueError("gates.max_repair out of range 0..10")
    if int(gates.get("dim_cap", 6)) < 1:
        raise ValueError("gates.dim_cap must be >= 1")


def config_hash(config: dict, *, corpus_rev: str, prompt_version: str) -> str:
    """sha256 over the canonicalized config plus the corpus revision and prompt
    version, so 'identical configuration' includes the inputs that shape output."""
    canon = json.dumps(config, sort_keys=True, ensure_ascii=False)
    blob = f"{canon}\x00corpus={corpus_rev}\x00prompt={prompt_version}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def check_immutable(existing_manifest: dict | None, new_hash: str) -> None:
    """Refuse to reuse a name whose saved config_hash differs from new_hash."""
    if existing_manifest and existing_manifest.get("config_hash") != new_hash:
        raise ValueError(
            "experiment name already exists with a DIFFERENT configuration "
            f"(saved {existing_manifest.get('config_hash')!r} != new {new_hash!r}); "
            "choose a new name, or restore the original configuration to resume")
