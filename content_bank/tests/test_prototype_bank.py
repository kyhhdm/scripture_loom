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

    def test_items_flattened_to_body_and_product_gated(self):
        # load_bank serves product mode (published only), flattening text/category
        # for the requested language to a 'body' string; no reviewed/draft leaks.
        self.assertTrue(self.bank["items"])
        item = self.bank["items"][0]
        self.assertIsInstance(item["body"], str)
        self.assertNotIn("text", item)
        statuses = {i.get("review_status") for i in self.bank["items"]}
        self.assertNotIn("draft", statuses)
        self.assertNotIn("reviewed", statuses)

    def test_load_sections_flattens_titles(self):
        from content_bank.lib import prototype_bank
        secs = prototype_bank.load_sections("MAT", lang="en")
        self.assertEqual(len(secs), 7)
        self.assertEqual(secs[0]["id"], "MAT-S1")
        self.assertEqual(secs[0]["title"], "Prologue: The Infancy")
        self.assertEqual(secs[0]["first_pericope"], "MAT-001")


if __name__ == "__main__":
    unittest.main()
