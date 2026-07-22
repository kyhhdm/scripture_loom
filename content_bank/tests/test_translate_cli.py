import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock
from content_bank.author import translate_cli, translate, build_cli

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


class TestDraftsInput(unittest.TestCase):
    def _drafts_dir(self):
        # a runs/<model>/drafts layout with two unit files
        root = tempfile.mkdtemp()
        d = pathlib.Path(root) / "PHP" / "runs" / "opus" / "drafts"
        d.mkdir(parents=True)
        (d / "PHP-001.json").write_text(json.dumps(
            [{"id": "PHP-001-D1-01", "passage": "PHP.1.1-11", "dimension": "D1",
              "type": "question", "text": {"en": "servants of Christ Jesus?"}}]),
            encoding="utf-8")
        (d / "PHP-002.json").write_text(json.dumps(
            [{"id": "PHP-002-D1-01", "passage": "PHP.1.12-18", "dimension": "D1",
              "type": "question", "text": {"en": "Who is emboldened?"}}]),
            encoding="utf-8")
        return str(d)

    def test_load_drafts_concatenates_sorted(self):
        got = translate_cli.load_drafts(self._drafts_dir())
        self.assertEqual([i["id"] for i in got],
                         ["PHP-001-D1-01", "PHP-002-D1-01"])

    def test_out_dir_routes_by_translator_slug(self):
        dd = self._drafts_dir()
        out = translate_cli.out_dir_for(dd, "llm_core", None)  # -> deepseek-v4-flash
        self.assertTrue(out.endswith("runs/opus/translations/deepseek-v4-flash"))
        out2 = translate_cli.out_dir_for(dd, "claude", "opus")
        self.assertTrue(out2.endswith("runs/opus/translations/opus"))

    def test_main_drafts_dir_writes_proposals_to_translator_dir(self):
        dd = self._drafts_dir()
        with mock.patch.object(translate, "llm",
                               return_value='{"text": {"zh": "「基督耶稣的仆人」？"}, '
                                            '"terms": [], "uncertain": []}'), \
             mock.patch.object(translate_cli, "back_translate_review",
                               return_value={"drift": False, "notes": ""}):
            translate_cli.main(["--book", "PHP", "--drafts-dir", dd,
                                "--items", "PHP-001-D1-01"])
        f = (pathlib.Path(dd).parent / "translations" / "deepseek-v4-flash"
             / "PHP-001-D1-01.json")
        self.assertTrue(f.exists())
        self.assertEqual(os.environ.get("SCRIPTURE_LOOM_LLM_BACKEND"), "llm_core")
