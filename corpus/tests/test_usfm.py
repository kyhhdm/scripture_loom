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

    def test_footnote_wrapped_across_lines_stripped(self):
        text = (
            "\\id MAT eng-test\n"
            "\\c 1\n"
            "\\p\n"
            "\\v 1 In the beginning\\f + \\fr 1:1 \\ft A long footnote that\n"
            "wraps onto the next physical line.\\f* was the Word.\n"
        )
        _, chapters, _ = usfm.parse(text)
        verse = chapters["1"]["1"]
        self.assertNotIn("footnote", verse)
        self.assertNotIn("\\", verse)
        self.assertIn("was the Word.", verse)


if __name__ == "__main__":
    unittest.main()
