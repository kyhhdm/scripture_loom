"""Multi-run comparison review page generator.

Reads several sibling ``work/content_bank_build/<BOOK>/drafts*/`` run directories
and emits ONE self-contained HTML file that shows the runs side by side, per unit,
grouped by dimension. A human accepts/rejects individual items and exports those
decisions as JSON. It is a review *instrument*: it never writes the store, and the
exported ``decisions.json`` feeds a separate, human-gated promote step.

CLI:
    uv run python -m content_bank.author.compare_html PHP \
        --runs drafts_py,drafts_pro,drafts_claude [--out review.html]

Gates are best-effort annotations, not a verdict: schema always runs; quote and
range/thread gates run when the corpus text / pericope ranges load, else they are
skipped and a page-level note records it. Adversarial verdicts attach only where an
item id matches a ``verdicts/<UNIT>.json`` key (historic slugs will not match — that
is expected). All quality judgment stays the human's, on the page.

See docs/superpowers/specs/2026-07-21-multi-run-comparison-page-design.md.
"""
import argparse
import json
import pathlib

from . import gates, rubric

_ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_BASE = _ROOT / "work" / "content_bank_build"
BRIEFS = _ROOT / "content_bank" / "author" / "briefs"
DIM_ORDER = ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8"]


def _resolve_run(book_dir, name):
    """Locate a run's dirs. New layout: <book>/runs/<name>/{drafts,verdicts,briefs}.
    Legacy: a flat <book>/<name>/ of draft json, shared <book>/verdicts, shared
    author/briefs. Returns (draft_dir, verdicts_dir, briefs_dir|None)."""
    run_dir = book_dir / "runs" / name
    if not run_dir.is_dir():
        run_dir = book_dir / name
    if not run_dir.is_dir():
        raise FileNotFoundError(f"run not found: {book_dir / 'runs' / name} "
                                f"nor {book_dir / name}")
    draft_dir = run_dir / "drafts" if (run_dir / "drafts").is_dir() else run_dir
    verdicts_dir = (run_dir / "verdicts" if (run_dir / "verdicts").is_dir()
                    else book_dir / "verdicts")
    briefs_dir = run_dir / "briefs" if (run_dir / "briefs").is_dir() else None
    return draft_dir, verdicts_dir, briefs_dir


def _load_brief(unit, briefs_dir):
    """The unit's brief (markdown) for a run, or None. Prefers the run's own briefs
    dir; falls back to the shared author/briefs. Brief files are lower-cased."""
    for base in (briefs_dir, BRIEFS):
        if base is None:
            continue
        p = pathlib.Path(base) / f"{unit.lower()}.md"
        if p.is_file():
            return p.read_text(encoding="utf-8")
    return None


def _load_verdicts(verdicts_dir):
    """{unit_id: {item_id: [{reviewer, verdict, notes}, ...]}} for one run's dir."""
    out = {}
    if verdicts_dir and pathlib.Path(verdicts_dir).is_dir():
        for f in sorted(pathlib.Path(verdicts_dir).glob("*.json")):
            out[f.stem] = json.loads(f.read_text(encoding="utf-8"))
    return out


def _allowed(book, unit):
    """Per-unit range list for the range/thread gates, or None if the unit id is not
    a known pericope or section (e.g. a synthetic test unit)."""
    try:
        return gates.pericope_allowed(book, unit)
    except (ValueError, KeyError, FileNotFoundError):
        pass
    try:
        return gates.section_allowed(book, unit)
    except (ValueError, KeyError, FileNotFoundError):
        return None


def _run_gates(book, unit_items, notes):
    """Return {item_id: [problems]} for one run's items. Appends page-level notes
    (deduped later) when a gate tier is skipped."""
    flags = {}

    def _merge(result):
        for k, v in result.items():
            flags.setdefault(k, []).extend(v)

    all_items = [it for items in unit_items.values() for it in items]
    try:
        _merge(gates.schema_check(all_items))
    except Exception as exc:  # schema is in-repo; a failure is worth surfacing.
        notes.append(f"schema gate not run: {exc}")
    try:
        _merge(gates.quote_check(book, all_items))
    except Exception:
        notes.append("quote gate not run (corpus text unavailable)")

    for unit, items in unit_items.items():
        _merge(gates.section_reveal_check(items))

    skipped_range = False
    for unit, items in unit_items.items():
        allowed = _allowed(book, unit)
        if allowed is None:
            skipped_range = True
            continue
        try:
            _merge(gates.refs_in_range(items, allowed))
            _merge(gates.thread_span_check(items, allowed))
        except Exception:
            skipped_range = True
    if skipped_range:
        notes.append("range/thread gates skipped for some units (range unavailable)")
    return flags


def _leader_ref(item):
    """The leader-only reference (answer key for D1-D5, leader note for D6-D8), or
    None. Shown to the reviewer — answer-key accuracy and note-openness are two of
    the seven rubric axes."""
    lr = item.get("leader_reference")
    if not lr:
        return None
    # Keep citation tags RAW here: this is a review instrument, and the page
    # highlights <verse>/<doctrine> spans client-side so the reviewer can see
    # and verify what was cited. (The family-facing kit still strips tags.)
    return {
        "kind": lr.get("kind"),
        "text_en": (lr.get("text") or {}).get("en"),
        "verse_en": (lr.get("verse") or {}).get("en"),
    }


def _lr_text(item):
    return (((item.get("leader_reference") or {}).get("text") or {}).get("en")) or ""


def _card(item, run, gate_flags, unit_verdicts, raw_by_id=None, has_raw=False):
    iid = item.get("id")
    problems = gate_flags.get(iid, [])
    card = {
        "id": iid,
        "run": run,
        "dimension": item.get("dimension"),
        "type": item.get("type"),
        "age_tier": item.get("age_tier"),
        "difficulty": item.get("difficulty"),
        "text_en": (item.get("text") or {}).get("en") or "(no en text)",  # raw tags; highlighted client-side
        "leader_ref": _leader_ref(item),
        "gate_ok": not problems,
        "gate_problems": problems,
        "verdict": unit_verdicts.get(iid),
    }
    # First-round (pre-review) counterpart, so the reviewer sees what repair/revise
    # changed. Only when raw drafts exist for this run (graceful on legacy runs).
    if has_raw:
        raw = (raw_by_id or {}).get(iid)
        if raw is None:
            card["origin"] = "added"      # appeared during review (rare)
        else:
            raw_text = (raw.get("text") or {}).get("en") or ""
            card["raw_text_en"] = raw_text
            card["raw_dimension"] = raw.get("dimension")
            card["raw_leader_ref"] = _leader_ref(raw)
            card["changed"] = bool(
                raw_text != card["text_en"]
                or raw.get("dimension") != item.get("dimension")
                or _lr_text(raw) != _lr_text(item))
    return card


def _dropped_card(raw_item, run):
    """A first-round item that review/revise DROPPED (in raw, absent from final)."""
    return {
        "id": raw_item.get("id"),
        "run": run,
        "dimension": raw_item.get("dimension"),
        "type": raw_item.get("type"),
        "age_tier": raw_item.get("age_tier"),
        "difficulty": raw_item.get("difficulty"),
        "text_en": (raw_item.get("text") or {}).get("en") or "(no en text)",
        "leader_ref": _leader_ref(raw_item),
        "dropped": True,
    }


def build_model(book, runs, base=None, resolve=None):
    """Assemble the nested comparison model: unit -> dimension -> run -> [item cards].

    Raises FileNotFoundError if a named run directory is missing. A run missing a
    given unit file contributes zero items for that unit (no error) — that raggedness
    is the padding signal the reviewer is looking for. ``resolve(run) ->
    (draft_dir, verdicts_dir, briefs_dir)`` overrides the default run-dir lookup
    (used by the experiment-column renderer, whose columns live in separate dirs).
    """
    base = pathlib.Path(base) if base else DEFAULT_BASE
    book_dir = base / book
    notes = []
    if resolve is None:
        def resolve(run):
            return _resolve_run(book_dir, run)

    run_items = {}   # run -> {unit_id: [items]}
    verdicts = {}    # run -> {unit_id: {item_id: [...]}}
    briefs_dirs = {}  # run -> briefs dir or None
    raw_items = {}   # run -> {unit_id: {item_id: raw_item}}
    has_raw = {}     # run -> bool (first-round drafts available?)
    for run in runs:
        draft_dir, verdicts_dir, briefs_dir = resolve(run)
        run_items[run] = {
            f.stem: json.loads(f.read_text(encoding="utf-8"))
            for f in sorted(pathlib.Path(draft_dir).glob("*.json"))
        }
        verdicts[run] = _load_verdicts(verdicts_dir)
        briefs_dirs[run] = briefs_dir
        raw_dir = pathlib.Path(draft_dir).parent / "raw_drafts"
        has_raw[run] = raw_dir.is_dir()
        raw_items[run] = {
            f.stem: {it.get("id"): it for it in json.loads(f.read_text(encoding="utf-8"))}
            for f in sorted(raw_dir.glob("*.json"))
        } if has_raw[run] else {}

    gate_flags = {run: _run_gates(book, run_items[run], notes) for run in runs}

    all_units = sorted({u for run in runs for u in run_items[run]})
    units = []
    for unit in all_units:
        final_ids = {run: {it.get("id") for it in run_items[run].get(unit, [])}
                     for run in runs}
        # dropped = first-round items whose id is gone from the final draft.
        dropped = {run: [r for rid, r in raw_items[run].get(unit, {}).items()
                         if rid not in final_ids[run]] for run in runs}
        present = {it.get("dimension") for run in runs
                   for it in run_items[run].get(unit, []) if it.get("dimension")}
        present |= {r.get("dimension") for run in runs for r in dropped[run]
                    if r.get("dimension")}
        ordered = [d for d in DIM_ORDER if d in present] + \
                  [d for d in sorted(present) if d not in DIM_ORDER]
        blocks = []
        for dim in ordered:
            cells, counts = {}, {}
            for run in runs:
                raw_by_id = raw_items[run].get(unit, {})
                items = [it for it in run_items[run].get(unit, [])
                         if it.get("dimension") == dim]
                cards = [_card(it, run, gate_flags[run], verdicts[run].get(unit, {}),
                               raw_by_id=raw_by_id, has_raw=has_raw[run])
                         for it in items]
                cards += [_dropped_card(r, run) for r in dropped[run]
                          if r.get("dimension") == dim]
                cells[run] = cards
                counts[run] = len(items)
            blocks.append({"dimension": dim, "counts": counts, "cells": cells})
        unit_briefs = {run: _load_brief(unit, briefs_dirs[run]) for run in runs}
        units.append({"id": unit, "briefs": unit_briefs, "dimensions": blocks})

    seen = set()
    notes = [n for n in notes if not (n in seen or seen.add(n))]
    rubric_text = rubric.build() + "\n\n" + rubric.reference_criteria()
    return {"book": book, "runs": list(runs), "notes": notes,
            "rubric": rubric_text, "units": units}


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

_PAGE = r"""<meta charset="utf-8">
<title>__TITLE__</title>
<style>
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0; font: 14px/1.5 system-ui, sans-serif; }
header { position: sticky; top: 0; z-index: 5; background: Canvas; padding: 10px 16px;
  border-bottom: 1px solid #8886; display: flex; gap: 16px; align-items: center;
  flex-wrap: wrap; }
header h1 { font-size: 15px; margin: 0; }
#tally { font-variant-numeric: tabular-nums; }
button { font: inherit; padding: 5px 12px; border: 1px solid #8888; border-radius: 6px;
  background: #8882; cursor: pointer; }
button:hover { background: #8884; }
#note { padding: 6px 16px; background: #f9731622; border-bottom: 1px solid #8886;
  font-size: 13px; }
#note:empty { display: none; }
nav { padding: 8px 16px; display: flex; gap: 6px; flex-wrap: wrap;
  border-bottom: 1px solid #8886; }
nav button.on { background: #3b82f6; color: #fff; border-color: #3b82f6; }
main { padding: 16px; }
details.dim { border: 1px solid #8886; border-radius: 8px; margin: 0 0 12px; }
details.dim > summary { padding: 8px 12px; cursor: pointer; font-weight: 600;
  list-style: none; display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap; }
summary .cnt { font-weight: 400; color: #888; font-size: 12px; }
.cols { display: flex; gap: 10px; padding: 4px 12px 12px; overflow-x: auto; }
.col { flex: 1 1 0; min-width: 240px; }
.col > h4 { margin: 4px 0 8px; font-size: 12px; color: #888;
  border-bottom: 1px solid #8886; padding-bottom: 4px; }
.card { border: 1px solid #8886; border-radius: 6px; padding: 8px; margin-bottom: 8px; }
.card.acc { border-color: #22c55e; background: #22c55e18; }
.card label { display: flex; gap: 8px; align-items: flex-start; cursor: pointer; }
.card .txt { flex: 1; }
.chips { margin-top: 6px; display: flex; gap: 6px; flex-wrap: wrap; font-size: 11px; }
.chip { padding: 1px 6px; border-radius: 10px; background: #8883; color: inherit; }
.chip.ok { background: #22c55e33; }
.chip.flag { background: #f9731633; cursor: help; }
.chip.pass { background: #22c55e33; }
.chip.fail { background: #ef444433; }
.empty { color: #999; font-style: italic; font-size: 12px; padding: 4px 0; }
.lref { margin: 6px 0 0 24px; padding: 6px 8px; border-left: 3px solid #a855f7aa;
  background: #a855f714; border-radius: 0 4px 4px 0; font-size: 13px; }
.lref .lref-kind { font-weight: 600; font-size: 11px; text-transform: uppercase;
  letter-spacing: .03em; color: #a855f7; }
.lref .lref-verse { color: #888; font-size: 12px; margin-left: 6px; }
details.ref { margin: 8px 16px; border: 1px solid #8886; border-radius: 8px; }
details.ref > summary { padding: 8px 12px; cursor: pointer; font-weight: 600; }
.refbody { padding: 4px 16px 12px; max-width: 70em; }
.refbody h3 { font-size: 15px; margin: 12px 0 6px; }
.refbody h4 { font-size: 13px; margin: 10px 0 4px; }
.refbody p { margin: 6px 0; }
details.brief { margin: 0 0 14px; border: 1px solid #3b82f677; border-radius: 8px;
  background: #3b82f611; }
details.brief > summary { padding: 8px 12px; cursor: pointer; font-weight: 600; }
.cite { border-radius: 3px; padding: 0 1px; }
.cite-verse { background: #22c55e2e; box-shadow: inset 0 -2px 0 #22c55eaa; }
.cite-doctrine { background: #f59e0b2e; box-shadow: inset 0 -2px 0 #f59e0baa; }
.citeref { font-size: 9px; font-weight: 700; margin-left: 2px; padding: 0 3px;
  border-radius: 6px; vertical-align: super; letter-spacing: .02em; }
.cite-verse .citeref { background: #22c55e; color: #04310f; }
.cite-doctrine .citeref { background: #f59e0b; color: #3a2600; }
.legend { font-size: 12px; color: #888; }
.legend .cite { padding: 0 4px; }
.card.changed { border-left: 3px solid #f59e0b; }
.chip.changed { background: #f59e0b33; }
.chip.retag { background: #a855f733; font-weight: 600; }
.chip.drop { background: #ef444433; }
.card.dropped { opacity: .6; border-style: dashed; }
.card.dropped .txt { text-decoration: line-through; }
details.firstdraft { margin: 6px 0 2px; font-size: 12px; }
details.firstdraft > summary { cursor: pointer; color: #b45309; }
.firstdraft .fdbody { margin-top: 4px; padding: 6px 8px; border-left: 2px solid #f59e0baa;
  background: #f59e0b14; border-radius: 0 4px 4px 0; }
.firstdraft .raw { color: #555; }
table.matrix { border-collapse: collapse; font-size: 12px; }
table.matrix th, table.matrix td { border: 1px solid #8886; padding: 3px 8px;
  text-align: left; }
table.matrix th.stage { color: #888; font-weight: 600; }
table.matrix thead th { background: #8882; }
</style>
<header>
  <h1>__TITLE__</h1>
  <span id="tally"></span>
  <button id="export">Export decisions</button>
  <span style="color:#888;font-size:12px">runs: __RUNS__</span>
  <span class="legend">citations:
    <span class="cite cite-verse">verse<sup class="citeref">REF</sup></span>
    <span class="cite cite-doctrine">doctrine<sup class="citeref">STD</sup></span>
    · <span class="chip changed">changed</span> repair/revise edited it (expand "1st draft")
    · <span class="chip drop">dropped in review</span></span>
</header>
<div id="note">__NOTE__</div>
__MATRIX__
<details class="ref" id="rubric">
  <summary>Rubric — the seven axes every item is judged against</summary>
  <div class="refbody" id="rubric-body"></div>
</details>
<nav id="nav"></nav>
<main id="main"></main>
<script type="application/json" id="review-data">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('review-data').textContent);
const KEY = 'slreview:' + DATA.book;
const state = JSON.parse(localStorage.getItem(KEY) || '{}');
let TOTAL = 0;
for (const u of DATA.units) for (const b of u.dimensions)
  for (const r of DATA.runs) TOTAL += (b.cells[r] || []).filter(x => !x.dropped).length;

function save() { localStorage.setItem(KEY, JSON.stringify(state)); }
function tally() {
  const acc = Object.values(state).filter(v => v === true).length;
  document.getElementById('tally').textContent = acc + ' accepted / ' + TOTAL + ' items';
}
function esc(s) { const d = document.createElement('div'); d.textContent = s == null ? '' : s; return d.innerHTML; }
// Attribute-safe: esc() does not escape quotes, so a note containing " would close
// a title="..." attribute early and drop the tooltip. Escape quotes too.
function escAttr(s) { return esc(s).replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
// Highlight citation tags for the reviewer. esc() runs FIRST (all item text is
// escaped, so no injection), then the now-escaped <verse>/<doctrine> markup —
// our own known syntax — is turned into styled spans with the ref shown inline.
function hlCite(s) {
  let h = esc(s == null ? '' : s);
  h = h.replace(/&lt;verse ref="([^"]*)"&gt;([\s\S]*?)&lt;\/verse&gt;/g,
    (_, ref, inner) => '<span class="cite cite-verse" title="verse ' + escAttr(ref) +
      '">' + inner + '<sup class="citeref">' + esc(ref) + '</sup></span>');
  h = h.replace(/&lt;doctrine std="([^"]*)" ref="([^"]*)"&gt;([\s\S]*?)&lt;\/doctrine&gt;/g,
    (_, std, ref, inner) => '<span class="cite cite-doctrine" title="doctrine ' +
      escAttr(std + ' ' + ref) + '">' + inner + '<sup class="citeref">' +
      esc(std + ' ' + ref) + '</sup></span>');
  return h;
}
function md(src) {
  if (!src) return '<em>no brief on file for this unit</em>';
  return esc(src)
    .replace(/^# (.*)$/gm, '<h3>$1</h3>')
    .replace(/^## (.*)$/gm, '<h4>$1</h4>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .split(/\n\n+/)
    .map(b => /^<h[34]>/.test(b.trim()) ? b : '<p>' + b.replace(/\n/g, ' ') + '</p>')
    .join('');
}

function lrefHtml(lr) {
  if (!lr || !lr.text_en) return '';
  const kind = (lr.kind === 'answer_key') ? 'Answer key'
    : (lr.kind === 'leader_note') ? 'Leader note' : (lr.kind || 'Leader ref');
  return '<div class="lref"><span class="lref-kind">' + esc(kind) + '</span>' +
    (lr.verse_en ? '<span class="lref-verse">' + hlCite(lr.verse_en) + '</span>' : '') +
    '<div>' + hlCite(lr.text_en) + '</div></div>';
}

function firstDraftBlock(c) {
  // Collapsible "1st draft" showing what repair/revise changed. Only when changed.
  if (!c.changed) return '';
  const retag = (c.raw_dimension && c.raw_dimension !== c.dimension)
    ? '<span class="chip retag">' + esc(c.raw_dimension) + ' → ' + esc(c.dimension) + '</span>'
    : '';
  return '<details class="firstdraft"><summary>1st draft ▸ changed by review</summary>' +
    '<div class="fdbody">' + retag +
    '<div class="raw">' + hlCite(c.raw_text_en || '') + '</div>' +
    lrefHtml(c.raw_leader_ref) + '</div></details>';
}

function card(c) {
  const el = document.createElement('div');
  if (c.dropped) {
    el.className = 'card dropped';
    el.innerHTML =
      '<div class="txt">' + hlCite(c.text_en) + '</div>' + lrefHtml(c.leader_ref) +
      '<div class="chips"><span class="chip drop">dropped in review</span>' +
      '<span class="chip">' + esc(c.dimension) + '</span>' +
      '<span class="chip">' + esc(c.type) + '</span></div>';
    return el;
  }
  el.className = 'card' + (state[c.id] === true ? ' acc' : '') +
    (c.changed ? ' changed' : '');
  const gate = c.gate_ok
    ? '<span class="chip ok">gate ok</span>'
    : '<span class="chip flag" title="' + escAttr(c.gate_problems.join('; ')) + '">gate flag</span>';
  let verdict = '';
  if (c.verdict) for (const v of c.verdict)
    verdict += '<span class="chip ' + esc(v.verdict) + '" title="' + escAttr(v.notes) + '">' +
      esc(v.reviewer) + ':' + esc(v.verdict) + '</span>';
  const changed = c.changed ? '<span class="chip changed" title="repair/revise edited this">changed</span>'
    : (c.origin === 'added' ? '<span class="chip changed">added in review</span>' : '');
  el.innerHTML =
    '<label><input type="checkbox" ' + (state[c.id] === true ? 'checked' : '') + '>' +
    '<span class="txt">' + hlCite(c.text_en) + '</span></label>' + lrefHtml(c.leader_ref) +
    firstDraftBlock(c) +
    '<div class="chips"><span class="chip">' + esc(c.age_tier) + '</span>' +
    '<span class="chip">diff ' + esc(c.difficulty) + '</span>' +
    '<span class="chip">' + esc(c.type) + '</span>' + gate + verdict + changed + '</div>';
  el.querySelector('input').addEventListener('change', e => {
    state[c.id] = e.target.checked;
    el.classList.toggle('acc', e.target.checked);
    save(); tally();
  });
  return el;
}

function renderUnit(unit) {
  const main = document.getElementById('main');
  main.innerHTML = '';
  const briefs = unit.briefs || {};
  const uniq = [];
  for (const r of DATA.runs) {
    const t = briefs[r];
    if (!t) continue;
    const hit = uniq.find(u => u.text === t);
    if (hit) hit.runs.push(r); else uniq.push({ text: t, runs: [r] });
  }
  function briefPanel(label, text) {
    const el = document.createElement('details');
    el.className = 'brief';
    el.innerHTML = '<summary>Brief — ' + esc(unit.id) + ' (' + esc(label) +
      ')</summary><div class="refbody">' + md(text) + '</div>';
    main.appendChild(el);
  }
  if (!uniq.length) {
    briefPanel('none on file', null);
  } else if (uniq.length === 1) {
    briefPanel(uniq[0].runs.length === DATA.runs.length ? 'shared across runs'
               : uniq[0].runs.join(', '), uniq[0].text);
  } else {
    for (const u of uniq) briefPanel(u.runs.join(', '), u.text);
  }
  for (const b of unit.dimensions) {
    const d = document.createElement('details');
    d.className = 'dim';
    d.open = true;
    const counts = DATA.runs.map(r => r + ':' + (b.counts[r] || 0)).join('  ');
    d.innerHTML = '<summary>' + esc(b.dimension) + ' <span class="cnt">' + esc(counts) + '</span></summary>';
    const cols = document.createElement('div');
    cols.className = 'cols';
    for (const r of DATA.runs) {
      const col = document.createElement('div');
      col.className = 'col';
      col.innerHTML = '<h4>' + esc(r) + ' (' + (b.counts[r] || 0) + ')</h4>';
      const items = b.cells[r] || [];
      if (!items.length) col.innerHTML += '<div class="empty">none</div>';
      for (const c of items) col.appendChild(card(c));
      cols.appendChild(col);
    }
    d.appendChild(cols);
    main.appendChild(d);
  }
}

function renderNav() {
  const nav = document.getElementById('nav');
  DATA.units.forEach((u, i) => {
    const b = document.createElement('button');
    b.textContent = u.id;
    b.onclick = () => {
      [...nav.children].forEach(x => x.classList.remove('on'));
      b.classList.add('on');
      renderUnit(u);
    };
    if (i === 0) b.classList.add('on');
    nav.appendChild(b);
  });
}

document.getElementById('export').onclick = () => {
  const accepted = Object.keys(state).filter(k => state[k] === true);
  const rejected = Object.keys(state).filter(k => state[k] === false);
  const out = { book: DATA.book, runs: DATA.runs, generated_from: 'review.html',
    accepted_item_ids: accepted, rejected_item_ids: rejected };
  const blob = new Blob([JSON.stringify(out, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'decisions-' + DATA.book + '.json';
  a.click();
};

document.getElementById('rubric-body').innerHTML = md(DATA.rubric);
renderNav();
if (DATA.units.length) renderUnit(DATA.units[0]);
tally();
</script>
"""


def render_html(model):
    title = model.get("title") or f"Compare runs — {model['book']}"
    note = "  ·  ".join(model.get("notes") or [])
    data = json.dumps(model, ensure_ascii=False).replace("</", "<\\/")
    return (_PAGE
            .replace("__TITLE__", title)
            .replace("__RUNS__", ", ".join(model["runs"]))
            .replace("__NOTE__", note)
            .replace("__MATRIX__", model.get("matrix_html", ""))
            .replace("__DATA__", data))


_STAGE_ORDER = ("brief", "draft", "repair", "review_r1", "review_r2", "revise",
                "evaluate")
_AGG_LABELS = (("calls_total", "calls"), ("claude_calls", "claude calls"),
               ("tokens_in_total", "tok in"), ("tokens_out_total", "tok out"),
               ("estimated_cost", "est cost"), ("first_pass_gate_rate", "1st-pass gate"),
               ("final_gate_rate", "final gate"),
               ("evaluator_is_drafter", "eval=drafter"))


def _experiment_matrix_html(specs):
    """A static route-matrix + telemetry table, one column per experiment, so the
    reviewer sees which model ran each stage and the aggregate efficiency."""
    names = [s["name"] for s in specs]
    head = "".join(f"<th>{_esc(n)}</th>" for n in names)
    rows = []
    for stage in _STAGE_ORDER:
        cells = "".join(
            f"<td>{_esc((s['matrix'].get(stage) or {}).get('backend') or '·')}"
            f" / {_esc((s['matrix'].get(stage) or {}).get('model') or '·')}</td>"
            for s in specs)
        rows.append(f"<tr><th class='stage'>{stage}</th>{cells}</tr>")
    for key, label in _AGG_LABELS:
        cells = "".join(f"<td>{_esc(_fmt_agg((s.get('aggregate') or {}).get(key)))}</td>"
                        for s in specs)
        rows.append(f"<tr><th class='stage'>{label}</th>{cells}</tr>")
    return (
        "<details class='ref' id='routes' open><summary>Experiment route matrix "
        "&amp; telemetry</summary><div class='refbody'>"
        "<table class='matrix'><thead><tr><th>stage</th>" + head + "</tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody></table></div></details>")


def _fmt_agg(v):
    if v is None:
        return "·"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _experiment_specs(experiment_dirs, book):
    """Specs (name/matrix/aggregate/dirs) for the experiments that cover ``book``."""
    specs = []
    for d in experiment_dirs:
        d = pathlib.Path(d)
        manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        name = manifest["name"]
        run_dir = d / book / "runs" / name
        if not (run_dir / "drafts").is_dir():
            continue
        specs.append({
            "name": name,
            "matrix": manifest.get("route_matrix", {}),
            "aggregate": manifest.get("aggregate", {}),
            "dirs": (run_dir / "drafts", run_dir / "verdicts", run_dir / "briefs"),
        })
    return specs


def render_experiments(book, experiment_dirs):
    """Render ONE comparison page whose columns are named experiments (#35).

    ``book`` may be a single book code or a list of book codes; multiple books are
    merged into one page (units are book-prefixed, so they stay distinct), each
    book's units gated against its own book. Per-unit items, citation
    highlighting, leader references, verdict badges, and accept/export are the
    existing per-item rendering, unchanged.
    """
    books = [book] if isinstance(book, str) else list(book)
    all_specs = {}          # name -> spec (first seen), for the route/telemetry matrix
    runs_order, merged_units, notes = [], [], []
    rubric_text = None
    for b in books:
        specs = _experiment_specs(experiment_dirs, b)
        if not specs:
            continue
        by_name = {s["name"]: s["dirs"] for s in specs}
        m = build_model(b, [s["name"] for s in specs],
                        resolve=lambda run, bn=by_name: bn[run])
        merged_units.extend(m["units"])
        notes.extend(m.get("notes") or [])
        rubric_text = m["rubric"]
        for s in specs:
            if s["name"] not in runs_order:
                runs_order.append(s["name"])
            all_specs.setdefault(s["name"], s)
    seen = set()
    notes = [n for n in notes if not (n in seen or seen.add(n))]
    label = ", ".join(books)
    model = {
        "book": "+".join(books),
        "runs": runs_order,
        "notes": notes,
        "rubric": rubric_text or (rubric.build() + "\n\n" + rubric.reference_criteria()),
        "units": merged_units,
        "title": f"Compare experiments — {label}",
        "matrix_html": _experiment_matrix_html(list(all_specs.values())),
        "route_matrix": {n: s["matrix"] for n, s in all_specs.items()},
        "telemetry": {n: s["aggregate"] for n, s in all_specs.items()},
    }
    return render_html(model)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate a multi-run comparison page.")
    ap.add_argument("book", help="book code, e.g. PHP")
    ap.add_argument("--runs", required=True,
                    help="comma-separated run dirs, e.g. drafts_py,drafts_pro")
    ap.add_argument("--base", default=None,
                    help="build root (default work/content_bank_build)")
    ap.add_argument("--out", default=None,
                    help="output html path (default <base>/<BOOK>/review.html)")
    args = ap.parse_args(argv)

    runs = [r.strip() for r in args.runs.split(",") if r.strip()]
    model = build_model(args.book, runs, base=args.base)
    base = pathlib.Path(args.base) if args.base else DEFAULT_BASE
    out = pathlib.Path(args.out) if args.out else base / args.book / "review.html"
    out.write_text(render_html(model), encoding="utf-8")
    n_items = sum(b["counts"][r] for u in model["units"]
                  for b in u["dimensions"] for r in runs)
    print(f"wrote {out}  ({len(model['units'])} units, {len(runs)} runs, "
          f"{n_items} items)")
    if model["notes"]:
        for note in model["notes"]:
            print(f"  note: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
