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

    def test_en_single_quotes_not_treated_as_quotes(self):
        # Deliberate decision: single quotes are used for fill-in-the-blank
        # drills and event-ordering lists, and false-flagged that legitimate
        # content. Single-quoted spans are no longer treated as quotes at all;
        # only double quotes (straight or curly) trigger the check. An
        # apostrophe (e.g. Paul's) must not create a spurious span either.
        single_quoted = self._item(en="They are 'friends of Rome forever' in Paul's words.")
        double_quoted = self._item(en='He calls them "friends of Rome forever" in Paul\'s words.')
        self.assertNotIn("T-1", gates.quote_check("PHP", [single_quoted]))
        self.assertIn("T-1", gates.quote_check("PHP", [double_quoted]))


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


class TestCuvQuoteOverlapScoped(unittest.TestCase):
    """cuv_quote_check only checks 「」 spans that OVERLAP a declared ref (the item's
    passage/section + its <verse> refs). 「」 is the Scripture convention; ordinary
    quotes (activity examples, answer options) share no run with the cited passage
    and must not be flagged."""

    def _item(self, zh, passage="PHP.1.1-11"):
        return {"id": "Z-1", "passage": passage, "text": {"zh": zh}}

    def test_ordinary_zh_quote_not_flagged(self):
        # An ordinary 「」 quote with no overlap with the cited passage (Philippians)
        # must NOT be flagged as a bad CUV quote.
        it = self._item("请做这个活动：「进门时把鞋子放到鞋架上」。")
        self.assertEqual(gates.cuv_quote_check([it]), {})

    def test_answer_option_quote_not_flagged(self):
        it = self._item("选项：「已回答」或「未回答」。")
        self.assertEqual(gates.cuv_quote_check([it]), {})

    def test_verbatim_cuv_from_passage_passes(self):
        it = self._item("「基督耶稣的仆人」")   # verbatim CUV of PHP.1.1
        self.assertEqual(gates.cuv_quote_check([it]), {})

    def test_misquote_of_cited_passage_flagged(self):
        # Overlaps PHP.1.1 (基督耶稣的…) but not verbatim -> a real mis-quote, flagged.
        it = self._item("「基督耶稣的门徒」")
        self.assertIn("Z-1", gates.cuv_quote_check([it]))

    def test_double_quotes_not_treated_as_scripture(self):
        # Ordinary quotes use “ ”; only 「」 is the Scripture convention and checked.
        it = self._item("他说“这不是经文”。")
        self.assertEqual(gates.cuv_quote_check([it]), {})

    def test_wrong_nested_tag_in_brackets_not_double_flagged(self):
        # Model wrongly wrapped the tag: 「<verse>…</verse>」 (brackets outside).
        # citation_check validates the tag; cuv_quote_check must strip the markup
        # and see the verbatim CUV text, not flag the angle-bracket noise.
        it = self._item('约拿「<verse ref="PHP.1.1">基督耶稣的仆人</verse>」。')
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
