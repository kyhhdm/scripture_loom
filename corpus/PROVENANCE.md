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
| mhc/helloao | Matthew Henry's Commentary (lamppost, "voice") | [bible.helloao.org](https://bible.helloao.org) Free Use Bible API, `/api/c/matthew-henry/{books.json,{BOOK}/{n}.json}` | Public domain (source `licenseUrl`: `https://creativecommons.org/publicdomain/mark/1.0/`) | 65/66 books (all but Song of Solomon — see below). Section-level anchoring; each section's own `number` is its starting verse, section end derived from the next section's start / chapter's last verse per KJV. |
| mhc/ccel | Matthew Henry's Commentary, Vol. III (Job–Song of Solomon), SNG supplement only | [ccel.org/ccel/henry/mhc3.xml](https://ccel.org/ccel/henry/mhc3.xml) (ThML) | Public domain (1706-1721 text; CCEL public-domain digitization) | Used only for Song of Solomon, the one book HelloAO's matthew-henry source omits. ThML `<div class="Commentary" id="Bible:Song.1.2-Song.1.6">` markers give the same kind of built-in section anchoring in a different markup convention. |
| jfb/helloao | Jamieson-Fausset-Brown Bible Commentary (lamppost, "facts") | [bible.helloao.org](https://bible.helloao.org) Free Use Bible API, `/api/c/jamieson-fausset-brown/{books.json,{BOOK}/{n}.json}` | Public domain (source `licenseUrl`: `https://creativecommons.org/publicdomain/mark/1.0/`) | 66/66 books. Verse-level anchoring (one block per verse), except Song of Solomon, whose JFB text is continuous per-chapter prose (see below). |

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

**MHC's `matthew-henry` HelloAO source is missing Song of Solomon entirely**
(65 of 66 books; confirmed by inspecting its `books.json` book list, not a
transient gap — Henry completed the whole Old Testament himself before his
death, so this is a digitization gap in this particular conversion, not a
genuine authorship gap). Rather than ship SNG empty, `ingest_commentary.py`
supplements it from the CCEL ThML edition of *Commentary on the Whole Bible,
Volume III (Job–Song of Solomon)* (`sources/mhc/ccel/mhc3.xml`, fetched via
`corpus/ingest/fetch.py` since it's a single static file). CCEL's ThML marks
each commentary section with
`<div class="Commentary" id="Bible:Song.1.2-Song.1.6">` — the same kind of
built-in section anchoring HelloAO provides, just a different markup
convention, so this is still source-derived anchoring, not hand-reconstructed
boundaries. `_mhc_ccel_song_blocks` extracts the text between one
`Commentary` div and the next (or the next chapter's `<div2>` open tag,
whichever comes first, so a chapter's leading synopsis paragraph never bleeds
into the previous chapter's last block), strips markup, and converts the
OSIS-style id (`Song.1.2-Song.1.6`) to our canonical range (`SNG.1.2-6`).
This is the only book sourced from CCEL; all other 65 MHC books and all 66
JFB books come from HelloAO.

**Source data quirks, all verified by direct inspection (re-requesting the
live endpoint, not just observing a test failure):**

- MHC's Isaiah has a genuine gap at chapter 67 (HTTP 200 but an HTML SPA
  shell instead of JSON, confirmed stable across retries — not a network
  flake) and a phantom empty chapter 68 (valid JSON, zero content items).
  Isaiah only has 66 real chapters; both are harmless artifacts of this
  source's chapter numbering for this one book, and Isaiah's real chapters
  1-66 are otherwise fully populated. `_mhc_helloao_blocks` fails loudly
  (raises) if a chapter number outside the KJV canon ever carries non-empty
  content, so this isn't silently masking a real loss.

- Most chapters where JFB writes continuous per-chapter prose instead of
  discrete verse items (the whole chapter's commentary lives in that
  chapter's `introduction` field, with verse references embedded inline as
  prose, e.g. Song of Solomon's "(Son. 1:2-2:7)") are correctly numbered by
  the source, and `_jfb_blocks` emits one whole-chapter block for them (e.g.
  Song of Solomon: 8 blocks, one per chapter, vs. the verse-level granularity
  of JFB's other 65 books).

- **A real defect was found in this same class of chapter, isolated to
  Mark's Passion/Resurrection narrative (JFB `MRK` api chapters 3–14) and
  three of Matthew's (api chapters 24–26).** Several of these "prose"
  chapters are filed under the *wrong* api chapter number — e.g. api chapter
  3 is actually Mark 4's commentary (self-titled "PARABLE OF THE SOWER...
  (Mark 4:1-34)"); api chapter 13 is actually Mark 14's ("(Mar 14:1-11)");
  api chapter 14 is actually Mark 16's ("(Mark 16:1-20)") — while the real
  Mark 3 and Mark 15 never appear anywhere in the source under any chapter
  number, and Mark 16 ends up present twice (once as this condensed prose
  block under the mislabeled api-14 slot, once again at its own correctly
  numbered api chapter 16, this time with normal verse-level granularity —
  both are kept, since both are genuine JFB text). Confirmed by reading each
  prose chapter's own embedded pericope heading and self-citation and
  comparing it against the api-reported chapter number.

  `ingest_commentary.py::_jfb_own_citation` parses that embedded heading (an
  ALL-CAPS title line immediately followed by a parenthetical self-citation,
  e.g. `PARABLE OF THE SOWER... (Mark 4:1-34)`) and, when it names the same
  book, uses its chapter and precise verse range instead of the api-reported
  number — this is still source-derived anchoring (the text's own stated
  reference), not hand-reconstruction. This recovers 11 correctly-labeled
  MRK blocks and 3 correctly-labeled MAT blocks (`MAT.25.1-13`,
  `MAT.27.1-10`, `MAT.28.1-15`) that the naive api-number mapping would have
  shipped under the wrong reference.

  One further MRK chapter (api chapter 4) has zero verse items, a non-empty
  but headingless one-sentence stub ("And they came over unto the other side
  of the sea, into the country of the Gadarenes.") that is not real
  commentary and carries no parseable self-citation to correct it. Once a
  book has shown even one confirmed api-number mismatch elsewhere (as MRK
  has), its remaining unlabeled prose chapters can no longer be trusted at
  face value, so rather than guess or hand-label it, `_jfb_blocks` drops it:
  **1 block dropped**, printed by the ingest script every run
  (`jfb: dropped 1 unlabeled prose-style chapter(s)...`). No other book
  triggered this drop path — every other book's prose chapters either had a
  confirmed self-citation or showed no mismatch evidence anywhere in the
  book, so their api numbers were trusted as before.

Final counts: MHC 66/66 books, 4,150 blocks total. JFB 66/66 books, 17,156
blocks total. 17,056 of those are genuine per-verse blocks, matching the
source catalog's own `totalNumberOfVerses: 17056` exactly; the rest are the
prose-style whole-chapter/citation-range blocks described above. Only the 1
MRK block noted above was dropped; every other source content item that
carried text made it into a block, under a verified-correct reference.
