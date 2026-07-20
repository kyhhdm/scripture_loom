import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.lib import validate, content


class TestMatthewStore(unittest.TestCase):
    def test_store_validates_clean(self):
        self.assertEqual(validate.validate_store("MAT")["errors"], [])

    def test_only_scoped_pericopes_present(self):
        # Every passage in the store must be a real pericope defined in the
        # corpus structure — no orphan/misnamed scopes. (The store now holds a
        # growing reviewed draft library, so this checks membership rather than
        # an exact pilot set.)
        import json
        pericope_ids = {
            p["id"]
            for p in json.load(
                open("corpus/canon/structure/pericopes/mat.json")
            )["pericopes"]
        }
        store = content.load_book_store("MAT")
        passages = {i["passage"] for i in store["items"]}
        self.assertTrue(passages <= pericope_ids, passages - pericope_ids)

    def test_gate_serves_published(self):
        # After the human confirmation gate, product mode serves the published
        # items and never a reviewed/draft one.
        pub = content.get_content("MAT", mode="product")
        self.assertTrue(pub)
        self.assertEqual({i["review_status"] for i in pub}, {"published"})

    def test_references_validate_and_cover_eligible(self):
        result = validate.validate_store("MAT")
        self.assertEqual(result["errors"], [])                    # refs valid
        refs = result["counts"]["references"]
        self.assertEqual(refs["missing_reference"], 0)            # all q/quest covered
        self.assertGreater(refs["answer_key"], 0)
        self.assertGreater(refs["leader_note"], 0)

    def test_no_reference_on_memory_verse(self):
        store = content.load_book_store("MAT")
        for it in store["items"]:
            if it["type"] == "memory_verse":
                self.assertNotIn("leader_reference", it)

    def test_reference_kind_matches_dimension(self):
        from content_bank.lib import schema
        store = content.load_book_store("MAT")
        for it in store["items"]:
            ref = it.get("leader_reference")
            if not ref:
                continue
            if ref["kind"] == "answer_key":
                self.assertIn(it["dimension"], schema.CLOSED_DIMENSIONS)
            else:
                self.assertIn(it["dimension"], schema.OPEN_DIMENSIONS)


if __name__ == "__main__":
    unittest.main()
