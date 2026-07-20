"""The content_bank llm() seam: llm_core backend + optional claude-CLI backend.

Network-free: llm_core.run_sync_llm and subprocess.run are mocked, so this only
checks the wiring (backend dispatch, argv shape, error handling) the standalone
builder relies on.
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from content_bank.author import llm as seam  # noqa: E402


class LlmCoreBackendTest(unittest.TestCase):
    def test_default_delegates_to_llm_core(self):
        with mock.patch.dict("os.environ", {}, clear=False) as _e:
            _e.pop("SCRIPTURE_LOOM_LLM_BACKEND", None)
            with mock.patch("llm_core.run_sync_llm", return_value="drafted") as m:
                out = seam.llm("RENDERED PROMPT")
        self.assertEqual(out, "drafted")
        m.assert_called_once()
        args, kwargs = m.call_args
        self.assertIn("RENDERED PROMPT", args)
        self.assertEqual(kwargs.get("caller"), "content_bank")


class ClaudeBackendTest(unittest.TestCase):
    def _fake_proc(self, returncode=0, stdout="OUT", stderr=""):
        p = mock.Mock()
        p.returncode = returncode
        p.stdout = stdout
        p.stderr = stderr
        return p

    def test_selected_by_env_builds_argv_and_passes_prompt_on_stdin(self):
        with mock.patch.dict("os.environ",
                             {"SCRIPTURE_LOOM_LLM_BACKEND": "claude"}), \
             mock.patch("content_bank.author.llm.subprocess.run",
                        return_value=self._fake_proc(stdout="COMPLETION")) as m:
            out = seam.llm("A PROMPT")
        self.assertEqual(out, "COMPLETION")
        argv = m.call_args.args[0]
        self.assertEqual(argv[0], "claude")
        self.assertIn("-p", argv)
        self.assertIn("--model", argv)
        self.assertEqual(argv[argv.index("--model") + 1], "opus")  # strong default
        self.assertIn("--output-format", argv)
        self.assertIn("--disallowed-tools", argv)
        self.assertNotIn("--bare", argv)  # --bare breaks subscription auth
        # Prompt goes on stdin, not argv.
        self.assertEqual(m.call_args.kwargs.get("input"), "A PROMPT")

    def test_model_override_passthrough(self):
        with mock.patch.dict("os.environ",
                             {"SCRIPTURE_LOOM_LLM_BACKEND": "claude"}), \
             mock.patch("content_bank.author.llm.subprocess.run",
                        return_value=self._fake_proc(stdout="X")) as m:
            seam.llm("P", model="sonnet")
        argv = m.call_args.args[0]
        self.assertEqual(argv[argv.index("--model") + 1], "sonnet")

    def test_nonzero_exit_raises_runtimeerror(self):
        with mock.patch.dict("os.environ",
                             {"SCRIPTURE_LOOM_LLM_BACKEND": "claude"}), \
             mock.patch("content_bank.author.llm.subprocess.run",
                        return_value=self._fake_proc(returncode=1, stderr="boom")):
            with self.assertRaises(RuntimeError):
                seam.llm("P")

    def test_empty_output_raises_runtimeerror(self):
        with mock.patch.dict("os.environ",
                             {"SCRIPTURE_LOOM_LLM_BACKEND": "claude"}), \
             mock.patch("content_bank.author.llm.subprocess.run",
                        return_value=self._fake_proc(stdout="   ")):
            with self.assertRaises(RuntimeError):
                seam.llm("P")


if __name__ == "__main__":
    unittest.main()
