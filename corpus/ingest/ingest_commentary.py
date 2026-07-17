"""Ingest Matthew Henry and JFB commentaries into per-book lamppost JSON.

Sources (see corpus/ingest/fetch_commentary_sources.py and
corpus/PROVENANCE.md for how they were fetched):

* JFB (66/66 books) and MHC (65/66 books, missing Song of Solomon) come from
  the HelloAO Free Use Bible API, already carrying scripture anchoring: JFB
  is one block per verse; MHC is one block per commentary "section", whose
  content items are keyed by the section's *starting* verse number (e.g. a
  block numbered 1 that runs through the material up to the next block's
  starting verse minus one). The end of each MHC section is therefore
  derived, not given directly by the source -- see `_last_verse`.
* MHC's missing Song of Solomon is supplemented from the CCEL ThML edition
  (Commentary on the Whole Bible Volume III), which anchors each commentary
  section with `<div class="Commentary" id="Bible:Song.1.2-Song.1.6">` --
  the same kind of built-in section anchoring, a different markup
  convention. This is the only book sourced from CCEL; all others come from
  HelloAO.
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


JFB_DROPPED_INTRO_ONLY = 0  # module-level counter; see _jfb_blocks docstring

# Some JFB chapters are written as continuous per-chapter prose (the whole
# chapter's commentary lives in `introduction`, with verse references
# embedded inline as prose, e.g. "(Son. 1:2-2:7)") rather than discrete verse
# items -- confirmed by inspection, not a parsing bug. Most such chapters are
# correctly numbered by the source and we fall back to a whole-chapter block.
# But a real defect was also found in this same class of chapter: in MRK's
# Passion/Resurrection narrative, several "prose" chapters are filed under
# the WRONG api chapter number (e.g. api chapter 3's prose is actually Mark
# 4's commentary; api chapter 13's is Mark 14's) while true Mark 3, 5, and 15
# never appear anywhere in the source at all -- confirmed by cross-checking
# each prose chapter's own embedded self-citation heading (e.g. "(Mark
# 4:1-34)") against the api-reported chapter number. Where that self-citation
# is present we trust it over the api number (source-derived anchoring, not
# hand reconstruction); where a book shows ANY such mismatch we do not trust
# that book's unlabeled prose chapters either, and drop them rather than
# risk shipping content under the wrong reference.
_CITE_RE = re.compile(r"\(\s*(=?)\s*([1-3]?[A-Za-z]+)\.?\s*(\d+):(\d+)(?:-(\d+))?\)")
_JFB_OWN_CITE_ABBR = {"Mat": "MAT", "Mark": "MRK", "Mar": "MRK", "2Ch": "2CH"}


def _is_heading_text(s):
    letters = [c for c in s if c.isalpha()]
    return len(letters) >= 6 and sum(c.isupper() for c in letters) / len(letters) > 0.8


def _jfb_own_citation(intro, book_code):
    """If `intro` opens with an ALL-CAPS pericope heading followed by a
    parenthetical self-citation (e.g. 'PARABLE OF THE SOWER... (Mark
    4:1-34)'), return (chapter, v1, v2|None) from that citation -- but only
    if it names this same book, so a stray cross-reference can't be
    mistaken for a self-citation. Returns None otherwise."""
    idx = intro.find("\n\n")
    header = intro[:idx] if idx != -1 else intro
    pre = header.split("(", 1)[0]
    if not _is_heading_text(pre):
        return None
    own = [c for c in _CITE_RE.findall(header) if c[0] != "="]
    if not own:
        return None
    _, abbr, c, v1, v2 = own[-1]
    if _JFB_OWN_CITE_ABBR.get(abbr) != book_code:
        return None
    return int(c), int(v1), int(v2) if v2 else None


def _jfb_blocks(book_code):
    """One block per verse (HelloAO already gives per-verse granularity),
    except prose-style chapters -- see module notes above."""
    global JFB_DROPPED_INTRO_ONLY
    chapters = _load_helloao_chapters("jfb", book_code)

    citations = {}
    book_has_mislabeled_chapter = False
    for ch in chapters:
        if ch["content"]:
            continue
        intro = (ch.get("introduction") or "").strip()
        if not intro:
            continue
        cite = _jfb_own_citation(intro, book_code)
        citations[ch["number"]] = cite
        if cite and cite[0] != ch["number"]:
            book_has_mislabeled_chapter = True

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
        intro = (ch.get("introduction") or "").strip()
        if not intro:
            continue
        cite = citations.get(cnum)
        if cite:
            c, v1, v2 = cite
            rng = (refs.fmt(book_code, c, v1) if not v2 or v2 == v1
                   else f"{book_code}.{c}.{v1}-{v2}")
            blocks.append({"range": rng, "text": intro})
        elif not book_has_mislabeled_chapter:
            last_v = _last_verse(book_code, cnum)
            rng = (refs.fmt(book_code, cnum, 1) if last_v == 1
                   else f"{book_code}.{cnum}.1-{last_v}")
            blocks.append({"range": rng, "text": intro})
        else:
            JFB_DROPPED_INTRO_ONLY += 1
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
# CCEL ThML supplement for MHC's Song of Solomon (absent from HelloAO).
# ---------------------------------------------------------------------------
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_NL_RE = re.compile(r"\n{2,}")
_COMMENTARY_OPEN_RE = re.compile(r'<div class="Commentary" id="Bible:([^"]+)">')
_CHAPTER_OPEN_RE = re.compile(r'<div2 title="[^"]*" n="[^"]*"')


def _clean_thml_fragment(raw):
    text = _TAG_RE.sub(" ", raw)
    text = unescape(text)
    text = _WS_RE.sub(" ", text)
    text = _NL_RE.sub("\n", text)
    return text.strip()


def _osis_book_chapter_verse(part, canonical_book):
    _, c, v = part.split(".")
    return canonical_book, c, v


def _osis_range_to_canonical(osis_range, canonical_book):
    """'Song.1.2-Song.1.6' -> 'SNG.1.2-6'; 'Song.1.1' -> 'SNG.1.1'."""
    if "-" not in osis_range:
        _, c, v = _osis_book_chapter_verse(osis_range, canonical_book)
        return f"{canonical_book}.{c}.{v}"
    left, right = osis_range.split("-", 1)
    _, c1, v1 = _osis_book_chapter_verse(left, canonical_book)
    _, c2, v2 = _osis_book_chapter_verse(right, canonical_book)
    left_canon = f"{canonical_book}.{c1}.{v1}"
    return f"{left_canon}-{v2}" if c1 == c2 else f"{left_canon}-{canonical_book}.{c2}.{v2}"


def _mhc_ccel_song_blocks():
    """Song of Solomon (SNG), supplemented from CCEL ThML volume III since
    HelloAO's matthew-henry source omits this book entirely."""
    xml_path = CORPUS / "sources" / "mhc" / "ccel" / "mhc3.xml"
    xml = xml_path.read_text(encoding="utf-8")
    section_start = xml.index('<div1 title="Song of Solomon"')
    section_end = xml.index("</div1>", section_start) + len("</div1>")
    section = xml[section_start:section_end]

    # Boundaries: each commentary-block open tag, plus each chapter-open tag
    # (which marks the start of a new chapter's synopsis/front matter that
    # must NOT be absorbed into the previous chapter's last block).
    boundaries = []
    for m in _COMMENTARY_OPEN_RE.finditer(section):
        boundaries.append((m.start(), m.end(), m.group(1)))
    chapter_starts = {m.start() for m in _CHAPTER_OPEN_RE.finditer(section)}
    cut_points = sorted(chapter_starts | {b[1] for b in boundaries} | {len(section)})

    def next_cut(after):
        for cp in cut_points:
            if cp > after:
                return cp
        return len(section)

    blocks = []
    for _start, body_start, osis_range in boundaries:
        body_end = next_cut(body_start)
        text = _clean_thml_fragment(section[body_start:body_end])
        if not text:
            continue
        blocks.append({"range": _osis_range_to_canonical(osis_range, "SNG"),
                        "text": text})
    return blocks


def read_source_blocks(source_dir, book_code):
    """Dispatch to the right reader for this source_dir/book_code pair.
    source_dir is corpus/sources/mhc or corpus/sources/jfb."""
    dirname = Path(source_dir).name
    if dirname == "jfb":
        return _jfb_blocks(book_code)
    if dirname == "mhc":
        if book_code == "SNG":
            return _mhc_ccel_song_blocks()
        return _mhc_helloao_blocks(book_code)
    raise ValueError(f"unknown source_dir: {source_dir!r}")


if __name__ == "__main__":
    for work, dirname, src in (
            ("Matthew Henry's Commentary", "mhc", CORPUS / "sources" / "mhc"),
            ("Jamieson-Fausset-Brown", "jfb", CORPUS / "sources" / "jfb")):
        for code in books.load():
            write_book(work, dirname, code, read_source_blocks(src, code))
        print(f"{dirname}: 66 books written")
    if JFB_DROPPED_INTRO_ONLY:
        print(f"jfb: dropped {JFB_DROPPED_INTRO_ONLY} unlabeled prose-style "
              f"chapter(s) in books with a confirmed api-chapter-number "
              f"mismatch elsewhere (see PROVENANCE.md)")
