"""Reshape the Westminster standards (WCF, WSC, WLC) from the NonlinearFruit/
Creeds.json source JSON into canon lamppost JSON.

Source is already structured (chapters/sections, questions/answers) with
proof texts given as OSIS-style abbreviated references (e.g. "Ps.19.1-Ps.19.3",
"1Cor.10.31"). We only need to remap book abbreviations to the repo's
canonical USFM-style 3-letter codes and reformat ranges to the
`refs.parse_range`-compatible form.
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import refs as reflib

CORPUS = Path(__file__).resolve().parents[1]

# OSIS-ish source abbreviation -> canonical USFM 3-letter code.
BOOK_MAP = {
    "Gen": "GEN", "Exod": "EXO", "Lev": "LEV", "Num": "NUM", "Deut": "DEU",
    "Josh": "JOS", "Judg": "JDG", "Ruth": "RUT", "1Sam": "1SA", "2Sam": "2SA",
    "1Kgs": "1KI", "2Kgs": "2KI", "1Chr": "1CH", "2Chr": "2CH", "Ezra": "EZR",
    "Neh": "NEH", "Esth": "EST", "Job": "JOB", "Ps": "PSA", "Prov": "PRO",
    "Eccl": "ECC", "Song": "SNG", "Isa": "ISA", "Jer": "JER", "Lam": "LAM",
    "Ezek": "EZK", "Dan": "DAN", "Hos": "HOS", "Joel": "JOL", "Amos": "AMO",
    "Obad": "OBA", "Jonah": "JON", "Mic": "MIC", "Nah": "NAM", "Hab": "HAB",
    "Zeph": "ZEP", "Hag": "HAG", "Zech": "ZEC", "Mal": "MAL",
    "Matt": "MAT", "Mark": "MRK", "Luke": "LUK", "John": "JHN", "Acts": "ACT",
    "Rom": "ROM", "1Cor": "1CO", "2Cor": "2CO", "Gal": "GAL", "Eph": "EPH",
    "Phil": "PHP", "Col": "COL", "1Thess": "1TH", "2Thess": "2TH",
    "1Tim": "1TI", "2Tim": "2TI", "Titus": "TIT", "Phlm": "PHM", "Heb": "HEB",
    "Jas": "JAS", "1Pet": "1PE", "2Pet": "2PE", "1John": "1JN", "2John": "2JN",
    "3John": "3JN", "Jude": "JUD", "Rev": "REV",
}


SKIPPED = 0  # whole-chapter proof texts the book.ch.v schema cannot represent


def _one(ref):
    book, ch, v = ref.split(".")
    return f"{BOOK_MAP[book]}.{ch}.{v}"


def _canon_ref(ref):
    """'Ps.19.1-Ps.19.3' -> 'PSA.19.1-3' (or full form across chapters)."""
    if "-" not in ref:
        return _one(ref)
    left, right = ref.split("-", 1)
    a = _one(left)
    b = _one(right)
    (b1, c1, _), (b2, c2, v2) = reflib.parse(a), reflib.parse(b)
    if b1 == b2 and c1 == c2:
        return f"{a}-{v2}"
    return f"{a}-{b}"


def _proof_texts(section_or_qa):
    """Flatten a source item's Proofs[].References[] into one canonical list.

    Source reference strings occasionally comma-join several refs into one
    array entry (e.g. "Luke.16.29,Luke.16.31") — split those first. A small
    number of references cite a whole chapter with no verse (e.g. "Gen.1",
    "Heb.8-Heb.10"); the book.chapter.verse schema `refs.parse_range` enforces
    cannot represent "whole chapter", so — consistent with the precedent in
    ingest_crossrefs.py of dropping refs the schema cannot express rather than
    fabricating verse bounds — these are skipped and counted in SKIPPED.
    """
    global SKIPPED
    out = []
    for proof in section_or_qa.get("Proofs") or []:
        for ref in proof["References"]:
            for piece in ref.split(","):
                if any(part.count(".") != 2 for part in piece.split("-")):
                    SKIPPED += 1
                    continue
                canon = _canon_ref(piece)
                reflib.parse_range(canon)  # raises if malformed; fail loud
                out.append(canon)
    return out


def parse_confession(data):
    chapters = []
    for item in data:
        sections = []
        for s in item["Sections"]:
            sections.append({
                "n": int(s["Section"]),
                "text": s["Content"],
                "proof_texts": _proof_texts(s),
            })
        chapters.append({
            "n": int(item["Chapter"]),
            "title": item["Title"],
            "sections": sections,
        })
    chapters.sort(key=lambda c: c["n"])
    return chapters


def parse_catechism(data):
    qs = []
    for item in data:
        qs.append({
            "n": item["Number"],
            "q": item["Question"],
            "a": item["Answer"],
            "proof_texts": _proof_texts(item),
        })
    qs.sort(key=lambda q: q["n"])
    return qs


def write(name, data):
    dest = CORPUS / "canon" / "lampposts" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"wrote {dest}")


if __name__ == "__main__":
    src = CORPUS / "sources" / "westminster"
    wcf_src = json.loads((src / "westminster_confession_of_faith.json")
                          .read_text(encoding="utf-8"))
    wsc_src = json.loads((src / "westminster_shorter_catechism.json")
                          .read_text(encoding="utf-8"))
    wlc_src = json.loads((src / "westminster_larger_catechism.json")
                          .read_text(encoding="utf-8"))

    write("wcf.json", {
        "title": "Westminster Confession of Faith",
        "license": "public-domain", "role": "lamppost",
        "chapters": parse_confession(wcf_src["Data"]),
    })
    write("wsc.json", {
        "title": "Westminster Shorter Catechism",
        "license": "public-domain", "role": "lamppost",
        "questions": parse_catechism(wsc_src["Data"]),
    })
    write("wlc.json", {
        "title": "Westminster Larger Catechism",
        "license": "public-domain", "role": "lamppost",
        "questions": parse_catechism(wlc_src["Data"]),
    })
    print(f"skipped {SKIPPED} whole-chapter proof texts "
          f"(book.chapter.verse schema cannot represent them)")
