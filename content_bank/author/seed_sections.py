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


_RANGE_HINT = "roughly 3-12, more for long narrative books"


def build_prompt(inputs):
    lines = [
        f"You are partitioning the book of {inputs['book_name']} "
        f"({inputs['book']}) into its major movements (\"sections\").",
        "",
        "You are given the book's pericopes IN ORDER, each with a short title "
        "and a snippet of public-domain commentary (Jamieson-Fausset-Brown or "
        "Matthew Henry) for grounding. Group these pericopes into contiguous "
        f"named movements ({_RANGE_HINT}). Rules:",
        "- Every pericope belongs to exactly ONE section; sections are "
        "contiguous and in order (no gaps, no overlaps, full coverage).",
        "- title_en uses the form \"Label: Description\" "
        "(e.g. \"Book One: The Sermon on the Mount\").",
        "- marker: a canonical verse ref BOOK.CH.V ONLY where a clear repeating "
        "textual formula hinges the movement (e.g. Matthew's \"when Jesus had "
        "finished\"); otherwise null. Do not invent markers.",
        "- rationale: ONE line, grounded in the commentary, for the boundary.",
        "- Do NOT include an id field; ids are assigned downstream.",
        "",
        "Pericopes:",
    ]
    for p in inputs["pericopes"]:
        g = f"  [{p['grounding_work']}] {p['grounding_text']}" if p["grounding_text"] else ""
        lines.append(f"- {p['id']} ({p['range']}): {p['title_en']}{g}")
    lines += [
        "",
        "Respond with STRICT JSON only, no prose, no code fence:",
        '{"sections": [{"title_en": "...", "first_pericope": "<id>", '
        '"last_pericope": "<id>", "marker": null, "rationale": "..."}]}',
    ]
    return "\n".join(lines)


def build_repair_prompt(base_prompt, proposal, errors):
    return (base_prompt + "\n\nYour previous answer was:\n"
            + json.dumps(proposal, ensure_ascii=False)
            + "\n\nIt FAILED validation:\n- " + "\n- ".join(errors)
            + "\n\nReturn corrected STRICT JSON only.")
