import json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import refs

CANON = Path(__file__).resolve().parents[1] / "canon"


class TestMatthewPericopes(unittest.TestCase):
    def setUp(self):
        with open(CANON / "structure" / "pericopes" / "mat.json",
                  encoding="utf-8") as f:
            self.data = json.load(f)
        with open(CANON / "bibles" / "kjv.json", encoding="utf-8") as f:
            self.kjv_mat = json.load(f)["books"]["MAT"]

    def test_ids_sequential_and_stable_format(self):
        ids = [p["id"] for p in self.data["pericopes"]]
        self.assertEqual(ids[0], "MAT-001")
        self.assertEqual(ids, [f"MAT-{i+1:03d}" for i in range(len(ids))])

    def test_all_seeded_with_titles(self):
        for p in self.data["pericopes"]:
            self.assertEqual(p["status"], "seeded")
            self.assertTrue(p["title_en"])
            self.assertIn("title_zh", p)

    def test_every_kjv_verse_in_exactly_one_pericope(self):
        ranges = [refs.parse_range(p["range"]) for p in self.data["pericopes"]]
        for ch, verses in self.kjv_mat.items():
            for vk in verses:
                v = int(vk.split("-")[0])
                hits = [r for r in ranges if refs.in_range(("MAT", int(ch), v), r)]
                self.assertEqual(len(hits), 1, f"MAT.{ch}.{v} in {len(hits)} pericopes")

    def test_session_sized_units(self):
        # sanity: Matthew should yield roughly 80-130 units, none absurdly long
        n = len(self.data["pericopes"])
        self.assertTrue(60 <= n <= 160, f"{n} pericopes")


if __name__ == "__main__":
    unittest.main()
