# Content-Pipeline Experiments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add named, reproducible content-pipeline experiments with per-stage model routing and normalized call telemetry, built on the existing builder (#35).

**Architecture:** Refactor `build_cli`'s pipeline to be driven by an explicit per-stage `RouteConfig` instead of process-wide env vars (single source of pipeline truth). The LLM seam returns a structured `LLMResult`; callers record `CallRecord`s to a `TelemetrySink`. A named experiment config (immutable, hash-guarded) drives a runner that executes the same pipeline, persists gate traces + telemetry, runs the D1–D8 evaluator, and feeds an experiment-column comparison page.

**Tech Stack:** Python 3 (stdlib + existing deps), `uv`, `unittest`. LLM via `content_bank/author/llm.py` seam over `llm_core` (LiteLLM/deepseek/gemini) and `claude -p`.

## Global Constraints

- Run everything under `uv`: tests via `uv run python -m unittest discover -s content_bank/tests -v`.
- All new tests are **network-free**: mock the `llm`/seam layer; never hit a provider.
- **No credentials** in any config, result, log, or `CallRecord` — only a `prompt_hash` (sha256), never prompt/response bodies.
- Deterministic gates stay **local and unchanged** in behaviour; the LLM never judges gate outcomes.
- Generated items stay **draft-only**, WCF-1 constrained, evidence-not-judgment. Prepare-time only; no during-gathering computation.
- The normal `build_cli --backend/--model` builder must stay **behaviour-identical** after the refactor (same single model every stage; existing tests green).
- Backends: `"llm_core"` (default model deepseek-v4-flash) and `"claude"` (default model opus). Stage names (exact, everywhere): `brief, draft, repair, review_r1, review_r2, revise`; plus `evaluate` as a telemetry-only stage.

---

## File Structure

```
content_bank/author/
  routing.py             NEW — Route, RouteConfig
  telemetry.py           NEW — TokenUsage, LLMResult, CallRecord, TelemetrySink, NullSink
  experiment_config.py   NEW — load/validate, config_hash, immutability guard
  experiment_cli.py      NEW — validate/run/evaluate/compare subcommands
  experiment_report.py   NEW — extended experiment metrics
  llm.py                 EDIT — llm(prompt, route)->LLMResult; llm_text() shim; claude JSON
  build_cli.py           EDIT — thread RouteConfig + sink; delete env-var switching
  review.py              EDIT — thread routes + sink through review()/revise()
  quality_eval.py        EDIT — evaluator Route + sink
llm_core/sync.py         EDIT — run_sync_llm_result() returning (text, summary)
experiments/             NEW — checked-in NAME.json configs (e.g. example.json)
content_bank/tests/
  test_routing.py            NEW
  test_telemetry.py          NEW
  test_llm_seam.py           EDIT (LLMResult + json claude)
  test_experiment_config.py  NEW
  test_experiment_runner.py  NEW
  test_experiment_report.py  NEW
  test_compare_html.py       EDIT (experiment columns)
```

`experiments-out/` is a git-ignored run-output dir (add to `.gitignore`).

---

## Phase A — Route-driven pipeline

### Task A1: Route and RouteConfig types

**Files:**
- Create: `content_bank/author/routing.py`
- Test: `content_bank/tests/test_routing.py`

**Interfaces:**
- Produces:
  - `Route(backend: str, model: str | None = None, settings: dict = {})` — frozen dataclass.
  - `RouteConfig` frozen dataclass with fields `brief, draft, repair, review_r1, review_r2, revise` (each a `Route`), plus:
    - `RouteConfig.single(backend: str, model: str | None = None) -> RouteConfig`
    - `RouteConfig.from_experiment(routes_json: dict) -> RouteConfig`
    - `STAGES: tuple[str, ...]` module constant = the six stage names.

- [ ] **Step 1: Write the failing test**

```python
# content_bank/tests/test_routing.py
import unittest
from content_bank.author.routing import Route, RouteConfig, STAGES


class RoutingTest(unittest.TestCase):
    def test_single_fills_every_stage_with_same_route(self):
        rc = RouteConfig.single("claude", "opus")
        for stage in STAGES:
            r = getattr(rc, stage)
            self.assertEqual((r.backend, r.model), ("claude", "opus"))

    def test_single_default_model_is_none(self):
        rc = RouteConfig.single("llm_core")
        self.assertIsNone(rc.draft.model)

    def test_from_experiment_maps_each_stage(self):
        rc = RouteConfig.from_experiment({
            "brief": {"backend": "llm_core", "model": "gemini-3.6-flash"},
            "draft": {"backend": "claude", "model": "opus", "settings": {"effort": "high"}},
            "repair": {"backend": "claude", "model": "sonnet"},
            "review_r1": {"backend": "llm_core", "model": "gemini-3.6-flash"},
            "review_r2": {"backend": "llm_core", "model": "gemini-3.6-flash"},
            "revise": {"backend": "claude", "model": "sonnet"},
        })
        self.assertEqual(rc.draft.model, "opus")
        self.assertEqual(rc.draft.settings, {"effort": "high"})
        self.assertEqual(rc.review_r1.backend, "llm_core")

    def test_from_experiment_rejects_missing_stage(self):
        with self.assertRaises(ValueError):
            RouteConfig.from_experiment({"brief": {"backend": "llm_core"}})

    def test_stages_constant(self):
        self.assertEqual(
            STAGES,
            ("brief", "draft", "repair", "review_r1", "review_r2", "revise"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_routing -v`
Expected: FAIL (module `routing` not found).

- [ ] **Step 3: Write minimal implementation**

```python
# content_bank/author/routing.py
"""Explicit per-stage LLM routing for the content pipeline.

A Route is (backend, model, settings). A RouteConfig assigns one Route to each
LLM stage, replacing the process-wide SCRIPTURE_LOOM_LLM_BACKEND/MODEL env vars
so a single build can draft on one model and review on another. The normal
builder uses RouteConfig.single() (behaviour-identical to the old env path); the
experiment runner uses RouteConfig.from_experiment(json).
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
        r = Route(backend, model)
        return cls(**{stage: r for stage in STAGES})

    @classmethod
    def from_experiment(cls, routes_json: dict) -> "RouteConfig":
        missing = [s for s in STAGES if s not in routes_json]
        if missing:
            raise ValueError(f"experiment routes missing stages: {missing}")
        return cls(**{s: Route.from_json(routes_json[s]) for s in STAGES})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_routing -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/routing.py content_bank/tests/test_routing.py
git commit -m "feat(experiments): add Route/RouteConfig per-stage routing types (#35)"
```

---

### Task A2: Seam accepts a Route (text-preserving, pre-telemetry)

**Files:**
- Modify: `content_bank/author/llm.py`
- Test: `content_bank/tests/test_llm_seam.py`

**Interfaces:**
- Consumes: `routing.Route`.
- Produces: `llm(prompt: str, route: Route) -> str` (still returns text in this task; the
  `LLMResult` upgrade is Task B2). Backend/model come from `route`, not env vars.
  `_claude_cli_llm(prompt, model, settings)` gains `settings` (reads `settings["effort"]`).

Note: this task changes `llm()`'s signature from `llm(prompt, model=None)` to
`llm(prompt, route)`. Update all in-repo callers to pass a `Route` (they will be fully
re-threaded in A3/A4; here give them a temporary `Route` derived from the current env so the
suite stays green). Keep behaviour identical.

- [ ] **Step 1: Write the failing test**

```python
# add to content_bank/tests/test_llm_seam.py
from content_bank.author.routing import Route

class RouteSeamTest(unittest.TestCase):
    def test_llm_core_route_calls_run_sync_with_model(self):
        import content_bank.author.llm as seam
        captured = {}
        def fake_run_sync(system, user, caller, model):
            captured["model"] = model
            return "OK"
        with mock.patch("llm_core.run_sync_llm", fake_run_sync):
            out = seam.llm("hi", Route("llm_core", "deepseek-v4-pro"))
        self.assertEqual(out, "OK")
        self.assertEqual(captured["model"], "deepseek-v4-pro")

    def test_claude_route_builds_argv_with_model_and_effort(self):
        import content_bank.author.llm as seam
        captured = {}
        class P:
            returncode = 0; stdout = "OUT"; stderr = ""
        def fake_run(argv, **kw):
            captured["argv"] = argv; return P()
        with mock.patch("subprocess.run", fake_run):
            out = seam.llm("hi", Route("claude", "sonnet", {"effort": "high"}))
        self.assertEqual(out, "OUT")
        self.assertIn("sonnet", captured["argv"])
```

(Keep existing tests in the file; adapt any that call `llm("x")` / `llm("x", model=...)`
to pass a `Route`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_llm_seam -v`
Expected: FAIL (`llm()` takes a `route`, not `model`).

- [ ] **Step 3: Write minimal implementation**

```python
# content_bank/author/llm.py — replace llm() and _claude_cli_llm()
from .routing import Route

def llm(prompt: str, route: Route) -> str:
    """Send one fully-rendered prompt via the given Route; return completion text.
    (Task B2 upgrades this to return a structured LLMResult; llm_text() will keep
    this text contract.)"""
    if route.backend == "claude":
        return _claude_cli_llm(prompt, route.model, route.settings)
    from llm_core import run_sync_llm
    return run_sync_llm("", prompt, caller="content_bank", model=route.model)


def _claude_cli_llm(prompt, model=None, settings=None):
    settings = settings or {}
    argv = ["claude", "-p", "--model", model or "opus",
            "--output-format", "text",
            "--disallowed-tools", *_CLAUDE_NO_TOOLS]
    # (effort/settings are threaded into the JSON path in Task B2; text path
    # ignores unsupported settings for now.)
    proc = subprocess.run(argv, input=prompt, capture_output=True, text=True,
                          timeout=_CLAUDE_TIMEOUT_S)
    if proc.returncode != 0:
        raise RuntimeError(
            f"claude -p failed (exit {proc.returncode}): {proc.stderr[:500]}")
    out = (proc.stdout or "").strip()
    if not out:
        raise RuntimeError("claude -p returned empty output")
    return out
```

Temporary caller shim (until A3/A4): in `build_cli._llm_with_backoff` and `review.py`,
wrap current calls as `llm(prompt, Route(os.environ.get("SCRIPTURE_LOOM_LLM_BACKEND") or
"llm_core", os.environ.get("SCRIPTURE_LOOM_LLM_MODEL")))`. This keeps the suite green
without yet plumbing RouteConfig.

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run python -m unittest content_bank.tests.test_llm_seam content_bank.tests.test_review content_bank.tests.test_build_cli -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/llm.py content_bank/author/build_cli.py content_bank/author/review.py content_bank/tests/test_llm_seam.py
git commit -m "feat(experiments): seam takes an explicit Route (#35)"
```

---

### Task A3: Thread RouteConfig through review()/revise()

**Files:**
- Modify: `content_bank/author/review.py`
- Test: `content_bank/tests/test_review.py`

**Interfaces:**
- Consumes: `routing.Route`, seam `llm(prompt, route)`.
- Produces:
  - `review(items, *, passage_text, brief, book, unit_id, r1_route, r2_route) -> list`
  - `revise(items, verdicts, *, passage_text, brief, route) -> list`

- [ ] **Step 1: Write the failing test**

```python
# add to content_bank/tests/test_review.py
from content_bank.author.routing import Route

class ReviewRoutingTest(unittest.TestCase):
    def test_review_uses_r1_and_r2_routes(self):
        import content_bank.author.review as rv
        seen = []
        def fake_llm(prompt, route):
            seen.append(route.model)
            return '{"verdicts": {}}'
        with mock.patch.object(rv, "llm", fake_llm):
            rv.review([{"id": "X", "dimension": "D1"}], passage_text="p",
                      brief="b", book="PHP", unit_id="PHP-001",
                      r1_route=Route("llm_core", "m1"),
                      r2_route=Route("claude", "m2"))
        self.assertEqual(seen, ["m1", "m2"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_review -v`
Expected: FAIL (unexpected keyword `r1_route`).

- [ ] **Step 3: Write minimal implementation**

Change `review()` signature to accept `r1_route`, `r2_route`; in its loop pass the matching
route to `llm(...)`. Change `revise()` to accept `route` and pass it to its `llm(...)` call.
Update the tuple loop so r1 uses `r1_route`, r2 uses `r2_route`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_review -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/review.py content_bank/tests/test_review.py
git commit -m "feat(experiments): route review lenses + revise explicitly (#35)"
```

---

### Task A4: Route-driven build_cli; delete env-var switching

**Files:**
- Modify: `content_bank/author/build_cli.py`
- Test: `content_bank/tests/test_build_cli.py`

**Interfaces:**
- Consumes: `RouteConfig`, routed `review`/`revise`, seam `llm(prompt, route)`.
- Produces:
  - `_llm_with_backoff(prompt, route, *, tries=4, base=2.0)`
  - `_repair_to_clean(prompt, items, book, allowed, *, max_repair, dim_cap, where, repair_route)`
  - `_draft_with_repair(prompt, book, allowed, *, max_repair, dim_cap, draft_route, repair_route)`
  - `build_pericope(..., routes: RouteConfig, ...)` and `build_section(..., routes, ...)`
  - `run(..., routes: RouteConfig | None = None, backend="llm_core", model=None, ...)` —
    if `routes` is None, build `RouteConfig.single(backend, model)`. The
    `os.environ["SCRIPTURE_LOOM_LLM_BACKEND"]=...` block is **removed**.

- [ ] **Step 1: Write the failing test**

```python
# add to content_bank/tests/test_build_cli.py
from content_bank.author.routing import Route, RouteConfig

class RouteDrivenBuildTest(unittest.TestCase):
    def test_brief_and_draft_use_their_configured_models(self):
        import content_bank.author.build_cli as bc
        seen = []
        def fake_llm(prompt, route):
            seen.append(route.model)
            # brief is free text; draft/repair must be a JSON array
            return "brief text" if len(seen) == 1 else "[]"
        # ... set up a minimal manifest_obj with one pending pericope, temp dirs,
        # patch bc.llm and bc.run_all -> {} (clean gates), patch _passage_text.
        # Assert seen[0] == brief model, seen[1] == draft model.
```

Fill in the fixture using the existing patterns in `test_build_cli.py` (temp `drafts_dir`,
`briefs_dir`, a `manifest_mod.init_manifest` object). Patch `bc.run_all` to return `{}` and
`gates.dimension_cap_check` to return `{}` so no repair loop runs.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_build_cli -v`
Expected: FAIL (build_pericope has no `routes` param).

- [ ] **Step 3: Write minimal implementation**

- Add `routes: RouteConfig` param to `build_pericope`/`build_section`; replace bare
  `_llm_with_backoff(prompt)` calls with the stage's route:
  brief → `routes.brief`; first draft parse → `routes.draft`; repair loop → `routes.repair`
  (thread `repair_route` into `_repair_to_clean`); `review_mod.review(..., r1_route=routes.review_r1, r2_route=routes.review_r2)`; `review_mod.revise(..., route=routes.revise)`.
- `_llm_with_backoff(prompt, route, ...)` passes `route` to `llm`.
- In `run()`: `routes = routes or RouteConfig.single(backend, model)`. Remove the
  `os.environ[...]=backend` / `SCRIPTURE_LOOM_LLM_MODEL` writes. Keep the availability check
  but drive it off the routes actually in use (collect distinct `(backend, model)` from
  `routes` and check each: `claude` → `shutil.which("claude")`; `llm_core` →
  `llm_configured(_effective_model(...))`). The per-model run slug uses `routes.draft`.
- `draft_stamp` uses `routes.draft` model/backend.

- [ ] **Step 4: Run the whole author suite**

Run: `uv run python -m unittest discover -s content_bank/tests -v`
Expected: PASS (existing + new). Confirms the normal builder is behaviour-identical.

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/build_cli.py content_bank/tests/test_build_cli.py
git commit -m "feat(experiments): route-driven build_cli; drop env-var model switching (#35)"
```

---

## Phase B — Telemetry

### Task B1: Telemetry types and sink

**Files:**
- Create: `content_bank/author/telemetry.py`
- Test: `content_bank/tests/test_telemetry.py`

**Interfaces:**
- Produces:
  - `TokenUsage(input=None, output=None, cache_creation=None, cache_read=None, thinking=None)` — all `int | None`; `.as_dict()`.
  - `LLMResult(text, usage: TokenUsage, requested_model, actual_model, stop_reason, duration_ms, usage_source, cost_estimate=None)`.
  - `CallRecord(...)` dataclass (fields per spec) with `.as_dict()`.
  - `TelemetrySink(path)` — `.add(record: CallRecord)` appends one JSON line; `.records()` reads back.
  - `NullSink()` — `.add(...)` is a no-op (default for normal builds).
  - `prompt_hash(prompt: str) -> str` — sha256 hex.

- [ ] **Step 1: Write the failing test**

```python
# content_bank/tests/test_telemetry.py
import json, pathlib, tempfile, unittest
from content_bank.author.telemetry import (
    TokenUsage, CallRecord, TelemetrySink, NullSink, prompt_hash)

class TelemetryTest(unittest.TestCase):
    def test_usage_nullable_fields_default_none(self):
        u = TokenUsage(input=10, output=20)
        self.assertIsNone(u.cache_read)
        self.assertEqual(u.as_dict()["input"], 10)

    def test_sink_appends_jsonl_and_reads_back(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "calls.jsonl"
            sink = TelemetrySink(p)
            rec = CallRecord(experiment="e", stage="draft", unit_id="PHP-001",
                             kind="pericope", attempt=1, backend="claude",
                             requested_model="opus", actual_model="opus",
                             usage=TokenUsage(input=5, output=7).as_dict(),
                             usage_source="provider", cost_estimate=None,
                             duration_ms=12, stop_reason="end_turn", success=True,
                             error=None, prompt_hash="abc")
            sink.add(rec)
            lines = p.read_text().strip().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])["stage"], "draft")
            self.assertEqual(len(list(sink.records())), 1)

    def test_null_sink_is_noop(self):
        NullSink().add(object())  # must not raise

    def test_prompt_hash_stable_and_not_the_prompt(self):
        h = prompt_hash("secret prompt")
        self.assertEqual(h, prompt_hash("secret prompt"))
        self.assertNotIn("secret", h)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_telemetry -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation**

```python
# content_bank/author/telemetry.py
"""Structured per-call LLM telemetry for content experiments.

One append-only JSONL CallRecord per LLM attempt (including retries/failures).
NEVER stores credentials or prompt/response bodies — only a sha256 prompt_hash.
Token numbers carry a usage_source: "provider" (claude -p JSON) or
"local_estimate" (llm_core's locally-tokenized summary; no cache/thinking split).
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import asdict, dataclass, field


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
    def add(self, record) -> None:
        return None


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_telemetry -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/telemetry.py content_bank/tests/test_telemetry.py
git commit -m "feat(experiments): telemetry types + append-only sink (#35)"
```

---

### Task B2: llm_core returns usage; seam returns LLMResult; llm_text shim

**Files:**
- Modify: `llm_core/sync.py`, `content_bank/author/llm.py`
- Test: `content_bank/tests/test_llm_seam.py`, `llm_core/tests/` (add a summary passthrough test)

**Interfaces:**
- Consumes: `telemetry.LLMResult`, `telemetry.TokenUsage`.
- Produces:
  - `llm_core.run_sync_llm_result(system, user, caller="", model=None) -> tuple[str, dict]`
    returning `(text, summary)` where `summary` is `run_batch_sync`'s summary dict.
    Exported from `llm_core/__init__.py`.
  - Seam `llm(prompt, route) -> LLMResult` (both backends) and
    `llm_text(prompt, route) -> str` returning `.text`.
  - claude backend uses `--output-format json`; parse `usage`, `stop_reason`, `model`.

- [ ] **Step 1: Write the failing test**

```python
# add to content_bank/tests/test_llm_seam.py
from content_bank.author.telemetry import LLMResult

class LLMResultSeamTest(unittest.TestCase):
    def test_llm_core_result_carries_local_estimate_usage(self):
        import content_bank.author.llm as seam
        def fake_result(system, user, caller, model):
            return ("BODY", {"model": "deepseek-v4-flash", "tokens_in_total": 100,
                             "tokens_out_total": 40, "cost": 0.001})
        with mock.patch("llm_core.run_sync_llm_result", fake_result):
            r = seam.llm("hi", Route("llm_core", "deepseek-v4-flash"))
        self.assertIsInstance(r, LLMResult)
        self.assertEqual(r.text, "BODY")
        self.assertEqual(r.usage.input, 100)
        self.assertIsNone(r.usage.cache_read)
        self.assertEqual(r.usage_source, "local_estimate")
        self.assertEqual(r.cost_estimate, 0.001)

    def test_claude_json_result_carries_provider_usage(self):
        import content_bank.author.llm as seam, json as _json
        payload = {"result": "TEXT", "stop_reason": "end_turn", "model": "opus",
                   "usage": {"input_tokens": 8, "output_tokens": 9,
                             "cache_creation_input_tokens": 2,
                             "cache_read_input_tokens": 3}}
        class P: returncode = 0; stdout = _json.dumps(payload); stderr = ""
        with mock.patch("subprocess.run", lambda *a, **k: P()):
            r = seam.llm("hi", Route("claude", "opus"))
        self.assertEqual(r.text, "TEXT")
        self.assertEqual(r.usage.input, 8)
        self.assertEqual(r.usage.cache_read, 3)
        self.assertEqual(r.usage_source, "provider")
        self.assertEqual(r.stop_reason, "end_turn")

    def test_llm_text_returns_text_only(self):
        import content_bank.author.llm as seam
        with mock.patch("llm_core.run_sync_llm_result",
                        lambda *a, **k: ("HI", {"model": "m"})):
            self.assertEqual(seam.llm_text("p", Route("llm_core")), "HI")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_llm_seam -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

In `llm_core/sync.py`, add (mirrors `run_sync_llm` but returns the summary too):

```python
def run_sync_llm_result(system_prompt, user_message, caller="", model=None):
    """Like run_sync_llm but returns (text, summary) so callers can keep the
    provider/estimate usage metadata instead of discarding it."""
    if not llm_configured(model):
        raise RuntimeError("analyst in-recipe LLM not configured ...")
    from llm_core.service import LLMService
    resolved = model or settings.analyst_llm_model
    messages = ([{"role": "system", "content": system_prompt}] if system_prompt else []) \
        + [{"role": "user", "content": user_message}]
    out = LLMService.run_batch_sync([messages], model=resolved,
                                    build_overrides=_build_overrides(),
                                    cache=settings.analyst_llm_cache_enabled)
    gen = out["generations"][0]
    if gen.get("error") or not gen.get("generation"):
        raise RuntimeError(f"analyst LLM failed (caller={caller}, model={resolved})")
    return gen["generation"], out["summary"]
```

Export it from `llm_core/__init__.py`.

In `content_bank/author/llm.py`, rewrite the seam to build `LLMResult`:

```python
import json, time
from .routing import Route
from .telemetry import LLMResult, TokenUsage

def llm(prompt: str, route: Route) -> LLMResult:
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
    return llm(prompt, route).text

def _claude_cli_llm(prompt, model=None, settings=None):
    settings = settings or {}
    argv = ["claude", "-p", "--model", model or "opus",
            "--output-format", "json",
            "--disallowed-tools", *_CLAUDE_NO_TOOLS]
    t0 = time.time()
    proc = subprocess.run(argv, input=prompt, capture_output=True, text=True,
                          timeout=_CLAUDE_TIMEOUT_S)
    dur = int((time.time() - t0) * 1000)
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p failed (exit {proc.returncode}): {proc.stderr[:500]}")
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"claude -p returned non-JSON: {(proc.stdout or '')[:300]!r}") from exc
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
```

Now update the two in-repo text callers to use `llm_text`: in `review.py` the two `llm(...)`
call sites return text → switch to `llm_text(..., route)`; in `build_cli._llm_with_backoff`
return `llm_text(prompt, route)` **for now** (Task B3 swaps it to capture the full result).

- [ ] **Step 4: Run tests**

Run: `uv run python -m unittest content_bank.tests.test_llm_seam content_bank.tests.test_review content_bank.tests.test_build_cli llm_core.tests -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add llm_core/sync.py llm_core/__init__.py content_bank/author/llm.py content_bank/author/review.py content_bank/author/build_cli.py content_bank/tests/test_llm_seam.py
git commit -m "feat(experiments): LLMResult seam + llm_core usage passthrough + claude JSON (#35)"
```

---

### Task B3: Record CallRecords through the pipeline

**Files:**
- Modify: `content_bank/author/build_cli.py`
- Test: `content_bank/tests/test_build_cli.py`

**Interfaces:**
- Consumes: `telemetry.TelemetrySink`, `NullSink`, `CallRecord`, `LLMResult`.
- Produces:
  - `_llm_with_backoff(prompt, route, *, sink, stage, unit_id, kind, experiment, tries=4, base=2.0) -> str`
    — calls `llm(prompt, route)`, records a `CallRecord` per attempt (success and failure),
    returns `.text`.
  - `build_pericope`/`build_section`/`run` gain `sink=None, experiment=None`; default sink
    is `NullSink()` (normal builds record nothing).

- [ ] **Step 1: Write the failing test**

```python
# add to content_bank/tests/test_build_cli.py
from content_bank.author.telemetry import TelemetrySink

class TelemetryCaptureTest(unittest.TestCase):
    def test_each_stage_records_a_callrecord(self):
        # Build one pericope with a fake llm returning brief then "[]" draft,
        # gates patched clean, a real TelemetrySink on a temp path.
        # Assert the sink has records for stage "brief" and stage "draft",
        # each with backend/model and a prompt_hash, and no prompt text.
        ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_build_cli -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

- `_llm_with_backoff` now: for each attempt call `res = llm(prompt, route)`; build a
  `CallRecord(experiment, stage, unit_id, kind, attempt, route.backend,
  route.model, res.actual_model, res.usage.as_dict(), res.usage_source,
  res.cost_estimate, res.duration_ms, res.stop_reason, success=True, error=None,
  prompt_hash=prompt_hash(prompt))`; `sink.add(rec)`; return `res.text`. On `RuntimeError`,
  record a failure `CallRecord(success=False, error=str(exc), ...)` (usage empty) before
  backoff/re-raise.
- Thread `sink`, `stage`, `unit_id`, `kind`, `experiment` from `build_pericope`/`build_section`
  into every `_llm_with_backoff` call (brief/draft/repair) with the correct `stage`.
  `_repair_to_clean` gets `sink`/attribution and tags its calls `stage="repair"`.
- `review`/`revise` telemetry: pass `sink` down and wrap their internal calls — simplest is
  to have `review.py` accept an optional `sink` + attribution and record there too (tag
  `review_r1`/`review_r2`/`revise`). If that widens Task A3's signatures, do it here.
- `run()` default `sink = sink or NullSink()`.

- [ ] **Step 4: Run the author suite**

Run: `uv run python -m unittest discover -s content_bank/tests -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/build_cli.py content_bank/author/review.py content_bank/tests/test_build_cli.py
git commit -m "feat(experiments): record per-attempt CallRecords through the pipeline (#35)"
```

---

## Phase C — Experiment runner

### Task C1: Experiment config: load, validate, config_hash, immutability

**Files:**
- Create: `content_bank/author/experiment_config.py`, `experiments/example.json`
- Test: `content_bank/tests/test_experiment_config.py`

**Interfaces:**
- Produces:
  - `load(path) -> dict`
  - `validate(config) -> None` (raises `ValueError` with a clear message on any problem)
  - `config_hash(config, *, corpus_rev: str, prompt_version: str) -> str`
  - `PROMPT_VERSION: str` constant (bump when prompt builders/rubric change).
  - `check_immutable(existing_manifest: dict | None, new_hash: str) -> None` — raises if an
    existing manifest's `config_hash` differs.
  - `CREDENTIAL_KEYS: frozenset` used by validation.

- [ ] **Step 1: Write the failing test**

```python
# content_bank/tests/test_experiment_config.py
import unittest
from content_bank.author import experiment_config as ec

VALID = {
    "schema_version": 1, "name": "e1", "book": "PHP", "units": ["PHP-001"],
    "routes": {s: {"backend": "llm_core", "model": "m"} for s in
               ("brief","draft","repair","review_r1","review_r2","revise")},
    "gates": {"max_repair": 2, "dim_cap": 6},
    "evaluator": {"backend": "claude", "model": "sonnet"},
}

class ConfigTest(unittest.TestCase):
    def test_valid_passes(self):
        ec.validate(VALID)  # no raise

    def test_missing_stage_rejected(self):
        bad = {**VALID, "routes": {"brief": {"backend": "llm_core"}}}
        with self.assertRaises(ValueError):
            ec.validate(bad)

    def test_credential_field_rejected(self):
        bad = {**VALID, "routes": {**VALID["routes"],
               "draft": {"backend": "claude", "api_key": "sk-x"}}}
        with self.assertRaises(ValueError):
            ec.validate(bad)

    def test_unknown_backend_rejected(self):
        bad = {**VALID, "evaluator": {"backend": "openai", "model": "x"}}
        with self.assertRaises(ValueError):
            ec.validate(bad)

    def test_hash_stable_and_sensitive(self):
        h1 = ec.config_hash(VALID, corpus_rev="abc", prompt_version="1")
        h2 = ec.config_hash(VALID, corpus_rev="abc", prompt_version="1")
        h3 = ec.config_hash(VALID, corpus_rev="DEF", prompt_version="1")
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, h3)

    def test_immutable_guard(self):
        ec.check_immutable(None, "h")            # first run ok
        ec.check_immutable({"config_hash": "h"}, "h")  # resume ok
        with self.assertRaises(ValueError):
            ec.check_immutable({"config_hash": "h"}, "OTHER")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_experiment_config -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
# content_bank/author/experiment_config.py
"""Load, validate, and hash a named experiment configuration.

The config assigns a backend/model Route to every LLM stage plus a fixed
evaluator route. The experiment NAME is the identity; a config_hash over the
canonicalized config (+ corpus revision + prompt version) makes "identical
configuration" precise so a run can resume only when nothing changed.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

from .routing import STAGES

KNOWN_BACKENDS = frozenset({"llm_core", "claude"})
CREDENTIAL_KEYS = frozenset({"api_key", "apikey", "token", "authorization",
                             "secret", "password", "ark_api_key"})
PROMPT_VERSION = "1"   # bump when brief/draft prompt builders or rubric change


def load(path) -> dict:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def _scan_credentials(obj, where="config"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in CREDENTIAL_KEYS:
                raise ValueError(f"credential-like field '{k}' not allowed in {where}")
            _scan_credentials(v, f"{where}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _scan_credentials(v, f"{where}[{i}]")


def validate(config: dict) -> None:
    _scan_credentials(config)
    for key in ("schema_version", "name", "book", "routes", "evaluator"):
        if key not in config:
            raise ValueError(f"config missing required key: {key}")
    routes = config["routes"]
    missing = [s for s in STAGES if s not in routes]
    if missing:
        raise ValueError(f"routes missing stages: {missing}")
    for name, r in list(routes.items()) + [("evaluator", config["evaluator"])]:
        if r.get("backend") not in KNOWN_BACKENDS:
            raise ValueError(f"route {name}: unknown backend {r.get('backend')!r}")
    gates = config.get("gates") or {}
    if not (0 <= int(gates.get("max_repair", 2)) <= 10):
        raise ValueError("gates.max_repair out of range 0..10")
    if int(gates.get("dim_cap", 6)) < 1:
        raise ValueError("gates.dim_cap must be >= 1")


def config_hash(config: dict, *, corpus_rev: str, prompt_version: str) -> str:
    canon = json.dumps(config, sort_keys=True, ensure_ascii=False)
    blob = f"{canon}\x00corpus={corpus_rev}\x00prompt={prompt_version}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def check_immutable(existing_manifest: dict | None, new_hash: str) -> None:
    if existing_manifest and existing_manifest.get("config_hash") != new_hash:
        raise ValueError(
            "experiment name already exists with a DIFFERENT configuration "
            f"(saved {existing_manifest.get('config_hash')!r} != new {new_hash!r}); "
            "use a new name or restore the original config to resume")
```

Also write `experiments/example.json` = the `VALID`-shaped config from the spec.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_experiment_config -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/experiment_config.py experiments/example.json content_bank/tests/test_experiment_config.py
git commit -m "feat(experiments): experiment config load/validate/hash + immutability (#35)"
```

---

### Task C2: quality_eval accepts an evaluator Route + sink

**Files:**
- Modify: `content_bank/author/quality_eval.py`
- Test: `content_bank/tests/test_quality_eval.py`

**Interfaces:**
- Consumes: `routing.Route`, seam `llm(prompt, route)`.
- Produces: `evaluate_dimension_fit(items, *, brief=None, route: Route, sink=None,
  unit_id=None)` — calls the seam with `route`, records a `CallRecord` (stage `"evaluate"`)
  when a sink is given. `evaluate(...)` gains an `evaluator_route` param used for fit.

Note: current `evaluate_dimension_fit(..., reviewer=llm, model=None)` passes a bare callable.
Change the internal call to `llm(prompt, route)` shape. Keep a back-compat path for the
existing CLI (`--fit-backend/--fit-model` → `Route(fit_backend, fit_model)`).

- [ ] **Step 1: Write the failing test**

```python
# add to content_bank/tests/test_quality_eval.py
from content_bank.author.routing import Route

class FitRouteTest(unittest.TestCase):
    def test_fit_uses_given_route(self):
        import content_bank.author.quality_eval as qe
        seen = {}
        def fake_llm(prompt, route):
            seen["model"] = route.model
            return '[{"id":"X","status":"accurate","dominant":"D1"}]'
        with mock.patch.object(qe, "llm", fake_llm):
            qe.evaluate_dimension_fit([{"id": "X", "dimension": "D1"}],
                                      route=Route("claude", "sonnet"))
        self.assertEqual(seen["model"], "sonnet")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_quality_eval -v`
Expected: FAIL (unexpected keyword `route`).

- [ ] **Step 3: Write minimal implementation**

Refactor `evaluate_dimension_fit` to take `route` (and optional `sink`, `unit_id`), call
`llm(prompt, route)`; on sink, add a `CallRecord(stage="evaluate", ...)`. In `evaluate()`,
build `evaluator_route` from either the new `evaluator_route` param or the legacy
`fit_backend`/`fit_model` and pass it down. Keep the CLI wiring working.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_quality_eval -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/quality_eval.py content_bank/tests/test_quality_eval.py
git commit -m "feat(experiments): evaluator takes an explicit Route + sink (#35)"
```

---

### Task C3: Gate-trace capture

**Files:**
- Modify: `content_bank/author/build_cli.py`
- Test: `content_bank/tests/test_build_cli.py`

**Interfaces:**
- Produces: `_repair_to_clean(...)` optionally appends to a `trace: list` — per round records
  `{round, hard_flags, soft_flags, route}`; and reports `first_pass_clean` (bool) + final
  status. `build_pericope`/`build_section` accept `gate_trace_dir=None`; when set, write
  `gate_trace_dir/UNIT.json` = `{initial, rounds, item_drops, first_pass_clean, final_pass}`.

- [ ] **Step 1: Write the failing test**

```python
# add to content_bank/tests/test_build_cli.py
class GateTraceTest(unittest.TestCase):
    def test_trace_records_initial_and_rounds(self):
        # llm returns a draft that fails a gate once then passes; assert the
        # written gate_trace UNIT.json has first_pass_clean False and >=1 round.
        ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_build_cli -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Thread an optional `trace` list into `_repair_to_clean`; append a dict per round with the
merged hard/soft flags and the repair route model. Capture `first_pass_clean = not (hard or
soft)` before the loop. In `build_pericope`/`build_section`, when `gate_trace_dir` is set,
`_write_json(gate_trace_dir / f"{uid}.json", {...})`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_build_cli -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/build_cli.py content_bank/tests/test_build_cli.py
git commit -m "feat(experiments): persist per-unit gate traces (#35)"
```

---

### Task C4: Experiment runner + results tree + report

**Files:**
- Create: `content_bank/author/experiment_cli.py`, `content_bank/author/experiment_report.py`
- Modify: `.gitignore` (add `experiments-out/`)
- Test: `content_bank/tests/test_experiment_runner.py`, `test_experiment_report.py`

**Interfaces:**
- Consumes: `experiment_config`, `routing.RouteConfig.from_experiment`, `build_cli.run`
  (with `routes`, `sink`, `experiment`, `gate_trace_dir`), `quality_eval.evaluate`,
  `telemetry.TelemetrySink`.
- Produces:
  - `experiment_report.build_report(out_dir) -> dict` — extended metrics from `calls.jsonl`
    + evaluator report + gate traces.
  - `experiment_cli.run_experiment(config_path, *, out_root="experiments-out", resume=False,
    now: str, corpus_rev: str) -> dict` — writes the results tree, returns the manifest.
  - `experiment_cli.main(argv)` — `validate | run [--resume] | evaluate NAME | compare`.
  - `_subscription_snapshot() -> dict` — best-effort; default `{"available": False,
    "reason": "no documented machine-readable Claude subscription allowance"}`.
  - `_corpus_rev() -> str` — `git rev-parse HEAD:corpus/canon` (or `"unknown"`).

- [ ] **Step 1: Write the failing test** (runner, fully mocked seam)

```python
# content_bank/tests/test_experiment_runner.py
import json, pathlib, tempfile, unittest
from unittest import mock
from content_bank.author import experiment_cli as ex

CONFIG = {
    "schema_version": 1, "name": "t1", "book": "PHP", "units": ["PHP-001"],
    "routes": {s: {"backend": "llm_core", "model": "m"} for s in
               ("brief","draft","repair","review_r1","review_r2","revise")},
    "gates": {"max_repair": 2, "dim_cap": 6},
    "evaluator": {"backend": "llm_core", "model": "m"},
}

class RunnerTest(unittest.TestCase):
    def _write_cfg(self, d):
        p = pathlib.Path(d) / "t1.json"
        p.write_text(json.dumps(CONFIG)); return p

    def test_run_writes_manifest_calls_and_report(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._write_cfg(d)
            with mock.patch("content_bank.author.build_cli.run",
                            return_value={"ok": ["PHP-001"], "failed": {}}) as run, \
                 mock.patch("content_bank.author.quality_eval.evaluate",
                            return_value={"runs": {}}):
                man = ex.run_experiment(cfg, out_root=d + "/out",
                                        now="2026-07-31T00:00:00Z", corpus_rev="abc")
            out = pathlib.Path(d) / "out" / "t1"
            self.assertTrue((out / "manifest.json").exists())
            self.assertIn("config_hash", man)
            run.assert_called_once()
            # routes passed through
            self.assertIn("routes", run.call_args.kwargs)

    def test_resume_refuses_changed_config(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._write_cfg(d)
            out = pathlib.Path(d) / "out" / "t1"; out.mkdir(parents=True)
            (out / "manifest.json").write_text(json.dumps({"config_hash": "DIFFERENT"}))
            with self.assertRaises(ValueError):
                ex.run_experiment(cfg, out_root=d + "/out",
                                  now="2026-07-31T00:00:00Z", corpus_rev="abc")

    def test_snapshot_reports_unavailable_honestly(self):
        snap = ex._subscription_snapshot()
        self.assertFalse(snap["available"])
        self.assertIn("reason", snap)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_experiment_runner -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation**

`experiment_report.build_report(out_dir)`: read `calls.jsonl`, aggregate calls & tokens by
`stage`/`backend`/`model`; count Claude calls; read `report.json` (evaluator) for D1–D8 fit;
read gate traces for first-pass/final rates + repairs; compute per-unit and per-accepted-item
tokens/time/cost; set `evaluator_is_drafter` by comparing the evaluator route to the draft
route. Return a dict.

`experiment_cli.run_experiment`:
1. `config = experiment_config.load(path)`; `experiment_config.validate(config)`.
2. `h = config_hash(config, corpus_rev=corpus_rev, prompt_version=PROMPT_VERSION)`.
3. `out = Path(out_root)/config["name"]`; load existing manifest if any;
   `check_immutable(existing, h)`.
4. `sink = TelemetrySink(out/"calls.jsonl")`.
5. `routes = RouteConfig.from_experiment(config["routes"])`.
6. snapshot before → `build_cli.run(book, units=config.get("units"), routes=routes,
   review_on=True, max_repair=gates.max_repair, dim_cap=gates.dim_cap, sink=sink,
   experiment=config["name"], drafts_dir=out/"drafts", briefs_dir=out/"briefs",
   verdicts_dir=out/"verdicts", gate_trace_dir=out/"gate_traces",
   manifest_path=out/"run_manifest.json")` → snapshot after.
7. `quality_eval.evaluate(book, [<draft run>], evaluator_route=<from config["evaluator"]>,
   ...)` writing `report.json` under `out`.
8. Write `manifest.json` = frozen config + `config_hash` + `corpus_rev` +
   `prompt_version` + route matrix + before/after snapshots + `created_at=now` + build result.
9. `experiment_report.build_report(out)` → write `report.json` (or merge). Return manifest.

`main(argv)`: argparse subcommands. `run` passes `now` from
`datetime.datetime.now(datetime.UTC).isoformat()` and `corpus_rev` from `_corpus_rev()`
(the CLI may read the clock; the tested `run_experiment` takes them as args).

- [ ] **Step 4: Run tests**

Run: `uv run python -m unittest content_bank.tests.test_experiment_runner content_bank.tests.test_experiment_report -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/experiment_cli.py content_bank/author/experiment_report.py .gitignore content_bank/tests/test_experiment_runner.py content_bank/tests/test_experiment_report.py
git commit -m "feat(experiments): experiment runner, results tree, extended report (#35)"
```

---

## Phase D — Comparison

### Task D1: Experiment-column comparison page

**Files:**
- Modify: `content_bank/author/compare_html.py`, `content_bank/author/experiment_cli.py`
- Test: `content_bank/tests/test_compare_html.py`

**Interfaces:**
- Produces:
  - `compare_html.render_experiments(book, experiment_dirs: list[pathlib.Path]) -> str` —
    one HTML page; each column = one experiment, header shows the route matrix + aggregate
    telemetry; per-unit items/citations/leader-refs/verdict badges/accept-export preserved
    (reuse the existing per-item rendering helpers).
  - `experiment_cli` `compare --book PHP --experiments A,B` → writes the HTML.

- [ ] **Step 1: Write the failing test**

```python
# add to content_bank/tests/test_compare_html.py
class ExperimentColumnsTest(unittest.TestCase):
    def test_render_shows_route_matrix_and_items(self):
        # Build two fake experiment out-dirs with a manifest (route matrix +
        # telemetry aggregate), drafts/PHP-001.json, verdicts. Render and assert
        # the HTML contains both experiment names, a stage->model cell (e.g.
        # "draft" + "opus"), and an item's text + a citation highlight span.
        ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest content_bank.tests.test_compare_html -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Add `render_experiments(...)` that loads each experiment's `manifest.json` (route matrix +
aggregates) and `drafts/` + `verdicts/`, and renders columns reusing the existing item/
citation/leader-ref/verdict helpers. Add the `compare` subcommand.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest content_bank.tests.test_compare_html -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add content_bank/author/compare_html.py content_bank/author/experiment_cli.py content_bank/tests/test_compare_html.py
git commit -m "feat(experiments): experiment-column comparison page (#35)"
```

---

### Task D2: Documentation + full-suite gate

**Files:**
- Create: `docs/content_experiment_usage.md`
- Modify: `docs/content_builder_usage.md`, `docs/content_build_terminology.md`, `CLAUDE.md`

- [ ] **Step 1: Write `docs/content_experiment_usage.md`** — config format; validate/run/
  resume/evaluate/compare commands; results-tree layout; **fair-comparison recipe**
  (identical units, corpus revision, prompts, gates, and a fixed evaluator route across
  compared experiments). Add cross-links + glossary terms (experiment, route, route matrix,
  CallRecord/telemetry) to the two content docs, and a one-line pointer in `CLAUDE.md`'s
  `content_bank/` bullet.

- [ ] **Step 2: Run the full suites**

Run: `uv run python -m unittest discover -s content_bank/tests -v && uv run python -m unittest discover -s llm_core/tests -v && uv run python -m unittest discover -s corpus/tests -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add docs/content_experiment_usage.md docs/content_builder_usage.md docs/content_build_terminology.md CLAUDE.md
git commit -m "docs(experiments): experiment usage + fair-comparison recipe (#35)"
```

---

## Self-Review

**Spec coverage:** per-stage routing (A1–A4), telemetry normalization both backends (B1–B2),
per-attempt CallRecords (B3), named immutable config + hash + resume (C1), evaluator route
(C2), gate traces (C3), runner + results + extended metrics + honest subscription snapshot
(C4), experiment-column comparison (D1), fair-comparison docs + tests (D2). All #35
acceptance criteria mapped.

**Placeholder scan:** the four test bodies marked `...` (A4-fixture, B3, C3, D1) intentionally
defer fixture wiring to existing patterns in the same test file; every one names the exact
assertions required. All production code steps carry real code.

**Type consistency:** stage names `brief/draft/repair/review_r1/review_r2/revise` (+
`evaluate` telemetry stage) used identically across `routing.STAGES`, config validation,
`CallRecord.stage`, and runner. `LLMResult`/`TokenUsage`/`CallRecord` field names match
between `telemetry.py`, the seam (B2), and recording (B3). `RouteConfig.from_experiment`
and `.single` signatures consistent A1→A4→C4.
