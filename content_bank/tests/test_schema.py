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
    def _ref(self, **over):
        ref = {
            "kind": "answer_key",
            "text": {"en": "The Spirit led Jesus; the devil tempted him."},
            "provenance": {"reviewed_by": "claude-adversarial",
                           "reviewed_date": "2026-07-19", "guardrail": "WCF-1"},
        }
        ref.update(over)
        return ref

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

    def test_valid_answer_key_reference(self):
        item = valid_item(dimension="D1", leader_reference=self._ref())
        self.assertEqual(schema.validate_item(item), [])

    def test_valid_leader_note_reference(self):
        note = self._ref(kind="leader_note",
                         text={"en": "Point where the text leads; keep it open."})
        item = valid_item(dimension="D7", leader_reference=note)
        self.assertEqual(schema.validate_item(item), [])

    def test_answer_key_rejected_on_open_dimension(self):
        item = valid_item(dimension="D7", leader_reference=self._ref())
        self.assertTrue(any("answer_key" in e for e in schema.validate_item(item)))

    def test_leader_note_rejected_on_closed_dimension(self):
        note = self._ref(kind="leader_note")
        item = valid_item(dimension="D2", leader_reference=note)
        self.assertTrue(any("leader_note" in e for e in schema.validate_item(item)))

    def test_bad_reference_kind_rejected(self):
        item = valid_item(dimension="D1", leader_reference=self._ref(kind="hint"))
        self.assertTrue(any("kind" in e for e in schema.validate_item(item)))

    def test_verse_rejected_on_leader_note(self):
        note = self._ref(kind="leader_note", verse={"en": "Matthew 5:7"})
        item = valid_item(dimension="D7", leader_reference=note)
        self.assertTrue(any("verse" in e for e in schema.validate_item(item)))

    def test_verse_allowed_on_answer_key(self):
        item = valid_item(dimension="D1",
                          leader_reference=self._ref(verse={"en": "Matthew 4:1"}))
        self.assertEqual(schema.validate_item(item), [])

    def test_reference_rejected_on_memory_verse(self):
        item = valid_item(type="memory_verse", dimension="D4",
                          leader_reference=self._ref(verse={"en": "Matthew 4:4"}))
        self.assertTrue(any("memory_verse" in e for e in schema.validate_item(item)))

    def test_reference_provenance_required(self):
        item = valid_item(dimension="D1",
                          leader_reference=self._ref(provenance={}))
        errs = schema.validate_item(item)
        self.assertTrue(any("leader_reference.provenance" in e for e in errs))

    def test_reference_text_must_be_lang_map(self):
        item = valid_item(dimension="D1", leader_reference=self._ref(text={}))
        self.assertTrue(any("leader_reference.text" in e for e in schema.validate_item(item)))

    def test_non_dict_reference_rejected(self):
        item = valid_item(dimension="D1", leader_reference="oops")
        errs = schema.validate_item(item)
        self.assertTrue(any("leader_reference: must be an object" in e for e in errs))

    def test_reference_wrong_guardrail_rejected(self):
        bad = self._ref(provenance={"reviewed_by": "claude-adversarial",
                                    "reviewed_date": "2026-07-19",
                                    "guardrail": "WCF-25"})
        item = valid_item(dimension="D1", leader_reference=bad)
        errs = schema.validate_item(item)
        self.assertTrue(any("leader_reference.provenance.guardrail" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
