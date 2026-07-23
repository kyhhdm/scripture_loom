"""Inline citation tags emitted by the authoring LLM.

Two elements live inside content text fields:
  <verse ref="PHP.1.6">verbatim Scripture</verse>
  <doctrine std="WCF" ref="1.4">paraphrase of the doctrine</doctrine>

This module parses and strips them. Pure/stdlib; shared by the deterministic
gate (verification) and the reader-facing renderers (strip on display).
"""
import re
from collections import namedtuple

Verse = namedtuple("Verse", "ref text")
Doctrine = namedtuple("Doctrine", "std ref text")

_VERSE_RE = re.compile(r'<verse\s+ref="([^"]*)"\s*>(.*?)</verse>', re.DOTALL)
_DOCTRINE_RE = re.compile(
    r'<doctrine\s+std="([^"]*)"\s+ref="([^"]*)"\s*>(.*?)</doctrine>', re.DOTALL)
_ANY_TAG_RE = re.compile(r'</?(?:verse|doctrine)\b[^>]*>')
_V_OPEN, _V_CLOSE = re.compile(r'<verse\b'), re.compile(r'</verse\b')
_D_OPEN, _D_CLOSE = re.compile(r'<doctrine\b'), re.compile(r'</doctrine\b')


def strip_tags(s):
    """Remove every <verse>/<doctrine> open/close tag, keeping inner text."""
    if not isinstance(s, str):
        return s
    return _ANY_TAG_RE.sub("", s)


def parse(s):
    """Return (verses, doctrines, malformed).

    `malformed` is True when the string holds tag markers that did not parse
    as well-formed elements (missing/extra attribute, unbalanced) — the gate
    treats that as fail-closed.
    """
    if not isinstance(s, str):
        return [], [], False
    verses = [Verse(m.group(1), m.group(2)) for m in _VERSE_RE.finditer(s)]
    doctrines = [Doctrine(m.group(1), m.group(2), m.group(3))
                 for m in _DOCTRINE_RE.finditer(s)]
    malformed = (
        len(_V_OPEN.findall(s)) != len(verses)
        or len(_V_CLOSE.findall(s)) != len(verses)
        or len(_D_OPEN.findall(s)) != len(doctrines)
        or len(_D_CLOSE.findall(s)) != len(doctrines))
    return verses, doctrines, malformed
