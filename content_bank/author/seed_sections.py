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
from content_bank.author.llm import llm  # patched as seed_sections.llm in tests

_CORPUS_LIB = str(pathlib.Path(corpus_bridge.__file__).resolve().parents[2] / "corpus")
if _CORPUS_LIB not in sys.path:
    sys.path.insert(0, _CORPUS_LIB)
from lib import refs  # corpus/lib/refs.py  # noqa: E402
from corpus.lib import sections as _sections  # validator (corpus lib on sys.path)

_GROUNDING_WORKS = ("jfb", "mhc")   # JFB first (terser), Matthew Henry fallback
_REPO = pathlib.Path(corpus_bridge.__file__).resolve().parents[2]


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


def parse_proposal(text):
    """Extract JSON proposal from LLM completion, tolerating fences and prose.

    Args:
        text: LLM completion text, possibly with markdown code fence.

    Returns:
        dict with 'sections' list.

    Raises:
        ValueError: if no JSON object with 'sections' list found.
    """
    s = text.strip()
    if "```" in s:                                  # strip a code fence if present
        parts = s.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                s = part
                break
    dec = json.JSONDecoder()
    i = 0
    while True:
        start = s.find("{", i)
        if start == -1:
            break
        try:
            obj, _ = dec.raw_decode(s, start)
        except ValueError:
            i = start + 1
            continue
        if isinstance(obj, dict) and isinstance(obj.get("sections"), list):
            return obj
        i = start + 1
    raise ValueError("no JSON object with a 'sections' list in completion")


def assign_section_ids(proposal, book):
    """Assign section IDs in the form <BOOK>-S<n> (1-based array order).

    Args:
        proposal: dict with 'sections' list.
        book: 3-letter book code (e.g., "PHP").

    Returns:
        The same proposal dict with ids assigned.
    """
    for i, sec in enumerate(proposal["sections"], start=1):
        sec["id"] = f"{book}-S{i}"
    return proposal


def verify_markers(sections, pericope_range_by_id):
    """Verify that proposed markers parse and fall within section spans.

    For each section with a non-null marker: keep it only if it refs.parse()s
    AND falls within the section's span (first_pericope range start →
    last_pericope range end via refs.in_range()); otherwise set marker=None
    and append {"id", "marker", "reason"} to dropped.

    Args:
        sections: list of section dicts, each with id, first_pericope,
                  last_pericope, and optional marker.
        pericope_range_by_id: dict mapping pericope id to range string
                              (e.g., {"PHP-001": "PHP.1.1-11"}).

    Returns:
        (sections, dropped) — sections mutated in place, dropped is a list
        of {"id", "marker", "reason"} dicts.
    """
    dropped = []
    for sec in sections:
        mk = sec.get("marker")
        if not mk:
            continue
        reason = None
        try:
            ref = refs.parse(mk)
            span = (refs.parse_range(pericope_range_by_id[sec["first_pericope"]])[0],
                    refs.parse_range(pericope_range_by_id[sec["last_pericope"]])[1])
            if not refs.in_range(ref, span):
                reason = "marker outside section span"
        except (ValueError, KeyError) as e:
            reason = f"marker unresolvable ({e})"
        if reason:
            dropped.append({"id": sec["id"], "marker": mk, "reason": reason})
            sec["marker"] = None
    return sections, dropped


def to_output(sections, book):
    """Build the canon-shaped output map with rationale stripped.

    Args:
        sections: list of section dicts from LLM, with id, title_en,
                  first_pericope, last_pericope, marker, and rationale.
        book: 3-letter book code (e.g., "PHP").

    Returns:
        dict with canonical structure:
        {"book": book, "sections": [...]}
        Each section has fields: id, title_en, title_zh, first_pericope,
        last_pericope, marker, status (status always "seeded"; rationale dropped).
    """
    # Canonical field order: id, title_en, title_zh, first, last, marker, status.
    # rationale is intentionally dropped; title_zh/status are added.
    out = [{"id": s["id"], "title_en": s["title_en"], "title_zh": "",
            "first_pericope": s["first_pericope"],
            "last_pericope": s["last_pericope"],
            "marker": s.get("marker"), "status": "seeded"} for s in sections]
    return {"book": book, "sections": out}


def write_output(sections, book, out_path):
    """Write the canonical section map to a JSON file.

    Creates parent directories as needed. Output is formatted with indent=1,
    ensure_ascii=False, and includes a trailing newline.

    Args:
        sections: list of section dicts.
        book: 3-letter book code.
        out_path: pathlib.Path or str for output JSON file.

    Returns:
        The pathlib.Path to the written file.
    """
    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(to_output(sections, book), ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    return out_path


def render_report(book, sections, dropped):
    """Generate a human-readable text report of the section map.

    Includes per-section details (id, pericope span, marker, title) with
    rationale lines, and a dropped-markers section.

    Args:
        book: 3-letter book code.
        sections: list of section dicts with rationale.
        dropped: list of dropped markers, each with id, marker, and reason.

    Returns:
        Multi-line string formatted for stdout.
    """
    lines = [f"{book}: {len(sections)} sections (status: seeded)"]
    for s in sections:
        mk = s.get("marker") or "-"
        lines.append(f"  {s['id']}  {s['first_pericope']}..{s['last_pericope']}"
                     f"  [{mk}]  {s['title_en']}")
        if s.get("rationale"):
            lines.append(f"      → {s['rationale']}")
    if dropped:
        lines.append("  dropped markers:")
        for d in dropped:
            lines.append(f"    {d['id']}: {d['marker']} ({d['reason']})")
    return "\n".join(lines)


def DEFAULT_OUT(book):
    return _REPO / "work" / "section_seeds" / f"{book.lower()}.json"


def _require_backend(backend):
    if backend == "claude":
        if not shutil.which("claude"):
            raise RuntimeError("backend=claude but the 'claude' CLI is not on "
                               "PATH; install Claude Code or use --backend llm_core")
    else:
        from llm_core import llm_configured
        if not llm_configured():
            raise RuntimeError("no LLM credential configured (ARK_API_KEY); see "
                               ".env.example")


def seed(book, *, backend="claude", model=None, max_repair=2,
         out=None, rationale_file=None, force=False):
    _require_backend(backend)
    os.environ["SCRIPTURE_LOOM_LLM_BACKEND"] = backend
    if model:
        os.environ["SCRIPTURE_LOOM_LLM_MODEL"] = model
    else:
        os.environ.pop("SCRIPTURE_LOOM_LLM_MODEL", None)

    out = pathlib.Path(out) if out else DEFAULT_OUT(book)
    if out.exists() and not force:
        raise FileExistsError(f"{out} exists; pass force=True/--force to overwrite")

    inputs = gather_inputs(book)
    order = [p["id"] for p in inputs["pericopes"]]
    range_by_id = {p["id"]: p["range"] for p in inputs["pericopes"]}
    prompt = build_prompt(inputs)

    errors, proposal = ["(no attempt)"], None
    for _ in range(max_repair + 1):
        text = llm(prompt, model)
        proposal = parse_proposal(text)
        assign_section_ids(proposal, book)
        errors = _sections.validate_data(proposal, order)
        if not errors:
            break
        prompt = build_repair_prompt(build_prompt(inputs), proposal, errors)
    if errors:
        raise RuntimeError("section partition still invalid after "
                           f"{max_repair} repair(s): {errors}")

    sections, dropped = verify_markers(proposal["sections"], range_by_id)
    write_output(sections, book, out)
    report = render_report(book, sections, dropped)
    if rationale_file:
        pathlib.Path(rationale_file).write_text(report + "\n", encoding="utf-8")
    return {"out": out, "sections": sections, "dropped": dropped, "report": report}


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Seed a book's section map (LLM-proposed, validator-guaranteed).")
    ap.add_argument("--book", required=True)
    ap.add_argument("--backend", choices=("claude", "llm_core"), default="claude")
    ap.add_argument("--model", help="override model (default: opus for claude, "
                    "deepseek-v4-flash for llm_core)")
    ap.add_argument("--max-repair", type=int, default=2)
    ap.add_argument("--out", help="output path (default: work/section_seeds/<book>.json)")
    ap.add_argument("--rationale-file", help="also write the report here")
    ap.add_argument("--force", action="store_true", help="overwrite existing --out")
    a = ap.parse_args(argv)
    try:
        res = seed(a.book, backend=a.backend, model=a.model,
                   max_repair=a.max_repair, out=a.out,
                   rationale_file=a.rationale_file, force=a.force)
    except (RuntimeError, FileExistsError) as e:
        print(f"[FAIL] {a.book}: {e}", file=sys.stderr)
        return 1
    print(res["report"])
    print(f"\nStaged → {res['out']}  (review, then copy to "
          f"corpus/canon/structure/sections/{a.book.lower()}.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
