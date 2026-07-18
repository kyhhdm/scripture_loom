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

    def test_items_are_product_mode_with_flattened_body(self):
        ids = {i["id"] for i in self.bank["items"]}
        self.assertIn("mt5a-q-who-blessed", ids)
        self.assertNotIn("mt5a-q-draft-kingdom", ids)  # draft gated out
        item = next(i for i in self.bank["items"] if i["id"] == "mt5a-q-who-blessed")
        self.assertIsInstance(item["body"], str)
        self.assertNotIn("text", item)

    def test_quest_category_flattened(self):
        q = next(i for i in self.bank["items"] if i["id"] == "mt5a-quest-tally")
        self.assertIsInstance(q["category"], str)

    def test_zh_bank_uses_translation(self):
        zh = pb.load_bank("MAT", lang="zh")
        mv = next(i for i in zh["items"] if i["id"] == "mt5a-mv-peacemakers")
        self.assertIn("马太福音", mv["body"])


if __name__ == "__main__":
    unittest.main()
