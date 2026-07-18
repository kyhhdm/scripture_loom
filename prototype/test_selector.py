"""Tests for the kit selector.

The central acceptance test: changing the member record changes the kit.
"""
import copy
import json
import pathlib
import sys
import unittest

import selector

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parent))          # repo root, for content_bank
from content_bank.lib import prototype_bank


def load():
    bank = prototype_bank.load_bank("MAT", lang="en")
    family = json.loads((HERE / "family.json").read_text())
    return bank, family


class TestPassageSelection(unittest.TestCase):
    def test_next_passage_follows_reading_sequence(self):
        bank, family = load()
        kit = selector.build_kit(bank, family)
        self.assertEqual(kit["passage"]["id"], "MAT-014")

    def test_after_studying_beatitudes_next_is_salt_and_light(self):
        bank, family = load()
        family["sessions"].append({"date": "2026-07-19", "passage": "MAT-014", "evidence": []})
        kit = selector.build_kit(bank, family)
        self.assertEqual(kit["passage"]["id"], "MAT-015")


class TestActivationStages(unittest.TestCase):
    def test_stages_from_history(self):
        bank, family = load()
        kit = selector.build_kit(bank, family)
        stages = {q["member"]: q["stage"] for q in kit["quests"]}
        # Grace has one unprompted question on record -> stage 2
        self.assertEqual(stages["grace"], 2)
        # Liberty has none -> stage 1
        self.assertEqual(stages["liberty"], 1)

    def test_more_unprompted_questions_advance_grace_to_write_your_own(self):
        """The acceptance test: change the record, the kit changes."""
        bank, family = load()
        extra = {
            "member": "grace", "dimension": "D6", "code": "Q", "quality": "✓",
            "prompted": False, "note": "Another unprompted question.",
        }
        family["sessions"][0]["evidence"].extend([copy.copy(extra), copy.copy(extra)])
        kit = selector.build_kit(bank, family)
        grace = next(q for q in kit["quests"] if q["member"] == "grace")
        self.assertEqual(grace["stage"], 3)
        self.assertIn("write your own", grace["text"].lower())

    def test_stage_4_omits_the_quest(self):
        bank, family = load()
        extra = {
            "member": "grace", "dimension": "D6", "code": "Q", "quality": "✓",
            "prompted": False, "note": "q",
        }
        family["sessions"][0]["evidence"].extend([copy.copy(extra) for _ in range(4)])
        kit = selector.build_kit(bank, family)
        grace = next(q for q in kit["quests"] if q["member"] == "grace")
        self.assertEqual(grace["stage"], 4)
        self.assertIsNone(grace["text"])

    def test_stage_1_gets_full_quest_stage_2_gets_category(self):
        bank, family = load()
        kit = selector.build_kit(bank, family)
        liberty = next(q for q in kit["quests"] if q["member"] == "liberty")
        grace = next(q for q in kit["quests"] if q["member"] == "grace")
        self.assertEqual(liberty["stage"], 1)
        self.assertIn("tally", liberty["text"].lower())  # full quest body
        self.assertIn("?", grace["text"])  # category is a direction, member writes the question


class TestReviewQuestions(unittest.TestCase):
    def test_review_targets_weak_dimensions(self):
        """Liberty marked △ on D2 and ? on D3 last session -> review hits those."""
        bank, family = load()
        kit = selector.build_kit(bank, family)
        dims = {q["dimension"] for q in kit["review_questions"]}
        self.assertIn("D2", dims)
        self.assertIn("D3", dims)

    def test_review_questions_come_from_studied_passages_only(self):
        bank, family = load()
        kit = selector.build_kit(bank, family)
        for q in kit["review_questions"]:
            self.assertEqual(q["passage"], "MAT-009")

    def test_at_most_three_review_questions(self):
        bank, family = load()
        kit = selector.build_kit(bank, family)
        self.assertLessEqual(len(kit["review_questions"]), 3)


class TestObservationTargets(unittest.TestCase):
    def test_at_most_three_targets(self):
        bank, family = load()
        kit = selector.build_kit(bank, family)
        self.assertLessEqual(len(kit["observation_targets"]), 3)

    def test_targets_include_libertys_weak_event_sequence(self):
        bank, family = load()
        kit = selector.build_kit(bank, family)
        pairs = {(t["member"], t["dimension"]) for t in kit["observation_targets"]}
        self.assertIn(("liberty", "D2"), pairs)

    def test_targets_never_name_the_leader(self):
        bank, family = load()
        kit = selector.build_kit(bank, family)
        self.assertNotIn("aquila", {t["member"] for t in kit["observation_targets"]})


class TestContentSelection(unittest.TestCase):
    def test_only_published_items_are_selected(self):
        bank, family = load()
        kit = selector.build_kit(bank, family)
        published = {i["id"] for i in bank["items"] if i["review_status"] == "published"}
        for item_id in kit["selected_item_ids"]:
            self.assertIn(item_id, published)

    def test_used_items_are_not_reselected_for_discussion(self):
        bank, family = load()
        kit1 = selector.build_kit(bank, family)
        chosen = kit1["discussion_questions"][0]["id"]
        family["used_item_ids"].append(chosen)
        kit2 = selector.build_kit(bank, family)
        self.assertNotIn(chosen, [q["id"] for q in kit2["discussion_questions"]])

    def test_quest_tier_matches_member(self):
        bank, family = load()
        items = {i["id"]: i for i in bank["items"]}
        kit = selector.build_kit(bank, family)
        tiers = {m["id"]: m["age_tier"] for m in family["members"]}
        for q in kit["quests"]:
            if q.get("item_id"):
                self.assertIn(items[q["item_id"]]["age_tier"], (tiers[q["member"]], "all"))


class TestPersonalizedLines(unittest.TestCase):
    def test_graces_starred_question_becomes_a_return_to_line(self):
        bank, family = load()
        kit = selector.build_kit(bank, family)
        lines = " ".join(kit["personalized_lines"])
        self.assertIn("Grace", lines)
        self.assertIn("tell the devil to leave", lines)

    def test_libertys_followup_becomes_a_review_line(self):
        bank, family = load()
        kit = selector.build_kit(bank, family)
        lines = " ".join(kit["personalized_lines"])
        self.assertIn("worship", lines)


if __name__ == "__main__":
    unittest.main()
