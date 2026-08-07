import unittest
from unittest import mock

from content_bank.author import review, routing
from content_bank.author.telemetry import LLMResult, TokenUsage


def _res(text):
    return LLMResult(text=text, usage=TokenUsage(), requested_model="opus",
                     actual_model="opus", stop_reason="end_turn", duration_ms=1,
                     usage_source="provider")


class TestReviewGroup(unittest.TestCase):
    def test_review_group_two_lens_calls_per_group(self):
        items = {"A": [{"id": "A-1"}]}
        ctx = {"A": {"passage_text": "p", "brief": "b"}}
        calls = []

        def fake(prompt, route):
            calls.append(prompt)
            return _res('{"units": {"A": {"A-1": {"verdict": "pass", "notes": ""}}}}')
        with mock.patch("content_bank.author.review.llm", side_effect=fake):
            out = review.review_group(items, ctx_by_unit=ctx, book="PHP",
                                      r1_route=routing.Route("claude", "opus"),
                                      r2_route=routing.Route("claude", "opus"))
        self.assertEqual(len(calls), 2)   # r1 + r2, one call each over the group
        self.assertEqual([r["reviewer"] for r in out], ["r1", "r2"])
        self.assertEqual(out[0]["verdicts_by_unit"]["A"]["A-1"]["verdict"], "pass")


class TestReviseGroup(unittest.TestCase):
    def test_only_failed_units_sent(self):
        items = {"A": [{"id": "A-1"}], "B": [{"id": "B-1"}]}
        gv = [{"reviewer": "r1",
               "verdicts_by_unit": {
                   "A": {"A-1": {"verdict": "fail", "notes": "x"}},
                   "B": {"B-1": {"verdict": "pass", "notes": ""}}}}]
        ctx = {u: {"passage_text": "p", "brief": "b"} for u in items}
        captured = {}

        def fake(prompt, route):
            captured["prompt"] = prompt
            return _res('{"units": {"A": [{"id": "A-1", "fixed": true}]}}')
        with mock.patch("content_bank.author.review.llm", side_effect=fake):
            out = review.revise_group(items, gv, ctx_by_unit=ctx,
                                      route=routing.Route("claude", "opus"))
        self.assertIn("A-1", captured["prompt"])
        self.assertNotIn("B-1", captured["prompt"])
        self.assertEqual(out["B"], [{"id": "B-1"}])
        self.assertEqual(out["A"], [{"id": "A-1", "fixed": True}])

    def test_no_failures_returns_unchanged_without_call(self):
        items = {"A": [{"id": "A-1"}]}
        gv = [{"reviewer": "r1",
               "verdicts_by_unit": {"A": {"A-1": {"verdict": "pass", "notes": ""}}}}]
        ctx = {"A": {"passage_text": "p", "brief": "b"}}
        with mock.patch("content_bank.author.review.llm") as m:
            out = review.revise_group(items, gv, ctx_by_unit=ctx,
                                      route=routing.Route("claude", "opus"))
        m.assert_not_called()
        self.assertEqual(out, items)


if __name__ == "__main__":
    unittest.main()
