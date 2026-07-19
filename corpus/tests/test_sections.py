import unittest
from corpus.lib import sections


class TestSections(unittest.TestCase):
    def test_load_returns_matthew_sections(self):
        data = sections.load("MAT")
        self.assertEqual(data["book"], "MAT")
        self.assertEqual(len(data["sections"]), 7)
        self.assertEqual(data["sections"][0]["id"], "MAT-S1")

    def test_matthew_partition_is_valid(self):
        self.assertEqual(sections.validate("MAT"), [])

    def test_gap_is_reported(self):
        # A partition that skips a pericope must error.
        bad = {"sections": [
            {"id": "S1", "title_en": "a", "first_pericope": "MAT-001", "last_pericope": "MAT-002", "marker": None},
            {"id": "S2", "title_en": "b", "first_pericope": "MAT-004", "last_pericope": "MAT-153", "marker": None},
        ]}
        errors = sections.validate_data(bad, ["MAT-%03d" % i for i in range(1, 154)])
        self.assertTrue(any("MAT-S" not in e and "gap" in e.lower() or "expected" in e.lower() for e in errors))

    def test_incomplete_cover_is_reported(self):
        bad = {"sections": [
            {"id": "S1", "title_en": "a", "first_pericope": "MAT-001", "last_pericope": "MAT-006", "marker": None},
        ]}
        errors = sections.validate_data(bad, ["MAT-%03d" % i for i in range(1, 154)])
        self.assertTrue(any("cover" in e.lower() for e in errors))
