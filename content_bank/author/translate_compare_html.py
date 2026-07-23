"""Self-contained page comparing one build run's draft translations across
translator models. Reads runs/<draft_run>/translations/<translator>/*.json and
renders: English ▸ CUV source verse ▸ one zh column per translator ▸ flags.
Read-only review instrument; never writes the store.
"""
import argparse
import html
import json
import pathlib

from ..lib import corpus_bridge, citation_tags

_ROOT = "work/content_bank_build"


def _load_translator(book, draft_run, translator, root):
    d = pathlib.Path(root) / book / "runs" / draft_run / "translations" / translator
    out = {}
    for path in sorted(d.glob("*.json")):
        p = json.loads(path.read_text(encoding="utf-8"))
        out[p["id"]] = p
    return out


def _cuv_for(refs):
    for ref in refs or []:
        try:
            return corpus_bridge.passage_text(ref, version="CUV")
        except Exception:
            continue
    return ""


_KIND_LABEL = {"answer_key": "Answer", "leader_note": "Notes"}


def _leader_ref(item, lang):
    """(label, ref-text, verse-text) for one language, or ('', '', '') if none.

    The leader_reference holds the answer key (closed dimensions) or the
    leader note (open dimensions) — the reviewer needs its translation as much
    as the main prompt text, so it gets its own line in every cell.
    """
    lr = item.get("leader_reference") or {}
    if not lr:
        return "", "", ""
    label = _KIND_LABEL.get(lr.get("kind"), "Reference")
    text = citation_tags.strip_tags((lr.get("text") or {}).get(lang, ""))
    verse = citation_tags.strip_tags((lr.get("verse") or {}).get(lang, ""))
    return label, text, verse


def build_page(book, draft_run, translators, *, root=_ROOT):
    loaded = {t: _load_translator(book, draft_run, t, root) for t in translators}
    ids = []
    for t in translators:
        for iid in loaded[t]:
            if iid not in ids:
                ids.append(iid)
    rows = []
    for iid in ids:
        first = next((loaded[t][iid] for t in translators if iid in loaded[t]), {})
        ref_label, ref_en, verse_en = _leader_ref(first.get("item", {}), "en")
        cat_en = citation_tags.strip_tags(
            (first.get("item", {}).get("category") or {}).get("en", ""))
        cells = {}
        for t in translators:
            p = loaded[t].get(iid)
            if not p:
                cells[t] = None
                continue
            _, ref_zh, verse_zh = _leader_ref(p["item"], "zh")
            cells[t] = {"zh": citation_tags.strip_tags(
                            (p["item"].get("text") or {}).get("zh", "")),
                        "ref_zh": ref_zh, "verse_zh": verse_zh,
                        "cat_zh": (p["item"].get("category") or {}).get("zh", ""),
                        "gate_ok": p.get("gate_ok", True),
                        "gate_flags": p.get("gate_flags", []),
                        "drift": p.get("drift", {}).get("drift", False),
                        "uncertain": p.get("uncertain", [])}
        rows.append({"id": iid, "en": citation_tags.strip_tags(first.get("en", "")),
                     "cuv": _cuv_for(first.get("cuv_refs")),
                     "ref_label": ref_label, "ref_en": ref_en,
                     "verse_en": verse_en, "cat_en": cat_en, "cells": cells})
    return {"book": book, "draft_run": draft_run, "translators": translators,
            "rows": rows}


def _flag_badges(cell):
    if cell is None:
        return "<span class=missing>—</span>"
    bits = []
    if not cell["gate_ok"]:
        bits.append('<span class="bad">gate</span>')
    if cell["drift"]:
        bits.append('<span class="bad">drift</span>')
    if cell["uncertain"]:
        bits.append('<span class="warn">uncertain</span>')
    return " ".join(bits) or '<span class="ok">ok</span>'


def _ref_block(label, text, verse):
    """A labelled answer/notes sub-block, or '' when the item has no reference."""
    if not (text or verse):
        return ""
    esc = html.escape
    parts = [f"<span class=reflabel>{esc(label)}:</span> {esc(text)}"]
    if verse:
        parts.append(f"<span class=reflabel>Verse:</span> {esc(verse)}")
    inner = "<br>".join(parts)
    return f"<div class=ref>{inner}</div>"


def _cat_block(text):
    """A labelled category sub-block, or '' when the item has no category."""
    if not text:
        return ""
    return (f"<div class=ref><span class=reflabel>Category:</span> "
            f"{html.escape(text)}</div>")


def render_html(page):
    esc = html.escape
    cols = "".join(f"<th>{esc(t)}</th>" for t in page["translators"])
    body = []
    for r in page["rows"]:
        cells = []
        for t in page["translators"]:
            c = r["cells"].get(t)
            zh = esc(c["zh"]) if c else "—"
            ref = _ref_block(r["ref_label"], c["ref_zh"], c["verse_zh"]) if c else ""
            cat = _cat_block(c["cat_zh"]) if c else ""
            cells.append(f"<td><div class=zh>{zh}</div>{ref}{cat}"
                         f"<div class=badges>{_flag_badges(c)}</div></td>")
        en_ref = _ref_block(r["ref_label"], r["ref_en"], r["verse_en"])
        en_cat = _cat_block(r["cat_en"])
        body.append(
            f"<tr><td class=id>{esc(r['id'])}</td>"
            f"<td class=en>{esc(r['en'])}{en_ref}{en_cat}</td>"
            f"<td class=cuv>{esc(r['cuv'])}</td>{''.join(cells)}</tr>")
    return f"""<!-- self-contained -->
<meta charset="utf-8"><title>Translation comparison — {esc(page['book'])} \
{esc(page['draft_run'])}</title>
<style>
 body{{font:14px/1.5 system-ui,sans-serif;margin:1rem;color:#111}}
 table{{border-collapse:collapse;width:100%}}
 th,td{{border:1px solid #ccc;padding:6px 8px;vertical-align:top;text-align:left}}
 th{{background:#f4f4f4}} .id{{font-family:monospace;font-size:12px;white-space:nowrap}}
 .en{{max-width:22ch}} .cuv{{max-width:26ch;color:#333}} .zh{{max-width:30ch}}
 .ref{{margin-top:5px;padding-top:4px;border-top:1px dotted #ccc;font-size:12px;color:#444}}
 .reflabel{{color:#888;font-weight:600}}
 .badges{{margin-top:4px;font-size:11px}}
 .ok{{color:#2a7}}.bad{{color:#c22;font-weight:600}}.warn{{color:#b70}}
 .missing{{color:#999}}
</style>
<h1>Translation comparison — {esc(page['book'])} · draft run \
<code>{esc(page['draft_run'])}</code></h1>
<p>English ▸ CUV source ▸ one column per translator. Flags: gate (CUV/glossary \
fail), drift (back-translation), uncertain (model-flagged).</p>
<table><thead><tr><th>id</th><th>English</th><th>CUV source</th>{cols}</tr></thead>
<tbody>{''.join(body)}</tbody></table>"""


def main(argv=None):
    ap = argparse.ArgumentParser(description="Compare draft translations across "
                                             "translator models.")
    ap.add_argument("book")
    ap.add_argument("--draft-run", required=True,
                    help="the drafting run dir name, e.g. opus")
    ap.add_argument("--translators", required=True,
                    help="comma-separated translator slugs, e.g. "
                         "deepseek-v4-flash,opus")
    ap.add_argument("--root", default=_ROOT)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    translators = [t.strip() for t in args.translators.split(",") if t.strip()]
    page = build_page(args.book, args.draft_run, translators, root=args.root)
    out = args.out or str(pathlib.Path(args.root) / args.book / "runs"
                          / args.draft_run / "translations" / "review.html")
    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(out).write_text(render_html(page), encoding="utf-8")
    print(f"wrote {out} ({len(page['rows'])} items, "
          f"{len(translators)} translators)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
