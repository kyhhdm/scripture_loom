import json
import pathlib
import tempfile
import unittest

from content_bank.author.telemetry import (
    CallRecord, NullSink, TelemetrySink, TokenUsage, prompt_hash)


class TelemetryTest(unittest.TestCase):
    def test_usage_nullable_fields_default_none(self):
        u = TokenUsage(input=10, output=20)
        self.assertIsNone(u.cache_read)
        self.assertIsNone(u.thinking)
        self.assertEqual(u.as_dict()["input"], 10)

    def _record(self):
        return CallRecord(
            experiment="e", stage="draft", unit_id="PHP-001", kind="pericope",
            attempt=1, backend="claude", requested_model="opus", actual_model="opus",
            usage=TokenUsage(input=5, output=7).as_dict(), usage_source="provider",
            cost_estimate=None, duration_ms=12, stop_reason="end_turn",
            success=True, error=None, prompt_hash="abc")

    def test_sink_appends_jsonl_and_reads_back(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "calls.jsonl"
            sink = TelemetrySink(p)
            sink.add(self._record())
            sink.add(self._record())
            lines = p.read_text().strip().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["stage"], "draft")
            self.assertEqual(len(list(sink.records())), 2)

    def test_null_sink_is_noop(self):
        NullSink().add(object())  # must not raise

    def test_prompt_hash_stable_and_not_the_prompt(self):
        h = prompt_hash("secret prompt")
        self.assertEqual(h, prompt_hash("secret prompt"))
        self.assertNotIn("secret", h)
        self.assertNotIn("prompt", h)


if __name__ == "__main__":
    unittest.main()
