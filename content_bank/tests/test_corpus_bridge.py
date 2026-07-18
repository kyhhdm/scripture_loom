import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.lib import corpus_bridge as cb


class TestCorpusBridge(unittest.TestCase):
    def test_pericope_ids_include_known_matthew_ids(self):
        ids = cb.pericope_ids("MAT")
        self.assertIn("MAT-009", ids)
        self.assertIn("MAT-014", ids)
        self.assertIn("MAT-015", ids)

    def test_pericope_records_have_ranges(self):
        by_id = {p["id"]: p for p in cb.pericopes("MAT")}
        self.assertEqual(by_id["MAT-014"]["range"], "MAT.5.3-12")

    def test_book_name_en_and_zh(self):
        self.assertEqual(cb.book_name("MAT", "en"), "Matthew")
        self.assertTrue(cb.book_name("MAT", "zh"))  # non-empty Chinese name

    def test_wcf_chapter1_mentions_scripture(self):
        text = cb.wcf_chapter1_text()
        self.assertIn("1.1", text)            # section numbering present
        self.assertIn("Holy Scripture", text)  # chapter 1 title "Of the Holy Scripture"

    def test_passage_text_returns_verses(self):
        text = cb.passage_text("MAT.5.13-16", version="BSB")
        self.assertIn("salt", text.lower())


if __name__ == "__main__":
    unittest.main()
