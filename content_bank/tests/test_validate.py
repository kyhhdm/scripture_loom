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


class TestReferenceCounts(unittest.TestCase):
    def _write_store(self, items):
        d = tempfile.mkdtemp()
        with open(pathlib.Path(d) / "mat.json", "w", encoding="utf-8") as f:
            json.dump({"items": items}, f)
        return d

    def _item(self, iid, dim, typ, ref=None):
        it = {"id": iid, "passage": "MAT-014", "dimension": dim, "type": typ,
              "age_tier": "youth", "difficulty": 1, "review_status": "published",
              "text": {"en": "x"}, "version": 1,
              "provenance": {"drafted_by": "claude", "reviewed_by": "claude",
                             "reviewed_date": "2026-07-19", "guardrail": "WCF-1"}}
        if ref is not None:
            it["leader_reference"] = ref
        return it

    def test_reference_counts(self):
        ak = {"kind": "answer_key", "text": {"en": "a"},
              "provenance": {"reviewed_by": "claude", "reviewed_date": "2026-07-19",
                             "guardrail": "WCF-1"}}
        note = {"kind": "leader_note", "text": {"en": "n"},
                "provenance": {"reviewed_by": "claude", "reviewed_date": "2026-07-19",
                               "guardrail": "WCF-1"}}
        items = [
            self._item("q1", "D1", "question", ak),
            self._item("q2", "D7", "question", note),
            self._item("q3", "D2", "question"),            # eligible, missing
            self._item("a1", "D8", "activity"),            # not counted as missing
        ]
        d = self._write_store(items)
        counts = validate.validate_store("MAT", store_dir=d)["counts"]
        self.assertEqual(counts["references"]["total"], 2)
        self.assertEqual(counts["references"]["answer_key"], 1)
        self.assertEqual(counts["references"]["leader_note"], 1)
        self.assertEqual(counts["references"]["missing_reference"], 1)


if __name__ == "__main__":
    unittest.main()
