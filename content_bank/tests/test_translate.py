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

    def test_merges_category_zh(self):
        item = {"id": "PHP-001-D1-03", "passage": "PHP.1.1-11", "dimension": "D1",
                "type": "pre_reading_quest",
                "text": {"en": "Who is named?"},
                "category": {"en": "People & roles"}}
        resp = ('{"text": {"zh": "谁被提名？"}, '
                '"category": {"zh": "人物与角色"}, "terms": [], "uncertain": []}')
        with mock.patch.object(translate, "llm", return_value=resp):
            out = translate.translate_item(item, "PHP", glossary=[])
        self.assertEqual(out["item"]["category"]["zh"], "人物与角色")
        self.assertEqual(out["item"]["category"]["en"], "People & roles")  # kept
        self.assertNotIn("zh", item["category"])  # original not mutated

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


GOOD = ('{"text": {"zh": "「基督耶稣的仆人」保罗和提摩太。"}, "terms": [], "uncertain": []}')
BAD = ('{"text": {"zh": "「基督耶稣的门徒」保罗和提摩太。"}, "terms": [], "uncertain": []}')


class TestTranslateWithGates(unittest.TestCase):
    def _item(self):
        return {"id": "PHP-001-D1-01", "passage": "PHP.1.1-11", "dimension": "D1",
                "type": "question", "text": {"en": "servants of Christ Jesus?"}}

    def test_clean_translation_passes_gate(self):
        with mock.patch.object(translate, "llm", return_value=GOOD):
            out = translate.translate_with_gates(self._item(), "PHP", glossary=[])
        self.assertTrue(out["gate_ok"])
        self.assertEqual(out["gate_flags"], [])

    def test_bad_span_repaired_on_second_round(self):
        # first call returns a non-CUV 「…」 span, repair returns a clean one
        with mock.patch.object(translate, "llm", side_effect=[BAD, GOOD]):
            out = translate.translate_with_gates(self._item(), "PHP", glossary=[],
                                                 max_repair=2)
        self.assertTrue(out["gate_ok"])

    def test_unrepaired_bad_span_reported_not_raised(self):
        with mock.patch.object(translate, "llm", side_effect=[BAD, BAD, BAD]):
            out = translate.translate_with_gates(self._item(), "PHP", glossary=[],
                                                 max_repair=2)
        self.assertFalse(out["gate_ok"])
        self.assertTrue(out["gate_flags"])
