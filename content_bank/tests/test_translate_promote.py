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

    def test_promote_merges_category_zh(self):
        store = {"book": "PHP", "items": [
            {"id": "PHP-001-D1-03", "dimension": "D1", "type": "pre_reading_quest",
             "review_status": "reviewed", "text": {"en": "Who is named?"},
             "category": {"en": "People & roles"}}]}
        prop = {"id": "PHP-001-D1-03",
                "item": {"id": "PHP-001-D1-03", "dimension": "D1",
                          "type": "pre_reading_quest", "review_status": "reviewed",
                          "text": {"en": "Who is named?", "zh": "谁被提名？"},
                          "category": {"en": "People & roles", "zh": "人物与角色"}}}
        d = tempfile.mkdtemp()
        (pathlib.Path(d) / "php.json").write_text(json.dumps(store), encoding="utf-8")
        translate.promote("PHP", [prop], ["PHP-001-D1-03"], store_dir=d)
        it = content.load_book_store("PHP", d)["items"][0]
        self.assertEqual(it["category"]["zh"], "人物与角色")
        self.assertEqual(it["category"]["en"], "People & roles")  # preserved

    def test_promote_merges_zh_into_leader_reference(self):
        store = {"book": "PHP", "items": [
            {"id": "PHP-001-D1-02", "dimension": "D1", "type": "question",
             "review_status": "reviewed", "text": {"en": "servants?"},
             "leader_reference": {"kind": "answer_key",
                                   "text": {"en": "Paul and Timothy."},
                                   "verse": {"en": "Philippians 1:1"}}}]}
        prop = {"id": "PHP-001-D1-02",
                "item": {"id": "PHP-001-D1-02", "dimension": "D1", "type": "question",
                          "review_status": "reviewed",
                          "text": {"en": "servants?", "zh": "仆人？"},
                          "leader_reference": {
                              "kind": "answer_key",
                              "text": {"en": "Paul and Timothy.", "zh": "保罗和提摩太。"},
                              "verse": {"en": "Philippians 1:1", "zh": "腓立比书1:1"}}}}
        d = tempfile.mkdtemp()
        (pathlib.Path(d) / "php.json").write_text(json.dumps(store), encoding="utf-8")
        ids = translate.promote("PHP", [prop], ["PHP-001-D1-02"], store_dir=d)
        self.assertEqual(ids, ["PHP-001-D1-02"])
        it = content.load_book_store("PHP", d)["items"][0]
        lr = it["leader_reference"]
        self.assertEqual(lr["text"]["zh"], "保罗和提摩太。")
        self.assertEqual(lr["text"]["en"], "Paul and Timothy.")
        self.assertEqual(lr["verse"]["zh"], "腓立比书1:1")
        self.assertEqual(lr["verse"]["en"], "Philippians 1:1")
        self.assertEqual(it["review_status"], "reviewed")
