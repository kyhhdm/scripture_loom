import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.lib import validate, content


class TestMatthewStore(unittest.TestCase):
    def test_store_is_valid(self):
        result = validate.validate_store("MAT")
        self.assertEqual(result["errors"], [])

    def test_expected_counts(self):
        counts = validate.validate_store("MAT")["counts"]
        self.assertEqual(counts["items"], 25)
        self.assertEqual(counts["published"], 24)
        self.assertEqual(counts["draft"], 1)
        self.assertEqual(counts["by_lang"]["zh"], 1)   # one seeded translation
        self.assertEqual(counts["missing_zh"], 24)

    def test_beatitudes_split(self):
        p13 = {i["id"] for i in content.get_content("MAT", pericope="MAT-013", mode="author")}
        self.assertEqual(p13, {"mt5a-q-mountain", "mt5a-quest-who-listens"})

    def test_draft_hidden_in_product_mode(self):
        ids = {i["id"] for i in content.get_content("MAT", mode="product", lang="en")}
        self.assertNotIn("mt5a-q-draft-kingdom", ids)

    def test_seeded_translation_present(self):
        zh = content.get_content("MAT", pericope="MAT-014", lang="zh")
        self.assertIn("mt5a-mv-peacemakers", {i["id"] for i in zh})


if __name__ == "__main__":
    unittest.main()
