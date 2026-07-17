import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import passage

CORPUS = Path(__file__).resolve().parents[1]


class TestGetPassage(unittest.TestCase):
    def test_kjv_beatitudes(self):
        p = passage.get_passage("KJV", "MAT.5.1-12")
        self.assertEqual(len(p.verses), 12)
        self.assertIn("Blessed", p.verses["MAT.5.3"])
        self.assertTrue(p.displayable)
        self.assertEqual(p.license, "public-domain")

    def test_cuv(self):
        p = passage.get_passage("CUV", "MAT.5.3")
        self.assertEqual(len(p.verses), 1)
        self.assertTrue(p.displayable)

    def test_cross_chapter_range(self):
        p = passage.get_passage("KJV", "MAT.5.47-MAT.6.2")
        self.assertEqual(sorted(p.verses),
                         ["MAT.5.47", "MAT.5.48", "MAT.6.1", "MAT.6.2"])

    def test_unknown_version_raises(self):
        with self.assertRaises(passage.LicenseError):
            passage.get_passage("ESV", "MAT.5.1")   # no private file, product mode

    def test_private_version_refused_in_product_mode(self):
        priv = CORPUS / "sources" / "private"
        priv.mkdir(parents=True, exist_ok=True)
        f = priv / "esv.json"
        f.write_text(json.dumps({
            "version": "ESV", "lang": "en", "license": "copyrighted",
            "role": "displayable", "source": "private", "ingested": "2026-07-17",
            "versification_exceptions": {},
            "books": {"MAT": {"5": {"1": "test verse"}}}}))
        try:
            with self.assertRaises(passage.LicenseError):
                passage.get_passage("ESV", "MAT.5.1")            # product mode
            p = passage.get_passage("ESV", "MAT.5.1", mode="personal")
            self.assertEqual(p.verses["MAT.5.1"], "test verse")
            self.assertFalse(p.displayable)
        finally:
            f.unlink()

    def test_lamppost_role_blocked_even_if_open_license(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "fake.json"
            bad.write_text(json.dumps({
                "version": "FAKE", "license": "public-domain",
                "role": "lamppost", "books": {"MAT": {"5": {"1": "x"}}}}))
            with self.assertRaises(passage.LicenseError):
                passage._gate(json.loads(bad.read_text()), "product")


if __name__ == "__main__":
    unittest.main()
