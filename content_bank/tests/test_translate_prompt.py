import unittest
from content_bank.author import build_translate_prompt as btp


class TestTranslatePrompt(unittest.TestCase):
    def _item(self):
        return {"id": "PHP-001-D1-01", "passage": "PHP.1.1-11", "dimension": "D1",
                "type": "question",
                "text": {"en": "Who calls themselves servants of Christ Jesus?"},
                "leader_reference": {"kind": "answer_key",
                                     "text": {"en": "Paul and Timothy (v.1)."},
                                     "verse": {"en": "Philippians 1:1"}}}

    def test_prompt_includes_cuv_bsb_glossary_and_rules(self):
        detected = [{"quote": "servants of Christ Jesus", "ref": "PHP.1.1-11"}]
        gloss = [{"en_term": "saints", "zh_term": "圣徒", "sources": ["CUV:PHP.1.1"]}]
        p = btp.build(self._item(), "PHP", detected=detected, glossary_entries=gloss)
        # CUV text for the passage is embedded (基督耶稣的仆人 is CUV PHP.1.1)
        self.assertIn("基督耶稣的仆人", p)
        # BSB text for the detected quote's ref is embedded
        self.assertIn("servants of Christ Jesus", p)
        # mandated glossary term present
        self.assertIn("圣徒", p)
        # the delimiter + fidelity rules are stated
        self.assertIn("「", p)
        # WCF-1 doctrinal anchor present
        self.assertIn("Holy Scripture", p)
        # structured-output keys named (category included for pre-reading items)
        for key in ('"text"', '"category"', '"terms"', '"uncertain"'):
            self.assertIn(key, p)

    def test_no_glossary_no_quotes_still_builds(self):
        p = btp.build(self._item(), "PHP", detected=[], glossary_entries=[])
        self.assertIn('"text"', p)

    def test_prompt_instructs_tag_preservation(self):
        p = btp.build(self._item(), "PHP", detected=[], glossary_entries=[])
        self.assertIn("<verse ref=", p)
        self.assertIn("<doctrine std=", p)

    def test_prompt_reserves_corner_brackets_for_scripture(self):
        # 「」 is the Scripture convention; ordinary quotes must use “ ”.
        p = btp.build(self._item(), "PHP", detected=[], glossary_entries=[])
        self.assertIn("“", p)          # the ordinary-quote mark is named
        self.assertIn("”", p)
        low = p.lower()
        self.assertTrue("reserve" in low and "scripture" in low)

    def test_prompt_instructs_nested_zh_form(self):
        # rules 2 & 8 must be reconciled: ZH Scripture is the tag AND 「…」 nested,
        # never a bare 「…」 without the <verse> tag.
        p = btp.build(self._item(), "PHP", detected=[], glossary_entries=[])
        self.assertIn('「…CUV…」</verse>', p)   # the nested-form example
        self.assertIn("drop the tag in favour of bare", p)
        # extent rule: words are always verbatim CUV; amount tracks the English,
        # decoupled so "verbatim" is not misread as "whole verse".
        self.assertIn("Match the CUV EXTENT to the English", p)
        self.assertIn("same AMOUNT as the English", p)
        self.assertIn('governs\n   the words, NOT the length', p)
