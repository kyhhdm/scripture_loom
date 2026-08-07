import unittest

from content_bank.author import build_group_prompt as bgp


class TestGroupPrompt(unittest.TestCase):
    def test_brief_envelope_names_each_unit_and_envelope(self):
        ids = ["PHP-S1", "PHP-001"]
        text = bgp.brief_envelope(ids, "PHP")
        for u in ids:
            self.assertIn(u, text)
        self.assertIn('"units"', text)
        self.assertIn("GROUP BRIEF BATCH", text)

    def test_draft_envelope_embeds_briefs(self):
        ids = ["PHP-S1", "PHP-001"]
        briefs = {"PHP-S1": "ARC-BRIEF-MARKER", "PHP-001": "PERI-BRIEF-MARKER"}
        text = bgp.draft_envelope(ids, "PHP", briefs)
        self.assertIn("ARC-BRIEF-MARKER", text)
        self.assertIn("PERI-BRIEF-MARKER", text)
        self.assertIn('"units"', text)

    def test_unit_kind(self):
        self.assertEqual(bgp._unit_kind("PHP-S2"), "section")
        self.assertEqual(bgp._unit_kind("PHP-001"), "pericope")


if __name__ == "__main__":
    unittest.main()
