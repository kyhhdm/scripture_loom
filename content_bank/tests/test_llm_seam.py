"""The content_bank llm() seam: llm_core backend + optional claude-CLI backend.

Network-free: llm_core.run_sync_llm and subprocess.run are mocked, so this only
checks the wiring (Route dispatch, argv shape, error handling) the builder and
the experiment runner rely on.
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from content_bank.author import llm as seam  # noqa: E402
from content_bank.author.routing import Route  # noqa: E402


class LlmCoreBackendTest(unittest.TestCase):
    def test_llm_core_route_calls_run_sync_with_model(self):
        captured = {}

        def fake_run_sync(system, user, caller="", model=None):
            captured["caller"] = caller
            captured["model"] = model
            captured["prompt"] = user
            return "OK"

        with mock.patch("llm_core.run_sync_llm", fake_run_sync):
            out = seam.llm("RENDERED PROMPT", Route("llm_core", "deepseek-v4-pro"))
        self.assertEqual(out, "OK")
        self.assertEqual(captured["model"], "deepseek-v4-pro")
        self.assertEqual(captured["caller"], "content_bank")
        self.assertEqual(captured["prompt"], "RENDERED PROMPT")

    def test_llm_core_default_model_is_none(self):
        with mock.patch("llm_core.run_sync_llm", return_value="ok") as m:
            seam.llm("P", Route("llm_core"))
        self.assertIsNone(m.call_args.kwargs.get("model"))


class RouteFromEnvTest(unittest.TestCase):
    def test_env_backend_and_model(self):
        with mock.patch.dict("os.environ",
                             {"SCRIPTURE_LOOM_LLM_BACKEND": "claude",
                              "SCRIPTURE_LOOM_LLM_MODEL": "sonnet"}):
            r = seam.route_from_env()
        self.assertEqual((r.backend, r.model), ("claude", "sonnet"))

    def test_default_backend_llm_core_when_unset(self):
        with mock.patch.dict("os.environ", {}, clear=False) as _e:
            _e.pop("SCRIPTURE_LOOM_LLM_BACKEND", None)
            _e.pop("SCRIPTURE_LOOM_LLM_MODEL", None)
            r = seam.route_from_env()
        self.assertEqual(r.backend, "llm_core")
        self.assertIsNone(r.model)

    def test_model_override_arg(self):
        with mock.patch.dict("os.environ", {}, clear=False) as _e:
            _e.pop("SCRIPTURE_LOOM_LLM_MODEL", None)
            r = seam.route_from_env("deepseek-v4-flash")
        self.assertEqual(r.model, "deepseek-v4-flash")


class ClaudeBackendTest(unittest.TestCase):
    def _fake_proc(self, returncode=0, stdout="OUT", stderr=""):
        p = mock.Mock()
        p.returncode = returncode
        p.stdout = stdout
        p.stderr = stderr
        return p

    def test_route_builds_argv_and_passes_prompt_on_stdin(self):
        with mock.patch("content_bank.author.llm.subprocess.run",
                        return_value=self._fake_proc(stdout="COMPLETION")) as m:
            out = seam.llm("A PROMPT", Route("claude"))
        self.assertEqual(out, "COMPLETION")
        argv = m.call_args.args[0]
        self.assertEqual(argv[0], "claude")
        self.assertIn("-p", argv)
        self.assertIn("--model", argv)
        self.assertEqual(argv[argv.index("--model") + 1], "opus")  # strong default
        self.assertIn("--output-format", argv)
        self.assertIn("--disallowed-tools", argv)
        self.assertNotIn("--bare", argv)  # --bare breaks subscription auth
        self.assertEqual(m.call_args.kwargs.get("input"), "A PROMPT")

    def test_model_override_passthrough(self):
        with mock.patch("content_bank.author.llm.subprocess.run",
                        return_value=self._fake_proc(stdout="X")) as m:
            seam.llm("P", Route("claude", "sonnet", {"effort": "high"}))
        argv = m.call_args.args[0]
        self.assertEqual(argv[argv.index("--model") + 1], "sonnet")

    def test_nonzero_exit_raises_runtimeerror(self):
        with mock.patch("content_bank.author.llm.subprocess.run",
                        return_value=self._fake_proc(returncode=1, stderr="boom")):
            with self.assertRaises(RuntimeError):
                seam.llm("P", Route("claude"))

    def test_empty_output_raises_runtimeerror(self):
        with mock.patch("content_bank.author.llm.subprocess.run",
                        return_value=self._fake_proc(stdout="   ")):
            with self.assertRaises(RuntimeError):
                seam.llm("P", Route("claude"))


if __name__ == "__main__":
    unittest.main()
