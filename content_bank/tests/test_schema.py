import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.lib import schema


def valid_item(**over):
    item = {
        "id": "mt5a-q-blessed",
        "passage": "MAT-014",
        "dimension": "D7",
        "type": "question",
        "age_tier": "youth",
        "difficulty": 2,
        "review_status": "published",
        "text": {"en": "Who does Jesus call blessed?"},
        "provenance": {"drafted_by": "hand", "reviewed_by": "kyhhdm",
                       "reviewed_date": "2026-07-18", "guardrail": "WCF-1"},
        "version": 1,
    }
    item.update(over)
    return item


class TestValidateItem(unittest.TestCase):
    def test_valid_item_has_no_errors(self):
        self.assertEqual(schema.validate_item(valid_item()), [])

    def test_bad_dimension_rejected(self):
        errs = schema.validate_item(valid_item(dimension="D9"))
        self.assertTrue(any("dimension" in e for e in errs))

    def test_bad_type_rejected(self):
        self.assertTrue(schema.validate_item(valid_item(type="poem")))

    def test_bad_age_tier_rejected(self):
        self.assertTrue(schema.validate_item(valid_item(age_tier="toddler")))

    def test_difficulty_out_of_range_rejected(self):
        self.assertTrue(schema.validate_item(valid_item(difficulty=4)))

    def test_text_must_have_a_language(self):
        self.assertTrue(schema.validate_item(valid_item(text={})))

    def test_text_language_must_be_non_empty(self):
        self.assertTrue(schema.validate_item(valid_item(text={"en": "  "})))

    def test_unknown_language_key_rejected(self):
        self.assertTrue(schema.validate_item(valid_item(text={"fr": "x"})))

    def test_category_only_allowed_on_quests(self):
        errs = schema.validate_item(valid_item(category={"en": "x"}))
        self.assertTrue(any("category" in e for e in errs))

    def test_category_allowed_on_pre_reading_quest(self):
        item = valid_item(type="pre_reading_quest", category={"en": "Listen for a repeat."})
        self.assertEqual(schema.validate_item(item), [])

    def test_draft_needs_no_provenance(self):
        item = valid_item(review_status="draft")
        del item["provenance"]
        self.assertEqual(schema.validate_item(item), [])

    def test_published_requires_review_provenance(self):
        item = valid_item()
        del item["provenance"]
        self.assertTrue(schema.validate_item(item))

    def test_published_requires_wcf_guardrail(self):
        item = valid_item()
        item["provenance"]["guardrail"] = "none"
        self.assertTrue(schema.validate_item(item))

    def test_missing_required_field_rejected(self):
        item = valid_item()
        del item["dimension"]
        self.assertTrue(schema.validate_item(item))


if __name__ == "__main__":
    unittest.main()
