"""Fetch raw Matthew Henry (MHC) and Jamieson-Fausset-Brown (JFB) commentary
source data into corpus/sources/{mhc,jfb}/.

Both works are served by the HelloAO Free Use Bible API
(https://bible.helloao.org) as public-domain JSON: one catalog file per
commentary (`/api/c/{id}/books.json`, book list + introductions) and one file
per chapter (`/api/c/{id}/{BOOK}/{n}.json`, verse/section-anchored content).
There is no single bulk artifact scoped to just these two commentaries (the
site's only bulk export is a 1.5GB+ zip covering 1000+ translations), so this
script crawls the per-chapter endpoints directly. It writes one JSON file per
book under sources/<work>/helloao/, dropping the `commentary` and `book`
wrapper objects the live API repeats byte-for-byte on every chapter response
(that metadata, including the lengthy per-book introductions, is preserved
once in the sibling books.json).

HelloAO's `matthew-henry` conversion is missing a number of chapters: Song of
Solomon entirely, plus MAT 19-28, NUM 31-35, JOS 22-23, 2SA 23-24 and PSA 72
(confirmed by direct inspection, not transient gaps).
corpus/ingest/ingest_commentary.py backfills these from the CCEL ThML edition
(Commentary on the Whole Bible, Volumes I-V), fetched below. CCEL's ThML marks
each commentary section with <div class="Commentary"
id="Bible:Matt.19.3-Matt.19.12"> — the same kind of built-in scripture
anchoring, just a different markup convention. Volumes fetched:

  * mhc1.xml  Genesis-Deuteronomy  (NUM 31-35)
  * mhc2.xml  Joshua-Esther        (JOS 22-23, 2SA 23-24)
  * mhc3.xml  Job-Song of Solomon  (SNG whole book, PSA 72)
  * mhc5.xml  Matthew-John         (MAT 19-28)

(mhc4 Isaiah-Malachi is not fetched: its Minor-Prophets commentary lacks the
id="Bible:..." section anchoring, so JON 2-4 cannot be recovered by the same
method and remains a documented gap -- see corpus/PROVENANCE.md.)
"""
import concurrent.futures as cf
import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import books

CORPUS = Path(__file__).resolve().parents[1]
API = "https://bible.helloao.org/api"
CCEL_VOLUMES = ["mhc1.xml", "mhc2.xml", "mhc3.xml", "mhc5.xml"]


def _get(url, retries=5):
    """GET with retries; the live API occasionally drops a connection or
    returns a truncated/empty body under concurrent load."""
    last_err = None
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "scripture-loom-corpus/0.1"})
            with urlopen(req, timeout=30) as resp:
                data = resp.read()
            if not data:
                raise ValueError("empty response body")
            return data
        except (URLError, ValueError, OSError) as e:
            last_err = e
            time.sleep(0.5 * (2 ** attempt))
    raise RuntimeError(f"failed to fetch {url} after {retries} attempts: {last_err}")


class ChapterMissing(Exception):
    """The source genuinely lacks this chapter (SPA 404 fallback returned
    HTML with a 200 status), as opposed to a transient network error."""


def _get_json(url, retries=5):
    """GET + json.loads with retries; the live API occasionally returns a
    non-JSON error page (5xx/429) that _get's byte-level checks don't catch.
    A stable HTML response (VuePress SPA shell, still HTML after retrying)
    means the chapter itself is absent from the source, not a flake."""
    last_err = None
    missing_count = 0
    for attempt in range(retries):
        try:
            data = _get(url, retries=1)
            stripped = data.lstrip()
            if stripped.startswith(b"<"):
                missing_count += 1
                if missing_count >= 3:      # stable across retries: real gap
                    raise ChapterMissing(url)
                time.sleep(0.5 * (2 ** attempt))
                continue
            return json.loads(data)
        except (json.JSONDecodeError, RuntimeError) as e:
            last_err = e
            time.sleep(0.5 * (2 ** attempt))
    raise RuntimeError(f"failed to fetch/parse {url} after {retries} attempts: {last_err}")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def fetch_helloao_commentary(commentary_id, dirname, book_codes):
    """Crawl one HelloAO commentary's books.json + every chapter for the
    given book codes, writing deduplicated per-book JSON into
    corpus/sources/<dirname>/helloao/."""
    dest = CORPUS / "sources" / dirname / "helloao"
    dest.mkdir(parents=True, exist_ok=True)

    raw_catalog = _get(f"{API}/c/{commentary_id}/books.json")
    (dest / "books.json").write_bytes(raw_catalog)
    catalog = json.loads(raw_catalog)
    by_id = {b["id"]: b for b in catalog["books"]}
    hashes = {"books.json": _sha(raw_catalog)}
    missing_chapters = {}   # book -> [chapter numbers absent from the source]

    for code in book_codes:
        existing = dest / f"{code}.json"
        if existing.exists():
            hashes[f"{code}.json"] = _sha(existing.read_bytes())
            print(f"  {commentary_id} {code}: already fetched, skipping")
            continue
        entry = by_id[code]
        n = entry["numberOfChapters"]
        last = entry["lastChapterNumber"]
        results = {}

        def fetch_ch(chapter_num):
            url = f"{API}/c/{commentary_id}/{code}/{chapter_num}.json"
            try:
                return chapter_num, _get_json(url)["chapter"]
            except ChapterMissing:
                return chapter_num, None

        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            for chapter_num, chapter in ex.map(fetch_ch, range(1, last + 1)):
                results[chapter_num] = chapter

        gaps = sorted(cn for cn, ch in results.items() if ch is None)
        if gaps:
            missing_chapters[code] = gaps
            print(f"  {commentary_id} {code}: source has no chapter(s) {gaps} "
                  f"(confirmed absent, not a network flake)")
        chapters = [results[cn] for cn in sorted(results) if results[cn] is not None]

        out = (json.dumps({"book": code, "chapters": chapters},
                           ensure_ascii=False, indent=1) + "\n").encode("utf-8")
        path = dest / f"{code}.json"
        path.write_bytes(out)
        hashes[f"{code}.json"] = _sha(out)
        print(f"  {commentary_id} {code}: {len(chapters)}/{n} chapters, {len(out)} bytes")

    meta = {
        "url_template": f"{API}/c/{commentary_id}/{{book}}/{{chapter}}.json",
        "books_index_url": f"{API}/c/{commentary_id}/books.json",
        "fetched": date.today().isoformat(),
        "license": "public-domain",
        "license_url": catalog["commentary"]["licenseUrl"],
        "note": ("per-chapter API responses deduplicated on fetch: the "
                 "top-level 'commentary' and 'book' wrapper objects "
                 "(repeated identically on every chapter response) are "
                 "dropped; book-level metadata, incl. introductions, lives "
                 "once per book in books.json."),
        "book_codes_fetched": book_codes,
        "missing_chapters": missing_chapters,
        "sha256": hashes,
    }
    (dest / "meta.json").write_text(
        json.dumps(meta, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8")
    print(f"{dirname}/helloao: wrote {len(book_codes)} book files"
          + (f"; missing_chapters={missing_chapters}" if missing_chapters else ""))


def fetch_ccel_volumes():
    """Fetch the CCEL ThML volumes used to backfill MHC chapters missing from
    the HelloAO conversion, recording a combined provenance meta.json."""
    dest = CORPUS / "sources" / "mhc" / "ccel"
    dest.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name in CCEL_VOLUMES:
        url = f"https://ccel.org/ccel/henry/{name}"
        data = _get(url)
        (dest / name).write_bytes(data)
        hashes[name] = _sha(data)
        print(f"  {name}: {len(data)} bytes sha256={hashes[name][:12]}…")
    meta = {
        "url_template": "https://ccel.org/ccel/henry/{volume}",
        "volumes": CCEL_VOLUMES,
        "fetched": date.today().isoformat(),
        "license": ("public-domain (1706-1721 text; CCEL digitization, "
                    "ccel.org public-domain texts)"),
        "note": ("Matthew Henry's Commentary on the Whole Bible, ThML edition. "
                 "Used to backfill chapters absent from the HelloAO "
                 "matthew-henry conversion: SNG (whole book) and PSA 72 from "
                 "mhc3; MAT 19-28 from mhc5; NUM 31-35 from mhc1; JOS 22-23 "
                 "and 2SA 23-24 from mhc2. Sections anchored by their built-in "
                 'id="Bible:Book.ch.v-Book.ch.v".'),
        "sha256": hashes,
    }
    (dest / "meta.json").write_text(
        json.dumps(meta, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8")
    print(f"mhc/ccel: wrote {len(CCEL_VOLUMES)} volume(s)")


if __name__ == "__main__":
    order = books.BOOK_ORDER

    print("Fetching Jamieson-Fausset-Brown (66/66 books present in source)...")
    fetch_helloao_commentary("jamieson-fausset-brown", "jfb", order)

    print("Fetching Matthew Henry (65/66; SNG absent from this source)...")
    fetch_helloao_commentary("matthew-henry", "mhc", [c for c in order if c != "SNG"])

    print("Fetching CCEL ThML volumes (MHC chapter backfill)...")
    fetch_ccel_volumes()
