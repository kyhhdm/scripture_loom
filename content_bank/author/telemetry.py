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


def record_call(sink, *, experiment, stage, unit_id, kind, attempt, route, prompt,
                result=None, error=None) -> None:
    """Append one CallRecord for an LLM attempt. ``result`` is an ``LLMResult`` on
    success; on failure pass ``error`` and leave ``result`` None (usage empty).
    No-op when ``sink`` is falsy."""
    if not sink:
        return
    usage = result.usage.as_dict() if result else TokenUsage().as_dict()
    sink.add(CallRecord(
        experiment=experiment, stage=stage, unit_id=unit_id, kind=kind,
        attempt=attempt, backend=route.backend, requested_model=route.model,
        actual_model=result.actual_model if result else None,
        usage=usage,
        usage_source=result.usage_source if result else "none",
        cost_estimate=result.cost_estimate if result else None,
        duration_ms=result.duration_ms if result else 0,
        stop_reason=result.stop_reason if result else None,
        success=result is not None, error=error, prompt_hash=prompt_hash(prompt)))
