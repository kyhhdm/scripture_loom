"""Seed pericope divisions for one book from \\s headings in a USFM source.

Boundaries: each heading starts a new pericope at the NEXT verse after the
heading's position; each pericope ends at the verse before the next one starts
(or the book's last verse). Text before the first heading becomes pericope 001.
"""
import json, sys, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import usfm

CORPUS = Path(__file__).resolve().parents[1]


def _last_verse_num(chapters, ch):
    return max(int(k.split("-")[-1]) for k in chapters[ch])


def seed(book_code, source_dir="bsb-ebible"):
    src = CORPUS / "sources" / source_dir
    meta = json.loads((src / "meta.json").read_text())
    chapters = headings = None
    with zipfile.ZipFile(src / meta["file"]) as z:
        for name in sorted(z.namelist()):
            if not name.lower().endswith((".usfm", ".sfm")):
                continue
            code, ch, hd = usfm.parse(z.read(name).decode("utf-8"))
            if code == book_code:
                chapters, headings = ch, hd
                break
    if chapters is None:
        raise SystemExit(f"{book_code} not found in {source_dir}")

    # heading -> start ref (chapter, verse after the heading position)
    starts = []
    for chap, after_verse, title in headings:
        if after_verse is None:
            starts.append((int(chap), 1, title))
        else:
            v = int(after_verse.split("-")[-1]) + 1
            if v > _last_verse_num(chapters, chap):        # heading at chapter end
                chap_n = int(chap) + 1
                starts.append((chap_n, 1, title))
            else:
                starts.append((int(chap), v, title))
    if not starts or starts[0][:2] != (1, 1):
        starts.insert(0, (1, 1, "Opening"))

    ordered_chs = sorted(chapters, key=int)
    last_ch = int(ordered_chs[-1])
    pericopes = []
    for i, (c1, v1, title) in enumerate(starts):
        if i + 1 < len(starts):
            c2, v2 = starts[i + 1][0], starts[i + 1][1] - 1
            if v2 == 0:
                c2 -= 1
                v2 = _last_verse_num(chapters, str(c2))
        else:
            c2, v2 = last_ch, _last_verse_num(chapters, str(last_ch))
        rng = (f"{book_code}.{c1}.{v1}-{v2}" if c1 == c2
               else f"{book_code}.{c1}.{v1}-{book_code}.{c2}.{v2}")
        pericopes.append({"id": f"{book_code}-{i+1:03d}", "range": rng,
                          "title_en": title, "title_zh": "", "status": "seeded"})

    out = CORPUS / "canon" / "structure" / "pericopes" / f"{book_code.lower()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"book": book_code, "pericopes": pericopes},
                              indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{book_code}: {len(pericopes)} pericopes -> {out}")


if __name__ == "__main__":
    seed(sys.argv[1] if len(sys.argv) > 1 else "MAT")

