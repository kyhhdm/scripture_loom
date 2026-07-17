import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import passage, refs

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

    def test_path_traversal_version_refused(self):
        with self.assertRaises(passage.LicenseError):
            passage.get_passage("../../canon/bibles/kjv", "MAT.5.1", mode="personal")

    def test_lamppost_role_blocked_even_if_open_license(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "fake.json"
            bad.write_text(json.dumps({
                "version": "FAKE", "license": "public-domain",
                "role": "lamppost", "books": {"MAT": {"5": {"1": "x"}}}}))
            with self.assertRaises(passage.LicenseError):
                passage._gate(json.loads(bad.read_text()), "product")

    def test_gate_closed_license_displayable_blocked(self):
        # The AND's license half in isolation: displayable + closed license.
        with self.assertRaises(passage.LicenseError):
            passage._gate({"role": "displayable", "license": "copyrighted"},
                          "product")

    def test_gate_open_license_displayable_allowed(self):
        # Locks in Fix 1: a bare CC-BY displayable asset passes the product gate.
        self.assertTrue(
            passage._gate({"role": "displayable", "license": "CC-BY"}, "product"))

    def test_bridged_verse_key_round_trips(self):
        priv = CORPUS / "sources" / "private"
        priv.mkdir(parents=True, exist_ok=True)
        f = priv / "brdg.json"
        f.write_text(json.dumps({
            "version": "BRDG", "lang": "en", "license": "copyrighted",
            "role": "displayable", "source": "private", "ingested": "2026-07-17",
            "versification_exceptions": {},
            "books": {"MAT": {"5": {"16": "before", "17-18": "bridged text"}}}}))
        try:
            p = passage.get_passage("BRDG", "MAT.5.16-18", mode="personal")
            # Every emitted key is a canonical single-verse ref refs.parse accepts.
            for key in p.verses:
                refs.parse(key)
            # The bridged text is retrievable under the first covered verse.
            self.assertEqual(p.verses["MAT.5.17"], "bridged text")
            self.assertIn("MAT.5.16", p.verses)
        finally:
            f.unlink()


if __name__ == "__main__":
    unittest.main()
