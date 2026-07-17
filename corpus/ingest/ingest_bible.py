"""Ingest a USFM zip from corpus/sources/ into corpus/canon/bibles/<version>.json."""
import io, json, sys, zipfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import books, usfm

CORPUS = Path(__file__).resolve().parents[1]


def ingest(zip_path, version, lang, license_note, source_dir, out_path):
    table = books.load()
    out_books = {}
    with zipfile.ZipFile(zip_path) as z:
        for name in sorted(z.namelist()):
            if not name.lower().endswith((".usfm", ".sfm")):
                continue
            text = z.read(name).decode("utf-8")
            code, chapters, _ = usfm.parse(text)
            if code in table:                 # skip FRT, GLO, apocrypha, etc.
                out_books[code] = chapters
    data = {
        "version": version, "lang": lang,
        "license": license_note, "role": "displayable",
        "source": source_dir, "ingested": date.today().isoformat(),
        "versification_exceptions": {},
        "books": out_books,
    }
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True)
                   + "\n", encoding="utf-8")
    n_verses = sum(len(ch) for b in out_books.values() for ch in b.values())
    print(f"{version}: {len(out_books)} books, {n_verses} verse entries -> {out}")
    return data


RUNS = [
    ("kjv-ebible", "KJV", "en", "kjv"),
    ("web-ebible", "WEB", "en", "web"),
    ("cuv-ebible", "CUV", "zh-Hans", "cuv-simp"),
    ("bsb-ebible", "BSB", "en", "bsb"),
]

if __name__ == "__main__":
    for src_dir, version, lang, out_name in RUNS:
        src = CORPUS / "sources" / src_dir
        meta = json.loads((src / "meta.json").read_text())
        ingest(src / meta["file"], version, lang, "public-domain",
               f"sources/{src_dir}", CORPUS / "canon" / "bibles" / f"{out_name}.json")
