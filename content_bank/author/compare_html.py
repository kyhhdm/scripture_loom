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
from ..lib import citation_tags

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
    return {
        "kind": lr.get("kind"),
        "text_en": citation_tags.strip_tags((lr.get("text") or {}).get("en")),
        "verse_en": citation_tags.strip_tags((lr.get("verse") or {}).get("en")),
    }


def _card(item, run, gate_flags, unit_verdicts):
    iid = item.get("id")
    problems = gate_flags.get(iid, [])
    return {
        "id": iid,
        "run": run,
        "dimension": item.get("dimension"),
        "type": item.get("type"),
        "age_tier": item.get("age_tier"),
        "difficulty": item.get("difficulty"),
        "text_en": citation_tags.strip_tags((item.get("text") or {}).get("en")) or "(no en text)",
        "leader_ref": _leader_ref(item),
        "gate_ok": not problems,
        "gate_problems": problems,
        "verdict": unit_verdicts.get(iid),
    }


def build_model(book, runs, base=None):
    """Assemble the nested comparison model: unit -> dimension -> run -> [item cards].

    Raises FileNotFoundError if a named run directory is missing. A run missing a
    given unit file contributes zero items for that unit (no error) — that raggedness
    is the padding signal the reviewer is looking for.
    """
    base = pathlib.Path(base) if base else DEFAULT_BASE
    book_dir = base / book
    notes = []

    run_items = {}   # run -> {unit_id: [items]}
    verdicts = {}    # run -> {unit_id: {item_id: [...]}}
    briefs_dirs = {}  # run -> briefs dir or None
    for run in runs:
        draft_dir, verdicts_dir, briefs_dir = _resolve_run(book_dir, run)
        run_items[run] = {
            f.stem: json.loads(f.read_text(encoding="utf-8"))
            for f in sorted(pathlib.Path(draft_dir).glob("*.json"))
        }
        verdicts[run] = _load_verdicts(verdicts_dir)
        briefs_dirs[run] = briefs_dir

    gate_flags = {run: _run_gates(book, run_items[run], notes) for run in runs}

    all_units = sorted({u for run in runs for u in run_items[run]})
    units = []
    for unit in all_units:
        present = {it.get("dimension") for run in runs
                   for it in run_items[run].get(unit, []) if it.get("dimension")}
        ordered = [d for d in DIM_ORDER if d in present] + \
                  [d for d in sorted(present) if d not in DIM_ORDER]
        blocks = []
        for dim in ordered:
            cells, counts = {}, {}
            for run in runs:
                items = [it for it in run_items[run].get(unit, [])
                         if it.get("dimension") == dim]
                cells[run] = [_card(it, run, gate_flags[run],
                                    verdicts[run].get(unit, {})) for it in items]
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
</style>
<header>
  <h1>__TITLE__</h1>
  <span id="tally"></span>
  <button id="export">Export decisions</button>
  <span style="color:#888;font-size:12px">runs: __RUNS__</span>
</header>
<div id="note">__NOTE__</div>
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
  for (const r of DATA.runs) TOTAL += (b.cells[r] || []).length;

function save() { localStorage.setItem(KEY, JSON.stringify(state)); }
function tally() {
  const acc = Object.values(state).filter(v => v === true).length;
  document.getElementById('tally').textContent = acc + ' accepted / ' + TOTAL + ' items';
}
function esc(s) { const d = document.createElement('div'); d.textContent = s == null ? '' : s; return d.innerHTML; }
// Attribute-safe: esc() does not escape quotes, so a note containing " would close
// a title="..." attribute early and drop the tooltip. Escape quotes too.
function escAttr(s) { return esc(s).replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
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

function card(c) {
  const el = document.createElement('div');
  el.className = 'card' + (state[c.id] === true ? ' acc' : '');
  const gate = c.gate_ok
    ? '<span class="chip ok">gate ok</span>'
    : '<span class="chip flag" title="' + escAttr(c.gate_problems.join('; ')) + '">gate flag</span>';
  let verdict = '';
  if (c.verdict) for (const v of c.verdict)
    verdict += '<span class="chip ' + esc(v.verdict) + '" title="' + escAttr(v.notes) + '">' +
      esc(v.reviewer) + ':' + esc(v.verdict) + '</span>';
  let lref = '';
  if (c.leader_ref && c.leader_ref.text_en) {
    const lr = c.leader_ref;
    const kind = (lr.kind === 'answer_key') ? 'Answer key'
      : (lr.kind === 'leader_note') ? 'Leader note' : (lr.kind || 'Leader ref');
    lref = '<div class="lref"><span class="lref-kind">' + esc(kind) + '</span>' +
      (lr.verse_en ? '<span class="lref-verse">' + esc(lr.verse_en) + '</span>' : '') +
      '<div>' + esc(lr.text_en) + '</div></div>';
  }
  el.innerHTML =
    '<label><input type="checkbox" ' + (state[c.id] === true ? 'checked' : '') + '>' +
    '<span class="txt">' + esc(c.text_en) + '</span></label>' + lref +
    '<div class="chips"><span class="chip">' + esc(c.age_tier) + '</span>' +
    '<span class="chip">diff ' + esc(c.difficulty) + '</span>' +
    '<span class="chip">' + esc(c.type) + '</span>' + gate + verdict + '</div>';
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
    title = f"Compare runs — {model['book']}"
    note = "  ·  ".join(model.get("notes") or [])
    data = json.dumps(model, ensure_ascii=False).replace("</", "<\\/")
    return (_PAGE
            .replace("__TITLE__", title)
            .replace("__RUNS__", ", ".join(model["runs"]))
            .replace("__NOTE__", note)
            .replace("__DATA__", data))


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
