import json
import pathlib
import tempfile
import unittest
from unittest import mock
from content_bank.author import translate_cli, translate

STORE = {"book": "PHP", "items": [
    {"id": "PHP-001-D1-01", "passage": "PHP.1.1-11", "dimension": "D1",
     "type": "question", "review_status": "reviewed",
     "text": {"en": "servants of Christ Jesus?"}},
    {"id": "PHP-001-D1-02", "passage": "PHP.1.1-11", "dimension": "D1",
     "type": "question", "review_status": "published",
     "text": {"en": "Who wrote the letter?"}},
]}
GOOD = '{"text": {"zh": "「基督耶稣的仆人」？"}, "terms": [], "uncertain": []}'


class TestTranslateCli(unittest.TestCase):
    def _store_dir(self):
        d = tempfile.mkdtemp()
        (pathlib.Path(d) / "php.json").write_text(json.dumps(STORE), encoding="utf-8")
        return d

    def test_select_by_status(self):
        d = self._store_dir()
        got = translate_cli.select_items("PHP", status="reviewed", store_dir=d)
        self.assertEqual([i["id"] for i in got], ["PHP-001-D1-01"])

    def test_select_by_ids(self):
        d = self._store_dir()
        got = translate_cli.select_items("PHP", item_ids=["PHP-001-D1-02"], store_dir=d)
        self.assertEqual([i["id"] for i in got], ["PHP-001-D1-02"])

    def test_proposal_shape(self):
        item = STORE["items"][0]
        with mock.patch.object(translate, "llm", return_value=GOOD), \
             mock.patch.object(translate_cli, "back_translate_review",
                               return_value={"drift": False, "notes": ""}):
            p = translate_cli.proposal_for(item, "PHP", glossary=[])
        self.assertEqual(p["id"], "PHP-001-D1-01")
        self.assertEqual(p["en"], "servants of Christ Jesus?")
        self.assertTrue(p["gate_ok"])
        self.assertEqual(p["item"]["text"]["zh"], "「基督耶稣的仆人」？")
        self.assertIn("drift", p)

    def test_write_proposals(self):
        out = tempfile.mkdtemp()
        translate_cli.write_proposals([{"id": "A-1", "gate_ok": True}], out)
        f = pathlib.Path(out) / "A-1.json"
        self.assertTrue(f.exists())
        self.assertEqual(json.loads(f.read_text())["id"], "A-1")
