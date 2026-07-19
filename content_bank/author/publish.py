"""Confirm drafted items: stamp provenance, set published, upsert, validate.

The human-confirmation write path. Stdlib only, offline.
"""
import copy

from . import store_writer
from ..lib import content, validate


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
    path = content.store_path(book, store_dir)
    prior = path.read_text(encoding="utf-8") if path.exists() else None
    store_writer.upsert_items(book, stamped, store_dir)
    report = validate.validate_store(book, store_dir)
    if report["errors"]:
        if prior is None:
            path.unlink(missing_ok=True)          # file did not exist before — remove it
        else:
            path.write_text(prior, encoding="utf-8")  # restore prior bytes
        raise ValueError("store invalid after publish: " + "; ".join(report["errors"]))
    return report
