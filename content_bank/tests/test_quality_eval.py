import json
import pathlib
import tempfile
import unittest
from unittest import mock

from content_bank.author import quality_eval
from content_bank.author.routing import Route
from content_bank.author.telemetry import LLMResult, TokenUsage


def _fit_result(text):
    return LLMResult(text=text, usage=TokenUsage(input=3, output=5),
                     requested_model="sonnet", actual_model="sonnet",
                     stop_reason="end_turn", duration_ms=1, usage_source="provider")


def _item(iid, dim, text="Question text", **extra):
    item = {
        "id": iid, "passage": "PHP.1.12-26", "dimension": dim,
        "type": "question", "age_tier": "youth", "difficulty": 2,
        "review_status": "draft", "text": {"en": text}, "version": 1,
    }
    item.update(extra)
    return item


class MetricsTest(unittest.TestCase):
    def test_computes_quality_metrics_and_saved_failures(self):
        items = [
            _item("a", "D1", '<verse ref="PHP.1.13">the whole palace guard</verse>',
                  difficulty=3, leader_reference={
                      "kind": "answer_key", "text": {"en": "The guard."}}),
            _item("b", "D8", "Write one concrete action."),
        ]
        metrics = quality_eval.compute_metrics(
            items, hard_flags={"b": ["bad"]}, soft_flags={},
            verdicts={"a": [{"reviewer": "r1", "verdict": "fail",
                              "notes": "fix it"}]})
        self.assertEqual(metrics["item_count"], 2)
        self.assertEqual(metrics["dimension_counts"]["D1"], 1)
        self.assertEqual(metrics["missing_dimensions"],
                         ["D2", "D3", "D4", "D5", "D6", "D7"])
        self.assertEqual(metrics["hard_gate_flagged_items"], 1)
        self.assertEqual(metrics["verse_tag_count"], 1)
        self.assertEqual(metrics["difficulty_3_count"], 1)
        self.assertEqual(metrics["saved_review_failure_count"], 1)


class DimensionFitTest(unittest.TestCase):
    def test_dedicated_fit_review_reports_adjusted_coverage(self):
        items = [_item("d1", "D1"), _item("fake-d6", "D6")]
        raw = json.dumps([
            {"id": "d1", "status": "accurate", "suggested_dimension": "D1",
             "confidence": 0.95, "reason": "The learner identifies a person."},
            {"id": "fake-d6", "status": "misclassified",
             "suggested_dimension": "D7", "confidence": 0.99,
             "reason": "The learner answers a supplied why-question."},
        ])

        def reviewer(prompt, model=None):
            self.assertIn("D6 requires the LEARNER", prompt)
            self.assertEqual(model, "reviewer-model")
            return raw

        result = quality_eval.evaluate_dimension_fit(
            items, reviewer=reviewer, model="reviewer-model")
        self.assertEqual(result["status_counts"]["misclassified"], 1)
        self.assertEqual(result["adjusted_dimension_counts"]["D7"], 1)
        self.assertIn("D6", result["adjusted_missing_dimensions"])

    def test_fit_uses_given_route_and_records_telemetry(self):
        from content_bank.author.telemetry import TelemetrySink
        items = [_item("d1", "D1")]
        raw = json.dumps([{"id": "d1", "status": "accurate",
                           "suggested_dimension": "D1", "confidence": 0.9,
                           "reason": "identifies a person"}])
        seen = {}

        def fake_llm(prompt, route):
            seen["model"] = route.model
            return _fit_result(raw)

        with tempfile.TemporaryDirectory() as d:
            sink = TelemetrySink(pathlib.Path(d) / "calls.jsonl")
            with mock.patch.object(quality_eval, "llm", fake_llm):
                quality_eval.evaluate_dimension_fit(
                    items, route=Route("claude", "sonnet"), sink=sink,
                    unit_id="PHP-001")
            records = list(sink.records())
        self.assertEqual(seen["model"], "sonnet")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["stage"], "evaluate")
        self.assertEqual(records[0]["unit_id"], "PHP-001")

    def test_rejects_missing_or_reordered_item_results(self):
        items = [_item("a", "D1"), _item("b", "D2")]
        raw = json.dumps([{"id": "b", "status": "accurate",
                           "suggested_dimension": "D2", "confidence": 1,
                           "reason": "flow"}])
        with self.assertRaisesRegex(ValueError, "ids/order"):
            quality_eval.evaluate_dimension_fit(
                items, reviewer=lambda *_a, **_k: raw)


class CliTest(unittest.TestCase):
    def test_metrics_only_cli_writes_json_without_llm(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            drafts = base / "PHP" / "runs" / "run-a" / "drafts"
            drafts.mkdir(parents=True)
            (drafts / "PHP-X.json").write_text(
                json.dumps([_item("x", "D1")]), encoding="utf-8")
            out = base / "report.json"
            rc = quality_eval.main([
                "--book", "PHP", "--runs", "run-a", "--units", "PHP-X",
                "--base", str(base), "--out", str(out), "--no-dimension-fit",
            ])
            self.assertEqual(rc, 0)
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertFalse(report["dimension_fit_reviewer"]["enabled"])
            self.assertEqual(
                report["runs"]["run-a"]["units"]["PHP-X"]["metrics"]["item_count"],
                1)


if __name__ == "__main__":
    unittest.main()
