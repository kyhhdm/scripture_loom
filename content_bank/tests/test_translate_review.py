import unittest
from unittest import mock
from content_bank.author import translate

ITEM = {"id": "x", "text": {"en": "Scripture is infallible.",
                            "zh": "圣经是无谬的。"}}


class TestBackTranslateReview(unittest.TestCase):
    def test_parses_drift_verdict(self):
        with mock.patch.object(translate, "llm",
                               return_value='{"drift": true, "notes": "softened"}'):
            v = translate.back_translate_review(ITEM)
        self.assertTrue(v["drift"])
        self.assertIn("soften", v["notes"])

    def test_no_zh_short_circuits(self):
        v = translate.back_translate_review({"id": "y", "text": {"en": "hi"}})
        self.assertFalse(v["drift"])
