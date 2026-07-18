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
    sys.path.insert(0, str(_CORPUS))
    from lib import passage  # corpus/lib/passage.py
    p = passage.get_passage(version, range_str, mode="product")
    return "\n".join(f"{ref}  {text}" for ref, text in p.verses.items())
