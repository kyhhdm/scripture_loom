"""Read-only access to corpus assets the content bank depends on.

Pericope, book, and WCF data are read directly from the corpus JSON canon.
Passage text goes through the corpus license gate (corpus/lib/passage.py),
imported lazily so importing this module never requires the corpus on sys.path.
"""
import json
import pathlib

_REPO = pathlib.Path(__file__).resolve().parents[2]
_CORPUS = _REPO / "corpus"


def _load(rel):
    with open(_CORPUS / rel, encoding="utf-8") as f:
        return json.load(f)


def pericopes(book):
    data = _load(f"canon/structure/pericopes/{book.lower()}.json")
    return data["pericopes"] if isinstance(data, dict) and "pericopes" in data else data


def pericope_ids(book):
    return {p["id"] for p in pericopes(book)}


def book_name(book, lang="en"):
    books = _load("canon/structure/books.json")
    key = "name_zh" if lang == "zh" else "name_en"
    return books[book][key]


def wcf_chapter1_text():
    wcf = _load("canon/lampposts/wcf.json")
    ch1 = next(c for c in wcf["chapters"] if c["n"] == 1)
    lines = [f"Chapter 1: {ch1['title']}"]
    for s in ch1["sections"]:
        lines.append(f"1.{s['n']} {s['text']}")
    return "\n".join(lines)


def passage_text(range_str, version="BSB"):
    import sys
    corpus_dir = str(_CORPUS)
    if corpus_dir not in sys.path:
        sys.path.insert(0, corpus_dir)
    from lib import passage  # corpus/lib/passage.py
    p = passage.get_passage(version, range_str, mode="product")
    # Serve verses in canonical (chapter, verse) order — get_passage's dict is
    # string-keyed, so "MAT.4.10" sorts before "MAT.4.2" unless we sort numerically.
    verses = sorted(p.verses.items(), key=lambda kv: _parse_range(kv[0])[1:3])
    return "\n".join(f"{ref}  {text}" for ref, text in verses)


def _parse_range(range_str):
    """'MAT.5.3-12' or 'MAT.5.3' -> ('MAT', 5, 3, 12)."""
    book, chapter, verses = range_str.split(".", 2)
    v1, v2 = (verses.split("-", 1) if "-" in verses else (verses, verses))
    return book, int(chapter), int(v1), int(v2)


def _overlaps(a, b):
    return a[0] == b[0] and a[1] == b[1] and a[2] <= b[3] and b[2] <= a[3]


def _safe_overlaps(target, ref):
    try:
        return _overlaps(target, _parse_range(ref))
    except (ValueError, AttributeError):
        return False


def commentary(range_str, book="MAT", works=("mhc", "jfb")):
    target = _parse_range(range_str)
    out = {}
    for work in works:
        data = _load(f"canon/lampposts/{work}/{book.lower()}.json")
        blocks = data.get("blocks", []) if isinstance(data, dict) else []
        out[work] = [b for b in blocks if _safe_overlaps(target, b["range"])]
    return out


def crossrefs(range_str, limit=15):
    target = _parse_range(range_str)
    data = _load("canon/structure/crossrefs.json")
    refs = data.get("refs", []) if isinstance(data, dict) else data
    hits = [r for r in refs if _safe_overlaps(target, r["from"])]
    hits.sort(key=lambda r: (-r.get("weight", 0), r.get("to", "")))
    return hits[:limit]


def confessional_refs(range_str):
    target = _parse_range(range_str)

    def _via(proof_texts):
        for pt in proof_texts:
            if _safe_overlaps(target, pt):
                return pt
        return None

    out = {"wcf": [], "wlc": [], "wsc": []}
    wcf = _load("canon/lampposts/wcf.json")
    for ch in wcf["chapters"]:
        for s in ch["sections"]:
            via = _via(s.get("proof_texts", []))
            if via:
                out["wcf"].append({"ref": f"WCF {ch['n']}.{s['n']}",
                                   "title": ch["title"], "text": s["text"], "via": via})
    for key, fname in (("wlc", "wlc.json"), ("wsc", "wsc.json")):
        cat = _load(f"canon/lampposts/{fname}")
        for q in cat["questions"]:
            via = _via(q.get("proof_texts", []))
            if via:
                out[key].append({"ref": f"{key.upper()} Q{q['n']}",
                                 "q": q["q"], "a": q["a"], "via": via})
    return out
