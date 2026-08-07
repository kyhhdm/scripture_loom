import json
import pathlib
import tempfile
import unittest

from content_bank.author import experiment_report
from content_bank.author.routing import Route


def _call(stage, backend="llm_core", model="m", tin=100, tout=40, cost=0.001,
          cc=None, cr=None):
    return {"experiment": "e", "stage": stage, "unit_id": "PHP-001",
            "kind": "pericope", "attempt": 1, "backend": backend,
            "requested_model": model, "actual_model": model,
            "usage": {"input": tin, "output": tout, "cache_creation": cc,
                      "cache_read": cr, "thinking": None},
            "usage_source": "local_estimate", "cost_estimate": cost,
            "duration_ms": 5, "stop_reason": None, "success": True,
            "error": None, "prompt_hash": "h"}


class ReportTest(unittest.TestCase):
    def _fixture(self, d):
        out = pathlib.Path(d)
        calls = [_call("brief"), _call("draft", backend="claude", model="opus"),
                 _call("repair")]
        (out / "calls.jsonl").write_text(
            "\n".join(json.dumps(c) for c in calls) + "\n")
        (out / "gate_traces").mkdir()
        (out / "gate_traces" / "PHP-001.json").write_text(json.dumps(
            {"first_pass_clean": False, "final_pass": True,
             "rounds": [{"round": 1}], "item_drops": 0}))
        drafts = out / "PHP" / "runs" / "e" / "drafts"
        drafts.mkdir(parents=True)
        (drafts / "PHP-001.json").write_text(json.dumps([{"id": "a"}, {"id": "b"}]))
        return out

    def test_aggregates_calls_tokens_gates(self):
        with tempfile.TemporaryDirectory() as d:
            out = self._fixture(d)
            rep = experiment_report.build_report(
                out, draft_route=Route("claude", "opus"),
                evaluator_route=Route("llm_core", "m"))
        self.assertEqual(rep["calls_total"], 3)
        self.assertEqual(rep["claude_calls"], 1)
        self.assertEqual(rep["calls_by_stage"]["repair"], 1)
        self.assertEqual(rep["tokens_in_total"], 300)
        self.assertEqual(rep["accepted_items"], 2)
        self.assertEqual(rep["first_pass_gate_rate"], 0.0)
        self.assertEqual(rep["final_gate_rate"], 1.0)
        self.assertEqual(rep["repaired_units"], 1)
        self.assertFalse(rep["evaluator_is_drafter"])

    def test_counts_accepted_items_across_multiple_books(self):
        with tempfile.TemporaryDirectory() as d:
            out = pathlib.Path(d)
            (out / "calls.jsonl").write_text(json.dumps(_call("draft")) + "\n")
            for book, unit, n in (("PHP", "PHP-002", 2), ("JON", "JON-002", 3)):
                dd = out / book / "runs" / "e" / "drafts"
                dd.mkdir(parents=True)
                (dd / f"{unit}.json").write_text(
                    json.dumps([{"id": f"{unit}-{i}"} for i in range(n)]))
            rep = experiment_report.build_report(out)
        self.assertEqual(rep["accepted_items"], 5)

    def test_input_total_includes_cache_tokens(self):
        # claude prompt caching puts most input in cache_creation/cache_read, not
        # the uncached `input` field; tokens_in must count all three.
        with tempfile.TemporaryDirectory() as d:
            out = pathlib.Path(d)
            (out / "calls.jsonl").write_text(json.dumps(
                _call("draft", tin=2, tout=9000, cc=20000, cr=16000)) + "\n")
            rep = experiment_report.build_report(out)
        self.assertEqual(rep["tokens_in_total"], 2 + 20000 + 16000)
        self.assertEqual(rep["tokens_in_uncached_total"], 2)
        self.assertEqual(rep["cache_creation_total"], 20000)
        self.assertEqual(rep["cache_read_total"], 16000)
        self.assertEqual(rep["tokens_in_by_stage"]["draft"], 36002)

    def test_evaluator_is_drafter_true_when_same(self):
        with tempfile.TemporaryDirectory() as d:
            out = self._fixture(d)
            rep = experiment_report.build_report(
                out, draft_route=Route("claude", "opus"),
                evaluator_route=Route("claude", "opus"))
        self.assertTrue(rep["evaluator_is_drafter"])


if __name__ == "__main__":
    unittest.main()
