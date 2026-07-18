import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.lib import validate


def item(**over):
    base = {
        "id": "a", "passage": "MAT-014", "dimension": "D7", "type": "question",
        "age_tier": "all", "difficulty": 1, "review_status": "draft",
        "text": {"en": "hi"}, "version": 1,
    }
    base.update(over)
    return base


class TestValidateStore(unittest.TestCase):
    def _write(self, items):
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "mat.json").write_text(
            json.dumps({"book": "MAT", "items": items}), encoding="utf-8")
        return d

    def test_clean_store_has_no_errors(self):
        d = self._write([item(id="a"), item(id="b", passage="MAT-015")])
        self.assertEqual(validate.validate_store("MAT", store_dir=d)["errors"], [])

    def test_dangling_passage_is_error(self):
        d = self._write([item(id="a", passage="MAT-999")])
        errs = validate.validate_store("MAT", store_dir=d)["errors"]
        self.assertTrue(any("MAT-999" in e for e in errs))

    def test_duplicate_id_is_error(self):
        d = self._write([item(id="dup"), item(id="dup", passage="MAT-015")])
        errs = validate.validate_store("MAT", store_dir=d)["errors"]
        self.assertTrue(any("dup" in e for e in errs))

    def test_schema_error_surfaced(self):
        d = self._write([item(id="a", dimension="D9")])
        self.assertTrue(validate.validate_store("MAT", store_dir=d)["errors"])

    def test_counts_and_bilingual_coverage(self):
        d = self._write([
            item(id="a", text={"en": "x"}),
            item(id="b", text={"en": "x", "zh": "y"}, passage="MAT-015"),
        ])
        counts = validate.validate_store("MAT", store_dir=d)["counts"]
        self.assertEqual(counts["items"], 2)
        self.assertEqual(counts["by_lang"]["zh"], 1)
        self.assertEqual(counts["missing_zh"], 1)


if __name__ == "__main__":
    unittest.main()
