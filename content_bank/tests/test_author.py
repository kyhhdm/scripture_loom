import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.author import build_draft_prompt, review_checklist, dimensions, rubric


class TestBuildDraftPrompt(unittest.TestCase):
    def setUp(self):
        self.brief = ("**Passage's own emphasis.** Jesus pronounces blessing...\n"
                      "**Cross-references.** Ps 37:11 — the meek inherit.\n")
        self.prompt = build_draft_prompt.build("MAT-014", book="MAT", brief=self.brief)

    def test_foregrounds_passage_text(self):
        self.assertIn("MAT-014", self.prompt)
        self.assertIn("blessed", self.prompt.lower())          # passage present
        self.assertIn("subject", self.prompt.lower())          # foregrounded label

    def test_carries_the_brief(self):
        self.assertIn("pronounces blessing", self.prompt)      # brief injected

    def test_compact_wcf_guardrail_not_full_chapter(self):
        p = self.prompt.lower()
        self.assertIn("westminster", p)
        # The real leanness gate: the full WCF ch.1 (~977 words) is absent — a raw
        # lamppost dump would be 60k+ chars. The char bound is a loose sanity check
        # with headroom for guidance text (fixture brief is tiny; real packs ~8k).
        self.assertNotIn("1.10", self.prompt)                  # full ch.1 absent
        self.assertLess(len(self.prompt), 9000)                # pack stays lean, not a dump

    def test_states_rules_types_and_rubric(self):
        p = self.prompt.lower()
        self.assertIn("answerable", p)
        self.assertTrue("genuinely support" in p or "only the dimensions" in p)
        self.assertIn("observable behavior", p)
        self.assertIn("memory_verse", p)
        self.assertIn("pedagog", p)                            # rubric embedded

    def test_all_dimension_templates_present(self):
        for d in dimensions.TEMPLATES:
            self.assertIn(d, self.prompt)

    def test_missing_brief_raises(self):
        with self.assertRaises(FileNotFoundError):
            build_draft_prompt.build("MAT-999-nobrief", book="MAT", brief=None)


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


class TestBuildBriefPrompt(unittest.TestCase):
    def setUp(self):
        from content_bank.author import build_brief_prompt
        self.pack = build_brief_prompt.build("MAT-014", book="MAT")

    def test_includes_passage_and_full_wcf1(self):
        self.assertIn("blessed", self.pack.lower())    # passage text
        self.assertIn("1.1", self.pack)                # full WCF ch.1 sections

    def test_includes_commentary_and_crossrefs(self):
        p = self.pack.lower()
        self.assertIn("commentary", p)
        self.assertIn("cross-reference", p)

    def test_includes_confessional_hits(self):
        self.assertIn("WCF 19.6", self.pack)
        self.assertIn("WLC Q172", self.pack)

    def test_states_brief_shape_and_safeguard(self):
        p = self.pack.lower()
        self.assertIn("~250", self.pack)               # length target
        self.assertIn("emphasis", p)                   # passage-primary shape
        self.assertIn("proof-text", p)                 # safeguard

    def test_setup_pericope_notes_no_confessional(self):
        from content_bank.author import build_brief_prompt
        pack = build_brief_prompt.build("MAT-013", book="MAT")
        self.assertIn("No confessional", pack)


class TestReferenceCriteria(unittest.TestCase):
    def test_rubric_exposes_reference_criteria(self):
        text = rubric.reference_criteria()
        low = text.lower()
        self.assertIn("answer key", low)
        self.assertIn("keep", low)          # notes kept open
        self.assertIn("open", low)

    def test_checklist_has_reference_section(self):
        text = review_checklist.build()
        self.assertIn("Leader references", text)
        self.assertIn("keep", text.lower())


if __name__ == "__main__":
    unittest.main()
