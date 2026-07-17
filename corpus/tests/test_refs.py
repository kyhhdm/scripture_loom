import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import refs


class TestParse(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(refs.parse("MAT.5.1"), ("MAT", 5, 1))

    def test_numbered_book(self):
        self.assertEqual(refs.parse("1CO.13.4"), ("1CO", 13, 4))

    def test_unknown_book_raises(self):
        with self.assertRaises(ValueError):
            refs.parse("XXX.1.1")

    def test_malformed_raises(self):
        for bad in ("MAT.5", "MAT", "MAT.5.1.2", "mat.5.1", "MAT.0.1"):
            with self.assertRaises(ValueError):
                refs.parse(bad)


class TestParseRange(unittest.TestCase):
    def test_same_chapter_short_form(self):
        self.assertEqual(refs.parse_range("MAT.5.1-12"),
                         (("MAT", 5, 1), ("MAT", 5, 12)))

    def test_cross_chapter_full_form(self):
        self.assertEqual(refs.parse_range("MAT.5.1-MAT.6.4"),
                         (("MAT", 5, 1), ("MAT", 6, 4)))

    def test_single_ref_is_unit_range(self):
        self.assertEqual(refs.parse_range("MAT.5.1"),
                         (("MAT", 5, 1), ("MAT", 5, 1)))

    def test_cross_book_raises(self):
        with self.assertRaises(ValueError):
            refs.parse_range("MAT.28.20-MRK.1.1")

    def test_backwards_raises(self):
        with self.assertRaises(ValueError):
            refs.parse_range("MAT.5.12-1")


class TestFmtAndInRange(unittest.TestCase):
    def test_fmt_roundtrip(self):
        self.assertEqual(refs.fmt(*refs.parse("PSA.119.105")), "PSA.119.105")

    def test_in_range(self):
        rng = refs.parse_range("MAT.5.1-MAT.6.4")
        self.assertTrue(refs.in_range(("MAT", 5, 7), rng))
        self.assertTrue(refs.in_range(("MAT", 6, 4), rng))
        self.assertFalse(refs.in_range(("MAT", 6, 5), rng))
        self.assertFalse(refs.in_range(("MRK", 5, 2), rng))


if __name__ == "__main__":
    unittest.main()
