import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.author import build_draft_prompt, review_checklist, dimensions


class TestBuildDraftPrompt(unittest.TestCase):
    def setUp(self):
        self.prompt = build_draft_prompt.build("MAT-014", book="MAT")

    def test_includes_passage_reference_and_text(self):
        self.assertIn("MAT-014", self.prompt)
        self.assertIn("Beatitudes", self.prompt)
        self.assertIn("blessed", self.prompt.lower())  # passage text present

    def test_includes_westminster_guardrail(self):
        self.assertIn("Westminster", self.prompt)
        self.assertIn("1.1", self.prompt)  # WCF chapter 1 sections

    def test_includes_all_dimension_templates(self):
        for d in dimensions.TEMPLATES:
            self.assertIn(d, self.prompt)

    def test_includes_schema_vocabularies(self):
        self.assertIn("pre_reading_quest", self.prompt)  # a type
        self.assertIn("review_status", self.prompt)

    def test_dimension_templates_match_schema_vocab(self):
        from content_bank.lib import schema
        self.assertEqual(set(dimensions.TEMPLATES), schema.DIMENSIONS)


class TestReviewChecklist(unittest.TestCase):
    def test_checklist_covers_all_seven_rubric_axes(self):
        text = review_checklist.build().lower()
        for token in ("westminster", "answerab", "judgment", "age",
                      "dimension", "worship", "pedagog"):
            self.assertIn(token, text)

    def test_checklist_still_takes_guardrail(self):
        self.assertIn("WCF-1", review_checklist.build(guardrail="WCF-1"))


class TestRubric(unittest.TestCase):
    def test_axes_are_seven_ordered_titles(self):
        from content_bank.author import rubric
        self.assertEqual(len(rubric.AXES), 7)
        self.assertEqual(rubric.AXES[0].lower()[:11], "confessiona")

    def test_build_names_every_axis_and_key_rules(self):
        from content_bank.author import rubric
        text = rubric.build().lower()
        for token in ("wcf-1", "answerable", "judgment", "age", "dimension",
                      "worship", "pedagog"):
            self.assertIn(token, text)


class TestDimensions(unittest.TestCase):
    def test_keys_still_match_schema(self):
        from content_bank.lib import schema
        self.assertEqual(set(dimensions.TEMPLATES), schema.DIMENSIONS)

    def test_guidance_is_expanded_not_one_liners(self):
        for d, text in dimensions.TEMPLATES.items():
            self.assertGreater(len(text), 60, f"{d} guidance too thin")


if __name__ == "__main__":
    unittest.main()
