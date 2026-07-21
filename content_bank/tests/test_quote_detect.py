import unittest
from content_bank.author import quote_detect


def _item(text_en=None, lr_text_en=None, passage="PHP.1.1-11"):
    it = {"id": "T-1", "passage": passage,
          "text": {"en": text_en or ""}}
    if lr_text_en is not None:
        it["leader_reference"] = {"kind": "answer_key",
                                  "text": {"en": lr_text_en}}
    return it


class TestDetectQuotes(unittest.TestCase):
    def test_detects_verbatim_bsb_span_without_quote_marks(self):
        # BSB PHP.1.1 contains "servants of Christ Jesus" — no quote marks used.
        it = _item(lr_text_en="They are the servants of Christ Jesus by title.")
        hits = quote_detect.detect_quotes(it, "PHP")
        quotes = [h["quote"].lower() for h in hits]
        self.assertTrue(any("servants of christ jesus" in q for q in quotes))
        self.assertTrue(all(h["ref"] for h in hits))

    def test_ignores_short_coincidental_runs(self):
        it = _item(text_en="Who is this and that here?")
        self.assertEqual(quote_detect.detect_quotes(it, "PHP"), [])

    def test_empty_when_no_passage(self):
        it = {"id": "T-2", "text": {"en": "servants of Christ Jesus"}}
        self.assertEqual(quote_detect.detect_quotes(it, "PHP"), [])
