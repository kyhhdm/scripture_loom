import json
import pathlib
import tempfile
import unittest
from content_bank.author import translate
from content_bank.lib import content

STORE = {"book": "PHP", "items": [
    {"id": "PHP-001-D1-01", "dimension": "D1", "type": "question",
     "review_status": "reviewed", "text": {"en": "servants?"}}]}
PROP = {"id": "PHP-001-D1-01",
        "item": {"id": "PHP-001-D1-01", "dimension": "D1", "type": "question",
                 "review_status": "reviewed",
                 "text": {"en": "servants?", "zh": "仆人？"}}}


class TestPromote(unittest.TestCase):
    def _store_dir(self):
        d = tempfile.mkdtemp()
        (pathlib.Path(d) / "php.json").write_text(json.dumps(STORE), encoding="utf-8")
        return d

    def test_promote_merges_zh_only(self):
        d = self._store_dir()
        ids = translate.promote("PHP", [PROP], ["PHP-001-D1-01"], store_dir=d)
        self.assertEqual(ids, ["PHP-001-D1-01"])
        it = content.load_book_store("PHP", d)["items"][0]
        self.assertEqual(it["text"]["zh"], "仆人？")
        self.assertEqual(it["text"]["en"], "servants?")     # preserved
        self.assertEqual(it["review_status"], "reviewed")   # NOT advanced

    def test_unaccepted_proposal_skipped(self):
        d = self._store_dir()
        ids = translate.promote("PHP", [PROP], [], store_dir=d)
        self.assertEqual(ids, [])
        it = content.load_book_store("PHP", d)["items"][0]
        self.assertNotIn("zh", it["text"])
