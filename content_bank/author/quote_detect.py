"""Content-based BSB quote detection.

Finds maximal spans of an item's English text that appear verbatim in the BSB
of the item's own passage + any structured ref it cites — independent of
quotation marks. Each hit carries the ref whose text matched (the CUV-mapping
key). Network-free; reads only committed corpus JSON.
"""
from ..lib import corpus_bridge
from . import gates

DETECT_MIN_WORDS = 4


def _detect_ranges(item):
    ranges = []
    if item.get("passage"):
        ranges.append(item["passage"])
    for tok in gates._stated_refs(item):
        if tok not in ranges:
            ranges.append(tok)
    return ranges


def _english_strings(item):
    out = []
    t = item.get("text") or {}
    if isinstance(t.get("en"), str):
        out.append(t["en"])
    ref = item.get("leader_reference") or {}
    for key in ("text", "verse"):
        m = ref.get(key) or {}
        if isinstance(m.get("en"), str):
            out.append(m["en"])
    return out


def _haystacks(item):
    hays = []
    for r in _detect_ranges(item):
        try:
            text = corpus_bridge.passage_text(r, version="BSB")
        except Exception:
            continue
        hays.append((r, gates._norm(text)))
    return hays


def detect_quotes(item, book):
    hays = _haystacks(item)
    found = []
    for s in _english_strings(item):
        words = s.split()
        n = len(words)
        i = 0
        while i < n:
            best_j, best_ref = i, None
            j = i + 1
            while j <= n:
                phrase = gates._norm(" ".join(words[i:j]))
                match = next((ref for ref, h in hays if phrase and phrase in h), None)
                if match is None:
                    break
                best_j, best_ref = j, match
                j += 1
            if best_j - i >= DETECT_MIN_WORDS:
                found.append({"quote": " ".join(words[i:best_j]), "ref": best_ref})
                i = best_j
            else:
                i += 1
    return found
