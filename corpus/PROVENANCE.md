# Corpus Provenance Ledger

Every asset in `canon/` traces to a raw source below. Each source directory
contains `meta.json` (url, fetch date, license, sha256). Nothing in
`sources/private/` is committed or may ever ship.

| Source dir | Asset | Upstream | License | Notes |
|---|---|---|---|---|
| kjv-ebible | KJV Bible text | ebible.org (eng-kjv2006, USFM) | Public domain | KJV versification is canonical |
| web-ebible | WEB Bible text | ebible.org (engwebp, USFM) | Public domain | also pericope-seed source (\s headings) |
| cuv-ebible | CUV 和合本 简体 | ebible.org (cmn-cu89s, USFM) | Public domain | only stored Chinese translation |
| bsb-ebible | BSB Bible text | ebible.org (engbsb, USFM) | Public domain | alternate pericope-seed source |

Copyrighted translations (ESV, NKJV, NIV, NLT, CNV 新译本) are used under
personal-use terms from `sources/private/` (git-ignored) and via licensed
APIs in the future. They never enter `canon/`.
