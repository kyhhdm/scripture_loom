"""Minimal USFM 3 parser: verses + section headings. Stdlib only.

Handles what eBible.org USFM actually contains: \\id \\c \\v, paragraph and
poetry markers whose trailing text continues the current verse, inline char
markers (stripped, content kept), footnotes/cross-refs (stripped entirely),
bridged verses (\\v 17-18 stored under key "17-18").
"""
import re

_NOTE = re.compile(r"\\(f|fe|x)\s.*?\\\1\*", re.S)          # drop content
_CHAR = re.compile(r"\\\+?[a-z]+\d?\s?\*?|\|[^\\]*(?=\\)")   # strip markers, keep text
_WS = re.compile(r"\s+")

# markers whose trailing text belongs to the current verse
_FLOW = {"p", "m", "pi", "pi1", "pi2", "mi", "nb", "pc", "cls", "q", "q1",
         "q2", "q3", "q4", "qr", "qc", "qm", "qm1", "qm2", "li", "li1",
         "li2", "li3", "d", "b", "po", "lh", "lf", "lim", "lim1"}


def _clean(s):
    s = _NOTE.sub("", s)
    s = _CHAR.sub("", s)
    return _WS.sub(" ", s).strip()


def parse(text):
    # Note-stripping (\f...\f*, \x...\x*) must run on the whole accumulated
    # verse text, not per physical line, because footnotes/xrefs can wrap
    # across lines in real eBible.org USFM. So raw text is accumulated per
    # verse here and _clean() is applied once per verse, lazily, right
    # before the verse's raw text would otherwise be overwritten or the
    # parse finishes.
    book, chapters, headings = None, {}, []
    chap, verse = None, None
    raw_verses = {}  # chap -> {verse: raw accumulated text}

    def finalize_verse():
        if chap is not None and verse is not None:
            chapters[chap][verse] = _clean(raw_verses[chap][verse])

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if not line.startswith("\\"):
            if chap is not None and verse is not None:
                raw_verses[chap][verse] += " " + line
            continue
        marker, _, rest = line[1:].partition(" ")
        if marker == "id":
            book = rest.split()[0][:3].upper()
        elif marker == "c":
            finalize_verse()
            chap = rest.split()[0]
            chapters[chap] = {}
            raw_verses[chap] = {}
            verse = None
        elif marker == "v":
            finalize_verse()
            vnum, _, vtext = rest.partition(" ")
            verse = vnum
            raw_verses[chap][verse] = vtext
        elif marker in ("s", "s1", "s2", "s3"):
            headings.append((chap, verse, _clean(rest)))
        elif marker in _FLOW:
            if rest and chap is not None and verse is not None:
                raw_verses[chap][verse] += " " + rest
        # every other marker (\h \toc1 \mt \r \rem …) is ignored
    finalize_verse()
    return book, chapters, headings
