# Group-batched content build mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `group` execution mode to the content builder that batches a section-group (a section + its pericopes) into one LLM call per stage, splitting each response back into the existing per-unit artifacts.

**Architecture:** A new `build_group.py` orchestrates batched stages by *wrapping the existing per-unit prompt outputs* in a `{"units": {unit_id: payload}}` JSON envelope, sending one call, splitting the envelope, then handing each unit's slice to the **unchanged** per-unit gates/repair/manifest/store code from `build_cli.py`. A `stop_reason`-driven bisection guard splits an oversized group and retries halves down to singletons.

**Tech Stack:** Python 3 (uv), stdlib `json`/`unittest`; existing `content_bank/author/` modules (`build_cli`, `build_*_prompt`, `review`, `gates`, `manifest`, `routing`, `telemetry`, `llm`); corpus via `content_bank/lib/corpus_bridge` and `corpus.lib.sections`.

## Global Constraints

- Network-free tests: the `llm` seam (`content_bank/author/llm.py:llm`) is always mocked in tests; never call a live provider.
- Group mode changes only LLM I/O batching. Downstream (gates, `manifest`, `store_writer`, provenance, run layout) stays per-unit and byte-identical.
- The envelope is exactly `{"units": {"<unit_id>": <payload>}}`. Brief payload = brief markdown string; draft/repair/revise payload = the unit's JSON item array; review payload = `{item_id: {"verdict","notes"}}`.
- Truncation guard fires on `stop_reason == "max_tokens"` OR a missing expected unit id OR an unparseable envelope → bisect unit list, recurse to singletons; a failing singleton raises for that unit only.
- `--group` is orthogonal to `--backend` (no warning on `llm_core`).
- Batched telemetry: `record_call` with `unit_id=<section_id>`, `kind="group"`.
- Test command: `uv run python -m unittest discover -s content_bank/tests -v`.

---

## File Structure

- **Create** `content_bank/author/build_group_prompt.py` — group envelope prompt builders (wrap per-unit prompts).
- **Create** `content_bank/author/build_group.py` — group orchestration: `groups_for_book`, envelope parse, bisection call, batched brief/draft/repair, `group_run`.
- **Modify** `content_bank/author/review.py` — add `review_group` and `revise_group` (batched, failed-units-only).
- **Modify** `content_bank/author/build_cli.py` — `--group` flag in `main()`; dispatch to `build_group.group_run`.
- **Create** `content_bank/tests/test_build_group_prompt.py`
- **Create** `content_bank/tests/test_build_group.py`
- **Create** `content_bank/tests/test_review_group.py`
- **Modify** `docs/content_builder_usage.md` — document `--group`.
- **Modify** `docs/content_build_terminology.md` — add a "group mode" glossary entry.

Fixture book for tests: **PHP** (built, committed corpus; offline). Its sections come from `corpus.lib.sections.load("PHP")`.

---

### Task 1: Group discovery + envelope parsing (`build_group.py` foundations)

**Files:**
- Create: `content_bank/author/build_group.py`
- Test: `content_bank/tests/test_build_group.py`

**Interfaces:**
- Produces:
  - `groups_for_book(book) -> list[tuple[str, list[str]]]` — `(section_id, [pericope_id,...])`, pericopes in span order; section-only unit list for a batched stage is `[section_id, *pericope_ids]`.
  - `class Truncated(Exception)` — raised by `parse_units` when the envelope is short/unparseable.
  - `parse_units(text, expected_ids) -> dict[str, object]` — extract `{"units": {...}}`; raise `Truncated` if unparseable or any id in `expected_ids` is missing.

- [ ] **Step 1: Write failing test for `groups_for_book`**

```python
# content_bank/tests/test_build_group.py
import unittest
from content_bank.author import build_group

class TestGroupsForBook(unittest.TestCase):
    def test_php_groups_partition_pericopes(self):
        groups = build_group.groups_for_book("PHP")
        self.assertTrue(groups)
        # every group is (section_id, [pericope_ids...]) with pericopes present
        for sid, pids in groups:
            self.assertTrue(sid.startswith("PHP-S"))
            self.assertTrue(all(p.startswith("PHP-") and "-S" not in p for p in pids))
        # pericopes partition: each PHP pericope appears in exactly one group
        from content_bank.lib import corpus_bridge
        all_peris = [p["id"] for p in corpus_bridge.pericopes("PHP")]
        seen = [p for _, pids in groups for p in pids]
        self.assertEqual(sorted(seen), sorted(all_peris))
```

- [ ] **Step 2: Run, expect fail** — `uv run python -m unittest content_bank.tests.test_build_group -v` → FAIL (module/attr missing).

- [ ] **Step 3: Implement `groups_for_book`**

```python
# content_bank/author/build_group.py
"""Group-batched execution: one LLM call per stage over a section-group."""
import json, re
from corpus.lib import sections as _sections
from ..lib import corpus_bridge

class Truncated(Exception):
    """Envelope missing units / unparseable — trigger bisection."""

def groups_for_book(book):
    peris = corpus_bridge.pericopes(book)
    ids = [p["id"] for p in peris]
    out = []
    for sec in _sections.load(book)["sections"]:
        i, j = ids.index(sec["first_pericope"]), ids.index(sec["last_pericope"])
        out.append((sec["id"], ids[i:j + 1]))
    return out
```

- [ ] **Step 4: Run, expect pass.**

- [ ] **Step 5: Write failing test for `parse_units`**

```python
class TestParseUnits(unittest.TestCase):
    def test_valid_envelope(self):
        text = '```json\n{"units": {"A": [1], "B": [2]}}\n```'
        self.assertEqual(build_group.parse_units(text, ["A", "B"]), {"A": [1], "B": [2]})
    def test_missing_unit_raises_truncated(self):
        with self.assertRaises(build_group.Truncated):
            build_group.parse_units('{"units": {"A": [1]}}', ["A", "B"])
    def test_unparseable_raises_truncated(self):
        with self.assertRaises(build_group.Truncated):
            build_group.parse_units('{"units": {"A": [1', ["A"])
```

- [ ] **Step 6: Run, expect fail.**

- [ ] **Step 7: Implement `parse_units`**

```python
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

def parse_units(text, expected_ids):
    m = _FENCE.search(text)
    body = m.group(1) if m else text
    s, e = body.find("{"), body.rfind("}")
    if s == -1 or e <= s:
        raise Truncated(f"no JSON object in output: {text[:200]!r}")
    try:
        obj = json.loads(body[s:e + 1])
    except json.JSONDecodeError as exc:
        raise Truncated(str(exc))
    units = obj.get("units")
    if not isinstance(units, dict):
        raise Truncated("no 'units' object")
    missing = [u for u in expected_ids if u not in units]
    if missing:
        raise Truncated(f"missing units: {missing}")
    return {u: units[u] for u in expected_ids}
```

- [ ] **Step 8: Run, expect pass.**

- [ ] **Step 9: Commit** — `git add content_bank/author/build_group.py content_bank/tests/test_build_group.py && git commit -m "feat(group): group discovery + envelope parsing"`

---

### Task 2: Group envelope prompt builders (`build_group_prompt.py`)

Wrap the existing per-unit prompt outputs in the envelope instruction. Maximum fidelity: each unit gets its exact tuned prompt (correct schema for its kind); the wrapper reframes each per-unit "Return a JSON array" as "place that array as this unit's value in the single top-level object."

**Files:**
- Create: `content_bank/author/build_group_prompt.py`
- Test: `content_bank/tests/test_build_group_prompt.py`

**Interfaces:**
- Consumes: `build_brief_prompt.build`, `build_section_brief_prompt.build`, `build_draft_prompt.build`, `build_section_draft_prompt.build`.
- Produces:
  - `brief_envelope(unit_ids, book) -> str`
  - `draft_envelope(unit_ids, book, briefs: dict[str,str]) -> str`
  - `_unit_kind(unit_id) -> "section"|"pericope"` (a `-S` in the id ⇒ section).

- [ ] **Step 1: Write failing test**

```python
# content_bank/tests/test_build_group_prompt.py
import unittest
from content_bank.author import build_group_prompt as bgp

class TestGroupPrompt(unittest.TestCase):
    def test_brief_envelope_names_each_unit_and_envelope(self):
        ids = ["PHP-S1", "PHP-001"]
        text = bgp.brief_envelope(ids, "PHP")
        for u in ids:
            self.assertIn(u, text)
        self.assertIn('"units"', text)
        self.assertIn("PHP-S1", text)  # section sub-pack present
    def test_draft_envelope_embeds_briefs(self):
        ids = ["PHP-S1", "PHP-001"]
        briefs = {"PHP-S1": "ARC-BRIEF-MARKER", "PHP-001": "PERI-BRIEF-MARKER"}
        text = bgp.draft_envelope(ids, "PHP", briefs)
        self.assertIn("ARC-BRIEF-MARKER", text)
        self.assertIn("PERI-BRIEF-MARKER", text)
        self.assertIn('"units"', text)
```

- [ ] **Step 2: Run, expect fail.**

- [ ] **Step 3: Implement**

```python
# content_bank/author/build_group_prompt.py
"""Group envelope prompts: wrap per-unit prompts, ask for one {"units":{...}} object."""
from . import (build_brief_prompt, build_section_brief_prompt,
               build_draft_prompt, build_section_draft_prompt)

def _unit_kind(unit_id):
    return "section" if "-S" in unit_id else "pericope"

_BRIEF_HEADER = (
    "# GROUP BRIEF BATCH\n\n"
    "Below are {n} independent brief-writing tasks, one per unit. Complete ALL of "
    "them. Each task tells you to 'Produce the ... BRIEF'; do that for each, then "
    "return ONE JSON object and nothing else:\n"
    '  {{"units": {{"<UNIT_ID>": "<that unit\'s full brief markdown as a JSON '
    'string>", ...}}}}\n'
    "Use EXACTLY these unit ids as keys: {ids}. Do not merge, summarize across, or "
    "omit any unit.\n\n---\n")

_DRAFT_HEADER = (
    "# GROUP DRAFT BATCH\n\n"
    "Below are {n} independent drafting tasks, one per unit. Complete ALL of them. "
    "Each task ends by asking for a JSON array; in this batch you instead place that "
    "array as the unit's value in ONE top-level object, and return nothing else:\n"
    '  {{"units": {{"<UNIT_ID>": [ ...that unit\'s items... ], ...}}}}\n'
    "Use EXACTLY these unit ids as keys: {ids}. Each unit keeps its own schema (a "
    "section unit produces throughline/threads/arc questions; a pericope unit "
    "produces its item types). Do not merge across units or omit any.\n\n---\n")

def _brief_subpack(unit_id, book):
    if _unit_kind(unit_id) == "section":
        return build_section_brief_prompt.build(unit_id, book)
    return build_brief_prompt.build(unit_id, book)

def _draft_subpack(unit_id, book, brief):
    if _unit_kind(unit_id) == "section":
        return build_section_draft_prompt.build(unit_id, book, brief)
    return build_draft_prompt.build(unit_id, book, brief)

def brief_envelope(unit_ids, book):
    head = _BRIEF_HEADER.format(n=len(unit_ids), ids=", ".join(unit_ids))
    blocks = [f"\n===== UNIT {u} =====\n{_brief_subpack(u, book)}" for u in unit_ids]
    return head + "\n".join(blocks)

def draft_envelope(unit_ids, book, briefs):
    head = _DRAFT_HEADER.format(n=len(unit_ids), ids=", ".join(unit_ids))
    blocks = [f"\n===== UNIT {u} =====\n{_draft_subpack(u, book, briefs[u])}"
              for u in unit_ids]
    return head + "\n".join(blocks)
```

- [ ] **Step 4: Run, expect pass.**

- [ ] **Step 5: Commit** — `git commit -am "feat(group): envelope prompt builders wrapping per-unit prompts"`

---

### Task 3: Bisecting group call + batched brief/draft with per-unit gates

**Files:**
- Modify: `content_bank/author/build_group.py`
- Test: `content_bank/tests/test_build_group.py`

**Interfaces:**
- Consumes: `build_cli._llm_with_backoff` semantics but needs the full `LLMResult` (for `stop_reason`); `build_group_prompt`; `build_cli._parse_items` not used (envelope path); `gates.run_all`, `gates.dimension_cap_check`, `build_cli._repair_to_clean`.
- Produces:
  - `group_call(build_prompt, unit_ids, *, route, attr, stage, sink, experiment) -> dict[str,object]` — sends the envelope; on `Truncated` or `stop_reason=="max_tokens"`, bisects `unit_ids` and merges halves; a singleton that still fails raises `Truncated`.
  - `build_group_briefs(unit_ids, book, *, route, ...) -> dict[str,str]`
  - `build_group_drafts(unit_ids, book, briefs, *, routes, book_allowed_fn, ...) -> dict[str, list]` (draft envelope → per-unit gate+repair via `_repair_to_clean`).

Note: `group_call` takes `build_prompt(ids) -> str` so bisection can rebuild the prompt for a sub-list.

- [ ] **Step 1: Write failing test — happy path draft (mocked llm)**

```python
# add to content_bank/tests/test_build_group.py
from unittest import mock
from content_bank.author.telemetry import LLMResult, TokenUsage
from content_bank.author import routing

def _res(text, stop="end_turn"):
    return LLMResult(text=text, usage=TokenUsage(), requested_model="opus",
                     actual_model="opus", stop_reason=stop, duration_ms=1,
                     usage_source="provider")

class TestGroupCall(unittest.TestCase):
    def test_group_call_returns_units(self):
        env = '{"units": {"A": [1], "B": [2]}}'
        with mock.patch("content_bank.author.build_group.llm",
                        return_value=_res(env)) as m:
            out = build_group.group_call(lambda ids: "P:" + ",".join(ids),
                                         ["A", "B"], route=routing.Route("claude", "opus"))
            self.assertEqual(out, {"A": [1], "B": [2]})
            self.assertEqual(m.call_count, 1)

    def test_group_call_bisects_on_truncation(self):
        # full group truncates; each singleton succeeds
        def fake(prompt, route):
            ids = prompt.split("P:")[1].split(",")
            if len(ids) > 1:
                return _res('{"units": {}}', stop="max_tokens")
            u = ids[0]
            return _res(json.dumps({"units": {u: [u]}}))
        with mock.patch("content_bank.author.build_group.llm", side_effect=fake) as m:
            out = build_group.group_call(lambda ids: "P:" + ",".join(ids),
                                         ["A", "B"], route=routing.Route("claude", "opus"))
            self.assertEqual(out, {"A": ["A"], "B": ["B"]})
            self.assertGreaterEqual(m.call_count, 3)  # full + 2 singletons

    def test_group_call_singleton_truncation_raises(self):
        with mock.patch("content_bank.author.build_group.llm",
                        return_value=_res('{"units": {}}', stop="max_tokens")):
            with self.assertRaises(build_group.Truncated):
                build_group.group_call(lambda ids: "P:" + ",".join(ids), ["A"],
                                       route=routing.Route("claude", "opus"))
```

- [ ] **Step 2: Run, expect fail.**

- [ ] **Step 3: Implement `group_call`** (add imports `from .llm import llm`, `from .telemetry import record_call`, and reuse `build_cli._Attr`/`_NO_ATTR` via a local default)

```python
# in build_group.py
from .llm import llm
from .telemetry import record_call, NullSink

def group_call(build_prompt, unit_ids, *, route, sink=None, experiment=None,
               stage="draft", section_id=None, tries=4):
    """One batched envelope call over unit_ids. On truncation (max_tokens / missing
    unit / unparseable) bisect and merge halves; a failing singleton raises."""
    prompt = build_prompt(list(unit_ids))
    res = llm(prompt, route)
    record_call(sink, experiment=experiment, stage=stage,
                unit_id=section_id or (unit_ids[0] if unit_ids else None),
                kind="group", attempt=1, route=route, prompt=prompt, result=res)
    truncated = res.stop_reason == "max_tokens"
    if not truncated:
        try:
            return parse_units(res.text, unit_ids)
        except Truncated:
            truncated = True
    if len(unit_ids) == 1:
        raise Truncated(f"singleton {unit_ids[0]} still truncated/omitted")
    mid = len(unit_ids) // 2
    left = group_call(build_prompt, unit_ids[:mid], route=route, sink=sink,
                      experiment=experiment, stage=stage, section_id=section_id)
    right = group_call(build_prompt, unit_ids[mid:], route=route, sink=sink,
                       experiment=experiment, stage=stage, section_id=section_id)
    return {**left, **right}
```

- [ ] **Step 4: Run, expect pass.**

- [ ] **Step 5: Write failing test — `build_group_briefs` / `build_group_drafts`** with mocked `group_call` returning briefs then drafts; assert each unit gated (use one clean item per unit; monkeypatch `gates.run_all`→`{}` and `dimension_cap_check`→`{}` to isolate batching from gate content).

```python
class TestBuildGroupStages(unittest.TestCase):
    def test_drafts_gate_each_unit(self):
        ids = ["PHP-S1", "PHP-001"]
        briefs = {u: "brief-" + u for u in ids}
        drafts_env = {u: [{"id": u + "-1"}] for u in ids}
        with mock.patch.object(build_group, "group_call", return_value=drafts_env), \
             mock.patch("content_bank.author.gates.run_all", return_value={}), \
             mock.patch("content_bank.author.gates.dimension_cap_check", return_value={}):
            out = build_group.build_group_drafts(
                ids, "PHP", briefs, routes=routing.RouteConfig.single("claude", "opus"),
                max_repair=0)
            self.assertEqual(set(out), set(ids))
            self.assertEqual(out["PHP-001"], [{"id": "PHP-001-1"}])
```

- [ ] **Step 6: Run, expect fail.**

- [ ] **Step 7: Implement `build_group_briefs` and `build_group_drafts`**

```python
from . import build_group_prompt, gates, build_cli

def build_group_briefs(unit_ids, book, *, route, sink=None, experiment=None,
                       section_id=None):
    return group_call(lambda ids: build_group_prompt.brief_envelope(ids, book),
                      unit_ids, route=route, sink=sink, experiment=experiment,
                      stage="brief", section_id=section_id)

def _allowed_for(book, unit_id):
    if _unit_kind(unit_id) == "section":
        return gates.section_allowed(book, unit_id)
    return gates.pericope_allowed(book, unit_id)

def build_group_drafts(unit_ids, book, briefs, *, routes, max_repair=2,
                       dim_cap=gates.DEFAULT_DIM_CAP, sink=None, experiment=None,
                       section_id=None):
    raw = group_call(
        lambda ids: build_group_prompt.draft_envelope(ids, book, briefs),
        unit_ids, route=routes.draft, sink=sink, experiment=experiment,
        stage="draft", section_id=section_id)
    out = {}
    for u in unit_ids:
        items = raw[u]
        allowed = _allowed_for(book, u)
        # draft-stage envelope prompt for this unit (for repair context)
        prompt = build_group_prompt._draft_subpack(u, book, briefs[u])
        out[u] = build_cli._repair_to_clean(
            prompt, items, book, allowed, max_repair=max_repair, dim_cap=dim_cap,
            where="group-", repair_route=routes.repair)
    return out
```

- [ ] **Step 8: Run, expect pass.**

- [ ] **Step 9: Commit** — `git commit -am "feat(group): bisecting group call + batched brief/draft with per-unit gates"`

---

### Task 4: Batched review + revise (failed-units-only)

**Files:**
- Modify: `content_bank/author/review.py`
- Test: `content_bank/tests/test_review_group.py`

**Interfaces:**
- Produces:
  - `review_group(items_by_unit, *, ctx_by_unit, book, r1_route, r2_route, sink, experiment, section_id) -> list[dict]` — two lens calls; each returns `{"reviewer": name, "verdicts_by_unit": {unit: {item_id: verdict}}}`.
  - `revise_group(items_by_unit, group_verdicts, *, ctx_by_unit, route, sink, experiment, section_id) -> dict[str, list]` — revises only units that have ≥1 failed item; passing units returned unchanged.
  - `failed_units(group_verdicts) -> set[str]`
- `ctx_by_unit[unit] = {"passage_text": ..., "brief": ...}`.

- [ ] **Step 1: Write failing test — only failed units revised**

```python
# content_bank/tests/test_review_group.py
import json, unittest
from unittest import mock
from content_bank.author import review
from content_bank.author.telemetry import LLMResult, TokenUsage
from content_bank.author import routing

def _res(text):
    return LLMResult(text=text, usage=TokenUsage(), requested_model="opus",
                     actual_model="opus", stop_reason="end_turn", duration_ms=1,
                     usage_source="provider")

class TestReviseGroup(unittest.TestCase):
    def test_only_failed_units_sent(self):
        items = {"A": [{"id": "A-1"}], "B": [{"id": "B-1"}]}
        gv = [{"reviewer": "r1",
               "verdicts_by_unit": {"A": {"A-1": {"verdict": "fail", "notes": "x"}},
                                    "B": {"B-1": {"verdict": "pass", "notes": ""}}}}]
        ctx = {u: {"passage_text": "p", "brief": "b"} for u in items}
        captured = {}
        def fake(prompt, route):
            captured["prompt"] = prompt
            return _res('{"units": {"A": [{"id": "A-1", "fixed": true}]}}')
        with mock.patch("content_bank.author.review.llm", side_effect=fake):
            out = review.revise_group(items, gv, ctx_by_unit=ctx,
                                      route=routing.Route("claude", "opus"))
        self.assertIn("A-1", captured["prompt"])
        self.assertNotIn("B-1", captured["prompt"])   # passing unit not sent
        self.assertEqual(out["B"], [{"id": "B-1"}])    # unchanged
        self.assertEqual(out["A"], [{"id": "A-1", "fixed": True}])
```

- [ ] **Step 2: Run, expect fail.**

- [ ] **Step 3: Implement `review_group`, `revise_group`, `failed_units`** in `review.py` (reuse `_R1`, `_R2`, `rubric`, `_extract_json`, `llm`, `record_call`). Envelope reviewer prompt embeds, per unit, its passage+brief+items; asks for `{"units": {unit: {item_id: {"verdict","notes"}}}}`. `revise_group` builds a `{"units": {...}}` revise prompt from only failed units and merges the result over the originals.

```python
def failed_units(group_verdicts):
    out = set()
    for r in group_verdicts:
        for unit, vmap in r.get("verdicts_by_unit", {}).items():
            if any(v.get("verdict") == "fail" for v in vmap.values()):
                out.add(unit)
    return out

def _group_reviewer_prompt(lens, rubric_text, items_by_unit, ctx_by_unit):
    blocks = []
    for u, items in items_by_unit.items():
        c = ctx_by_unit[u]
        blocks.append(f"===== UNIT {u} =====\n## Passage\n{c['passage_text']}\n\n"
                      f"## Brief\n{c['brief']}\n\n## Draft items (JSON)\n"
                      f"{json.dumps(items, ensure_ascii=False)}")
    return (f"{lens}\n\n## Rubric\n{rubric_text}\n\n" + "\n\n".join(blocks) +
            "\n\nReturn STRICT JSON ONLY mapping each unit id to its item verdicts:\n"
            '{"units": {"<UNIT_ID>": {"<item_id>": {"verdict":"pass"|"fail",'
            '"notes":"concrete"}}}}. No prose.')

def review_group(items_by_unit, *, ctx_by_unit, book, r1_route=None, r2_route=None,
                 sink=None, experiment=None, section_id=None):
    r1_route = r1_route or route_from_env()
    r2_route = r2_route or route_from_env()
    out = []
    for name, lens, rubric_text, route in (
            ("r1", _R1, rubric.build(), r1_route),
            ("r2", _R2, rubric.build() + "\n" + rubric.reference_criteria(), r2_route)):
        prompt = _group_reviewer_prompt(lens, rubric_text, items_by_unit, ctx_by_unit)
        res = llm(prompt, route)
        record_call(sink, experiment=experiment, stage=f"review_{name}",
                    unit_id=section_id, kind="group", attempt=1, route=route,
                    prompt=prompt, result=res)
        obj = _extract_json(res.text)
        out.append({"reviewer": name, "verdicts_by_unit": obj.get("units", obj)})
    return out

def revise_group(items_by_unit, group_verdicts, *, ctx_by_unit, route=None,
                 sink=None, experiment=None, section_id=None):
    route = route or route_from_env()
    failed = failed_units(group_verdicts)
    if not failed:
        return dict(items_by_unit)
    sub_items = {u: items_by_unit[u] for u in failed}
    sub_verdicts = [
        {"reviewer": r["reviewer"],
         "verdicts_by_unit": {u: r["verdicts_by_unit"].get(u, {}) for u in failed}}
        for r in group_verdicts]
    blocks = []
    for u in failed:
        c = ctx_by_unit[u]
        blocks.append(f"===== UNIT {u} =====\n## Passage\n{c['passage_text']}\n\n"
                      f"## Brief\n{c['brief']}\n\n## Current items (JSON)\n"
                      f"{json.dumps(sub_items[u], ensure_ascii=False)}")
    prompt = (
        "Revise ONLY the flagged items to address each reviewer note precisely "
        "(fix fact/quote; retag dimension and switch answer_key<->leader_note; "
        "reframe judgment->observable behavior; make answerable/grounded). Leave "
        "passing items byte-identical; DROP an item that cannot be made accurate and "
        "gate-clean.\n\n## Reviewer verdicts (JSON)\n"
        f"{json.dumps(sub_verdicts, ensure_ascii=False)}\n\n" + "\n\n".join(blocks) +
        '\n\nReturn ONLY {"units": {"<UNIT_ID>": [ ...corrected items... ]}} for the '
        "units above.")
    res = llm(prompt, route)
    record_call(sink, experiment=experiment, stage="revise", unit_id=section_id,
                kind="group", attempt=1, route=route, prompt=prompt, result=res)
    revised = _extract_json(res.text)
    revised = revised.get("units", revised)
    out = dict(items_by_unit)
    out.update({u: revised[u] for u in failed if u in revised})
    return out
```

- [ ] **Step 4: Run, expect pass.**

- [ ] **Step 5: Commit** — `git commit -am "feat(group): batched review + failed-units-only revise"`

---

### Task 5: `group_run` orchestration (manifest, run layout, telemetry, write)

**Files:**
- Modify: `content_bank/author/build_group.py`
- Test: `content_bank/tests/test_build_group.py`

**Interfaces:**
- Produces: `group_run(book, *, units=None, review_on=True, max_repair=2, limit=None, run_root=None, backend="llm_core", model=None, routes=None, dim_cap=..., sink=None, experiment=None) -> {"ok": [...], "failed": {...}}`.
- Consumes: `build_cli._run_slug`, `_run_layout`, `_load_run_manifest`, `_effective_model`, `_write_json`, `_stamp_draft_provenance`, `_verdicts_by_item`-analogue, `_passage_text`, `_section_text`, `manifest_mod`, `review.review_group`, `review.revise_group`, `build_group_briefs`, `build_group_drafts`.

Behavior per group: build briefs (write each `briefs/<unit>.md`, mark `briefed`) → build drafts (per-unit gated) → if `review_on`: `review_group` (save per-unit verdict files) + `revise_group` + per-unit `_regate` → stamp provenance, write `drafts/<unit>.json`, mark each unit `drafted`. `--limit` limits groups. A group that raises records every not-yet-drafted unit of it in `failed` and continues. Units already `drafted` are skipped (resumability).

- [ ] **Step 1: Write failing end-to-end test (mocked stages) incl. call-count assertion**

```python
class TestGroupRunCallCount(unittest.TestCase):
    def test_one_group_uses_batched_calls(self):
        # PHP-S1 is a single-pericope section -> group ["PHP-S1","PHP-001"]
        calls = {"n": 0}
        def fake_llm(prompt, route):
            calls["n"] += 1
            # respond per stage by sniffing the header
            if "GROUP BRIEF BATCH" in prompt:
                units = {"PHP-S1": "arc", "PHP-001": "peri"}
            elif "GROUP DRAFT BATCH" in prompt:
                units = {"PHP-S1": [{"id": "php-s1-throughline"}],
                         "PHP-001": [{"id": "PHP-001-1"}]}
            else:  # review or revise
                units = {"PHP-S1": {}, "PHP-001": {}}
            return _res(json.dumps({"units": units}))
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as d, \
             mock.patch("content_bank.author.build_group.llm", side_effect=fake_llm), \
             mock.patch("content_bank.author.gates.run_all", return_value={}), \
             mock.patch("content_bank.author.gates.dimension_cap_check", return_value={}), \
             mock.patch("content_bank.author.review.llm", side_effect=fake_llm):
            res = build_group.group_run("PHP", units=["PHP-S1"], review_on=True,
                                        run_root=d, backend="claude", model="opus")
        self.assertIn("PHP-001", res["ok"])
        self.assertIn("PHP-S1", res["ok"])
        # 1 brief + 1 draft + 2 review + (0 revise, nothing failed) = 4 calls,
        # far below per-unit 4*(1+1)=8+
        self.assertLessEqual(calls["n"], 4)
```

- [ ] **Step 2: Run, expect fail.**

- [ ] **Step 3: Implement `group_run`** (mirror `build_cli.run`'s layout/manifest/stamp logic; iterate groups; write per-unit artifacts). Reuse `build_cli` helpers. Save verdicts per unit via a small `_verdicts_by_item` on the unit's slice of `verdicts_by_unit`.

- [ ] **Step 4: Run, expect pass.**

- [ ] **Step 5: Add resumability test** — pre-mark `PHP-001` `drafted` in the run manifest; assert `group_run` does not re-draft it (llm not called for that unit's group if all drafted).

- [ ] **Step 6: Run, expect pass.**

- [ ] **Step 7: Commit** — `git commit -am "feat(group): group_run orchestration with per-unit manifest + telemetry"`

---

### Task 6: CLI `--group` flag

**Files:**
- Modify: `content_bank/author/build_cli.py:main` (and `run` dispatch)
- Test: `content_bank/tests/test_build_group.py`

**Interfaces:**
- Consumes: `build_group.group_run`.
- `main()` gains `--group` (store_true). When set, `main` calls `build_group.group_run(...)` with the same book/units/review/max_repair/limit/run_root/backend/model/dim_cap args instead of `build_cli.run(...)`.

- [ ] **Step 1: Write failing test — `--group` dispatches to `group_run`**

```python
class TestCliGroupDispatch(unittest.TestCase):
    def test_group_flag_calls_group_run(self):
        from content_bank.author import build_cli
        with mock.patch("content_bank.author.build_group.group_run",
                        return_value={"ok": ["PHP-S1"], "failed": {}}) as g:
            rc = build_cli.main(["--book", "PHP", "--group", "--backend", "claude",
                                 "--model", "opus", "--units", "PHP-S1"])
        self.assertEqual(rc, 0)
        g.assert_called_once()
```

- [ ] **Step 2: Run, expect fail.**

- [ ] **Step 3: Implement** — add `ap.add_argument("--group", action="store_true", help="batch each section-group into one LLM call per stage")`; in `main`, branch: `if a.group: res = build_group.group_run(a.book, units=a.units, review_on=a.review, max_repair=a.max_repair, limit=a.limit, run_root=a.run_root, backend=a.backend, model=a.model, dim_cap=a.dim_cap)` else the existing `run(...)`. Import `build_group` lazily inside `main` to avoid a cycle.

- [ ] **Step 4: Run, expect pass.**

- [ ] **Step 5: Commit** — `git commit -am "feat(group): --group CLI flag"`

---

### Task 7: Docs

**Files:**
- Modify: `docs/content_builder_usage.md`, `docs/content_build_terminology.md`

- [ ] **Step 1:** Add a `--group` section to `docs/content_builder_usage.md`: what a group is, the one-call-per-stage flow, the bisection guard, the telemetry tradeoff, and the example command `--book PHP --group --backend claude --model opus`.
- [ ] **Step 2:** Add a "group mode" glossary entry to `docs/content_build_terminology.md` cross-linking the design spec.
- [ ] **Step 3:** Commit — `git commit -am "docs(group): document --group batched build mode"`

---

## Self-Review

**Spec coverage:** §1 group def → Task 1 (`groups_for_book`). §2 module layout → Tasks 1–6 (`build_group.py`, reuse). §3 envelope/prompts → Task 2. §4 per-group flow (brief/draft/repair/review/revise) → Tasks 3–5. §5 bisection → Task 3 (`group_call`). §6 unchanged downstream → Tasks 3/5 reuse `_repair_to_clean`/`_regate`/manifest. §7 telemetry → Tasks 3–5 `record_call(unit_id=section_id, kind="group")`. §8 error handling/resumability → Task 5. CLI → Task 6. Tests list → covered across tasks. Follow-ups (experiment wiring, A/B) correctly out of scope.

**Placeholder scan:** none — every step has concrete code or an explicit doc instruction.

**Type consistency:** `parse_units`/`Truncated`/`group_call`/`build_group_drafts`/`review_group`/`revise_group`/`group_run` signatures are consistent across Tasks 1–6; envelope shape `{"units": {...}}` uniform; `verdicts_by_unit` key used consistently in Task 4 and consumed in Task 5.
