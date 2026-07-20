import pathlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.author import publish
from content_bank.lib import content, schema


def _q(iid="php1-q1"):
    return {"id": iid, "passage": "PHP-001", "dimension": "D1", "type": "question",
            "age_tier": "all", "difficulty": 1, "review_status": "draft",
            "text": {"en": "Who wrote to the Philippians?"}, "version": 1,
            "leader_reference": {"kind": "answer_key", "text": {"en": "Paul"}}}


def _mat_item(iid, passage="MAT-009"):
    return {"id": iid, "passage": passage, "dimension": "D1", "type": "question",
            "age_tier": "all", "difficulty": 1, "review_status": "draft",
            "text": {"en": "Who was tempted?"}, "version": 1}


class TestStamp(unittest.TestCase):
    def test_stamp_sets_published_and_provenance(self):
        out = publish.stamp([_q()], reviewed_date="2026-07-19", confirmed_by="kyhhdm")
        it = out[0]
        self.assertEqual(it["review_status"], "published")
        self.assertEqual(it["provenance"]["drafted_by"], "claude")
        self.assertEqual(it["provenance"]["reviewed_by"], "claude-adversarial")
        self.assertEqual(it["provenance"]["confirmed_by"], "kyhhdm")
        self.assertEqual(it["provenance"]["guardrail"], "WCF-1")

    def test_stamp_fills_leader_reference_provenance(self):
        out = publish.stamp([_q()], reviewed_date="2026-07-19", confirmed_by="kyhhdm")
        prov = out[0]["leader_reference"]["provenance"]
        self.assertEqual(prov["reviewed_by"], "claude-adversarial")
        self.assertEqual(prov["guardrail"], "WCF-1")

    def test_stamped_item_is_schema_valid(self):
        out = publish.stamp([_q()], reviewed_date="2026-07-19", confirmed_by="kyhhdm")
        self.assertEqual(schema.validate_item(out[0]), [])

    def test_stamp_does_not_mutate_input(self):
        item = _q()
        publish.stamp([item], reviewed_date="2026-07-19", confirmed_by="kyhhdm")
        self.assertEqual(item["review_status"], "draft")

    def test_draft_model_run_preserved_and_drives_drafted_by(self):
        item = _q()
        item["provenance"] = {"model": "deepseek-v4-pro", "backend": "llm_core",
                              "run": "deepseek-v4-pro"}
        out = publish.stamp([item], reviewed_date="2026-07-19", confirmed_by="kyhhdm")
        prov = out[0]["provenance"]
        self.assertEqual(prov["model"], "deepseek-v4-pro")
        self.assertEqual(prov["backend"], "llm_core")
        self.assertEqual(prov["run"], "deepseek-v4-pro")
        # drafted_by defaults to the model when the draft recorded one.
        self.assertEqual(prov["drafted_by"], "deepseek-v4-pro")
        self.assertEqual(schema.validate_item(out[0]), [])

    def test_explicit_drafted_by_overrides_model(self):
        item = _q()
        item["provenance"] = {"model": "opus", "backend": "claude", "run": "opus"}
        out = publish.stamp([item], reviewed_date="2026-07-19", confirmed_by="k",
                            drafted_by="human")
        self.assertEqual(out[0]["provenance"]["drafted_by"], "human")
        self.assertEqual(out[0]["provenance"]["model"], "opus")


class TestPublishRollback(unittest.TestCase):
    def test_absent_store_removed_on_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                publish.publish("MAT", [_mat_item("bad", passage="MAT-999")],
                                reviewed_date="2026-07-19", confirmed_by="k", store_dir=d)
            self.assertFalse(content.store_path("MAT", d).exists())

    def test_prior_store_restored_on_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            publish.publish("MAT", [_mat_item("good")], reviewed_date="2026-07-19",
                            confirmed_by="k", store_dir=d)
            before = content.store_path("MAT", d).read_text()
            with self.assertRaises(ValueError):
                publish.publish("MAT", [_mat_item("bad", passage="MAT-999")],
                                reviewed_date="2026-07-19", confirmed_by="k", store_dir=d)
            self.assertEqual(content.store_path("MAT", d).read_text(), before)

    def test_valid_publish_writes_store(self):
        with tempfile.TemporaryDirectory() as d:
            report = publish.publish("MAT", [_mat_item("good")], reviewed_date="2026-07-19",
                                     confirmed_by="k", store_dir=d)
            self.assertEqual(report["errors"], [])
            self.assertTrue(content.store_path("MAT", d).exists())


if __name__ == "__main__":
    unittest.main()
