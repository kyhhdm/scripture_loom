# Translation Drift — Suggested Fixes — Design

- **Date:** 2026-07-30
- **Status:** design (approved in brainstorming; pending spec review)
- **Author:** pairing session (kyhhdm + Claude)

## Problem

The Chinese translator already repairs **gate** flags: `translate_with_gates`
(`content_bank/author/translate.py:98-114`) loops up to `--max-repair` rounds,
feeding the detailed flag text back to the model via `_repair_prompt`
(`translate.py:86`) and re-gating. So "call the LLM again with the flag info to
fix it" is **already done for gate flags**.

The **drift** review is different. `back_translate_review` (`translate.py:117-130`)
runs **once, after** the gate loop (`translate_cli.py:47`), back-translates the zh,
and reports `{drift, notes}` describing any doctrinal divergence from the English +
Westminster frame. Its `notes` are recorded on the proposal but **never fed back**
to a fixing call — the human is left to act on the prose note by hand.

In the Psalms 1–10 run, 9/187 proposals drew drift flags (see
`docs/2026-07-29-psalms-1-10-pipeline-findings.md` §6). Two kinds appeared:

- **Real translator errors** — e.g. Ps 2 flash *inserted* 「受膏者说：我要传圣旨」 into a
  quote. Fixable.
- **CUV-vs-BSB translation-philosophy divergence** — e.g. the CUV renders Ps 1:6
  "guards" (shomer) as 知道 ("knows"). Not the translator's error; **not fixable**
  without leaving the CUV.

## Goal

When a proposal is drift-flagged, make **one** additional LLM call that proposes a
**revised zh** resolving the drift — recorded alongside the original as a
`suggested_fix`, **never replacing it**. The human sees both and picks. This keeps
the project's core invariant intact ("AI proposes; the leader confirms",
`CLAUDE.md`) and, by construction, cannot silently break CUV alignment.

## Scope decisions (settled in brainstorming)

- **Suggest-and-confirm, not auto-fix.** The revision rides on the proposal as
  `suggested_fix`; `item` (the original) is untouched. Nothing is auto-replaced.
- **Drift-only trigger.** Fires only when `drift.drift == true`. Gate-flagged items
  that survived the `max_repair` loop are **not** re-attempted here — that would
  duplicate the existing repair loop.
- **CUV-safe by construction.** The fix prompt forbids leaving the CUV; a drift that
  is CUV-inherent must be returned unchanged with `changed:false` and a reason.
- **Verify, don't trust.** Re-run the deterministic gates AND the drift review on the
  revision, so the human sees whether the fix actually worked.
- **Default on**, disable with `--no-suggest-fixes` (drift is rare, ~5%).
- **Promote is out of scope.** Accepting a suggestion into the store stays a manual
  edit in v1; `translate.promote --use-suggested` is a noted follow-up.

## Why the shape already fits

- The proposal is a plain dict assembled in `proposal_for` (`translate_cli.py:44-53`)
  — adding a `suggested_fix` key is additive; no schema in `content_bank/lib/`
  governs proposal files (they are review-stage artifacts, not store items).
- Re-gating reuses `zh_gate_flags(item, glossary)` (`translate.py:67`) verbatim.
- Re-checking drift reuses `back_translate_review(item, model)` verbatim.
- Rendering reuses the badge machinery in `translate_compare_html.py` (the gate/drift
  tooltips added 2026-07-30, PR #29).

## Design

### New function — `suggest_drift_fix` (`translate.py`)

```python
def suggest_drift_fix(item, book, drift, *, glossary=None, model=None):
    """Given a drift-flagged translated item, ask the model for a CUV-safe revision.
    Returns a suggested_fix dict, or None when there is no drift to fix."""
```

Behaviour:

1. Guard: if not `drift["drift"]`, return `None` (caller only invokes on drift, but
   the guard keeps the function honest/testable).
2. Build the fix prompt (below) from `item` + `drift["notes"]`; call `llm` once;
   `_extract_json` the response. The response carries `{"changed": bool,
   "reason": str, "text": {...}, "leader_reference": {...}, "terms": [...],
   "uncertain": [...]}` (same zh-bearing shape the translate/repair calls return,
   plus `changed`/`reason`).
3. If `changed` is false (model declined — CUV-inherent), return
   `{"changed": False, "rationale": reason, "item": item, "gate_ok": <regate item>,
   "gate_flags": <…>, "drift": drift}` — i.e. the suggestion **is** the original,
   flagged as unchanged, so the review page can say "no fix — CUV wording".
4. Otherwise merge the zh onto a **copy** of the item (`_merge_zh`), then:
   - re-gate: `flags = zh_gate_flags(revised, glossary)`
   - re-drift: `new_drift = back_translate_review(revised, model=model)`
   - return `{"changed": True, "rationale": reason, "item": revised,
     "gate_ok": not flags, "gate_flags": flags, "drift": new_drift,
     "terms": resp["terms"], "uncertain": resp["uncertain"]}`

The original `item` is never mutated — `_merge_zh` must operate on a copy (verify it
does; if not, `copy.deepcopy(item)` first).

### The fix prompt (CUV-safe)

```
A back-translation drift review found a DOCTRINAL divergence between this Chinese
translation and the original English / Westminster frame. Propose a revised zh that
RESOLVES the drift, under these hard rules:

- Every Scripture quote must stay a verbatim CUV span in 「…」 inside its <verse ...>
  tag; keep every <verse>/<doctrine> tag and its ref/std unchanged.
- Change ONLY what the drift note requires; keep everything else identical.
- If the drift exists ONLY because the CUV itself renders the wording this way, you
  CANNOT fix it without leaving the CUV. In that case DO NOT change the text: return
  changed=false and explain.

## Drift note
{drift notes}

## Current item (with its zh)
{json item}

Return STRICT JSON ONLY: {"changed": true|false, "reason": "...",
"text": {"zh": ...}, "leader_reference": {...}, "terms": [...], "uncertain": [...]}.
```

### Wiring — `proposal_for` (`translate_cli.py:44-53`)

Add a `suggest_fixes=True` parameter. After the existing drift line:

```python
drift = back_translate_review(out["item"], model=model)
suggested = (suggest_drift_fix(out["item"], book, drift,
                               glossary=glossary, model=model)
             if suggest_fixes and drift["drift"] else None)
```

Thread `suggest_fixes` through `run_proposals` and add the `--suggest-fixes /
--no-suggest-fixes` argparse pair in `main` (default **True**). Include
`suggested_fix` in the returned proposal dict only when non-`None` (keeps clean
proposals unchanged).

The `[ok] <id>` progress line gains a ` (fix suggested)` / ` (fix: CUV-inherent)`
marker when a suggestion is produced.

### Rendering — `translate_compare_html.py`

When a cell's proposal has a `suggested_fix`, render a sub-block beneath the original
zh: a "suggested" label, the revised zh (highlighted, same `citation_tags.highlight`),
its own gate/drift badges (reusing `_flag_badges` + the tooltips), and the
`rationale`. A `changed:false` suggestion renders as "no fix available (CUV wording)"
with the reason, and no revised text.

### Cost

Per drift-flagged item: 1 revise call + 1 re-drift call (+ deterministic re-gate, free).
For the whole PSA run that is ~18 extra calls total. Negligible; gated behind the
rare drift trigger and the `--no-suggest-fixes` off-switch.

## Testing

- **`suggest_drift_fix` — happy path:** a drift-flagged item, mock `llm` returns
  `changed:true` with a corrected zh → returned dict has `changed:True`, the revised
  zh, and a re-gated/re-drifted result; the **original item is unmutated**.
- **CUV-inherent decline:** mock returns `changed:false` → returned dict has
  `changed:False`, `item` equal to the original, `rationale` set, no exception.
- **Re-gate catches a bad fix:** mock returns a `changed:true` revision that drops a
  `<verse>` tag → `suggested_fix.gate_ok` is `False` with the flag recorded (not
  dropped).
- **No drift → no call:** `suggest_drift_fix` with `drift:false` returns `None` and
  makes no `llm` call (assert the mock was not called).
- **`proposal_for` wiring:** drift-flagged proposal carries a `suggested_fix`;
  non-drift proposal has no `suggested_fix` key; `--no-suggest-fixes` suppresses it.
- **Rendering:** a proposal with a `suggested_fix` renders the revised zh, its badges,
  and the rationale; a `changed:false` fix renders the "no fix" note.

## Out of scope

- **Promotion of a suggestion** into the store (`translate.promote --use-suggested`) —
  follow-up; v1 leaves acceptance as a manual edit.
- **Auto-fix loop / auto-replacement** — explicitly rejected in brainstorming.
- **Gate-only suggestions** — gate flags already have the `max_repair` loop.
- **Any change to store-item schema** (`content_bank/lib/schema.py`) — proposals are
  review-stage, unschema'd.
- **English-side (draft) drift** — this is a translation-pipeline feature only.
