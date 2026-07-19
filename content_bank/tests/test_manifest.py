import json
import pathlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.author import manifest


class TestManifest(unittest.TestCase):
    def test_init_marks_all_units_pending(self):
        m = manifest.init_manifest("PHP", ["PHP-001", "PHP-002"], ["PHP-S1"])
        self.assertEqual(m["book"], "PHP")
        self.assertEqual(m["units"]["PHP-001"], {"kind": "pericope", "stage": "pending"})
        self.assertEqual(m["units"]["PHP-S1"], {"kind": "section", "stage": "pending"})

    def test_set_stage_advances_one_unit(self):
        m = manifest.init_manifest("PHP", ["PHP-001"])
        manifest.set_stage(m, "PHP-001", "drafted")
        self.assertEqual(m["units"]["PHP-001"]["stage"], "drafted")

    def test_set_stage_rejects_unknown_stage(self):
        m = manifest.init_manifest("PHP", ["PHP-001"])
        with self.assertRaises(ValueError):
            manifest.set_stage(m, "PHP-001", "bogus")

    def test_set_stage_rejects_unknown_unit(self):
        m = manifest.init_manifest("PHP", ["PHP-001"])
        with self.assertRaises(KeyError):
            manifest.set_stage(m, "PHP-009", "drafted")

    def test_units_at_returns_sorted(self):
        m = manifest.init_manifest("PHP", ["PHP-002", "PHP-001", "PHP-003"])
        manifest.set_stage(m, "PHP-002", "drafted")
        self.assertEqual(manifest.units_at(m, "pending"), ["PHP-001", "PHP-003"])
        self.assertEqual(manifest.units_at(m, "drafted"), ["PHP-002"])

    def test_save_then_load_roundtrips(self):
        m = manifest.init_manifest("PHP", ["PHP-001"])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sub" / "manifest.json"
            manifest.save(p, m)
            self.assertEqual(manifest.load(p), m)


if __name__ == "__main__":
    unittest.main()
