import unittest
from content_bank.author import gates

GLOSS = [{"en_term": "justification", "zh_term": "称义",
          "sources": ["WSC.33"], "avoid": ["合理化"]}]


def _item(en, zh=None):
    text = {"en": en}
    if zh is not None:
        text["zh"] = zh
    return {"id": "G-1", "passage": "PHP.1.1-11", "text": text}


class TestGlossaryCheck(unittest.TestCase):
    def test_mandated_term_present_passes(self):
        it = _item("A question about justification.", "关于称义的问题。")
        self.assertEqual(gates.glossary_check([it], GLOSS), {})

    def test_missing_mandated_term_flags(self):
        it = _item("A question about justification.", "关于成义的问题。")
        self.assertIn("G-1", gates.glossary_check([it], GLOSS))

    def test_forbidden_rendering_flags(self):
        it = _item("A question about justification.", "关于合理化的问题。")
        self.assertIn("G-1", gates.glossary_check([it], GLOSS))

    def test_en_only_item_skipped(self):
        it = _item("A question about justification.")  # no zh yet
        self.assertEqual(gates.glossary_check([it], GLOSS), {})

    def test_term_absent_from_english_skipped(self):
        it = _item("A question about people and places.", "关于人物的问题。")
        self.assertEqual(gates.glossary_check([it], GLOSS), {})
