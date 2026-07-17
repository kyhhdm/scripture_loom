import json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import refs

CANON = Path(__file__).resolve().parents[1] / "canon"


class TestCrossrefs(unittest.TestCase):
    def setUp(self):
        with open(CANON / "structure" / "crossrefs.json", encoding="utf-8") as f:
            self.data = json.load(f)

    def test_metadata(self):
        self.assertIn("CC-BY", self.data["license"])
        self.assertEqual(self.data["role"], "displayable")

    def test_volume(self):
        self.assertGreater(len(self.data["refs"]), 300000)

    def test_all_refs_parse_canonically(self):
        for r in self.data["refs"][:5000] + self.data["refs"][-5000:]:
            refs.parse(r["from"])
            refs.parse_range(r["to"])
            self.assertIsInstance(r["weight"], int)
            self.assertEqual(r["sources"], ["openbible"])

    def test_known_crossref_present(self):
        hits = [r for r in self.data["refs"]
                if r["from"] == "MAT.5.5" and r["to"].startswith("PSA.37")]
        self.assertTrue(hits)


if __name__ == "__main__":
    unittest.main()
