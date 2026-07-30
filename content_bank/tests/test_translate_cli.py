import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock
from content_bank.author import translate_cli, translate, build_cli
from content_bank.author import translate_cli as tc

STORE = {"book": "PHP", "items": [
    {"id": "PHP-001-D1-01", "passage": "PHP.1.1-11", "dimension": "D1",
     "type": "question", "review_status": "reviewed",
     "text": {"en": "servants of Christ Jesus?"}},
    {"id": "PHP-001-D1-02", "passage": "PHP.1.1-11", "dimension": "D1",
     "type": "question", "review_status": "published",
     "text": {"en": "Who wrote the letter?"}},
]}
# ZH Scripture form: <verse ref>「…verbatim CUV…」</verse> (tag + brackets nested).
GOOD = ('{"text": {"zh": "<verse ref=\\"PHP.1.1\\">「基督耶稣的仆人」</verse>？"},'
        ' "terms": [], "uncertain": []}')
GOOD_ZH = '<verse ref="PHP.1.1">「基督耶稣的仆人」</verse>？'


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
        self.assertEqual(p["item"]["text"]["zh"], GOOD_ZH)
        self.assertIn("drift", p)

    def test_run_proposals_parallel_preserves_order_and_isolates_failures(self):
        items = [{"id": f"PHP-001-D1-0{i}", "passage": "PHP.1.1-11",
                  "dimension": "D1", "type": "question",
                  "text": {"en": f"q{i}?"}} for i in range(1, 5)]

        def fake_proposal(it, book, **kw):
            if it["id"].endswith("03"):
                raise RuntimeError("boom")
            return {"id": it["id"], "gate_ok": True,
                    "drift": {"drift": False}}

        with mock.patch.object(translate_cli, "proposal_for",
                               side_effect=fake_proposal):
            got = translate_cli.run_proposals(items, "PHP", glossary=[],
                                              concurrency=4)
        # order preserved (input order), failed item dropped
        self.assertEqual([p["id"] for p in got],
                         ["PHP-001-D1-01", "PHP-001-D1-02", "PHP-001-D1-04"])

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


class TestSuggestFixWiring(unittest.TestCase):
    ITEM = {"id": "PSA-003-i14", "text": {"en": "But You, O LORD.", "zh": "但你。"}}

    def _patch(self, drift, suggested):
        gated = {"item": self.ITEM, "cuv_refs": [], "terms": [], "uncertain": [],
                 "gate_ok": True, "gate_flags": []}
        return (mock.patch.object(tc, "translate_with_gates", return_value=gated),
                mock.patch.object(tc, "back_translate_review", return_value=drift),
                mock.patch.object(tc, "suggest_drift_fix", return_value=suggested))

    def test_drift_flagged_proposal_carries_suggested_fix(self):
        sug = {"changed": True, "rationale": "x", "item": self.ITEM,
               "gate_ok": True, "gate_flags": [], "drift": {"drift": False},
               "terms": [], "uncertain": []}
        a, b, c = self._patch({"drift": True, "notes": "n"}, sug)
        with a, b, c as m:
            p = tc.proposal_for(self.ITEM, "PSA", glossary=[], suggest_fixes=True)
        self.assertIn("suggested_fix", p)
        m.assert_called_once()

    def test_no_drift_no_suggested_fix_and_no_call(self):
        a, b, c = self._patch({"drift": False, "notes": ""}, None)
        with a, b, c as m:
            p = tc.proposal_for(self.ITEM, "PSA", glossary=[], suggest_fixes=True)
        self.assertNotIn("suggested_fix", p)
        m.assert_not_called()

    def test_suggest_fixes_off_suppresses_call(self):
        a, b, c = self._patch({"drift": True, "notes": "n"}, None)
        with a, b, c as m:
            p = tc.proposal_for(self.ITEM, "PSA", glossary=[], suggest_fixes=False)
        self.assertNotIn("suggested_fix", p)
        m.assert_not_called()

    def test_drift_model_routes_drift_review_and_fix(self):
        # --drift-model must reach BOTH the back-translation review and the
        # re-drift inside suggest_drift_fix, while translation stays on --model.
        sug = {"changed": True, "rationale": "x", "item": self.ITEM,
               "gate_ok": True, "gate_flags": [], "drift": {"drift": False},
               "terms": [], "uncertain": []}
        a, b, c = self._patch({"drift": True, "notes": "n"}, sug)
        with a, b as btr, c as sdf:
            tc.proposal_for(self.ITEM, "PSA", glossary=[], model="flash",
                            drift_model="pro", suggest_fixes=True)
        # drift review ran on the drift model, not the translation model
        self.assertEqual(btr.call_args.kwargs.get("model"), "pro")
        # suggest_drift_fix received both the translation model and drift_model
        self.assertEqual(sdf.call_args.kwargs.get("model"), "flash")
        self.assertEqual(sdf.call_args.kwargs.get("drift_model"), "pro")

    def test_drift_model_defaults_to_model(self):
        a, b, c = self._patch({"drift": False, "notes": ""}, None)
        with a, b as btr, c:
            tc.proposal_for(self.ITEM, "PSA", glossary=[], model="flash",
                            suggest_fixes=True)
        self.assertEqual(btr.call_args.kwargs.get("model"), "flash")
