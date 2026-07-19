"""Confirm drafted items: stamp provenance, set published, upsert, validate.

The human-confirmation write path. Stdlib only, offline.
"""
import copy

from . import store_writer
from ..lib import validate


def _provenance(reviewed_date, confirmed_by, drafted_by, reviewed_by, guardrail):
    return {"drafted_by": drafted_by, "reviewed_by": reviewed_by,
            "reviewed_date": reviewed_date, "guardrail": guardrail,
            "confirmed_by": confirmed_by}


def stamp(items, *, reviewed_date, confirmed_by, drafted_by="claude",
          reviewed_by="claude-adversarial", guardrail="WCF-1"):
    prov = _provenance(reviewed_date, confirmed_by, drafted_by, reviewed_by, guardrail)
    out = []
    for it in items:
        it = copy.deepcopy(it)
        it["review_status"] = "published"
        it["provenance"] = dict(prov)
        ref = it.get("leader_reference")
        if ref is not None:
            ref["provenance"] = {"reviewed_by": reviewed_by,
                                 "reviewed_date": reviewed_date,
                                 "guardrail": guardrail}
        out.append(it)
    return out


def publish(book, items, *, reviewed_date, confirmed_by, store_dir=None, **stamp_kw):
    stamped = stamp(items, reviewed_date=reviewed_date, confirmed_by=confirmed_by,
                    **stamp_kw)
    store_writer.upsert_items(book, stamped, store_dir)
    report = validate.validate_store(book, store_dir)
    if report["errors"]:
        raise ValueError("store invalid after publish: " + "; ".join(report["errors"]))
    return report
