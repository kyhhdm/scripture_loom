"""Seed a book's section map with an LLM, guaranteed by the partition validator.

Sibling of corpus/ingest/seed_pericopes.py, but LLM-based: it PROPOSES a
contiguous named partition of a book's pericopes, the existing
corpus/lib/sections.py validator GUARANTEES it, proposed markers are verified
against the corpus, and the result is STAGED for human confirmation. Not part of
the corpus deterministic rebuild — its committed output is treated as a source.
"""
import argparse
import json
import os
import pathlib
import shutil
import sys

from content_bank.lib import corpus_bridge

_GROUNDING_WORKS = ("jfb", "mhc")   # JFB first (terser), Matthew Henry fallback


def commentary_snippet(range_str, book, max_chars=200):
    """First overlapping commentary block, JFB-preferred, flattened + truncated."""
    blocks_by_work = corpus_bridge.commentary(range_str, book,
                                               works=_GROUNDING_WORKS)
    for work in _GROUNDING_WORKS:
        blocks = blocks_by_work.get(work) or []
        if blocks:
            text = " ".join(blocks[0]["text"].split())
            return work, text[:max_chars]
    return None, ""


def gather_inputs(book):
    peris = []
    for p in corpus_bridge.pericopes(book):
        work, text = commentary_snippet(p["range"], book)
        peris.append({"id": p["id"], "range": p["range"],
                      "title_en": p.get("title_en", ""),
                      "grounding_work": work, "grounding_text": text})
    return {"book": book, "book_name": corpus_bridge.book_name(book),
            "pericopes": peris}
