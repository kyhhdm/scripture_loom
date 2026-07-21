"""Mandated theological term glossary: English head-term -> Chinese rendering,
each traceable to CUV (biblical terms) and/or the Westminster Standards
(doctrinal terms). Term-level vocabulary only — see the licensing guard in
docs/superpowers/specs/2026-07-21-cuv-alignment-translation-design.md.
"""
import json
import pathlib

_DEFAULT = pathlib.Path(__file__).with_name("glossary.json")


def load_glossary(path=None):
    p = pathlib.Path(path) if path else _DEFAULT
    return json.loads(p.read_text(encoding="utf-8"))


def validate_glossary(entries):
    errors = []
    seen = set()
    for e in entries:
        term = e.get("en_term")
        if not term:
            errors.append("entry missing en_term")
            continue
        if not e.get("zh_term"):
            errors.append(f"{term}: missing zh_term")
        if not e.get("sources"):
            errors.append(f"{term}: needs at least one source")
        if term.lower() in seen:
            errors.append(f"{term}: duplicate en_term")
        seen.add(term.lower())
    return errors
