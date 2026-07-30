"""Network-free coverage for Gemini model registration and credentials."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from llm_core import chatmodels, sync  # noqa: E402
from llm_core.chatmodels.LiteLLM import LiteLLM2Chat  # noqa: E402


class GeminiProviderTest(unittest.TestCase):
    def test_models_are_registered_with_paid_list_price_equivalents(self):
        models = {m["name"]: m for m in chatmodels.list_models()}
        self.assertEqual(models["gemini-3.6-flash"]["provider"], "gemini")
        self.assertEqual(models["gemini-3.6-flash"]["output_max_token"], 64000)
        self.assertEqual(models["gemini-3.5-flash-lite"]["provider"], "gemini")
        self.assertGreater(models["gemini-3.6-flash"]["output_price"], 0)

    def test_build_uses_gemini_prefix_key_and_no_deprecated_temperature(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-gemini-key"},
                             clear=False):
            model, error = chatmodels.build_chat("gemini-3.6-flash")
        self.assertEqual(error, "")
        self.assertEqual(model.provider, "gemini")
        self.assertEqual(model.modelId, "gemini/gemini-3.6-flash")
        self.assertEqual(model.api_key, "test-gemini-key")
        self.assertNotIn("temperature", model._build_completion_kwargs())

    def test_google_api_key_alias_is_accepted(self):
        with mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "test-google-key"},
                             clear=False), \
                mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            model = LiteLLM2Chat(modelId="gemini/gemini-3.5-flash-lite",
                                 provider="gemini")
        self.assertEqual(model.api_key, "test-google-key")

    def test_configuration_gate_recognizes_both_key_names(self):
        with mock.patch.object(sync.settings, "llm_api_key", None), \
                mock.patch.object(sync.settings, "llm_api_base", None), \
                mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(sync.llm_configured())
            os.environ["GEMINI_API_KEY"] = "gemini"
            self.assertTrue(sync.llm_configured())
            del os.environ["GEMINI_API_KEY"]
            os.environ["GOOGLE_API_KEY"] = "google"
            self.assertTrue(sync.llm_configured())

    def test_unrelated_provider_key_does_not_enable_gemini(self):
        with mock.patch.object(sync.settings, "llm_api_key", None), \
                mock.patch.object(sync.settings, "llm_api_base", None), \
                mock.patch.dict(os.environ, {"ARK_API_KEY": "ark"}, clear=True):
            self.assertTrue(sync.llm_configured("deepseek-v4-flash"))
            self.assertFalse(sync.llm_configured("gemini-3.6-flash"))


if __name__ == "__main__":
    unittest.main()
