"""Ingest Matthew Henry and JFB commentaries into per-book lamppost JSON.

Sources (see corpus/ingest/fetch_commentary_sources.py and
corpus/PROVENANCE.md for how they were fetched):

* JFB (66/66 books) and MHC come from the HelloAO Free Use Bible API, already
  carrying scripture anchoring: JFB is one block per verse; MHC is one block
  per commentary "section", whose content items are keyed by the section's
  *starting* verse number (its end is derived as the next section's start
  minus one, or the chapter's last verse -- see `_last_verse`).

* Some JFB chapters are written as one continuous per-chapter prose essay
  (stored in the chapter's `introduction`, with no per-verse items) rather
  than verse-by-verse. In this source those prose chapters are frequently
  filed under the WRONG api chapter number -- e.g. the whole back half of the
  Psalter (api 70-144 -> true Psalms 71-150) and 2Sa api 22-23 -> true 23-24,
  Mark api 3-14, Matthew api 24-26. The api chapter number therefore CANNOT be
  trusted for a prose-only chapter. We instead read the pericope's own
  embedded self-citation (e.g. "(Psa. 71:1-24)", "(Mark 6:14-29)") and anchor
  to that; a prose-only chapter with no confident same-book self-citation is
  DROPPED (never shipped under an uncorroborated reference) and counted.

* MHC's HelloAO conversion is missing a number of chapters (Song of Solomon
  entirely, plus MAT 19-28, NUM 31-35, JOS 22-23, 2SA 23-24, PSA 72). These
  are backfilled from the CCEL ThML edition (Commentary on the Whole Bible,
  Volumes I-V), which anchors each commentary section with a built-in
  `<div class="Commentary" id="Bible:Matt.19.3-Matt.19.12">` -- the same kind
  of scripture anchoring, a different markup convention. See `_MHC_CCEL`.
"""
import json
import re
import sys
from html import unescape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import books, refs

CORPUS = Path(__file__).resolve().parents[1]


def write_book(work, dirname, book_code, blocks):
    """blocks: list of {"range": canonical range str, "text": str}, in text order."""
    for b in blocks:
        refs.parse_range(b["range"])       # fail fast on bad anchoring
    dest = CORPUS / "canon" / "lampposts" / dirname / f"{book_code.lower()}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(
        {"work": work, "book": book_code, "license": "public-domain",
         "role": "lamppost", "blocks": blocks},
        indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def blocks_for(work_dir, range_str):
    """Return texts of blocks overlapping range_str. Used by drafting prompts."""
    (book, c1, v1), (_, c2, v2) = refs.parse_range(range_str)
    path = Path(work_dir) / f"{book.lower()}.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for b in data["blocks"]:
        (bb, bc1, bv1), (_, bc2, bv2) = refs.parse_range(b["range"])
        if bb == book and not ((bc2, bv2) < (c1, v1) or (bc1, bv1) > (c2, v2)):
            out.append(b["text"])
    return out


# ---------------------------------------------------------------------------
# KJV chapter-length table: MHC's section blocks give a *starting* verse but
# not where the last section of a chapter ends. We close it against the
# actual last verse of that chapter/book, per the already-ingested KJV canon
# bible (corpus/canon/bibles/kjv.json), rather than guessing.
# ---------------------------------------------------------------------------
_KJV_BOOKS = None


def _kjv_chapters(book_code):
    global _KJV_BOOKS
    if _KJV_BOOKS is None:
        with open(CORPUS / "canon" / "bibles" / "kjv.json", encoding="utf-8") as f:
            _KJV_BOOKS = json.load(f)["books"]
    return _KJV_BOOKS[book_code]


def _last_verse(book_code, chapter):
    return max(int(v) for v in _kjv_chapters(book_code)[str(chapter)])


def _join_content(content_list):
    parts = [c for c in content_list if isinstance(c, str)]
    return "".join(parts).strip()


def _load_helloao_chapters(work_dirname, book_code):
    path = CORPUS / "sources" / work_dirname / "helloao" / f"{book_code}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)["chapters"]


# ---------------------------------------------------------------------------
# JFB prose-chapter self-citation.
#
# A parenthetical scripture citation such as "(Psa. 71:1-24)", "(Mark
# 6:14-29)" or "(Sa2 23:1-7)". The abbreviation may be number-suffixed
# ("Sa2"), number-prefixed ("2Sa") or a plain/full name; it may carry a
# trailing period. We recognise all 66 books via `_resolve_book_abbr` so the
# recovery is not limited to the handful of books that were hand-inspected.
# ---------------------------------------------------------------------------
_CITE_RE = re.compile(
    r"\(\s*(=?)\s*(\d?[A-Za-z]{2,4}\d?)\.?\s*(\d+):(\d+)(?:-(\d+))?\)")

# Non-numbered books: 3-4 letter stem (JFB/older abbreviation styles and full
# names) -> USFM code.
_ABBR_SIMPLE = {
    "Gen": "GEN", "Exo": "EXO", "Lev": "LEV", "Num": "NUM", "Deu": "DEU",
    "Jos": "JOS", "Jdg": "JDG", "Rut": "RUT", "Rth": "RUT", "Ezr": "EZR",
    "Ezra": "EZR", "Neh": "NEH", "Est": "EST", "Job": "JOB", "Psa": "PSA",
    "Pro": "PRO", "Ecc": "ECC", "Son": "SNG", "Sol": "SNG", "Isa": "ISA",
    "Jer": "JER", "Lam": "LAM", "Eze": "EZK", "Dan": "DAN", "Hos": "HOS",
    "Joe": "JOL", "Joel": "JOL", "Amo": "AMO", "Amos": "AMO", "Oba": "OBA",
    "Jon": "JON", "Mic": "MIC", "Nah": "NAM", "Hab": "HAB", "Zep": "ZEP",
    "Hag": "HAG", "Zec": "ZEC", "Zac": "ZEC", "Mal": "MAL", "Mat": "MAT",
    "Mar": "MRK", "Mark": "MRK", "Luk": "LUK", "Luke": "LUK", "Joh": "JHN",
    "John": "JHN", "Act": "ACT", "Acts": "ACT", "Rom": "ROM", "Gal": "GAL",
    "Eph": "EPH", "Phi": "PHP", "Col": "COL", "Tit": "TIT", "Phm": "PHM",
    "Plm": "PHM", "Heb": "HEB", "Jam": "JAS", "Jde": "JUD", "Rev": "REV",
}
# Numbered books: alpha stem -> USFM family base (combine with the digit).
_ABBR_NUMBERED = {
    "Sa": "SA", "Sam": "SA", "Ki": "KI", "Kin": "KI", "Kg": "KI",
    "Ch": "CH", "Chr": "CH", "Co": "CO", "Cor": "CO", "Th": "TH",
    "Thes": "TH", "Ti": "TI", "Tim": "TI", "Pe": "PE", "Pet": "PE",
    "Jo": "JN",
}


def _resolve_book_abbr(token):
    """Resolve a JFB/older citation abbreviation to a USFM code, or None.

    Handles number-suffixed ('Sa2', 'Ch2', 'Jo1'), number-prefixed ('2Sa',
    '1Ki') and plain/full names ('Psa', 'Mark', 'Acts')."""
    num = None
    stem = token
    if stem and stem[0].isdigit():
        num, stem = stem[0], stem[1:]
    elif stem and stem[-1].isdigit():
        num, stem = stem[-1], stem[:-1]
    if not stem:
        return None
    stem = stem[:1].upper() + stem[1:].lower()
    if num is None:
        return _ABBR_SIMPLE.get(stem)
    base = _ABBR_NUMBERED.get(stem)
    return f"{num}{base}" if base else None


def _jfb_self_citation(intro, book_code):
    """Return (chapter, v1, v2) from the prose chapter's own embedded pericope
    self-citation, or None.

    The self-citation is the first parenthetical scripture citation in the
    intro that (a) is NOT an '='-prefixed parallel-passage cross-reference,
    (b) names THIS book, and (c) is a multi-verse RANGE (has an end verse) --
    a whole-chapter/pericope reference like "(Psa. 71:1-24)" or "(Mark
    6:14-29)". Single-verse parentheticals are ordinary cross-references, not
    the pericope header, so they are skipped; this is what distinguishes the
    genuine self-citation from stray same-book cross-references that may
    precede it in the summary sentence."""
    for m in _CITE_RE.finditer(intro):
        eq, token, c, v1, v2 = m.groups()
        if eq == "=":
            continue
        if _resolve_book_abbr(token) != book_code:
            continue
        if not v2:
            continue
        return int(c), int(v1), int(v2)
    return None


JFB_DROPPED_PROSE = 0            # module-level counter, printed each run
JFB_DROPPED_DETAIL = []          # (book_code, api_chapter) for reporting


def _jfb_blocks(book_code):
    """One block per verse (HelloAO already gives per-verse granularity).
    Prose-only chapters (no per-verse items) are anchored by their own
    embedded self-citation; those without a confident same-book self-citation
    are dropped and counted -- see module notes above."""
    global JFB_DROPPED_PROSE
    chapters = _load_helloao_chapters("jfb", book_code)

    blocks = []
    for ch in chapters:
        cnum = ch["number"]
        verse_items = [it for it in ch["content"] if it.get("type") == "verse"]
        for item in verse_items:
            text = _join_content(item["content"])
            if not text:
                continue
            blocks.append({"range": refs.fmt(book_code, cnum, item["number"]),
                           "text": text})
        if verse_items:
            continue
        # Prose-only chapter: the api chapter number is untrustworthy. Anchor
        # to the pericope's own self-citation, or drop it.
        intro = (ch.get("introduction") or "").strip()
        if not intro:
            continue
        cite = _jfb_self_citation(intro, book_code)
        if cite is None:
            JFB_DROPPED_PROSE += 1
            JFB_DROPPED_DETAIL.append((book_code, cnum))
            continue
        c, v1, v2 = cite
        rng = (refs.fmt(book_code, c, v1) if v2 == v1
               else f"{book_code}.{c}.{v1}-{v2}")
        blocks.append({"range": rng, "text": intro})
    blocks.sort(key=lambda b: refs.parse_range(b["range"])[0])
    return blocks


def _mhc_helloao_blocks(book_code):
    """One block per commentary section. Each section's `number` is its
    starting verse; its end is the verse before the next section's start,
    or the chapter's last verse for the final section."""
    blocks = []
    for ch in _load_helloao_chapters("mhc", book_code):
        cnum = ch["number"]
        items = [it for it in ch["content"] if it.get("type") == "verse"]
        if str(cnum) not in _kjv_chapters(book_code):
            # Source data quirk (observed in ISA: a phantom chapter number
            # beyond the book's real range, always with zero content items).
            # Fail loudly if it ever carries real content -- that would mean
            # our chapter-length assumption is wrong, not just a stray key.
            if items:
                raise ValueError(
                    f"{book_code} {cnum}: not a real chapter per KJV canon "
                    f"but source has {len(items)} content item(s)")
            continue
        last_v = _last_verse(book_code, cnum)
        for i, item in enumerate(items):
            start = item["number"]
            end = items[i + 1]["number"] - 1 if i + 1 < len(items) else last_v
            if end < start:
                end = start
            text = _join_content(item["content"])
            if not text:
                continue
            rng = (refs.fmt(book_code, cnum, start) if end == start
                   else f"{book_code}.{cnum}.{start}-{end}")
            blocks.append({"range": rng, "text": text})
    return blocks


# ---------------------------------------------------------------------------
# CCEL ThML supplement for MHC chapters absent from the HelloAO conversion.
# ---------------------------------------------------------------------------
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_NL_RE = re.compile(r"\n{2,}")
_COMMENTARY_OPEN_RE = re.compile(r'<div class="Commentary" id="Bible:([^"]+)">')
_CHAPTER_OPEN_RE = re.compile(r'<div2[ >]')

# canonical book -> (CCEL volume file, div1 id in that volume, chapters).
# chapters=None means the whole book is taken from CCEL (HelloAO lacks it);
# a set means only those chapters are backfilled (HelloAO has the rest).
_MHC_CCEL = {
    "SNG": ("mhc3.xml", "Song", None),
    "PSA": ("mhc3.xml", "Ps", {72}),
    "MAT": ("mhc5.xml", "Matt", set(range(19, 29))),
    "NUM": ("mhc1.xml", "Num", {31, 32, 33, 34, 35}),
    "JOS": ("mhc2.xml", "Jos", {22, 23}),
    "2SA": ("mhc2.xml", "iiSam", {23, 24}),
}


def _clean_thml_fragment(raw):
    text = _TAG_RE.sub(" ", raw)
    text = unescape(text)
    text = _WS_RE.sub(" ", text)
    text = _NL_RE.sub("\n", text)
    return text.strip()


def _osis_range_to_canonical(osis_range, canonical_book):
    """'Matt.19.3-Matt.19.12' -> 'MAT.19.3-12'; 'Ps.72.1' -> 'PSA.72.1';
    'Song.1.2-Song.2.7' -> 'SNG.1.2-SNG.2.7'. The OSIS book token is ignored
    (we already know the canonical book); only chapter/verse are read."""
    def cv(part):
        _, c, v = part.split(".")
        return c, v
    if "-" not in osis_range:
        c, v = cv(osis_range)
        return f"{canonical_book}.{c}.{v}"
    left, right = osis_range.split("-", 1)
    c1, v1 = cv(left)
    c2, v2 = cv(right)
    left_canon = f"{canonical_book}.{c1}.{v1}"
    return f"{left_canon}-{v2}" if c1 == c2 else f"{left_canon}-{canonical_book}.{c2}.{v2}"


def _mhc_ccel_blocks(volume_file, div1_id, canonical_book, chapters=None):
    """Extract MHC commentary blocks for one book (optionally restricted to a
    set of chapters) from a CCEL ThML volume, anchored by each section's
    built-in `id="Bible:Book.ch.v-Book.ch.v"`."""
    xml_path = CORPUS / "sources" / "mhc" / "ccel" / volume_file
    xml = xml_path.read_text(encoding="utf-8")
    m = re.search(r'<div1 [^>]*\bid="' + re.escape(div1_id) + r'"[^>]*>', xml)
    if not m:
        raise ValueError(f"{volume_file}: no div1 id={div1_id!r}")
    section_start = m.start()
    section_end = xml.index("</div1>", section_start) + len("</div1>")
    section = xml[section_start:section_end]

    # Boundaries: each commentary-block open tag, plus each chapter-open tag
    # (so a chapter's leading synopsis is never absorbed into the previous
    # chapter's last block).
    boundaries = [(mm.start(), mm.end(), mm.group(1))
                  for mm in _COMMENTARY_OPEN_RE.finditer(section)]
    chapter_starts = {mm.start() for mm in _CHAPTER_OPEN_RE.finditer(section)}
    cut_points = sorted(chapter_starts | {b[1] for b in boundaries} | {len(section)})

    def next_cut(after):
        for cp in cut_points:
            if cp > after:
                return cp
        return len(section)

    blocks = []
    for _start, body_start, osis_range in boundaries:
        start_chapter = int(osis_range.split("-", 1)[0].split(".")[1])
        if chapters is not None and start_chapter not in chapters:
            continue
        body_end = next_cut(body_start)
        text = _clean_thml_fragment(section[body_start:body_end])
        if not text:
            continue
        blocks.append({"range": _osis_range_to_canonical(osis_range, canonical_book),
                       "text": text})
    return blocks


def _mhc_blocks(book_code):
    """MHC section blocks: HelloAO where available, backfilled from CCEL for
    chapters (or whole books) the HelloAO conversion omits."""
    ccel = _MHC_CCEL.get(book_code)
    if ccel and ccel[2] is None:            # whole book from CCEL
        volume_file, div1_id, _ = ccel
        return _mhc_ccel_blocks(volume_file, div1_id, book_code)
    blocks = _mhc_helloao_blocks(book_code)
    if ccel:
        volume_file, div1_id, chapters = ccel
        blocks = blocks + _mhc_ccel_blocks(volume_file, div1_id, book_code, chapters)
        blocks.sort(key=lambda b: refs.parse_range(b["range"])[0])
    return blocks


def read_source_blocks(source_dir, book_code):
    """Dispatch to the right reader for this source_dir/book_code pair.
    source_dir is corpus/sources/mhc or corpus/sources/jfb."""
    dirname = Path(source_dir).name
    if dirname == "jfb":
        return _jfb_blocks(book_code)
    if dirname == "mhc":
        return _mhc_blocks(book_code)
    raise ValueError(f"unknown source_dir: {source_dir!r}")


def _coverage_report(dirname, blocks_by_book):
    """Print, for each book, the chapters that have no block vs KJV -- so a
    within-book chapter gap can never ship silently."""
    total_missing = 0
    lines = []
    for code in books.load():
        covered = set()
        for b in blocks_by_book[code]:
            (_, c1, _), (_, c2, _) = refs.parse_range(b["range"])
            covered.update(range(c1, c2 + 1))
        allch = {int(c) for c in _kjv_chapters(code)}
        missing = sorted(allch - covered)
        if missing:
            total_missing += len(missing)
            lines.append(f"    {code}: missing {missing}")
    print(f"{dirname}: chapter coverage -- {total_missing} missing chapter(s)"
          + (":" if lines else " (complete)"))
    for ln in lines:
        print(ln)


if __name__ == "__main__":
    for work, dirname, src in (
            ("Matthew Henry's Commentary", "mhc", CORPUS / "sources" / "mhc"),
            ("Jamieson-Fausset-Brown", "jfb", CORPUS / "sources" / "jfb")):
        blocks_by_book = {code: read_source_blocks(src, code) for code in books.load()}
        for code in books.load():
            write_book(work, dirname, code, blocks_by_book[code])
        print(f"{dirname}: 66 books written")
        _coverage_report(dirname, blocks_by_book)
    if JFB_DROPPED_PROSE:
        print(f"jfb: dropped {JFB_DROPPED_PROSE} prose-only chapter(s) with no "
              f"confident same-book self-citation (see PROVENANCE.md): "
              f"{JFB_DROPPED_DETAIL}")
