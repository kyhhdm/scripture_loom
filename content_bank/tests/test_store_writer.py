import json
import pathlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.author import store_writer


def _item(iid, text="hi"):
    return {"id": iid, "passage": "PHP-001", "dimension": "D1", "type": "question",
            "age_tier": "all", "difficulty": 1, "review_status": "draft",
            "text": {"en": text}, "version": 1}


class TestStoreWriter(unittest.TestCase):
    def test_creates_store_when_absent(self):
        with tempfile.TemporaryDirectory() as d:
            store = store_writer.upsert_items("PHP", [_item("a")], store_dir=d)
            self.assertEqual(store["book"], "PHP")
            on_disk = json.loads((Path(d) / "php.json").read_text())
            self.assertEqual(len(on_disk["items"]), 1)

    def test_appends_new_id(self):
        with tempfile.TemporaryDirectory() as d:
            store_writer.upsert_items("PHP", [_item("a")], store_dir=d)
            store = store_writer.upsert_items("PHP", [_item("b")], store_dir=d)
            self.assertEqual([i["id"] for i in store["items"]], ["a", "b"])

    def test_replaces_existing_id_in_place(self):
        with tempfile.TemporaryDirectory() as d:
            store_writer.upsert_items("PHP", [_item("a", "old"), _item("b")], store_dir=d)
            store = store_writer.upsert_items("PHP", [_item("a", "new")], store_dir=d)
            self.assertEqual([i["id"] for i in store["items"]], ["a", "b"])
            self.assertEqual(store["items"][0]["text"]["en"], "new")


if __name__ == "__main__":
    unittest.main()
