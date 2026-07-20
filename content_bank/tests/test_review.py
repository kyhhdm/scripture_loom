import json
import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.author import review


def _item(iid, **kw):
    base = dict(id=iid, dimension="D1", type="question", age_tier="child",
                difficulty=1, review_status="draft", version=1, passage="PHP-001",
                text={"en": "Who wrote to the Philippians?"})
    base.update(kw)
    return base


class ReviewTest(unittest.TestCase):
    def test_review_parses_two_reviewer_verdicts(self):
        r1 = json.dumps({"a": {"verdict": "pass", "notes": ""}})
        r2 = json.dumps({"a": {"verdict": "fail", "notes": "judgment language"}})
        with mock.patch("content_bank.author.review.llm", side_effect=[r1, r2]):
            verdicts = review.review([_item("a")], passage_text="P", brief="B",
                                     book="PHP", unit_id="PHP-001")
        self.assertEqual(len(verdicts), 2)
        merged = {v["reviewer"]: v["verdicts"] for v in verdicts}
        self.assertEqual(merged["r2"]["a"]["verdict"], "fail")


class ReviseTest(unittest.TestCase):
    def test_revise_returns_corrected_array(self):
        items = [_item("a"), _item("b")]
        verdicts = [{"reviewer": "r1", "verdicts": {"a": {"verdict": "fail",
                     "notes": "fix"}}}]
        corrected = json.dumps([_item("a", text={"en": "Paul — who wrote it?"}),
                                _item("b")])
        with mock.patch("content_bank.author.review.llm", return_value=corrected):
            out = review.revise(items, verdicts, passage_text="P", brief="B")
        self.assertEqual(out[0]["text"]["en"], "Paul — who wrote it?")
        self.assertEqual(len(out), 2)

    def test_no_failures_skips_llm(self):
        items = [_item("a")]
        verdicts = [{"reviewer": "r1", "verdicts": {"a": {"verdict": "pass"}}}]
        with mock.patch("content_bank.author.review.llm") as m:
            out = review.revise(items, verdicts, passage_text="P", brief="B")
        m.assert_not_called()
        self.assertEqual(out, items)


if __name__ == "__main__":
    unittest.main()
