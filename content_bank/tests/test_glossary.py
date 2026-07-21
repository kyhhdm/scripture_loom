import unittest
from content_bank.author import glossary


class TestGlossary(unittest.TestCase):
    def test_loads_and_validates(self):
        entries = glossary.load_glossary()
        self.assertTrue(entries)
        self.assertEqual(glossary.validate_glossary(entries), [])

    def test_entries_have_required_fields_and_a_source(self):
        for e in glossary.load_glossary():
            self.assertTrue(e.get("en_term"))
            self.assertTrue(e.get("zh_term"))
            self.assertTrue(e.get("sources"), f"{e['en_term']} needs a source")

    def test_validate_flags_missing_source(self):
        bad = [{"en_term": "grace", "zh_term": "恩典", "sources": []}]
        self.assertTrue(glossary.validate_glossary(bad))

    def test_known_terms_present(self):
        by_en = {e["en_term"]: e for e in glossary.load_glossary()}
        self.assertEqual(by_en["justification"]["zh_term"], "称义")
        self.assertEqual(by_en["saints"]["zh_term"], "圣徒")
