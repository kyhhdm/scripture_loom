import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.lib import content


def item(**over):
    base = {
        "id": "x", "passage": "MAT-014", "dimension": "D7", "type": "question",
        "age_tier": "all", "difficulty": 1, "review_status": "published",
        "text": {"en": "hi"}, "version": 1,
    }
    base.update(over)
    return base


class TestGetContent(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        store = {"book": "MAT", "items": [
            item(id="pub", review_status="published"),
            item(id="draft", review_status="draft"),
            item(id="reviewed", review_status="reviewed"),
            item(id="youth", age_tier="youth"),
            item(id="p13", passage="MAT-013"),
            item(id="zhonly", text={"zh": "你好"}),
        ]}
        (self.dir / "mat.json").write_text(json.dumps(store), encoding="utf-8")

    def ids(self, **kw):
        return {i["id"] for i in content.get_content("MAT", store_dir=self.dir, **kw)}

    def test_product_mode_serves_only_published(self):
        got = self.ids()
        self.assertIn("pub", got)
        self.assertNotIn("draft", got)
        self.assertNotIn("reviewed", got)

    def test_author_mode_serves_all_statuses(self):
        got = self.ids(mode="author")
        self.assertIn("draft", got)
        self.assertIn("reviewed", got)

    def test_pericope_filter(self):
        self.assertEqual(self.ids(pericope="MAT-013"), {"p13"})

    def test_age_tier_filter_includes_all(self):
        got = self.ids(age_tier="youth")
        self.assertIn("youth", got)   # tier match
        self.assertIn("pub", got)     # age_tier="all" always matches

    def test_missing_language_excluded(self):
        self.assertNotIn("zhonly", self.ids(lang="en"))
        self.assertIn("zhonly", self.ids(lang="zh"))

    def test_dimension_filter(self):
        self.assertEqual(self.ids(dimension="D1"), set())


if __name__ == "__main__":
    unittest.main()
