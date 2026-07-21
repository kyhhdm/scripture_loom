"""Standalone Chinese-translation tool: walk a store slice, translate each item
with strict CUV alignment + glossary enforcement, back-translation review, and
emit a human-reviewable proposal per item. NEVER writes the store — see
translate.promote for the human-gated landing step.
"""
import argparse
import json
import os
import pathlib

from ..lib import content
from . import glossary as _glossary
from .translate import translate_with_gates, back_translate_review


def select_items(book, *, item_ids=None, status=None, store_dir=None):
    items = content.load_book_store(book, store_dir).get("items", [])
    if item_ids:
        want = set(item_ids)
        return [it for it in items if it["id"] in want]
    if status:
        return [it for it in items if it.get("review_status") == status]
    return list(items)


def proposal_for(item, book, *, glossary=None, model=None, max_repair=2):
    out = translate_with_gates(item, book, glossary=glossary, model=model,
                               max_repair=max_repair)
    drift = back_translate_review(out["item"], model=model)
    return {"id": item["id"],
            "en": (item.get("text") or {}).get("en", ""),
            "item": out["item"], "cuv_refs": out.get("cuv_refs", []),
            "terms": out["terms"], "uncertain": out["uncertain"],
            "gate_ok": out["gate_ok"], "gate_flags": out["gate_flags"],
            "drift": drift}


def write_proposals(proposals, out_dir):
    d = pathlib.Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    for p in proposals:
        (d / f"{p['id']}.json").write_text(
            json.dumps(p, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--items", nargs="*")
    ap.add_argument("--status")
    ap.add_argument("--model")
    ap.add_argument("--max-repair", type=int, default=2)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    if args.model:
        os.environ["SCRIPTURE_LOOM_LLM_MODEL"] = args.model
    out_dir = args.out or f"work/content_bank_build/{args.book}/translations"
    glossary = _glossary.load_glossary()
    items = select_items(args.book, item_ids=args.items, status=args.status)
    proposals, ok = [], 0
    for it in items:
        try:
            p = proposal_for(it, args.book, glossary=glossary, model=args.model,
                             max_repair=args.max_repair)
        except Exception as exc:  # isolate per item
            print(f"[FAIL] {it['id']}: {exc}")
            continue
        proposals.append(p)
        ok += 1
        print(f"[ok] {it['id']}" + ("" if p["gate_ok"] else " (gate flags)")
              + (" (drift)" if p["drift"]["drift"] else ""))
    write_proposals(proposals, out_dir)
    print(f"Done. proposals={ok}/{len(items)} -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
