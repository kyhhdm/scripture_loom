"""The content_bank llm() seam delegates to llm_core without importing litellm.

Network-free: llm_core.run_sync_llm is mocked, so this only checks the wiring
(lazy import + argument passing) issue #16's build_cli.py will rely on.
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from content_bank.author import llm as seam  # noqa: E402


class SeamTest(unittest.TestCase):
    def test_delegates_to_llm_core(self):
        with mock.patch("llm_core.run_sync_llm", return_value="drafted") as m:
            out = seam.llm("RENDERED PROMPT")
        self.assertEqual(out, "drafted")
        m.assert_called_once()
        args, kwargs = m.call_args
        # Prompt goes through as the user message; system prompt is empty.
        self.assertIn("RENDERED PROMPT", args)
        self.assertEqual(kwargs.get("caller"), "content_bank")


if __name__ == "__main__":
    unittest.main()
