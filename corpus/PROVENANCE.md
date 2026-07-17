# Corpus Provenance Ledger

Every asset in `canon/` traces to a raw source below. Each source directory
contains `meta.json` (url, fetch date, license, sha256). Nothing in
`sources/private/` is committed or may ever ship.

| Source dir | Asset | Upstream | License | Notes |
|---|---|---|---|---|
| kjv-ebible | KJV Bible text | ebible.org (eng-kjv2006, USFM) | Public domain | KJV versification is canonical |
| web-ebible | WEB Bible text | ebible.org (engwebp, USFM) | Public domain | not usable as pericope-seed source (see below) |
| cuv-ebible | CUV 和合本 简体 | ebible.org (cmn-cu89s, USFM) | Public domain | only stored Chinese translation |
| bsb-ebible | BSB Bible text | ebible.org (engbsb, USFM) | Public domain | pericope-seed source for Matthew |
| openbible-crossrefs | Cross-references (weighted) | openbible.info/labs/cross-references | CC-BY — attribute openbible.info in any shipped product | TSK public-domain base layer deferred until a verified machine-readable source is pinned |

Copyrighted translations (ESV, NKJV, NIV, NLT, CNV 新译本) are used under
personal-use terms from `sources/private/` (git-ignored) and via licensed
APIs in the future. They never enter `canon/`.

| westminster | WCF / WSC / WLC (lamppost) | [NonlinearFruit/Creeds.json](https://github.com/NonlinearFruit/Creeds.json), raw JSON files under `creeds/westminster_*.json` | Underlying 1646-47 text: public domain (Westminster Assembly). JSON structuring/repackaging: repo-wide Unlicense; the Westminster documents are not among the repo's explicitly copyrighted exceptions (Chicago Statement, Savoy Declaration, Helvetic Consensus translation, etc. — see repo README). Each document's own `Metadata.SourceUrl` points to an archive.org scan of the original 1646/1647 parliamentary edition. | proof texts: ingested for WCF (1831) and WLC (2622); the chosen source carries no `Proofs` field at all for WSC, so all 107 questions have `proof_texts: []` for v1 — not yet ingested for the Shorter Catechism (a different source would be needed to add them). See note below on 33 skipped WCF/WLC references. |

## Pericope seeding source (Task 6, Matthew)

`corpus/ingest/seed_pericopes.py` derives pericope boundaries from `\s`
section-heading markers in a USFM source. The `engwebp_usfm.zip` edition of
WEB stored in `web-ebible` contains **zero** `\s` headings in its Matthew
file (`70-MATengwebp.usfm`) — confirmed by direct inspection, not just a
coverage-test failure. `bsb-ebible` (`70-MATengbsb.usfm`) carries `\s1`
headings with `\r` cross-reference lines throughout Matthew and seeds 153
pericopes that pass the full-coverage test against KJV cleanly. `seed()`'s
default `source_dir` was changed from `"web-ebible"` to `"bsb-ebible"` so
that `python3 corpus/ingest/seed_pericopes.py MAT` reproduces the committed
`canon/structure/pericopes/mat.json`.

## Cross-references (Task 7)

Of the 344,799 rows in the OpenBible.info source, 18 are dropped by design
during ingestion: they are legitimate cross-book ranges (e.g.
`2Chr.36.22-Ezra.1.3`, `Hag.2.20-Zech.1.1`) that the Task 2 `refs.parse_range`
schema cannot represent, since it requires a range's start and end to share
one book. This is real, canonically significant data (e.g. the
Chronicles→Ezra narrative continuation) lost to a schema limitation, not
junk — a candidate to revisit if the range schema is extended or the TSK
base layer lands.

## Westminster standards (Task 8)

`corpus/ingest/ingest_westminster.py` reshapes the three source files fetched
from NonlinearFruit/Creeds.json (raw JSON, already carrying OSIS-abbreviation
proof texts for WCF and WLC) into `canon/lampposts/{wcf,wsc,wlc}.json`. Book
abbreviations are remapped via the same `Gen→GEN` style table used by
`ingest_crossrefs.py`'s `OSIS_TO_USFM`.

Of 4,486 individual proof-text references across WCF and WLC, 33 are dropped
by design: they cite an entire chapter (e.g. `Gen.1`, `Ps.73`) or a chapter
range (e.g. `Heb.8-Heb.10`) with no verse, which `refs.parse_range`'s
book.chapter.verse schema cannot represent — the same schema limitation noted
above for cross-references. These are not fabricated as verse-1-to-last-verse
ranges (that would require a verse-count table and misrepresent what the
divines actually cited); they are simply omitted from `proof_texts`, and the
ingest script prints the count (`skipped 33 whole-chapter proof texts`) on
every run so the number stays visible.
