"""Explicit per-stage LLM routing for the content pipeline.

A ``Route`` is ``(backend, model, settings)``. A ``RouteConfig`` assigns one
Route to each LLM stage, replacing the process-wide ``SCRIPTURE_LOOM_LLM_BACKEND``
/ ``SCRIPTURE_LOOM_LLM_MODEL`` env vars so a single build can draft on one model
and review on another. The normal builder uses ``RouteConfig.single()``
(behaviour-identical to the old env path); the experiment runner (#35) uses
``RouteConfig.from_experiment(json)``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

STAGES = ("brief", "draft", "repair", "review_r1", "review_r2", "revise")


@dataclass(frozen=True)
class Route:
    backend: str
    model: str | None = None
    settings: dict = field(default_factory=dict)

    @classmethod
    def from_json(cls, d: dict) -> "Route":
        return cls(backend=d["backend"], model=d.get("model"),
                   settings=dict(d.get("settings") or {}))


@dataclass(frozen=True)
class RouteConfig:
    brief: Route
    draft: Route
    repair: Route
    review_r1: Route
    review_r2: Route
    revise: Route

    @classmethod
    def single(cls, backend: str, model: str | None = None) -> "RouteConfig":
        """Every stage -> the same Route. The normal --backend/--model builder
        uses this; behaviour is identical to the old single-model env path."""
        r = Route(backend, model)
        return cls(**{stage: r for stage in STAGES})

    @classmethod
    def from_experiment(cls, routes_json: dict) -> "RouteConfig":
        missing = [s for s in STAGES if s not in routes_json]
        if missing:
            raise ValueError(f"experiment routes missing stages: {missing}")
        return cls(**{s: Route.from_json(routes_json[s]) for s in STAGES})
