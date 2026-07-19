"""Per-book build ledger: the stage each pericope/section unit has reached.

Lives in untracked work/ at runtime; this module only reads/writes the JSON.
Stdlib only, offline.
"""
import json
import pathlib

STAGES = ("pending", "briefed", "drafted", "reviewed",
          "in_queue", "confirmed", "published")


def init_manifest(book, pericope_ids, section_ids=()):
    units = {}
    for pid in pericope_ids:
        units[pid] = {"kind": "pericope", "stage": "pending"}
    for sid in section_ids:
        units[sid] = {"kind": "section", "stage": "pending"}
    return {"book": book, "units": units}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, manifest):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def set_stage(manifest, unit_id, stage):
    if stage not in STAGES:
        raise ValueError(f"unknown stage '{stage}' (expected one of {STAGES})")
    if unit_id not in manifest["units"]:
        raise KeyError(f"no unit '{unit_id}' in manifest")
    manifest["units"][unit_id]["stage"] = stage


def units_at(manifest, stage):
    return sorted(u for u, meta in manifest["units"].items()
                  if meta["stage"] == stage)
