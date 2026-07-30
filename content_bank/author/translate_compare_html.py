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
    # Keep citation tags RAW here: this is a review instrument, and render_html
    # highlights <verse>/<doctrine> spans so the reviewer can verify the ZH
    # translation kept them. (The family-facing kit strips tags.)
    text = (lr.get("text") or {}).get(lang, "")
    verse = (lr.get("verse") or {}).get(lang, "")
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
        cat_en = (first.get("item", {}).get("category") or {}).get("en", "")
        cells = {}
        for t in translators:
            p = loaded[t].get(iid)
            if not p:
                cells[t] = None
                continue
            _, ref_zh, verse_zh = _leader_ref(p["item"], "zh")
            cells[t] = {"zh": (p["item"].get("text") or {}).get("zh", ""),
                        "ref_zh": ref_zh, "verse_zh": verse_zh,
                        "cat_zh": (p["item"].get("category") or {}).get("zh", ""),
                        "gate_ok": p.get("gate_ok", True),
                        "gate_flags": p.get("gate_flags", []),
                        "drift": (p.get("drift") or {}).get("drift", False),
                        "drift_notes": (p.get("drift") or {}).get("notes", ""),
                        "uncertain": p.get("uncertain", []),
                        "suggested_fix": p.get("suggested_fix")}
        rows.append({"id": iid, "en": first.get("en", ""),
                     "cuv": _cuv_for(first.get("cuv_refs")),
                     "ref_label": ref_label, "ref_en": ref_en,
                     "verse_en": verse_en, "cat_en": cat_en, "cells": cells})
    return {"book": book, "draft_run": draft_run, "translators": translators,
            "rows": rows}


def _badge(cls, label, tip):
    """One flag badge; `tip` becomes a hover tooltip (title=) when non-empty."""
    attr = f' title="{html.escape(tip, quote=True)}"' if tip else ""
    return f'<span class="{cls}"{attr}>{label}</span>'


def _flag_badges(cell):
    if cell is None:
        return "<span class=missing>—</span>"
    bits = []
    if not cell["gate_ok"]:
        bits.append(_badge("bad", "gate", "\n".join(cell["gate_flags"])))
    if cell["drift"]:
        bits.append(_badge("bad", "drift", cell.get("drift_notes", "")))
    if cell["uncertain"]:
        bits.append(_badge("warn", "uncertain", "\n".join(cell["uncertain"])))
    return " ".join(bits) or '<span class="ok">ok</span>'


def _suggested_block(cell):
    """Render the drift suggested-fix sub-block, or '' when there is none."""
    fix = cell.get("suggested_fix") if cell else None
    if not fix:
        return ""
    hl = citation_tags.highlight_html
    badges = _flag_badges({"gate_ok": fix.get("gate_ok", True),
                           "gate_flags": fix.get("gate_flags", []),
                           "drift": (fix.get("drift") or {}).get("drift", False),
                           "drift_notes": (fix.get("drift") or {}).get("notes", ""),
                           "uncertain": fix.get("uncertain", [])})
    cuv_note = fix.get("cuv_note", "")
    ref_html = ""
    if cuv_note:
        # CUV-inherent drift: nothing to revise, the CUV must stand.
        head = "<div class=nofix>CUV stands — teach the divergence</div>"
    elif fix.get("changed"):
        zh = hl((fix.get("item") or {}).get("text", {}).get("zh", ""))
        head = f"<div class=zh>{zh}</div>"
        # The drift/fix often lands in the leader-note (answer), not the question
        # text — render the revised reference so that change is visible too.
        label, ref_zh, verse_zh = _leader_ref(fix.get("item") or {}, "zh")
        ref_html = _ref_block(label, ref_zh, verse_zh)
    else:
        head = "<div class=nofix>no fix — CUV wording</div>"
    note_html = (f"<div class=scuvnote><span class=reflabel>CUV divergence (teach):"
                 f"</span> {html.escape(cuv_note)}</div>" if cuv_note else "")
    addresses = fix.get("addresses", "")
    addr = (f"<div class=saddr><span class=reflabel>Addresses drift:</span> "
            f"{html.escape(addresses)}</div>" if addresses else "")
    rationale = html.escape(fix.get("rationale", ""))
    return (f"<div class=suggest><span class=reflabel>Suggested fix:</span> {head}"
            f"{ref_html}{note_html}{addr}<div class=srat>{rationale}</div>"
            f"<div class=badges>{badges}</div></div>")


def _ref_block(label, text, verse):
    """A labelled answer/notes sub-block, or '' when the item has no reference."""
    if not (text or verse):
        return ""
    hl = citation_tags.highlight_html
    parts = [f"<span class=reflabel>{html.escape(label)}:</span> {hl(text)}"]
    if verse:
        parts.append(f"<span class=reflabel>Verse:</span> {hl(verse)}")
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
            zh = citation_tags.highlight_html(c["zh"]) if c else "—"
            ref = _ref_block(r["ref_label"], c["ref_zh"], c["verse_zh"]) if c else ""
            cat = _cat_block(c["cat_zh"]) if c else ""
            sug = _suggested_block(c) if c else ""
            cells.append(f"<td><div class=zh>{zh}</div>{ref}{cat}"
                         f"<div class=badges>{_flag_badges(c)}</div>{sug}</td>")
        en_ref = _ref_block(r["ref_label"], r["ref_en"], r["verse_en"])
        en_cat = _cat_block(r["cat_en"])
        body.append(
            f"<tr><td class=id>{esc(r['id'])}</td>"
            f"<td class=en>{citation_tags.highlight_html(r['en'])}{en_ref}{en_cat}</td>"
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
 .cite{{border-radius:3px;padding:0 1px}}
 .cite-verse{{background:#22c55e2e;box-shadow:inset 0 -2px 0 #22c55eaa}}
 .cite-doctrine{{background:#f59e0b2e;box-shadow:inset 0 -2px 0 #f59e0baa}}
 .citeref{{font-size:9px;font-weight:700;margin-left:2px;padding:0 3px;
   border-radius:6px;vertical-align:super}}
 .cite-verse .citeref{{background:#22c55e;color:#04310f}}
 .cite-doctrine .citeref{{background:#f59e0b;color:#3a2600}}
 .suggest{{margin-top:6px;padding:6px;border-left:3px solid #f59e0b;background:#fffbeb}}
 .suggest .srat{{font-size:11px;color:#92400e;margin-top:2px}}
 .suggest .saddr{{font-size:11px;color:#78350f;margin-top:2px}}
 .suggest .scuvnote{{font-size:12px;color:#1e3a8a;background:#eff6ff;padding:4px;margin-top:3px;border-radius:3px}}
 .nofix{{font-style:italic;color:#92400e}}
</style>
<h1>Translation comparison — {esc(page['book'])} · draft run \
<code>{esc(page['draft_run'])}</code></h1>
<p>English ▸ CUV source ▸ one column per translator. Flags (hover a badge for the \
reason): gate (CUV/glossary fail), drift (back-translation), uncertain \
(model-flagged). Citations: \
<span class="cite cite-verse">verse<sup class=citeref>REF</sup></span> \
<span class="cite cite-doctrine">doctrine<sup class=citeref>STD</sup></span> \
(a good ZH translation keeps every <verse> span, verbatim CUV).</p>
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
