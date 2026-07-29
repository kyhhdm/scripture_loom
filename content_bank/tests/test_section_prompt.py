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

    def test_prompt_inlines_leader_reference_for_questions(self):
        text = bsd.build("PHP-S1", "PHP")
        # The leader_reference shape must be in a JSON example (not just prose), so
        # the model actually emits answer keys / leader notes on arc questions.
        self.assertIn('"leader_reference":{"kind":"answer_key"', text)
        self.assertIn('"leader_reference":{"kind":"leader_note"', text)

    def test_brief_is_embedded_when_supplied(self):
        text = bsd.build("PHP-S1", "PHP", brief="ARC SPINE: partnership in the gospel.")
        self.assertIn("ARC SPINE: partnership in the gospel.", text)
        self.assertIn("Section arc brief", text)

    def test_prompt_instructs_citation_tagging(self):
        # Section items (esp. quote-dense threads) are gated by citation_check, so
        # the section draft prompt must tell the model to emit <verse>/<doctrine>
        # tags — otherwise the gate rejects untagged quotes it never asked for.
        text = bsd.build("PHP-S1", "PHP")
        self.assertIn("<verse ref=", text)
        self.assertIn("<doctrine std=", text)
        self.assertIn("PHP.1.6", text)          # canonical ref example
        self.assertIn("thread", text.lower())   # the per-quote thread guidance

    def test_throughline_and_thread_carry_leader_reference_in_json(self):
        text = bsd.build("PHP-S1", "PHP")
        # The throughline JSON example must now include a leader_note reveal...
        self.assertIn('"type":"throughline"', text)
        tl = text.split('"type":"throughline"', 1)[1].split("}\n", 1)[0]
        self.assertIn("leader_reference", tl)
        self.assertIn("leader_note", tl)
        # ...and the old "need NO leader_reference" instruction must be gone.
        self.assertNotIn("need NO leader_reference", text)

    def test_prompt_frames_throughline_and_thread_as_questions(self):
        text = bsd.build("PHP-S1", "PHP").lower()
        # Discovery framing: the stem is a question leading to a reveal.
        self.assertIn("discovery question", text)
        self.assertIn("reveal", text)

    def test_reveal_kind_rule_stated(self):
        text = bsd.build("PHP-S1", "PHP")
        # D3 -> answer_key, D7 -> leader_note must be spelled out for section items.
        self.assertIn("D3", text)
        self.assertIn("answer_key", text)
        self.assertIn("leader_note", text)


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
