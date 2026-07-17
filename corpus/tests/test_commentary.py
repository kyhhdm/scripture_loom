import json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import books, refs

LAMP = Path(__file__).resolve().parents[1] / "canon" / "lampposts"


class TestCommentary(unittest.TestCase):
    def _check_work(self, dirname, workname):
        table = books.load()
        found = {p.stem.upper() for p in (LAMP / dirname).glob("*.json")}
        self.assertEqual(found, set(table), f"{dirname}: book coverage")
        with open(LAMP / dirname / "mat.json", encoding="utf-8") as f:
            mat = json.load(f)
        self.assertEqual(mat["role"], "lamppost")
        self.assertEqual(mat["license"], "public-domain")
        self.assertEqual(mat["book"], "MAT")
        self.assertIn(workname, mat["work"])
        for b in mat["blocks"]:
            refs.parse_range(b["range"])
            self.assertTrue(b["text"].strip())
        return mat

    def test_mhc_all_books_and_mat_shape(self):
        mat = self._check_work("mhc", "Henry")
        joined = " ".join(b["text"].lower() for b in mat["blocks"]
                          if refs.parse_range(b["range"])[0][1] == 5)
        self.assertIn("blessed", joined)

    def test_jfb_all_books_and_verse_level(self):
        mat = self._check_work("jfb", "Jamieson")
        ch5 = [b for b in mat["blocks"]
               if refs.parse_range(b["range"])[0][1] == 5]
        self.assertGreater(len(ch5), 10)   # verse-level granularity

    def test_blocks_for_helper(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingest"))
        from ingest_commentary import blocks_for
        texts = blocks_for(LAMP / "mhc", "MAT.5.1-12")
        self.assertTrue(texts)
        self.assertTrue(any("blessed" in t.lower() for t in texts))


if __name__ == "__main__":
    unittest.main()
