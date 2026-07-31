"""Structured per-call LLM telemetry for content experiments (#35).

One append-only JSONL ``CallRecord`` per LLM attempt (including retries and
failures). It NEVER stores credentials or prompt/response bodies — only a sha256
``prompt_hash``. Token numbers carry a ``usage_source``: ``"provider"`` (from
``claude -p`` JSON usage) or ``"local_estimate"`` (llm_core's locally-tokenized
summary, which has no cache/thinking split).
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import asdict, dataclass


@dataclass
class TokenUsage:
    input: int | None = None
    output: int | None = None
    cache_creation: int | None = None
    cache_read: int | None = None
    thinking: int | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class LLMResult:
    text: str
    usage: TokenUsage
    requested_model: str | None
    actual_model: str | None
    stop_reason: str | None
    duration_ms: int
    usage_source: str
    cost_estimate: float | None = None


@dataclass
class CallRecord:
    experiment: str | None
    stage: str
    unit_id: str | None
    kind: str | None
    attempt: int
    backend: str
    requested_model: str | None
    actual_model: str | None
    usage: dict
    usage_source: str
    cost_estimate: float | None
    duration_ms: int
    stop_reason: str | None
    success: bool
    error: str | None
    prompt_hash: str

    def as_dict(self) -> dict:
        return asdict(self)


class TelemetrySink:
    """Append-only JSONL sink; one line per CallRecord."""

    def __init__(self, path):
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, record: CallRecord) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.as_dict(), ensure_ascii=False) + "\n")

    def records(self):
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                yield json.loads(line)


class NullSink:
    """Default sink for ordinary builds: records nothing."""

    def add(self, record) -> None:
        return None


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()
