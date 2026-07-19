import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.author import digest


def _item(iid, dim, typ="question", scope=("passage", "PHP-001")):
    it = {"id": iid, "dimension": dim, "type": typ, "age_tier": "all",
          "difficulty": 1, "review_status": "draft", "text": {"en": iid}, "version": 1}
    it[scope[0]] = scope[1]
    return it


class TestTierOf(unittest.TestCase):
    def test_closed_dimension_is_batch(self):
        self.assertEqual(digest.tier_of(_item("a", "D3")), "batch")

    def test_open_dimension_is_item(self):
        self.assertEqual(digest.tier_of(_item("a", "D7")), "item")

    def test_throughline_is_item(self):
        it = _item("t", "D7", "throughline", scope=("section", "PHP-S1"))
        self.assertEqual(digest.tier_of(it), "item")


class TestBuildDigest(unittest.TestCase):
    def test_splits_by_tier(self):
        items = [_item("a", "D1"), _item("b", "D7")]
        d = digest.build_digest("PHP-001", items, {})
        self.assertEqual([i["id"] for i in d["batch"]], ["a"])
        self.assertEqual([i["id"] for i in d["item_tier"]], ["b"])


class TestRenderDigest(unittest.TestCase):
    def test_render_has_both_sections_and_verdicts(self):
        items = [_item("a", "D1"), _item("b", "D7")]
        verdicts = {"b": [{"reviewer": "r1", "verdict": "pass", "notes": "ok"}]}
        text = digest.render_digest(digest.build_digest("PHP-001", items, verdicts))
        self.assertIn("PHP-001", text)
        self.assertIn("Batch review (D1-D5)", text)
        self.assertIn("Item-by-item review", text)
        self.assertIn("r1", text)


if __name__ == "__main__":
    unittest.main()
