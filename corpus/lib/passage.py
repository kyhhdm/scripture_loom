"""The one read path for Bible text: get_passage with the license gate.

Product rule: only role=displayable AND license in OPEN_LICENSES may be
served in product mode. Copyrighted personal copies (sources/private/) are
served only in mode='personal' and are never displayable.
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path
from . import refs

CORPUS = Path(__file__).resolve().parents[1]
OPEN_LICENSES = {"public-domain", "CC-BY"}
CANON_VERSIONS = {"KJV": "kjv", "WEB": "web", "CUV": "cuv-simp", "BSB": "bsb"}
_PRIVATE_VERSION_RE = re.compile(r"[A-Za-z0-9_-]+")


class LicenseError(Exception):
    pass


@dataclass
class Passage:
    version: str
    range: str
    verses: dict
    license: str
    role: str
    displayable: bool


def _gate(data, mode):
    open_ok = (data.get("role") == "displayable"
               and data.get("license") in OPEN_LICENSES)
    if mode == "product" and not open_ok:
        raise LicenseError(
            f"{data.get('version')}: role={data.get('role')} "
            f"license={data.get('license')} not allowed in product mode")
    return open_ok


def _load(version, mode):
    if version in CANON_VERSIONS:
        path = CORPUS / "canon" / "bibles" / f"{CANON_VERSIONS[version]}.json"
    else:
        if not _PRIVATE_VERSION_RE.fullmatch(version):
            raise LicenseError(f"{version}: invalid version name")
        path = CORPUS / "sources" / "private" / f"{version.lower()}.json"
        if mode != "personal":
            raise LicenseError(f"{version}: private versions require mode='personal'")
    if not path.exists():
        raise LicenseError(f"{version}: no canon or private text available")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_passage(version, range_str, mode="product"):
    data = _load(version, mode)
    displayable = _gate(data, mode)
    if version not in CANON_VERSIONS:
        displayable = False           # private texts are never displayable
    (book, c1, v1), (_, c2, v2) = refs.parse_range(range_str)
    verses = {}
    for ch_key, ch in data["books"].get(book, {}).items():
        for v_key, text in ch.items():
            # Some versions (WEB, CUV) store a bridged verse under a range key
            # like "17-18" with shared text. Emit the canonical single-verse ref
            # for the FIRST covered verse so every key round-trips through
            # refs.parse (a range string like MAT.5.17-18 would not).
            v = int(v_key.split("-")[0])
            if refs.in_range((book, int(ch_key), v), ((book, c1, v1), (book, c2, v2))):
                verses[refs.fmt(book, int(ch_key), v)] = text
    return Passage(version=version, range=range_str, verses=verses,
                   license=data["license"], role=data["role"],
                   displayable=displayable)
