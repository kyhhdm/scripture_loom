"""Resolve a Westminster Standards citation against the committed canon
lampposts. WCF ref is "chapter.section"; WLC/WSC ref is "Q<number>".
Returns the cited text if it exists, else None. Network-free."""
import re

from . import corpus_bridge

_FILES = {"WCF": "canon/lampposts/wcf.json",
          "WLC": "canon/lampposts/wlc.json",
          "WSC": "canon/lampposts/wsc.json"}
_WCF_RE = re.compile(r"^(\d+)\.(\d+)$")
_Q_RE = re.compile(r"^Q(\d+)$")


def resolve(std, ref):
    if std not in _FILES:
        return None
    data = corpus_bridge._load(_FILES[std])
    if std == "WCF":
        m = _WCF_RE.match(ref or "")
        if not m:
            return None
        c, sec = int(m.group(1)), int(m.group(2))
        ch = next((x for x in data["chapters"] if x["n"] == c), None)
        if ch is None:
            return None
        s = next((x for x in ch["sections"] if x["n"] == sec), None)
        return s["text"] if s else None
    m = _Q_RE.match(ref or "")
    if not m:
        return None
    n = int(m.group(1))
    q = next((x for x in data["questions"] if x["n"] == n), None)
    return q["a"] if q else None
