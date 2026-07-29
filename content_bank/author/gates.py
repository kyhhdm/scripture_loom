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
import copy
import json
import pathlib
import re

from ..lib import corpus_bridge, schema, citation_tags, standards
from . import glossary as _glossary

_ROOT = pathlib.Path(__file__).resolve().parents[2]
MIN_WORDS = 3
MIN_HAN = 4
_EN_VERSION, _ZH_VERSION = "BSB", "CUV"
_VERSION_FILE = {"BSB": "bsb.json", "CUV": "cuv-simp.json"}
_HAYSTACK_CACHE = {}


_CJK = "\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef"
_WS_AFTER_CJK = re.compile(rf"(?<=[{_CJK}])\s+")
_WS_BEFORE_CJK = re.compile(rf"\s+(?=[{_CJK}])")


def _norm(s):
    # Drop straight/curly quotes AND CUV corner brackets \u300c\u300d\u300e\u300f so a nested
    # <verse ref>\u300c\u2026CUV\u2026\u300d</verse> verifies against the bracket-free corpus text.
    # (cuv_quote_check extracts text from inside \u300c\u300d before norming, so stripping
    # brackets here is a no-op there; the CUV haystack has no brackets either.)
    s = re.sub(r"[\"'\u201c\u201d\u2018\u2019\u300c\u300d\u300e\u300f]", "", s)
    # CUV poetry/psalms carry Hebrew-cola spacing (a space mid-line) that correct
    # Chinese prose omits; drop whitespace touching any CJK char (Chinese has no
    # inter-word spaces) so a verbatim quote still matches. Latin word-spacing is
    # untouched \u2014 English strings have no CJK chars, so these two subs are no-ops
    # there and BSB comparison behavior is unchanged.
    s = _WS_AFTER_CJK.sub("", s)
    s = _WS_BEFORE_CJK.sub("", s)
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
            + re.findall("\u201c([^\u201d]{3,300})\u201d", s))


def quote_check(book, items):
    flags = {}
    for it in items:
        misses = _quote_misses_for_lang(it, "en") + _quote_misses_for_lang(it, "zh")
        if misses:
            flags[it["id"]] = misses
    return flags


# Scripture convention in Chinese content: corner brackets 「」. Ordinary quotes
# (activity examples, answer options, dialogue) use “ ” and are NOT checked here.
_ZH_SCRIPTURE_SPAN = re.compile(r"「([^」]{2,300})」")


def _item_passage_ranges(item):
    """The verse range(s) an item is 'about': its pericope/section passage resolved
    to CUV-addressable ranges. Best-effort — returns [] if unresolvable."""
    p = item.get("passage") or item.get("section") or ""
    if not p:
        return []
    if "." in p:                         # already a ref-range, e.g. PHP.1.1-11
        return [p]
    book = p[:3]
    try:
        peri = corpus_bridge.pericopes(book)
    except Exception:
        return []
    by_id = {x["id"]: x["range"] for x in peri}
    if p in by_id:                       # pericope id, e.g. JON-004
        return [by_id[p]]
    try:                                 # section id, e.g. JON-S1 -> member pericopes
        from corpus.lib import sections as _sections
        ids = [x["id"] for x in peri]
        for s in _sections.load(book)["sections"]:
            if s["id"] == p:
                i, j = ids.index(s["first_pericope"]), ids.index(s["last_pericope"])
                return [by_id[k] for k in ids[i:j + 1]]
    except Exception:
        pass
    return []


def _declared_cuv(item):
    """Normalized CUV text of everything the item declares: its <verse> refs plus
    its passage/section range. This is the haystack a 「」 span must overlap to be
    treated as an (attempted) Scripture quote."""
    refs = set(_item_passage_ranges(item))
    for _, s in _lang_strings(item):
        for v in citation_tags.parse(s)[0]:
            refs.add(v.ref)
    texts = []
    for r in refs:
        try:
            texts.append(_passage_plain(r, _ZH_VERSION))
        except Exception:
            continue
    return _norm(" ".join(texts))


def _overlaps_cuv(core, declared):
    """True if the span shares any MIN_HAN-length contiguous run with the declared
    CUV — i.e. it is clearly an attempt at the cited passage, not an ordinary quote."""
    return any(core[i:i + MIN_HAN] in declared
               for i in range(len(core) - MIN_HAN + 1))


def _cuv_quote_misses(item):
    declared = _declared_cuv(item)
    misses = []
    for lang, s in _lang_strings(item):
        if lang != "zh":
            continue
        for span in _ZH_SCRIPTURE_SPAN.findall(s):
            # A 「」 may (wrongly) wrap a <verse> tag: 「<verse ref>…</verse>」.
            # citation_check validates the tag; strip tag markup so cuv_quote_check
            # evaluates only the quoted text, not the angle-bracket noise.
            span = citation_tags.strip_tags(span)
            core = _norm(span.strip(" \t\n,.;:!?\"'—-…"))
            if _han_len(core) < MIN_HAN:
                continue
            if core in declared:                 # verbatim CUV from a declared ref
                continue
            if _overlaps_cuv(core, declared):     # attempted verse, but wrong -> flag
                misses.append(span)
            # else: no overlap with any declared ref -> ordinary quote -> skip
    return misses


def cuv_quote_check(items):
    flags = {}
    for it in items:
        misses = _cuv_quote_misses(it)
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


_VERSE_REF_RE = re.compile(r"^[A-Z0-9]{3}\.\d+\.\d+(?:-(?:\d+\.)?\d+)?$")


def _passage_plain(ref, version):
    """Verse text for `ref` with the leading 'MARKER  ' stripped from each line."""
    raw = corpus_bridge.passage_text(ref, version=version)
    out = []
    for line in raw.splitlines():
        parts = line.split("  ", 1)
        out.append(parts[1] if len(parts) == 2 else line)
    return " ".join(out)


def _verse_problem(ref, inner, version, item_type):
    """Return a flag string if the tagged verse fails, else None."""
    if not _VERSE_REF_RE.match(ref):
        return f"citation.malformed: bad verse ref '{ref}'"
    try:
        hay = _norm(_passage_plain(ref, version))
    except Exception:
        return f"citation.verse_mismatch: '{ref}' does not resolve in {version}"
    core = _norm(inner)
    if not core:
        return f"citation.verse_mismatch: '{ref}' has empty quote"
    ok = (core == hay) if item_type == "memory_verse" else (core in hay)
    if not ok:
        return (f"citation.verse_mismatch: '{ref}' inner text does not match "
                f"{version}")
    return None


def _untagged_quote_flags(item, langs):
    """EN recall net: verbatim BSB spans left outside a <verse> tag."""
    if langs is not None and "en" not in langs:
        return []
    from . import quote_detect  # lazy: quote_detect imports gates
    covered = []
    stripped = copy.deepcopy(item)
    for m in (stripped.get("text"), (stripped.get("leader_reference") or {}).get("text"),
              (stripped.get("leader_reference") or {}).get("verse")):
        if isinstance(m, dict) and isinstance(m.get("en"), str):
            verses, _, _ = citation_tags.parse(m["en"])
            covered.extend(_norm(v.text) for v in verses)
            m["en"] = citation_tags.strip_tags(m["en"])
    out = []
    for hit in quote_detect.detect_quotes(stripped, None):
        q = _norm(hit["quote"])
        if any(q in c or c in q for c in covered):
            continue
        out.append(f"citation.untagged_quote: '{hit['quote']}' ({hit['ref']}) "
                   f"not wrapped in a <verse> tag")
    return out


def _untagged_zh_quote_flags(item, langs):
    """ZH recall net: a verbatim-CUV 「…」 span left OUTSIDE a <verse> tag. In the
    ZH form every Scripture quote is <verse ref>「…CUV…」</verse>, so a bare 「…」
    that is verbatim CUV means the model dropped the tag — flag it for repair."""
    if langs is not None and "zh" not in langs:
        return []
    hay = _version_text(_ZH_VERSION)
    out = []
    for lang, s in _lang_strings(item):
        if lang != "zh":
            continue
        verses, _, _ = citation_tags.parse(s)
        covered = {_norm(v.text) for v in verses}   # brackets stripped by _norm
        for span in _zh_quoted_spans(s):
            core = _norm(span.strip(" \t\n,.;:!?\"'—-…"))
            if _han_len(core) < MIN_HAN:
                continue
            if core in hay and core not in covered:
                out.append(f"citation.untagged_quote: '{span}' (verbatim CUV) "
                           f"not wrapped in a <verse> tag")
    return out


def citation_check(items, *, langs=None):
    """Verify declared citations. quote-mode: <verse> inner text is verbatim in
    the corpus version for its language (equality for memory_verse, containment
    otherwise). basis-mode: <doctrine> ref resolves in WCF/WLC/WSC. Fail-closed
    on malformed markup. quote_detect recall net flags untagged verbatim spans."""
    flags = {}
    for it in items:
        problems = []
        itype = it.get("type")
        for lang, s in _lang_strings(it):
            if langs is not None and lang not in langs:
                continue
            verses, doctrines, malformed = citation_tags.parse(s)
            if malformed:
                problems.append("citation.malformed: unbalanced or malformed "
                                "<verse>/<doctrine> markup")
            version = _ZH_VERSION if lang == "zh" else _EN_VERSION
            for v in verses:
                p = _verse_problem(v.ref, v.text, version, itype)
                if p:
                    problems.append(p)
            for d in doctrines:
                if standards.resolve(d.std, d.ref) is None:
                    problems.append(f"citation.basis_unresolved: {d.std} {d.ref}")
        problems.extend(_untagged_quote_flags(it, langs))
        problems.extend(_untagged_zh_quote_flags(it, langs))
        if problems:
            flags[it["id"]] = problems
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


_REVEAL_KIND_FOR_DIM = {"D3": "answer_key", "D7": "leader_note"}


def section_reveal_check(items):
    """HARD: every section-level `throughline`/`thread` is a discovery question and
    MUST carry a leader_reference reveal whose kind matches its dimension
    (D3 -> answer_key, D7 -> leader_note). Missing reveal or mismatched kind is a
    defect. Non-section types are untouched (their reveal rules live elsewhere)."""
    flags = {}
    for it in items:
        if it.get("type") not in ("throughline", "thread"):
            continue
        want = _REVEAL_KIND_FOR_DIM.get(it.get("dimension"))
        lr = it.get("leader_reference")
        if not lr:
            flags[it["id"]] = [f"section item missing its leader_reference reveal "
                               f"(expected kind '{want}')"]
        elif lr.get("kind") != want:
            flags[it["id"]] = [f"reveal kind '{lr.get('kind')}' does not match "
                               f"dimension {it.get('dimension')} (expected '{want}')"]
    return flags


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
    """The HARD gate tier: quote + schema + ref-range + thread-span + section-reveal
    + citation. Any flag here is a defect the repair loop must clear or the unit
    fails. Soft anti-padding (dimension_cap_check) is deliberately NOT included."""
    merged = {}
    for gate in (quote_check(book, items), schema_check(items),
                 refs_in_range(items, allowed), thread_span_check(items, allowed),
                 section_reveal_check(items), citation_check(items)):
        for k, v in gate.items():
            merged.setdefault(k, []).extend(v)
    return merged
