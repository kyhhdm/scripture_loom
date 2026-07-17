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

Copyrighted translations (ESV, NKJV, NIV, NLT, CNV 新译本) are used under
personal-use terms from `sources/private/` (git-ignored) and via licensed
APIs in the future. They never enter `canon/`.

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
