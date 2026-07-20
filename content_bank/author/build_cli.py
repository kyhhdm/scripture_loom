"""Standalone content-bank draft builder (issue #16).

Walks a per-book manifest and, per unit, drives the deterministic pipeline:
prompt-builder -> llm() -> parse -> gates (+ bounded repair) -> gated draft file.
Optional --review adds a two-lens adversarial pass. Items are written
review_status "draft"; staging into the store stays a separate human-gated step.
"""
import argparse
import json
import pathlib
import random
import re
import time

from . import (build_brief_prompt, build_draft_prompt,
               build_section_brief_prompt, gates, manifest as manifest_mod)
from .gates import run_all
from .llm import llm
from llm_core import llm_configured

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_BRIEFS_DIR = pathlib.Path(__file__).parent / "briefs"


class GateError(Exception):
    """Gates never came clean within the repair budget."""


class LLMUnavailable(Exception):
    """No LLM credential configured; the run cannot proceed."""


def _parse_items(text):
    m = _FENCE.search(text)
    body = m.group(1) if m else text
    start = body.find("[")
    end = body.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"no JSON array in LLM output: {text[:200]!r}")
    return json.loads(body[start:end + 1])


def _llm_with_backoff(prompt, *, tries=4, base=2.0):
    last = None
    for attempt in range(1, tries + 1):
        try:
            return llm(prompt)
        except RuntimeError as exc:  # rate-limit / transient; llm_core already retried
            last = exc
            if attempt == tries:
                break
            time.sleep(base ** attempt + random.uniform(0, 1))
    raise last


def _repair_prompt(prompt, items, flags):
    return (prompt
            + "\n\n## Previous attempt (fix and RETURN THE FULL CORRECTED ARRAY)\n"
            + json.dumps(items, ensure_ascii=False)
            + "\n\n## Gate problems to fix (item id -> problems)\n"
            + json.dumps(flags, ensure_ascii=False)
            + "\n\nReturn ONLY the corrected JSON array.")


def _draft_with_repair(prompt, book, allowed, *, max_repair=2):
    items = _parse_items(_llm_with_backoff(prompt))
    flags = run_all(book, items, allowed)
    rounds = 0
    while flags and rounds < max_repair:
        rounds += 1
        items = _parse_items(_llm_with_backoff(_repair_prompt(prompt, items, flags)))
        flags = run_all(book, items, allowed)
    if flags:
        raise GateError(f"gates unclean after {max_repair} repair(s): {flags}")
    return items
