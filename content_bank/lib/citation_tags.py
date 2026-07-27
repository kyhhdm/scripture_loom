"""Inline citation tags emitted by the authoring LLM.

Two elements live inside content text fields:
  <verse ref="PHP.1.6">verbatim Scripture</verse>
  <doctrine std="WCF" ref="1.4">paraphrase of the doctrine</doctrine>

This module parses and strips them. Pure/stdlib; shared by the deterministic
gate (verification) and the reader-facing renderers (strip on display). Review
instruments instead call ``highlight_html`` to SHOW the tags as styled spans.
"""
import html as _html
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


# After html.escape (quote=True): <verse ref="X"> -> &lt;verse ref=&quot;X&quot;&gt;
_HL_VERSE_RE = re.compile(
    r"&lt;verse ref=&quot;(.*?)&quot;&gt;(.*?)&lt;/verse&gt;", re.DOTALL)
_HL_DOCTRINE_RE = re.compile(
    r"&lt;doctrine std=&quot;(.*?)&quot; ref=&quot;(.*?)&quot;&gt;(.*?)"
    r"&lt;/doctrine&gt;", re.DOTALL)


def highlight_html(s):
    """HTML-escape ``s``, then render its <verse>/<doctrine> tags as styled
    spans with the citation shown inline (a ``.cite``/``.citeref`` pair, styled
    by the host page's CSS). Escaping runs FIRST, so item text is injection-safe
    and only our own now-escaped tag syntax is turned into markup. For review
    instruments only — the reader kit uses ``strip_tags``. Non-strings -> ''.
    """
    if not isinstance(s, str):
        return ""
    out = _html.escape(s)
    out = _HL_VERSE_RE.sub(
        lambda m: (f'<span class="cite cite-verse" title="verse {m.group(1)}">'
                   f'{m.group(2)}<sup class="citeref">{m.group(1)}</sup></span>'),
        out)
    out = _HL_DOCTRINE_RE.sub(
        lambda m: (f'<span class="cite cite-doctrine" title="doctrine '
                   f'{m.group(1)} {m.group(2)}">{m.group(3)}'
                   f'<sup class="citeref">{m.group(1)} {m.group(2)}</sup></span>'),
        out)
    return out


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
