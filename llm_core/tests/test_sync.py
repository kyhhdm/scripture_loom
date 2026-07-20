"""Network-free tests for the llm_core sync seam.

The LLM boundary (`LLMService.run_batch_sync`) is mocked, so no provider key,
no litellm, and no network are exercised — this validates only our vendored
glue: the config gate, prompt->messages mapping, and generation extraction.
"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from llm_core import sync  # noqa: E402


class RunSyncLLMTest(unittest.TestCase):
    def setUp(self):
        # Gate passes without depending on the real .env being present.
        os.environ.setdefault("ARK_API_KEY", "test-key")

    def test_maps_generation_text(self):
        fake = {"generations": [{"generation": "hello world", "error": None}],
                "summary": {"tokens_out_total": 2, "cost": 0.0}}
        with mock.patch("llm_core.service.LLMService.run_batch_sync",
                        return_value=fake) as m, \
                mock.patch.object(sync, "llm_configured", return_value=True):
            out = sync.run_sync_llm("sys", "user", model="deepseek-v4-flash")
        self.assertEqual(out, "hello world")
        self.assertEqual(m.call_count, 1)
        # One prompt (list of messages) submitted, system+user turns.
        (prompts,), kwargs = m.call_args
        self.assertEqual(kwargs["model"], "deepseek-v4-flash")
        self.assertEqual(prompts[0][0], {"role": "system", "content": "sys"})
        self.assertEqual(prompts[0][1], {"role": "user", "content": "user"})

    def test_batch_maps_and_fails_open_per_item(self):
        fake = {"generations": [
                    {"generation": "a", "error": None},
                    {"generation": "", "error": "model_returned_empty"}],
                "summary": {}}
        with mock.patch("llm_core.service.LLMService.run_batch_sync",
                        return_value=fake), \
                mock.patch.object(sync, "llm_configured", return_value=True):
            out = sync.run_batch_llm([("s1", "u1"), ("s2", "u2")])
        self.assertEqual(out, ["a", ""])

    def test_unconfigured_raises(self):
        with mock.patch.object(sync, "llm_configured", return_value=False):
            with self.assertRaises(RuntimeError):
                sync.run_sync_llm("", "hi")

    def test_empty_batch_short_circuits(self):
        # No gate check, no LLM call for an empty batch.
        self.assertEqual(sync.run_batch_llm([]), [])


if __name__ == "__main__":
    unittest.main()
