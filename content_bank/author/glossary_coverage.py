"""Glossary-coverage report: which theological terms appear in a book's content
but have no mandated glossary rendering. Deterministic; network-free. The
lexicon is the recognizer (candidate theological vocabulary, broader than the
glossary) so genuinely-missing terms surface, not just tracked ones.
"""
import json
import pathlib
import re

from . import glossary as _glossary
from . import gates

_LEXICON = pathlib.Path(__file__).with_name("theological_lexicon.json")


def load_lexicon(path=None):
    p = pathlib.Path(path) if path else _LEXICON
    return json.loads(p.read_text(encoding="utf-8"))


def _en_text(items):
    return " ".join(s for it in items
                    for l, s in gates._lang_strings(it) if l == "en")


def _present(term, text):
    return re.search(r"\b" + re.escape(term) + r"\b", text, re.IGNORECASE) is not None


def coverage_report(items, glossary=None, lexicon=None):
    entries = glossary if glossary is not None else _glossary.load_glossary()
    terms = lexicon if lexicon is not None else load_lexicon()
    glossed = {e["en_term"].lower() for e in entries}
    text = _en_text(items)
    covered, uncovered = [], []
    for term in terms:
        if not _present(term, text):
            continue
        (covered if term.lower() in glossed else uncovered).append(term)
    return {"covered": sorted(covered), "uncovered": sorted(uncovered)}
