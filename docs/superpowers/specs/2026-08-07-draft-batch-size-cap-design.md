# Draft-stage batch-size cap for group mode — design

**Date:** 2026-08-07
**Status:** approved for implementation
**Follows:** `2026-08-07-group-batched-content-build-design.md`

## Problem

The PHP-S2 A/B run showed the group **draft** stage cost 5 calls, not the ideal 1: at
a 6-unit group the model returned `end_turn` but **omitted units**, so the bisection
guard split the group down to recover. The guard worked (all units drafted, zero
failures), but the churn ate most of the draft-stage savings (group landed at 9 calls
instead of ~5). Every *other* stage (brief, review r1/r2, revise) batched cleanly at
full group size — only **draft**, the highest-output-volume stage, drops units when
asked for too many at once.

## Goal

Cap how many units go into a single **draft** `group_call` (default **4**), so the
model reliably emits each chunk first-try and bisection rarely fires. Brief, review,
and revise stay batched at full group size. This is a tuning knob on top of the
bisection *safety net*, pushing the realized win from ~3.8× toward the ~6–7× ceiling
and making draft-call counts predictable.

## Design

### Chunking (draft stage only)

`group_draft_items(unit_ids, book, briefs, *, route, batch_size=None, ...)` splits
`unit_ids` into consecutive chunks of at most `batch_size` and issues **one
`group_call` per chunk** (each chunk still passing through the bisection guard),
merging the per-unit results:

```
def _draft_chunks(unit_ids, batch_size):
    if not batch_size or batch_size <= 0 or len(unit_ids) <= batch_size:
        return [list(unit_ids)]
    return [unit_ids[i:i + batch_size] for i in range(0, len(unit_ids), batch_size)]
```

`batch_size <= 0` (or `None`) means **no cap** — the whole group in one draft call
(the pre-cap behavior, kept for uncapped comparisons).

Chunking is safe because the draft envelope wraps each unit's *independent* draft
sub-pack (its own brief + passage); there is no cross-unit dependency at draft time
(unlike the section **brief**, whose arc references its pericopes — which is why only
draft is chunked, and briefs are still computed over the whole group first).

The section unit and its pericopes may land in different chunks; that is fine — each
unit drafts from its own brief.

### Threading

`draft_batch_size` flows: CLI/experiment config → `group_run` → `_build_one_group` →
`group_draft_items` / `build_group_drafts`. Default **4** at the entry points
(`group_run`, the CLI flag, the experiment default); the lower-level
`group_draft_items`/`build_group_drafts` default to `None` (uncapped) so their unit
tests stay predictable unless a size is passed.

### Surfaces

- **CLI** (`build_cli.py`): `--draft-batch-size N` (default 4), help notes it applies
  only in `--group` mode, draft stage only; `<= 0` disables the cap. Ignored for
  non-group builds.
- **Experiment config**: optional top-level `"draft_batch_size"` (int `>= 0`, default
  4). Part of the config → included in `config_hash`. Only meaningful when
  `"execution": "group"`.

### Telemetry

Each chunk's draft call records as `stage: "draft"`, `kind: "group"`, attributed to the
section id — so `calls_by_stage.draft` honestly reflects the number of draft chunks
(plus any bisections). No change to the report schema.

## What stays the same

Brief / review r1 / review r2 / revise batch over the full group. Gates, manifest,
the deferred single gate (after revise, review-on), per-unit artifacts, and the
bisection guard are unchanged. `draft_batch_size >= len(group)` reproduces the exact
pre-cap behavior, so existing group runs/tests with small groups are unaffected.

## Testing

1. `_draft_chunks`: uncapped (`None`/`0`/`>= len`) → one chunk; `4` over 6 units →
   `[4, 2]`.
2. `group_draft_items` with `batch_size=4` over a 6-unit list issues **2** draft
   `group_call`s and merges all 6 units (mocked `group_call`).
3. `group_run(..., draft_batch_size=4)` over a ≥5-unit group makes >1 draft call but
   fewer than per-unit; a 2-unit group with default 4 still makes exactly 1 draft call
   (no behavior change).
4. `experiment_config.validate`: accepts `draft_batch_size: 4`, `0`; rejects `-1`;
   changes `config_hash`.
5. `experiment_cli`: a group config's `draft_batch_size` reaches `group_run`; default
   4 when omitted.
6. CLI: `--draft-batch-size` parsed and passed to `group_run`.
