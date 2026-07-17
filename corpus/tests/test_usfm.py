import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import usfm

FIXTURE = Path(__file__).parent / "fixtures" / "sample.usfm"


class TestUsfm(unittest.TestCase):
    def setUp(self):
        self.book, self.chapters, self.headings = usfm.parse(
            FIXTURE.read_text(encoding="utf-8"))

    def test_book_code(self):
        self.assertEqual(self.book, "MAT")

    def test_verse_counts(self):
        self.assertEqual(set(self.chapters["4"]), {"23", "24", "25"})
        self.assertEqual(set(self.chapters["5"]), {"1", "2", "3", "13"})

    def test_multiline_verse_joined(self):
        self.assertIn("his disciples came unto him", self.chapters["5"]["1"])

    def test_char_markers_stripped(self):
        self.assertEqual(self.chapters["4"]["23"],
            "And Jesus went about all Galilee, teaching in their synagogues.")
        self.assertNotIn("\\w", self.chapters["5"]["3"])

    def test_footnotes_and_xrefs_stripped(self):
        self.assertEqual(self.chapters["4"]["24"],
            "And his fame went throughout all Syria.")
        self.assertEqual(self.chapters["5"]["13"], "Ye are the salt of the earth.")

    def test_headings_with_position(self):
        self.assertEqual(self.headings, [
            ("5", None, "The Beatitudes"),
            ("5", "3", "Salt and Light"),
        ])


if __name__ == "__main__":
    unittest.main()
