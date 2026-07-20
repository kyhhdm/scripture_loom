"""Confirm drafted items: stamp provenance, set published, upsert, validate.

The human-confirmation write path. Stdlib only, offline.
"""
import copy

from . import store_writer
from ..lib import content, validate


# Provenance keys stamped onto the draft at build time (which model/run produced it);
# preserved verbatim into the published record so model identity survives to the store.
_DRAFT_KEYS = ("model", "backend", "run")


def stamp(items, *, reviewed_date, confirmed_by, drafted_by=None,
          reviewed_by="claude-adversarial", guardrail="WCF-1"):
    out = []
    for it in items:
        it = copy.deepcopy(it)
        it["review_status"] = "published"
        draft_prov = it.get("provenance") or {}
        prov = {"drafted_by": drafted_by or draft_prov.get("model") or "claude",
                "reviewed_by": reviewed_by, "reviewed_date": reviewed_date,
                "guardrail": guardrail, "confirmed_by": confirmed_by}
        for k in _DRAFT_KEYS:                    # carry model/backend/run forward
            if draft_prov.get(k) is not None:
                prov[k] = draft_prov[k]
        it["provenance"] = prov
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
