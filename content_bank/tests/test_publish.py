import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.author import publish
from content_bank.lib import schema


def _q(iid="php1-q1"):
    return {"id": iid, "passage": "PHP-001", "dimension": "D1", "type": "question",
            "age_tier": "all", "difficulty": 1, "review_status": "draft",
            "text": {"en": "Who wrote to the Philippians?"}, "version": 1,
            "leader_reference": {"kind": "answer_key", "text": {"en": "Paul"}}}


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


if __name__ == "__main__":
    unittest.main()
