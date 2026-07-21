import unittest
from content_bank.author import glossary_coverage as gc

LEXICON = ["justification", "propitiation", "covenant of grace"]
GLOSS = [{"en_term": "justification", "zh_term": "称义", "sources": ["WSC.33"]}]


def _item(en):
    return {"id": "C-1", "passage": "PHP.1.1-11", "text": {"en": en}}


class TestCoverageReport(unittest.TestCase):
    def test_flags_uncovered_term_present_in_content(self):
        items = [_item("A note on justification and propitiation.")]
        rep = gc.coverage_report(items, glossary=GLOSS, lexicon=LEXICON)
        self.assertIn("justification", rep["covered"])
        self.assertIn("propitiation", rep["uncovered"])
        self.assertNotIn("covenant of grace", rep["uncovered"])  # absent from text

    def test_multiword_term_matched(self):
        items = [_item("This is the covenant of grace in view.")]
        rep = gc.coverage_report(items, glossary=GLOSS, lexicon=LEXICON)
        self.assertIn("covenant of grace", rep["uncovered"])

    def test_defaults_load(self):
        rep = gc.coverage_report([_item("nothing theological here")])
        self.assertEqual(rep["covered"], [])
        self.assertEqual(rep["uncovered"], [])
