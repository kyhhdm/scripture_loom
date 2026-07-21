import unittest
from content_bank.author import gates


class TestLangAwareQuoteCheck(unittest.TestCase):
    def _item(self, en=None, zh=None):
        text = {}
        if en is not None:
            text["en"] = en
        if zh is not None:
            text["zh"] = zh
        return {"id": "T-1", "passage": "PHP.1.1-11", "text": text}

    def test_zh_verbatim_cuv_span_passes(self):
        # CUV PHP.1.1 contains 基督耶稣的仆人.
        it = self._item(zh="他们是「基督耶稣的仆人」。")
        self.assertNotIn("T-1", gates.quote_check("PHP", [it]))

    def test_zh_non_cuv_span_fails(self):
        it = self._item(zh="他们是「基督耶稣的好朋友」。")
        self.assertIn("T-1", gates.quote_check("PHP", [it]))

    def test_zh_span_not_checked_against_bsb(self):
        # A real CUV span must not be flagged just because it isn't in BSB.
        it = self._item(zh="「基督耶稣的仆人」")
        self.assertNotIn("T-1", gates.quote_check("PHP", [it]))

    def test_en_double_quote_still_works(self):
        good = self._item(en='He calls them "servants of Christ Jesus" here.')
        bad = self._item(en='He calls them "friends of Rome forever" here.')
        self.assertNotIn("T-1", gates.quote_check("PHP", [good]))
        self.assertIn("T-1", gates.quote_check("PHP", [bad]))

    def test_en_single_quote_detected_apostrophe_ignored(self):
        # Single-quoted BSB phrase should be checked; Paul's apostrophe must not
        # create a spurious span.
        bad = self._item(en="They are 'friends of Rome forever' in Paul's words.")
        self.assertIn("T-1", gates.quote_check("PHP", [bad]))


class TestCuvQuoteCheck(unittest.TestCase):
    def _item(self, zh):
        return {"id": "Z-1", "passage": "PHP.1.1-11", "text": {"zh": zh}}

    def test_verbatim_cuv_passes(self):
        self.assertEqual(gates.cuv_quote_check([self._item("「基督耶稣的仆人」")]), {})

    def test_altered_cuv_fails(self):
        self.assertIn("Z-1", gates.cuv_quote_check([self._item("「基督耶稣的门徒」")]))

    def test_ignores_en_only_item(self):
        it = {"id": "Z-2", "passage": "PHP.1.1-11",
              "text": {"en": '"nonexistent phrase here now"'}}
        self.assertEqual(gates.cuv_quote_check([it]), {})


class TestNormStripsAllQuoteGlyphs(unittest.TestCase):
    def test_norm_strips_straight_and_curly_quotes(self):
        result = gates._norm("“”‘’\"' abc")
        for glyph in ['"', "'", "“", "”", "‘", "’"]:
            self.assertNotIn(glyph, result)
        self.assertEqual(result, "abc")

    def test_en_span_straddling_curly_quote_passes(self):
        # 1SA.31.4 BSB: Saul said to his armor-bearer,
        # “Draw your sword and run it through me...”
        # The span below straddles the opening curly double-quote marker
        # that introduces Saul's command; a buggy _norm that fails to
        # strip “/” would leave it in the haystack and the
        # normalized span would not match, falsely flagging a verbatim quote.
        it = {
            "id": "N-1",
            "passage": "1SA.31.4",
            "text": {"en": 'Saul told his armor-bearer, '
                            '"armor-bearer, Draw your sword and run it '
                            'through me" in his final desperation.'},
        }
        self.assertEqual(gates.quote_check("1SA", [it]), {})
