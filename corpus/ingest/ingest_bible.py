"""Ingest a USFM zip from corpus/sources/ into corpus/canon/bibles/<version>.json."""
import io, json, sys, zipfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import books, usfm

CORPUS = Path(__file__).resolve().parents[1]

MAX_EXCEPTIONS = 120


def _expand(vkey):
    """Verse-key coverage: '17-18' covers verses 17 and 18."""
    if "-" in vkey:
        a, b = vkey.split("-")
        return range(int(a), int(b) + 1)
    return (int(vkey),)


def _verse_numbers(books_dict):
    """book -> chapter -> set of covered verse numbers.

    A verse key whose text is empty after cleanup (e.g. WEB's Romans 16:25,
    which is nothing but a footnote pointing readers to the relocated
    doxology at 14:24-26) does not count as content actually present --
    otherwise a genuinely omitted verse would be missed just because the
    version kept a placeholder key.
    """
    out = {}
    for code, chapters in books_dict.items():
        out[code] = {}
        for ch, verses in chapters.items():
            nums = set()
            for vkey, text in verses.items():
                if not text.strip():
                    continue
                nums.update(_expand(vkey))
            out[code][ch] = nums
    return out


def derive_versification_exceptions(out_books, kjv_books):
    """Compare per-chapter verse-number coverage against canonical KJV.

    Verse present in KJV but absent from this version -> "omitted".
    Verse present in this version but absent from KJV -> "added".
    """
    if kjv_books is None:
        return {}
    version_nums = _verse_numbers(out_books)
    kjv_nums = _verse_numbers(kjv_books)
    exceptions = {}
    for code, kjv_chapters in kjv_nums.items():
        version_chapters = version_nums.get(code, {})
        for ch, kjv_set in kjv_chapters.items():
            version_set = version_chapters.get(ch, set())
            for v in kjv_set - version_set:
                exceptions[f"{code}.{ch}.{v}"] = "omitted"
            for v in version_set - kjv_set:
                exceptions[f"{code}.{ch}.{v}"] = "added"
    return exceptions


def ingest(zip_path, version, lang, license_note, source_dir, out_path, kjv_books=None):
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

    if version == "KJV":
        exceptions = {}
    else:
        exceptions = derive_versification_exceptions(out_books, kjv_books)
        if len(exceptions) > MAX_EXCEPTIONS:
            raise RuntimeError(
                f"{version}: derived {len(exceptions)} versification exceptions "
                f"(> {MAX_EXCEPTIONS}) -- likely a parser/comparison bug, refusing to write")

    data = {
        "version": version, "lang": lang,
        "license": license_note, "role": "displayable",
        "source": source_dir, "ingested": date.today().isoformat(),
        "versification_exceptions": exceptions,
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
    kjv_books = None
    for src_dir, version, lang, out_name in RUNS:
        src = CORPUS / "sources" / src_dir
        meta = json.loads((src / "meta.json").read_text())
        data = ingest(src / meta["file"], version, lang, "public-domain",
                       f"sources/{src_dir}", CORPUS / "canon" / "bibles" / f"{out_name}.json",
                       kjv_books=kjv_books)
        if version == "KJV":
            kjv_books = data["books"]
