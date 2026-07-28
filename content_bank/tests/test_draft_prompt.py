import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.author import build_draft_prompt as bdp


class DraftPromptRequestsReferencesTest(unittest.TestCase):
    def setUp(self):
        self.text = bdp.build("PHP-002", "PHP", brief="(stub brief)")

    def test_requests_inline_leader_references(self):
        for needle in ("leader_reference", "answer_key", "leader_note",
                       "provenance", "WCF-1"):
            self.assertIn(needle, self.text)

    def test_states_memory_verse_gets_no_reference(self):
        self.assertIn("NO leader_reference", self.text)

    def test_does_not_still_say_no_provenance(self):
        # The old pack said "No provenance; the reviewer stamps it" — gone now.
        self.assertNotIn("No provenance", self.text)


class TestDraftPromptTagging(unittest.TestCase):
    def test_tagging_block_present(self):
        # PHP-001 has a committed brief; build the real draft pack.
        p = bdp.build("PHP-001", book="PHP")
        self.assertIn("<verse ref=", p)
        self.assertIn("<doctrine std=", p)
        self.assertIn("PHP.1.6", p)  # canonical ref-format example


if __name__ == "__main__":
    unittest.main()
