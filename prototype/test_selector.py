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


def kit_passage_dims(bank, passage_id):
    return selector.available_dimensions(bank, passage_id)


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
        self.assertIn("listen for", liberty["text"].lower())  # full quest body handed out
        self.assertIn("?", grace["text"])  # category is a direction, member writes the question


class TestReviewQuestions(unittest.TestCase):
    def test_review_targets_weak_dimensions(self):
        """Liberty's recent weak marks are on D2 (and D3) -> review prioritises them.

        The selector ranks review candidates weak-dimension-first; with the weakest
        dimension (D2) well-stocked it fills from there, so the guarantee we assert
        is that the review is drawn from the weak dimensions, led by the weakest."""
        bank, family = load()
        kit = selector.build_kit(bank, family)
        dims = {q["dimension"] for q in kit["review_questions"]}
        weak = set(selector.weak_dimensions(family))
        self.assertIn("D2", dims)                 # the weakest dimension is targeted
        self.assertTrue(dims <= weak)             # nothing outside the weak set

    def test_review_questions_come_from_studied_passages_only(self):
        bank, family = load()
        studied = {s["passage"] for s in family["sessions"]}
        kit = selector.build_kit(bank, family)
        for q in kit["review_questions"]:
            self.assertIn(q["passage"], studied)  # MAT-009 and MAT-013 are studied

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

    def test_no_target_on_dimension_absent_from_passage(self):
        """The Beatitudes (MAT-014, the fixture's next passage) publish no D1
        content, so no member may be given a D1 observation target there."""
        bank, family = load()
        self.assertEqual(kit_passage_dims(bank, "MAT-014") & {"D1"}, set())  # precondition
        kit = selector.build_kit(bank, family)
        self.assertEqual(kit["passage"]["id"], "MAT-014")
        target_dims = {t["dimension"] for t in kit["observation_targets"]}
        self.assertNotIn("D1", target_dims)


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
        # personalized_lines reflects the most recent session (MAT-013), where
        # Grace asked a starred question about Jesus sitting down to teach.
        bank, family = load()
        kit = selector.build_kit(bank, family)
        lines = " ".join(kit["personalized_lines"])
        self.assertIn("Grace", lines)
        self.assertIn("sit down to teach", lines)

    def test_libertys_followup_becomes_a_review_line(self):
        # Liberty's unresolved '?' from the most recent session surfaces as a
        # review line naming her.
        bank, family = load()
        kit = selector.build_kit(bank, family)
        lines = " ".join(kit["personalized_lines"])
        self.assertIn("Review with Liberty", lines)


class TestReadingSequence(unittest.TestCase):
    def test_reading_sequence_includes_mat013_before_beatitudes(self):
        fam = json.loads((HERE / "family.json").read_text())
        self.assertIn("MAT-013", fam["reading_sequence"])
        self.assertEqual(fam["reading_sequence"].index("MAT-013"),
                         fam["reading_sequence"].index("MAT-014") - 1)


SECTIONS = [
    {"id": "MAT-S1", "title": "Prologue: The Infancy",
     "first_pericope": "MAT-001", "last_pericope": "MAT-006", "marker": None},
    {"id": "MAT-S2", "title": "Book One: The Sermon on the Mount",
     "first_pericope": "MAT-007", "last_pericope": "MAT-033", "marker": "MAT.7.28"},
]


class TestArcRecap(unittest.TestCase):
    def test_recap_names_section_and_lists_studied_titles_in_order(self):
        bank, family = load()
        # Study the first two infancy pericopes; next_passage will be MAT-003.
        family["reading_sequence"] = [p["id"] for p in bank["pericopes"]]
        family["sessions"] = [
            {"date": "d", "passage": "MAT-001", "evidence": []},
            {"date": "d", "passage": "MAT-002", "evidence": []},
        ]
        recap = selector.arc_recap(SECTIONS, bank, family)
        self.assertEqual(recap["section"], "Prologue: The Infancy")
        self.assertEqual(recap["studied"],
                         ["The Genealogy of Jesus", "The Birth of Jesus"])
        self.assertEqual(recap["position"], "2 of 6")

    def test_recap_before_any_study_names_section_only(self):
        bank, family = load()
        family["reading_sequence"] = [p["id"] for p in bank["pericopes"]]
        family["sessions"] = []
        recap = selector.arc_recap(SECTIONS, bank, family)
        self.assertEqual(recap["section"], "Prologue: The Infancy")
        self.assertEqual(recap["studied"], [])


if __name__ == "__main__":
    unittest.main()
