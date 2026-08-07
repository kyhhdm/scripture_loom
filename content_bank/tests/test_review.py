import json
import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.author import review
from content_bank.author.routing import Route
from content_bank.author.telemetry import LLMResult, TokenUsage


def _result(text):
    return LLMResult(text=text, usage=TokenUsage(), requested_model=None,
                     actual_model=None, stop_reason=None, duration_ms=1,
                     usage_source="local_estimate")


def _item(iid, **kw):
    base = dict(id=iid, dimension="D1", type="question", age_tier="child",
                difficulty=1, review_status="draft", version=1, passage="PHP-001",
                text={"en": "Who wrote to the Philippians?"})
    base.update(kw)
    return base


class ReviewTest(unittest.TestCase):
    def test_review_parses_two_reviewer_verdicts(self):
        r1 = _result(json.dumps({"a": {"verdict": "pass", "notes": ""}}))
        r2 = _result(json.dumps({"a": {"verdict": "fail", "notes": "judgment language"}}))
        with mock.patch("content_bank.author.review.llm", side_effect=[r1, r2]):
            verdicts = review.review([_item("a")], passage_text="P", brief="B",
                                     book="PHP", unit_id="PHP-001")
        self.assertEqual(len(verdicts), 2)
        merged = {v["reviewer"]: v["verdicts"] for v in verdicts}
        self.assertEqual(merged["r2"]["a"]["verdict"], "fail")

    def test_review_uses_r1_and_r2_routes(self):
        seen = []

        def fake_llm(prompt, route):
            seen.append(route.model)
            return _result('{"verdicts": {}}')

        with mock.patch.object(review, "llm", fake_llm):
            review.review([_item("a")], passage_text="p", brief="b",
                          book="PHP", unit_id="PHP-001",
                          r1_route=Route("llm_core", "m1"),
                          r2_route=Route("claude", "m2"))
        self.assertEqual(seen, ["m1", "m2"])


class ReviseTest(unittest.TestCase):
    def test_revise_uses_given_route(self):
        items = [_item("a")]
        verdicts = [{"reviewer": "r1", "verdicts": {"a": {"verdict": "fail",
                     "notes": "fix"}}}]
        seen = {}

        def fake_llm(prompt, route):
            seen["model"] = route.model
            return _result(json.dumps(items))

        with mock.patch.object(review, "llm", fake_llm):
            review.revise(items, verdicts, passage_text="P", brief="B",
                          route=Route("claude", "sonnet"))
        self.assertEqual(seen["model"], "sonnet")
    def test_revise_returns_corrected_array(self):
        items = [_item("a"), _item("b")]
        verdicts = [{"reviewer": "r1", "verdicts": {"a": {"verdict": "fail",
                     "notes": "fix"}}}]
        corrected = _result(json.dumps([_item("a", text={"en": "Paul — who wrote it?"}),
                                        _item("b")]))
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
