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

    def test_gate_serves_published(self):
        # After the human confirmation gate, product mode serves the published
        # items and never a reviewed/draft one.
        pub = content.get_content("MAT", mode="product")
        self.assertTrue(pub)
        self.assertEqual({i["review_status"] for i in pub}, {"published"})


if __name__ == "__main__":
    unittest.main()
