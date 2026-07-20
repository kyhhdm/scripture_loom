import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.author import build_section_brief_prompt as bsp


class SectionPromptSelfContainedTest(unittest.TestCase):
    def test_prompt_specifies_json_item_schema(self):
        text = bsp.build("PHP-S1", "PHP")
        # The item shapes must be in the prompt itself (previously only in the
        # workflow JS), so the standalone builder needs no external template.
        for needle in ('"type":"throughline"', '"type":"thread"',
                       "exactly one throughline", "JSON array"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
