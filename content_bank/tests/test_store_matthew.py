import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.lib import validate, content


class TestMatthewStore(unittest.TestCase):
    def test_store_validates_clean(self):
        self.assertEqual(validate.validate_store("MAT")["errors"], [])

    def test_only_scoped_pericopes_present(self):
        store = content.load_book_store("MAT")
        passages = {i["passage"] for i in store["items"]}
        self.assertEqual(passages, {"MAT-009", "MAT-013", "MAT-014", "MAT-015"})

    def test_every_item_reviewed_before_confirmation(self):
        # Before the human confirmation gate, nothing is published, so product
        # mode serves nothing while author mode sees the full reviewed set.
        self.assertEqual(content.get_content("MAT", mode="product"), [])
        self.assertTrue(content.get_content("MAT", mode="author"))


if __name__ == "__main__":
    unittest.main()
