import json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import books, refs

CORPUS = Path(__file__).resolve().parents[1]
LAMP = CORPUS / "canon" / "lampposts"

# Chapters genuinely absent from each source, mirroring corpus/PROVENANCE.md.
# A NEW within-book chapter gap (not in this allowlist) must fail the test --
# these are the only tolerated holes.
KNOWN_ABSENT = {
    "mhc": {"JON": {2, 3, 4}},
    "jfb": {
        "2SA": {22},
        "MAT": {24, 26},
        "MRK": {3, 5, 15},
        "PSA": {70, 108, 139, 141, 144, 146},
        "SNG": {1, 2, 5, 6, 7, 8},
    },
}


def _kjv_chapter_counts():
    with open(CORPUS / "canon" / "bibles" / "kjv.json", encoding="utf-8") as f:
        return {b: {int(c) for c in chs}
                for b, chs in json.load(f)["books"].items()}


def _covered_chapters(work_dir, book_code):
    with open(work_dir / f"{book_code.lower()}.json", encoding="utf-8") as f:
        data = json.load(f)
    covered = set()
    for b in data["blocks"]:
        (_, c1, _), (_, c2, _) = refs.parse_range(b["range"])
        covered.update(range(c1, c2 + 1))
    return covered


class TestCommentary(unittest.TestCase):
    def _check_work(self, dirname, workname):
        table = books.load()
        found = {p.stem.upper() for p in (LAMP / dirname).glob("*.json")}
        self.assertEqual(found, set(table), f"{dirname}: book coverage")
        with open(LAMP / dirname / "mat.json", encoding="utf-8") as f:
            mat = json.load(f)
        self.assertEqual(mat["role"], "lamppost")
        self.assertEqual(mat["license"], "public-domain")
        self.assertEqual(mat["book"], "MAT")
        self.assertIn(workname, mat["work"])
        for b in mat["blocks"]:
            refs.parse_range(b["range"])
            self.assertTrue(b["text"].strip())
        return mat

    def test_mhc_all_books_and_mat_shape(self):
        mat = self._check_work("mhc", "Henry")
        joined = " ".join(b["text"].lower() for b in mat["blocks"]
                          if refs.parse_range(b["range"])[0][1] == 5)
        self.assertIn("blessed", joined)

    def test_jfb_all_books_and_verse_level(self):
        mat = self._check_work("jfb", "Jamieson")
        ch5 = [b for b in mat["blocks"]
               if refs.parse_range(b["range"])[0][1] == 5]
        self.assertGreater(len(ch5), 10)   # verse-level granularity

    def test_blocks_for_helper(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingest"))
        from ingest_commentary import blocks_for
        texts = blocks_for(LAMP / "mhc", "MAT.5.1-12")
        self.assertTrue(texts)
        self.assertTrue(any("blessed" in t.lower() for t in texts))

    def test_chapter_level_coverage(self):
        """Every book's blocks must cover all of its KJV chapters except the
        explicit, documented allowlist -- so a silent within-book chapter gap
        (e.g. MHC MAT 19-28, or a JFB mis-anchoring that leaves a real chapter
        uncovered) fails the test instead of shipping invisibly."""
        kjv = _kjv_chapter_counts()
        for dirname in ("mhc", "jfb"):
            allow = KNOWN_ABSENT[dirname]
            for code in books.load():
                covered = _covered_chapters(LAMP / dirname, code)
                missing = kjv[code] - covered
                self.assertEqual(
                    missing, allow.get(code, set()),
                    f"{dirname}/{code}: chapter coverage differs from the "
                    f"documented allowlist (missing={sorted(missing)})")

    def test_jfb_anchoring_fidelity(self):
        """Spot-check that block text matches its assigned range on cases the
        old code mis-anchored (prose-only chapters filed under the wrong api
        chapter number). These fail on the pre-fix output."""
        def text_at(book, rng):
            with open(LAMP / "jfb" / f"{book.lower()}.json", encoding="utf-8") as f:
                for b in json.load(f)["blocks"]:
                    if b["range"] == rng:
                        return b["text"].lower()
            return None

        # Psalm 121 ("I will lift up mine eyes"), NOT Psalm 119 -- the old
        # output put this text under PSA.119 and Psalm 123 text under PSA.121.
        t121 = text_at("PSA", "PSA.121.1-8")
        self.assertIsNotNone(t121, "PSA.121.1-8 block missing")
        self.assertIn("lift up mine eyes", t121)
        self.assertNotIn("earnest and expecting prayer", t121)  # that is Ps 123

        # Psalm 71 (old age / enemies), Psalm 73 (Asaph / prosperity of wicked).
        self.assertIn("old age", text_at("PSA", "PSA.71.1-24"))
        self.assertIn("asaph", text_at("PSA", "PSA.73.1-28"))

        # 2 Samuel 23 / 24 (old code shipped these under 2SA.22 / 2SA.23).
        self.assertIn("last words of david", text_at("2SA", "2SA.23.1-7"))
        self.assertIn("numbers the people", text_at("2SA", "2SA.24.1-9"))

    def test_mhc_mat_passion_backfilled(self):
        """MAT 19-28 (missing from HelloAO) must be present with real text."""
        covered = _covered_chapters(LAMP / "mhc", "MAT")
        self.assertTrue(set(range(19, 29)) <= covered, "MHC MAT 19-28 not covered")
        sys.path.insert(0, str(CORPUS / "ingest"))
        from ingest_commentary import blocks_for
        virgins = blocks_for(LAMP / "mhc", "MAT.25.1-13")
        self.assertTrue(any("virgins" in t.lower() for t in virgins))


if __name__ == "__main__":
    unittest.main()
