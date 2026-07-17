import json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import books

CANON = Path(__file__).resolve().parents[1] / "canon"
VERSIONS = ["kjv", "web", "cuv-simp", "bsb"]


def _expand(vkey):
    """Verse-key coverage: '17-18' covers verses 17 and 18."""
    if "-" in vkey:
        a, b = vkey.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(vkey)]


class TestCanonBibles(unittest.TestCase):
    def _load(self, v):
        with open(CANON / "bibles" / f"{v}.json", encoding="utf-8") as f:
            return json.load(f)

    def test_all_versions_have_66_books_with_exact_chapter_counts(self):
        table = books.load()
        for v in VERSIONS:
            data = self._load(v)
            self.assertEqual(set(data["books"]), set(table), v)
            for code, meta in table.items():
                self.assertEqual(len(data["books"][code]), meta["chapters"],
                                 f"{v} {code}: chapter count")

    def test_kjv_total_verse_count(self):
        data = self._load("kjv")
        total = sum(len(_expand(vk)) for book in data["books"].values()
                    for ch in book.values() for vk in ch)
        self.assertEqual(total, 31102)

    def test_metadata_fields(self):
        for v in VERSIONS:
            data = self._load(v)
            self.assertEqual(data["role"], "displayable", v)
            self.assertEqual(data["license"], "public-domain", v)
            for key in ("version", "lang", "source", "ingested",
                        "versification_exceptions"):
                self.assertIn(key, data, f"{v}: {key}")

    def test_spot_checks(self):
        kjv = self._load("kjv")["books"]
        self.assertTrue(kjv["GEN"]["1"]["1"].startswith("In the beginning"))
        self.assertIn("Blessed", kjv["MAT"]["5"]["3"])
        cuv = self._load("cuv-simp")["books"]
        self.assertIn("起初", cuv["GEN"]["1"]["1"])

    def test_no_leftover_markup(self):
        for v in VERSIONS:
            data = self._load(v)
            for code in ("GEN", "MAT", "PSA"):
                for ch in data["books"][code].values():
                    for text in ch.values():
                        self.assertNotIn("\\", text, f"{v} {code}")


if __name__ == "__main__":
    unittest.main()
