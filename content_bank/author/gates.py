"""Deterministic content gates for the standalone builder (issue #16).

Pure functions, each returning ``{item_id: [problems]}`` (empty dict = clean):
- quote_check : language-aware quoted-span verbatim check — English quotes
  (straight/curly double or single) must match the BSB haystack; Chinese
  「…」-quoted spans must match the CUV haystack (by Han-character length)
- cuv_quote_check: standalone CUV-only variant of the quote check
- schema_check: content_bank.lib.schema.validate_item, keyed by id
- refs_in_range: stated verse references must fall in the unit's range
- thread_span_check: cross-item throughline/thread span gate
- dimension_cap_check: caps how many items may cover a given fluency dimension
- glossary_check: flags approved-term glossary misses/violations

Committed replacement for the untracked work/content_bank_build/quote_check.py.
Stdlib + in-repo packages only; offline.
"""
import json
import pathlib
import re

from ..lib import corpus_bridge, schema
from . import glossary as _glossary

_ROOT = pathlib.Path(__file__).resolve().parents[2]
MIN_WORDS = 3
MIN_HAN = 4
_EN_VERSION, _ZH_VERSION = "BSB", "CUV"
_VERSION_FILE = {"BSB": "bsb.json", "CUV": "cuv-simp.json"}
_HAYSTACK_CACHE = {}


def _norm(s):
    s = re.sub(r"[\"'\u201c\u201d\u2018\u2019]", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def _version_text(version):
    if version not in _HAYSTACK_CACHE:
        path = _ROOT / "corpus" / "canon" / "bibles" / _VERSION_FILE[version]
        data = json.loads(path.read_text(encoding="utf-8"))
        parts = []
        for bk in data["books"].values():
            for ch in bk.values():
                for verse in ch.values():
                    if isinstance(verse, str):
                        parts.append(verse)
        _HAYSTACK_CACHE[version] = _norm(" ".join(parts))
    return _HAYSTACK_CACHE[version]


def _zh_quoted_spans(s):
    return (re.findall(r"「([^」]{2,300})」", s)
            + re.findall(r'"([^"]{2,300})"', s)
            + re.findall("\u201c([^\u201d]{2,300})\u201d", s))


def _han_len(s):
    return len(re.findall(r"[一-鿿]", s))


def _lang_strings(item):
    ref = item.get("leader_reference") or {}
    for m in (item.get("text"), ref.get("text"), ref.get("verse")):
        if isinstance(m, dict):
            for lang, s in m.items():
                if isinstance(s, str):
                    yield lang, s


def _has_en_term(text_en, term):
    return re.search(r"\b" + re.escape(term) + r"\b",
                     text_en, re.IGNORECASE) is not None


def glossary_check(items, glossary=None):
    entries = glossary if glossary is not None else _glossary.load_glossary()
    flags = {}
    for it in items:
        en_text = " ".join(s for l, s in _lang_strings(it) if l == "en")
        zh_text = " ".join(s for l, s in _lang_strings(it) if l == "zh")
        if not zh_text:
            continue  # nothing translated yet
        problems = []
        for e in entries:
            if not _has_en_term(en_text, e["en_term"]):
                continue
            if e["zh_term"] not in zh_text:
                problems.append(f"'{e['en_term']}' -> expected '{e['zh_term']}' "
                                f"(source {', '.join(e.get('sources', []))})")
            for wrong in e.get("avoid", []):
                if wrong in zh_text:
                    problems.append(f"'{e['en_term']}' uses forbidden '{wrong}'")
        if problems:
            flags[it["id"]] = problems
    return flags


def _quote_misses_for_lang(item, lang):
    version = _ZH_VERSION if lang == "zh" else _EN_VERSION
    hay = _version_text(version)
    misses = []
    for l, s in _lang_strings(item):
        if l != lang:
            continue
        spans = _zh_quoted_spans(s) if lang == "zh" else _quoted_spans(s)
        for span in spans:
            core = span.strip(" \t\n,.;:!?\"'—-…")
            if lang == "zh":
                if _han_len(core) < MIN_HAN:
                    continue
            elif len(core.split()) < MIN_WORDS:
                continue
            if _norm(core) not in hay:
                misses.append(span)
    return misses


def _book_text(_book):
    return _version_text("BSB")


def _quoted_spans(s):
    return (re.findall(r'"([^"]{3,300})"', s)
            + re.findall("\u201c([^\u201d]{3,300})\u201d", s)
            + re.findall(r"(?<!\w)'([^']{3,300})'(?!\w)", s))


def quote_check(book, items):
    flags = {}
    for it in items:
        misses = _quote_misses_for_lang(it, "en") + _quote_misses_for_lang(it, "zh")
        if misses:
            flags[it["id"]] = misses
    return flags


def cuv_quote_check(items):
    flags = {}
    for it in items:
        misses = _quote_misses_for_lang(it, "zh")
        if misses:
            flags[it["id"]] = misses
    return flags


def schema_check(items):
    flags = {}
    for it in items:
        errs = schema.validate_item(it)
        if errs:
            flags[it["id"]] = errs
    return flags


_REF_TOKEN = re.compile(r"\b[A-Z0-9]{3}\.\d+\.\d+\b")


def _parsed(range_str):
    return corpus_bridge._parse_range(range_str)


def pericope_allowed(book, pericope_id):
    peris = {p["id"]: p for p in corpus_bridge.pericopes(book)}
    if pericope_id not in peris:
        raise ValueError(f"{pericope_id} is not a {book} pericope")
    return [_parsed(peris[pericope_id]["range"])]


def section_allowed(book, section_id):
    from corpus.lib import sections as _sections
    secs = {s["id"]: s for s in _sections.load(book)["sections"]}
    if section_id not in secs:
        raise ValueError(f"{section_id} is not a {book} section")
    sec = secs[section_id]
    peris = corpus_bridge.pericopes(book)
    ids = [p["id"] for p in peris]
    i, j = ids.index(sec["first_pericope"]), ids.index(sec["last_pericope"])
    return [_parsed(p["range"]) for p in peris[i:j + 1]]


def _in_any(book, chapter, verse, allowed):
    return any(b == book and c == chapter and lo <= verse <= hi
               for (b, c, lo, hi) in allowed)


def _stated_refs(item):
    blob = json.dumps(item, ensure_ascii=False)
    tokens = set(_REF_TOKEN.findall(blob))
    tokens.update(item.get("refs") or [])
    return sorted(tokens)


def refs_in_range(items, allowed):
    flags = {}
    for it in items:
        # D5 (Connections) pericope items legitimately cross-reference.
        if "passage" in it and it.get("dimension") == "D5":
            continue
        bad = []
        for ref in _stated_refs(it):
            try:
                b, c, lo, hi = _parsed(ref)
            except (ValueError, AttributeError):
                continue
            if not _in_any(b, c, lo, allowed) or not _in_any(b, c, hi, allowed):
                bad.append(ref)
        if bad:
            flags[it["id"]] = bad
    return flags


DEFAULT_DIM_CAP = 3


def thread_span_check(items, allowed):
    """HARD: a `thread` item must recur across 2+ pericopes, so it is invalid on a
    section that spans a single pericope. `allowed` is the per-pericope range list
    (`section_allowed`), so len == 1 means a single-pericope section."""
    if len(allowed) != 1:
        return {}
    return {it["id"]: ["thread on a single-pericope section (a thread must recur "
                       "across 2+ pericopes)"]
            for it in items if it.get("type") == "thread"}


def dimension_cap_check(items, *, cap=DEFAULT_DIM_CAP):
    """SOFT (anti-padding): flag every item in any dimension the unit emits > cap of.
    Model-independent; fed into the repair loop to prune over-generation, then logged
    (not hard-failed) if still over budget — a rich passage may legitimately exceed."""
    counts = {}
    for it in items:
        counts[it.get("dimension")] = counts.get(it.get("dimension"), 0) + 1
    over = {d for d, n in counts.items() if n > cap}
    if not over:
        return {}
    return {it["id"]: [f"dimension {it.get('dimension')} over cap "
                       f"({counts[it.get('dimension')]} > {cap}); keep the strongest "
                       f"{cap}, drop the rest"]
            for it in items if it.get("dimension") in over}


def run_all(book, items, allowed):
    """The HARD gate tier: quote + schema + ref-range + thread-span. Any flag here is
    a defect the repair loop must clear or the unit fails. Soft anti-padding
    (dimension_cap_check) is deliberately NOT included."""
    merged = {}
    for gate in (quote_check(book, items), schema_check(items),
                 refs_in_range(items, allowed), thread_span_check(items, allowed)):
        for k, v in gate.items():
            merged.setdefault(k, []).extend(v)
    return merged
