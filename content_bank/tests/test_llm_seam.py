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
from content_bank.author.telemetry import LLMResult  # noqa: E402


class LlmCoreBackendTest(unittest.TestCase):
    def test_llm_core_result_carries_local_estimate_usage(self):
        def fake_result(system, user, caller="", model=None):
            return ("BODY", {"model": "deepseek-v4-flash", "tokens_in_total": 100,
                             "tokens_out_total": 40, "cost": 0.001})

        with mock.patch("llm_core.run_sync_llm_result", fake_result):
            r = seam.llm("hi", Route("llm_core", "deepseek-v4-flash"))
        self.assertIsInstance(r, LLMResult)
        self.assertEqual(r.text, "BODY")
        self.assertEqual(r.usage.input, 100)
        self.assertEqual(r.usage.output, 40)
        self.assertIsNone(r.usage.cache_read)
        self.assertEqual(r.usage_source, "local_estimate")
        self.assertEqual(r.cost_estimate, 0.001)
        self.assertEqual(r.actual_model, "deepseek-v4-flash")

    def test_llm_text_returns_text_only(self):
        with mock.patch("llm_core.run_sync_llm_result",
                        return_value=("HI", {"model": "m"})):
            self.assertEqual(seam.llm_text("p", Route("llm_core")), "HI")

    def test_llm_core_passes_model(self):
        captured = {}

        def fake_result(system, user, caller="", model=None):
            captured["model"] = model
            return ("x", {"model": model})

        with mock.patch("llm_core.run_sync_llm_result", fake_result):
            seam.llm("P", Route("llm_core", "deepseek-v4-pro"))
        self.assertEqual(captured["model"], "deepseek-v4-pro")


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
    def _fake_proc(self, returncode=0, stdout="", stderr=""):
        p = mock.Mock()
        p.returncode = returncode
        p.stdout = stdout
        p.stderr = stderr
        return p

    def _json_proc(self, result="OUT", **usage_extra):
        import json
        payload = {"result": result, "stop_reason": "end_turn", "model": "opus",
                   "usage": {"input_tokens": 8, "output_tokens": 9,
                             "cache_creation_input_tokens": 2,
                             "cache_read_input_tokens": 3, **usage_extra}}
        return self._fake_proc(stdout=json.dumps(payload))

    def test_route_builds_json_argv_and_passes_prompt_on_stdin(self):
        with mock.patch("content_bank.author.llm.subprocess.run",
                        return_value=self._json_proc(result="COMPLETION")) as m:
            r = seam.llm("A PROMPT", Route("claude"))
        self.assertEqual(r.text, "COMPLETION")
        argv = m.call_args.args[0]
        self.assertEqual(argv[0], "claude")
        self.assertIn("-p", argv)
        self.assertIn("--model", argv)
        self.assertEqual(argv[argv.index("--model") + 1], "opus")  # strong default
        self.assertEqual(argv[argv.index("--output-format") + 1], "json")
        self.assertIn("--disallowed-tools", argv)
        self.assertNotIn("--bare", argv)  # --bare breaks subscription auth
        self.assertEqual(m.call_args.kwargs.get("input"), "A PROMPT")

    def test_json_result_carries_provider_usage(self):
        with mock.patch("content_bank.author.llm.subprocess.run",
                        return_value=self._json_proc(result="TEXT")):
            r = seam.llm("hi", Route("claude", "opus"))
        self.assertEqual(r.usage.input, 8)
        self.assertEqual(r.usage.output, 9)
        self.assertEqual(r.usage.cache_creation, 2)
        self.assertEqual(r.usage.cache_read, 3)
        self.assertEqual(r.usage_source, "provider")
        self.assertEqual(r.stop_reason, "end_turn")
        self.assertEqual(r.actual_model, "opus")

    def test_model_override_passthrough(self):
        with mock.patch("content_bank.author.llm.subprocess.run",
                        return_value=self._json_proc(result="X")) as m:
            seam.llm("P", Route("claude", "sonnet", {"effort": "high"}))
        argv = m.call_args.args[0]
        self.assertEqual(argv[argv.index("--model") + 1], "sonnet")

    def test_nonzero_exit_raises_runtimeerror(self):
        with mock.patch("content_bank.author.llm.subprocess.run",
                        return_value=self._fake_proc(returncode=1, stderr="boom")):
            with self.assertRaises(RuntimeError):
                seam.llm("P", Route("claude"))

    def test_empty_result_raises_runtimeerror(self):
        with mock.patch("content_bank.author.llm.subprocess.run",
                        return_value=self._json_proc(result="   ")):
            with self.assertRaises(RuntimeError):
                seam.llm("P", Route("claude"))

    def test_non_json_output_raises_runtimeerror(self):
        with mock.patch("content_bank.author.llm.subprocess.run",
                        return_value=self._fake_proc(stdout="not json at all")):
            with self.assertRaises(RuntimeError):
                seam.llm("P", Route("claude"))


if __name__ == "__main__":
    unittest.main()
