import json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import refs

LAMP = Path(__file__).resolve().parents[1] / "canon" / "lampposts"


def _load(name):
    with open(LAMP / name, encoding="utf-8") as f:
        return json.load(f)


class TestWCF(unittest.TestCase):
    def test_shape(self):
        wcf = _load("wcf.json")
        self.assertEqual(wcf["role"], "lamppost")
        self.assertEqual(wcf["license"], "public-domain")
        self.assertEqual(len(wcf["chapters"]), 33)

    def test_chapter_one_on_scripture(self):
        ch1 = _load("wcf.json")["chapters"][0]
        self.assertIn("Scripture", ch1["title"])
        self.assertEqual(len(ch1["sections"]), 10)
        # WCF 1.9: Scripture interprets Scripture
        self.assertIn("infallible rule of interpretation",
                      ch1["sections"][8]["text"])

    def test_proof_texts_parse(self):
        for ch in _load("wcf.json")["chapters"]:
            for s in ch["sections"]:
                for pt in s["proof_texts"]:
                    refs.parse_range(pt)


class TestCatechisms(unittest.TestCase):
    def test_shorter_has_107_questions(self):
        wsc = _load("wsc.json")
        self.assertEqual(len(wsc["questions"]), 107)
        self.assertIn("chief end of man", wsc["questions"][0]["q"])
        self.assertIn("glorify God", wsc["questions"][0]["a"])

    def test_larger_has_196_questions(self):
        self.assertEqual(len(_load("wlc.json")["questions"]), 196)

    def test_numbering_sequential(self):
        for name in ("wsc.json", "wlc.json"):
            qs = _load(name)["questions"]
            self.assertEqual([q["n"] for q in qs], list(range(1, len(qs) + 1)))


if __name__ == "__main__":
    unittest.main()
