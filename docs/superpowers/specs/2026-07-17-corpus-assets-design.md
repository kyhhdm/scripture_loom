# Design: Corpus Assets — Lamppost Documents and Bible Text Store

**Date:** 2026-07-17
**Status:** Approved design, pre-implementation
**Builds on:** `docs/design-kit_generator.md` (content bank, WCF guardrail, pericope indexing), `docs/core_principles.md`

## Purpose

The content bank (`design-kit_generator.md`) needs a layer underneath it: the source
texts everything is authored from and anchored to. This spec defines how those assets
are acquired, stored, and organized:

- **Lamppost documents** — Bible, Westminster Confession, catechisms, commentary.
  They shape content at drafting and review time and are never shown in kits directly.
- **Bible text structure** — books, pericopes, cross-references, in multiple versions
  (English: ESV, NKJV, KJV, NIV, NLT; Chinese: CUV 和合本, CNV 新译本).

## Governing decisions (made during brainstorming)

1. **Licensing posture: hybrid.** Personal use now, product path kept clean. Full text
   is stored and committed only for public-domain / openly licensed texts. Copyrighted
   translations live in a git-ignored private directory now and behind a licensed API
   adapter later. Nothing copyrighted is ever committed or shipped.
2. **Pericopes: seed, then canonicalize.** Pericope boundaries are seeded from an open
   dataset (section markers in public-domain USFM), then editorially adjusted during
   content authoring — the same human review the content pipeline already requires.
   The reviewed division is canonical and owned by the product.
3. **Commentary lampposts: Matthew Henry + JFB.** Matthew Henry's Commentary is the
   devotional *voice* (family-worship register, matches "worship, not academy");
   Jamieson-Fausset-Brown is the *facts* source (concise verse-level data feeding
   `key_facts` authoring). Both public domain.
4. **Storage: normalized JSON as the canonical store** (Approach A). Sources are
   acquired in their upstream formats; deterministic ingestion scripts normalize them
   into plain JSON committed to the repo. Diff-able, human-reviewable in git, zero
   dependencies — consistent with the prototype's stdlib-Python + JSON style.
   Standard formats (USFM/OSIS) survive only at the ingestion boundary; SQLite may
   appear later only as a derived build artifact.

## 1. Two roles, one rule

Every corpus asset carries a `role` and a `license` field:

- **`lamppost`** — used at drafting/review time (injected into AI drafting prompts,
  cited by human reviewers); never printed in a kit. WCF, catechisms, Matthew Henry,
  JFB.
- **`displayable`** — may be printed into kits: Bible text, pericope titles,
  cross-references.

**License gate (enforced in code):** only assets with `role: displayable` *and*
`license` in `{public-domain, CC-BY}` may enter a kit. Copyrighted personal-use texts
live under a git-ignored directory and cannot be committed or shipped by construction.

## 2. Directory layout

New top-level `corpus/` directory, sibling of `docs/` and `prototype/`:

```text
corpus/
  sources/            # raw upstream files, byte-for-byte as downloaded
    kjv-ebible/         each dir contains meta.json:
    cuv-ebible/         { url, fetched (date), license, checksum }
    web-ebible/
    bsb/
    wcf-standards/
    mhc-ccel/
    jfb-ccel/
    tsk/
    openbible-crossrefs/
    private/          # GIT-IGNORED: personal copies of ESV/NKJV/NIV/NLT/CNV
  ingest/             # one-off Python stdlib scripts: sources/ -> canon/
  canon/              # the normalized store — the ONLY thing consumers read
    bibles/           # kjv.json, cuv-simp.json, web.json, bsb.json
    structure/        # books.json, pericopes/<book>.json, crossrefs.json
    lampposts/        # wcf.json, wsc.json, wlc.json, mhc/<book>.json, jfb/<book>.json
  PROVENANCE.md       # human-readable ledger of every source
```

Estimated committed size ≈ 60 MB total (two full Bibles ≈ 5 MB each as JSON,
confession + catechisms < 1 MB, Matthew Henry ≈ 25 MB, JFB ≈ 15 MB, cross-references
≈ 10 MB). Committed directly; no git-LFS needed.

`sources/` (except `private/`) is committed so ingestion stays reproducible even if
upstream sites disappear.

## 3. Canonical reference scheme

- **Book IDs:** OSIS/USFM three-letter codes (`GEN` … `MAT` … `REV`) —
  ecosystem-standard and language-neutral.
- **Verse references:** `MAT.5.1`; ranges `MAT.5.1-12` (cross-chapter ranges written
  `MAT.5.1-MAT.6.4`).
- **`books.json`:** canonical book list with chapter/verse counts (Protestant/KJV
  versification) plus English and Chinese book names — the authority every
  verification test checks against.
- **Versification:** KJV versification is canonical. CUV deviations are minor and are
  handled by a small per-version exception map *inside* each bible file, not a
  separate versification system.
- **Pericope IDs are opaque and stable:** `MAT-012` (sequence number within book);
  the verse range is *data* on the record. When a boundary is adjusted during
  authoring, the range changes but the ID — which every ContentItem and EvidenceItem
  keys on — survives. This replaces the prototype's `"Matthew 5:1-12"` string keys;
  the prototype's `content_bank.json` and `family.json` migrate to pericope IDs when
  they next change.

## 4. Acquisition sources

| Asset | Source | License | Stored where |
|---|---|---|---|
| KJV | eBible.org USFM (`eng-kjv`) | Public domain | `canon/bibles/kjv.json` |
| CUV 和合本 (simplified; traditional optional later) | eBible.org USFM (`cmn-cu89s`) | Public domain | `canon/bibles/cuv-simp.json` |
| WEB (World English Bible) | eBible.org USFM | Public domain | `canon/bibles/web.json` |
| BSB (Berean Standard Bible) | berean.bible download | Public domain | `canon/bibles/bsb.json` |
| ESV, NKJV, NIV, NLT, CNV 新译本 | personal copies now; licensed API adapter later | Copyrighted | `sources/private/` (git-ignored) — never `canon/` |
| WCF + Shorter/Larger Catechisms, with proof texts | structured public-domain e-texts (CCEL; reformed-standards GitHub repos) | Public domain | `canon/lampposts/wcf.json`, `wsc.json`, `wlc.json` |
| Matthew Henry's Commentary | CCEL structured e-text | Public domain | `canon/lampposts/mhc/<book>.json` |
| Jamieson-Fausset-Brown | CCEL / public-domain module | Public domain | `canon/lampposts/jfb/<book>.json` |
| Cross-references, base layer | Treasury of Scripture Knowledge | Public domain | merged into `canon/structure/crossrefs.json` |
| Cross-references, weighted layer | OpenBible.info dataset | CC-BY (attribute in PROVENANCE.md and any shipped product) | merged into `canon/structure/crossrefs.json` |
| Pericope seed | `\s` section markers from WEB/BSB USFM | Public domain (headings included) | `canon/structure/pericopes/<book>.json` |

### Known gaps (accepted, recorded)

- **No public-domain modern Chinese translation exists.** The stored Chinese layer is
  CUV only; CNV arrives via the licensed adapter. Chinese-side content authoring
  anchors to CUV.
- **Chinese WCF translations have unverified copyright.** Circulating Chinese
  translations (e.g., 赵中辉) are modern works. Personal use is fine
  (`sources/private/`); product use requires license verification or a fresh
  translation. The English WCF is the canonical guardrail text meanwhile.
- **Commentary lampposts are English-only.** Matthew Henry and JFB feed drafting for
  both languages; there is no machine-readable public-domain Chinese commentary.
  Accepted trade-off: lampposts shape drafting, they are not shipped.

## 5. Canonical schemas

Verses are keyed by number (objects, not arrays) to tolerate versification gaps.

```jsonc
// canon/bibles/kjv.json
{
  "version": "KJV", "lang": "en",
  "license": "public-domain", "role": "displayable",
  "source": "sources/kjv-ebible", "ingested": "2026-07-17",
  "versification_exceptions": {},          // ref remaps where this version deviates
  "books": {
    "MAT": { "5": { "1": "And seeing the multitudes, he went up…" } }
  }
}
```

```jsonc
// canon/structure/pericopes/mat.json
{
  "book": "MAT",
  "pericopes": [
    {
      "id": "MAT-012",
      "range": "MAT.5.1-12",
      "title_en": "The Beatitudes",
      "title_zh": "论福",
      "status": "seeded"        // "seeded" -> "canonical" once reviewed
    }                           //   during that book's content authoring
  ]
}
```

```jsonc
// canon/structure/crossrefs.json
{
  "license": "CC-BY (openbible.info) + public-domain (TSK)",
  "refs": [
    { "from": "MAT.5.5", "to": "PSA.37.11", "weight": 91,
      "sources": ["tsk", "openbible"] }
  ]
}
```

```jsonc
// canon/lampposts/wcf.json — same shape for wsc.json / wlc.json (Q&A numbered)
{
  "title": "Westminster Confession of Faith",
  "license": "public-domain", "role": "lamppost",
  "chapters": [
    { "n": 1, "title": "Of the Holy Scripture",
      "sections": [
        { "n": 9, "text": "The infallible rule of interpretation of Scripture is…",
          "proof_texts": ["2PE.1.20-21", "ACT.15.15-16"] }
      ] }
  ]
}
```

```jsonc
// canon/lampposts/mhc/mat.json — commentary keeps its native granularity;
// consumers query by pericope range, no forced re-chunking
{
  "work": "Matthew Henry's Commentary", "book": "MAT",
  "license": "public-domain", "role": "lamppost",
  "blocks": [
    { "range": "MAT.5.1-12", "text": "…" }     // MHC: section-level blocks
  ]
}
// canon/lampposts/jfb/mat.json — same shape, verse-level ranges
```

## 6. The version adapter seam

One interface, used by the kit composer and by lamppost-drafting prompts alike:

```python
get_passage(version, ref) -> PassageText   # verses + license/role metadata
```

Three providers:

1. **canon** — reads `canon/bibles/*.json`. The only provider built now.
2. **private** — reads `sources/private/`; refuses to run outside personal mode, so
   copyrighted text cannot leak into a shippable path.
3. **api** — future: ESV API, API.Bible (NKJV/NLT/others), CNV licensing. Stub with
   the interface only; no implementation in this scope.

Adding a new version later touches zero consumers.

## 7. Ingestion, verification, testing

Each `ingest/` script is deterministic stdlib Python: read `sources/X`, write
`canon/Y`, print a verification report. Tests follow the existing
`prototype/test_selector.py` style (`unittest`, no dependencies):

- **Verse-count check:** every ingested Bible's per-chapter verse counts match
  `books.json` (modulo its declared `versification_exceptions`) — catches truncated
  downloads and versification surprises.
- **Schema validation:** every `canon/` file validates against its schema
  (hand-rolled stdlib validation is sufficient).
- **Pericope coverage:** every verse of an ingested book belongs to exactly one
  pericope — no gaps, no overlaps.
- **License gate:** the displayable query path must reject any asset with
  `role: lamppost` or a license outside `{public-domain, CC-BY}`.

## 8. Out of scope

- Content-bank *items* (questions, activities) — this is the layer beneath them.
- Real implementations of the `api` provider or any licensing agreements.
- Chinese commentary lampposts.
- Any runtime database; SQLite remains a possible future *derived* build artifact.
- Migrating the prototype to pericope IDs (noted in §3; done when the prototype next
  changes, not as part of corpus ingestion).

## Open questions

- Traditional-script CUV (`cmn-cu89t`): ingest alongside simplified now or when a
  traditional-script family appears?
- Whether BSB section headings or WEB section markers make the better pericope seed —
  decide empirically during the first book's ingestion by comparing both against
  session-sized units for Matthew.
