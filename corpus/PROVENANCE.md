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
| mhc/helloao | Matthew Henry's Commentary (lamppost, "voice") | [bible.helloao.org](https://bible.helloao.org) Free Use Bible API, `/api/c/matthew-henry/{books.json,{BOOK}/{n}.json}` | Public domain (source `licenseUrl`: `https://creativecommons.org/publicdomain/mark/1.0/`) | Section-level anchoring; each section's own `number` is its starting verse, section end derived from the next section's start / chapter's last verse per KJV. This conversion omits SNG entirely plus a scatter of chapters (MAT 19–28, NUM 31–35, JOS 22–23, 2SA 23–24, PSA 72) — backfilled from CCEL (see below). |
| mhc/ccel | Matthew Henry's Commentary, Vols. I–V (ThML) — MHC backfill for chapters absent from the HelloAO conversion | [ccel.org/ccel/henry/{mhc1,mhc2,mhc3,mhc5}.xml](https://ccel.org/ccel/henry/mhc3.xml) | Public domain (1706-1721 text; CCEL public-domain digitization) | Backfills chapters HelloAO omits: SNG (whole book) + PSA 72 from `mhc3`; MAT 19–28 from `mhc5`; NUM 31–35 from `mhc1`; JOS 22–23 and 2SA 23–24 from `mhc2`. ThML `<div class="Commentary" id="Bible:Matt.19.3-Matt.19.12">` markers give the same kind of built-in section anchoring in a different markup convention. |
| jfb/helloao | Jamieson-Fausset-Brown Bible Commentary (lamppost, "facts") | [bible.helloao.org](https://bible.helloao.org) Free Use Bible API, `/api/c/jamieson-fausset-brown/{books.json,{BOOK}/{n}.json}` | Public domain (source `licenseUrl`: `https://creativecommons.org/publicdomain/mark/1.0/`) | 66/66 books. Verse-level anchoring (one block per verse), except chapters JFB writes as continuous per-chapter prose (anchored by their own embedded self-citation; see below). |

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

## Commentary lampposts: Matthew Henry (MHC) + Jamieson-Fausset-Brown (JFB) (Task 9)

Both works are served by the [HelloAO Free Use Bible API](https://bible.helloao.org)
as public-domain JSON with built-in scripture anchoring: a catalog file per
commentary (`/api/c/{id}/books.json`) and one file per chapter
(`/api/c/{id}/{BOOK}/{n}.json`). There is no single bulk artifact scoped to
just these two commentaries (the site's only bulk export is a 1.5GB+ zip
covering 1000+ translations across the whole API), so
`corpus/ingest/fetch_commentary_sources.py` crawls the per-chapter endpoints
directly (~2340 requests total) and writes one deduplicated JSON file per
book under `sources/{mhc,jfb}/helloao/` — the `commentary` and `book`
wrapper objects the live API repeats byte-for-byte on every chapter response
are dropped; that metadata (incl. the lengthy per-book introductions) is kept
once per book in the sibling `books.json`. Each per-book file's sha256 is
recorded in `sources/{mhc,jfb}/helloao/meta.json` alongside the fetch date
and license URL.

**Anchoring formats differ by work:**
- **JFB** is verse-level: each chapter's `content` is a list of `{type:
  "verse", number, content}` items, one per commented verse. `MAT` chapter 5
  alone yields 46 blocks (46 of its 48 verses; JFB doesn't comment on
  literally every verse, e.g. it folds Mat.5.1 into its Mat.5.2 note).
- **MHC** is section-level: content items are also numbered, but that number
  is the section's *starting* verse — the source never states where a
  section ends. `ingest_commentary.py::_mhc_helloao_blocks` derives each
  section's end as (next section's start − 1), or the chapter's actual last
  verse for a chapter's final section, using the already-ingested KJV canon
  bible (`canon/bibles/kjv.json`) as the verse-count table (never guessed or
  hand-authored). E.g. Matt 5's nine sections start at verses
  1,3,13,17,21,27,33,38,43 and close as `MAT.5.1-2`, `MAT.5.3-12`, ...,
  `MAT.5.43-48` — the last one closing at 48 because that's Matthew 5's real
  last verse per KJV.

**MHC's `matthew-henry` HelloAO conversion is missing whole chapters, not
just Song of Solomon.** SNG is absent entirely, and a scatter of other
chapters is missing too because the HelloAO catalog itself is truncated for
those books (the fetch only looks for chapters the catalog claims exist, so a
truncated catalog is invisible at fetch time). The full list, confirmed by
comparing each book's populated chapters against the KJV chapter count:
**SNG (all), MAT 19–28, NUM 31–35, JOS 22–23, 2SA 23–24, PSA 72** — 23
chapters plus SNG. Henry completed the whole Bible (only the Epistles were
finished posthumously), so these are digitization gaps in this conversion,
not authorship gaps.

These are backfilled from the **CCEL ThML edition of Matthew Henry's
Commentary on the Whole Bible** (`sources/mhc/ccel/{mhc1,mhc2,mhc3,mhc5}.xml`,
fetched by `fetch_commentary_sources.py::fetch_ccel_volumes`): SNG (whole
book) and PSA 72 from `mhc3` (Job–Song of Solomon); MAT 19–28 from `mhc5`
(Matthew–John); NUM 31–35 from `mhc1` (Genesis–Deuteronomy); JOS 22–23 and
2SA 23–24 from `mhc2` (Joshua–Esther). CCEL marks each commentary section
with `<div class="Commentary" id="Bible:Matt.19.3-Matt.19.12">` — the same
kind of built-in section anchoring HelloAO provides, a different markup
convention, so this is still source-derived anchoring, not hand-reconstructed
boundaries. `_mhc_ccel_blocks` extracts the text between one `Commentary` div
and the next (or the next chapter's `<div2>` open tag, whichever comes first,
so a chapter's leading synopsis never bleeds into the previous block), strips
markup, and converts the OSIS-style id to our canonical range. For a book
with a partial gap, only the missing chapters are taken from CCEL and merged
into the HelloAO-derived blocks; SNG (fully absent) is taken whole from CCEL.

*Not recoverable this way:* MHC's **JON 2–4**. CCEL's Minor-Prophets
commentary (`mhc4`) does not wrap Jonah's exposition in
`id="Bible:..."`-anchored `Commentary` divs (it is plain `<p>` prose with
inline `<scripRef>` tags only), so there is no built-in section anchoring to
reuse and we do not hand-reconstruct one. JON 2–4 therefore remains a
documented MHC gap (JON 1 is present from HelloAO).

**JFB prose-style chapters and the anchoring fix (the central correction of
this pass):** JFB frequently writes a whole chapter as one continuous prose
essay (stored in the chapter's `introduction`, with no per-verse items). In
this conversion those prose chapters are routinely filed under the **wrong
api chapter number**, and the number cannot be trusted:
- the entire back half of the Psalter is shifted — api chapters 70–144 are
  actually Psalms 71–150 (a growing offset: +1 near Ps 71, +6 by Ps 150,
  because JFB folds several psalms together);
- 2SA api 22–23 are actually 2 Sam 23–24; MAT api 24–26 are Matt 25/27/28;
  MRK api 3–14 are Mark 4–16.

The api number is therefore ignored for any prose-only chapter. Instead,
`_jfb_self_citation` reads the pericope's **own embedded self-citation** — the
first parenthetical scripture reference in the intro that (a) is not an
`=`-prefixed parallel-passage cross-reference, (b) names *this same book*, and
(c) is a multi-verse range, e.g. `(Psa. 71:1-24)`, `(Mark 6:14-29)`,
`(Sa2 23:1-7)`. Condition (c) is what separates the genuine pericope header
from stray single-verse cross-references that can precede it. Abbreviations
are resolved generically for all 66 books via `_resolve_book_abbr`, which
handles number-suffixed (`Sa2`, `Ch2`, `Jo1`), number-prefixed (`2Sa`,
`1Ki`) and plain/full names (`Psa`, `Mark`, `Acts`); `_CITE_RE` was widened to
parse letters-then-digit abbreviations like `Sa2 23:1-7`.

**Flipped default (correctness over coverage):** if a prose-only chapter has
no confident same-book self-citation, its block is **dropped and counted**
(printed every run) rather than shipped under an uncorroborated reference.
This recovers all the mis-anchored Psalms, 2 Samuel, Matthew and Mark prose
blocks under their true references, and drops **7 prose-only chapters**:
`MRK 4` (a headingless one-sentence stub, "And they came over unto the other
side of the sea…", no parseable citation) and `SNG 1, 2, 5, 6, 7, 8` (JFB's
Song-of-Solomon prose whose pericope citations are cross-chapter or absent, so
they cannot be confidently anchored — MHC's SNG, the devotional voice, is
fully present from CCEL, so this is a thin loss on the secondary lamppost).

**Residual documented gaps (chapters genuinely absent from a source, after
the fix):**
- **MHC:** JON 2–4 (CCEL anchoring unavailable, above). MHC's Isaiah source
  also has a genuine gap at api chapter 67 (HTML SPA shell instead of JSON,
  stable across retries) and a phantom empty chapter 68; Isaiah's real 66
  chapters are fully populated, and `_mhc_helloao_blocks` raises if a
  non-canonical chapter ever carries real content, so this can't silently
  mask a loss.
- **JFB:** 2SA 22, MAT 24, MAT 26, MRK 3, MRK 5, MRK 15, and PSA 70, 108,
  139, 141, 144, 146. Each is a psalm/chapter that has no source api chapter
  (JFB's essays skip or fold it): e.g. api 106→Ps 107 then api 107→Ps 109
  skips Ps 108. These are secondary-lamppost gaps, documented not fabricated.

Both lists are mirrored in `corpus/tests/test_commentary.py`
(`KNOWN_ABSENT`), whose `test_chapter_level_coverage` fails if any *new*
within-book chapter gap appears, and `_coverage_report` in the ingest prints
the missing-chapter list for each work on every run.

Final counts: MHC 66/66 books, 4,226 blocks total (complete except JON 2–4).
JFB 66/66 books, 17,150 blocks total; 17,056 are genuine per-verse blocks
(matching the source catalog's own `totalNumberOfVerses: 17056` exactly), the
rest are prose-style pericope blocks anchored by self-citation. Every JFB
prose block's assigned range matches the chapter named in its own embedded
self-citation (verified across all 94 such blocks corpus-wide).
