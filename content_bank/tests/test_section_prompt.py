import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.author import (build_section_draft_prompt as bsd,
                                 build_section_brief_prompt as bsb)


class SectionDraftPromptSelfContainedTest(unittest.TestCase):
    def test_prompt_specifies_json_item_schema(self):
        text = bsd.build("PHP-S1", "PHP")
        # The item shapes must be in the prompt itself (previously only in the
        # workflow JS), so the standalone builder needs no external template.
        for needle in ('"type":"throughline"', '"type":"thread"',
                       "exactly one throughline", "JSON array"):
            self.assertIn(needle, text)

    def test_brief_is_embedded_when_supplied(self):
        text = bsd.build("PHP-S1", "PHP", brief="ARC SPINE: partnership in the gospel.")
        self.assertIn("ARC SPINE: partnership in the gospel.", text)
        self.assertIn("Section arc brief", text)


class SectionBriefPromptTest(unittest.TestCase):
    def test_brief_prompt_distills_the_arc_not_items(self):
        text = bsb.build("PHP-S1", "PHP")
        # A distillation prompt: asks for an arc brief, NOT a JSON item array.
        self.assertIn("SECTION ARC BRIEF", text)
        self.assertIn("Recurring motifs", text)
        self.assertNotIn("JSON array", text)

    def test_lists_the_span_pericopes(self):
        text = bsb.build("PHP-S1", "PHP")
        self.assertIn("stations of the arc", text)


if __name__ == "__main__":
    unittest.main()
