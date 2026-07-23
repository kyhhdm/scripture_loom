import json
import pathlib
import sys
import tempfile
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


class TestLoadBankStripsTags(unittest.TestCase):
    def _store_dir(self, item):
        d = tempfile.mkdtemp()
        (pathlib.Path(d) / "php.json").write_text(
            json.dumps({"book": "PHP", "items": [item]}), encoding="utf-8")
        return d

    def test_body_and_leader_ref_stripped(self):
        item = {"id": "PHP-001-D1-01", "passage": "PHP.1.1-11", "dimension": "D1",
                "type": "question", "review_status": "published", "version": 1,
                "age_tier": "all", "difficulty": 1,
                "text": {"en": 'Who are the <verse ref="PHP.1.1">servants of Christ '
                               'Jesus</verse>?'},
                "leader_reference": {"kind": "answer_key",
                                     "text": {"en": 'Rests on <doctrine std="WCF" '
                                              'ref="1.4">God its author</doctrine>.'},
                                     "verse": {"en": "Philippians 1:1"}}}
        bank = pb.load_bank("PHP", lang="en", store_dir=self._store_dir(item))
        it = bank["items"][0]
        self.assertNotIn("<verse", it["body"])
        self.assertEqual(it["body"], "Who are the servants of Christ Jesus?")
        self.assertNotIn("<doctrine", it["leader_reference"]["text"]["en"])


if __name__ == "__main__":
    unittest.main()
