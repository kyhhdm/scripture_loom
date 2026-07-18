import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.lib import prototype_bank as pb


class TestDisplayRef(unittest.TestCase):
    def test_multi_verse(self):
        self.assertEqual(pb.display_ref("MAT.5.3-12", "en"), "Matthew 5:3–12")

    def test_two_verse(self):
        self.assertEqual(pb.display_ref("MAT.5.1-2", "en"), "Matthew 5:1–2")

    def test_cross_chapter_style_range(self):
        self.assertEqual(pb.display_ref("MAT.4.1-11", "en"), "Matthew 4:1–11")


class TestLoadBank(unittest.TestCase):
    def setUp(self):
        self.bank = pb.load_bank("MAT", lang="en")

    def test_pericopes_include_corpus_ids_with_display_refs(self):
        by_id = {p["id"]: p for p in self.bank["pericopes"]}
        self.assertEqual(by_id["MAT-014"]["ref"], "Matthew 5:3–12")
        self.assertEqual(by_id["MAT-014"]["title"], "The Beatitudes")

    def test_product_bank_empty_before_publish(self):
        # load_bank serves product mode (published only). Before the human
        # confirmation gate nothing is published, so the bank has no items yet.
        # (Task 13 flips this to assert the flattened 'body' shape on published items.)
        self.assertEqual(self.bank["items"], [])


if __name__ == "__main__":
    unittest.main()
