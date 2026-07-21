import unittest
from unittest import mock
from content_bank.author import translate

ITEM = {"id": "PHP-001-D1-01", "passage": "PHP.1.1-11", "dimension": "D1",
        "type": "question", "review_status": "reviewed",
        "text": {"en": "Who are the servants of Christ Jesus?"},
        "leader_reference": {"kind": "answer_key",
                             "text": {"en": "Paul and Timothy."},
                             "verse": {"en": "Philippians 1:1"}}}

LLM_JSON = ('{"text": {"zh": "谁是「基督耶稣的仆人」？"},'
            ' "leader_reference": {"text": {"zh": "保罗和提摩太。"},'
            ' "verse": {"zh": "腓立比书 1:1"}},'
            ' "terms": [{"en": "saints", "zh": "圣徒"}],'
            ' "uncertain": []}')


class TestTranslateItem(unittest.TestCase):
    def test_merges_zh_preserves_en_and_structured(self):
        with mock.patch.object(translate, "llm", return_value=LLM_JSON):
            out = translate.translate_item(ITEM, "PHP", glossary=[])
        item = out["item"]
        self.assertEqual(item["text"]["zh"], "谁是「基督耶稣的仆人」？")
        self.assertEqual(item["text"]["en"], ITEM["text"]["en"])  # unchanged
        self.assertEqual(item["leader_reference"]["text"]["zh"], "保罗和提摩太。")
        self.assertEqual(item["id"], ITEM["id"])                  # structured intact
        self.assertEqual(item["review_status"], "reviewed")
        self.assertEqual(out["terms"], [{"en": "saints", "zh": "圣徒"}])
        # original item object not mutated
        self.assertNotIn("zh", ITEM["text"])

    def test_applicable_glossary_filters_by_english(self):
        gloss = [{"en_term": "saints", "zh_term": "圣徒", "sources": ["x"]},
                 {"en_term": "predestination", "zh_term": "预定", "sources": ["y"]}]
        got = translate._applicable_glossary(ITEM, gloss)
        self.assertEqual([e["en_term"] for e in got], [])  # neither term in EN text

    def test_applicable_glossary_matches_present_term(self):
        item = {"id": "x", "text": {"en": "A question about justification."}}
        gloss = [{"en_term": "justification", "zh_term": "称义", "sources": ["z"]}]
        got = translate._applicable_glossary(item, gloss)
        self.assertEqual([e["en_term"] for e in got], ["justification"])
