import hashlib, json, unittest
from pathlib import Path

SOURCES = Path(__file__).resolve().parents[1] / "sources"
BIBLE_DIRS = ["kjv-ebible", "web-ebible", "cuv-ebible", "bsb-ebible"]


class TestSources(unittest.TestCase):
    def test_bible_sources_present_with_valid_meta(self):
        for d in BIBLE_DIRS:
            src = SOURCES / d
            meta = json.loads((src / "meta.json").read_text())
            for key in ("url", "fetched", "license", "file", "sha256"):
                self.assertIn(key, meta, f"{d}: missing {key}")
            blob = (src / meta["file"]).read_bytes()
            self.assertEqual(hashlib.sha256(blob).hexdigest(), meta["sha256"],
                             f"{d}: checksum mismatch")

    def test_private_dir_is_gitignored(self):
        gitignore = (Path(__file__).resolve().parents[2] / ".gitignore").read_text()
        self.assertIn("corpus/sources/private/", gitignore)


if __name__ == "__main__":
    unittest.main()
