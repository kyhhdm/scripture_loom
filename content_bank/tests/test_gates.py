import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.author import gates


def _item(**kw):
    base = dict(id="x-d1-a", dimension="D1", type="question", age_tier="child",
                difficulty=1, review_status="draft", version=1,
                passage="MAT-035", text={"en": "Who came to Jesus?"})
    base.update(kw)
    return base


class QuoteCheckTest(unittest.TestCase):
    def test_flags_non_verbatim_quote(self):
        it = _item(text={"en": 'He said "partakers of grace" to them.'})
        flags = gates.quote_check("MAT", [it])
        self.assertIn("x-d1-a", flags)

    def test_passes_verbatim_bsb_quote(self):
        # "I have not found" appears verbatim in Matthew 8:10 (BSB).
        it = _item(text={"en": 'Jesus said "I have not found" such faith.'})
        self.assertEqual(gates.quote_check("MAT", [it]), {})


class SchemaCheckTest(unittest.TestCase):
    def test_surfaces_validate_item_errors_by_id(self):
        bad = _item(dimension="D9")  # invalid dimension
        flags = gates.schema_check([bad])
        self.assertIn("x-d1-a", flags)
        self.assertTrue(flags["x-d1-a"])

    def test_clean_item_absent(self):
        self.assertEqual(gates.schema_check([_item()]), {})


class RefsInRangeTest(unittest.TestCase):
    def setUp(self):
        # MAT-035 = "The Faith of the Centurion", MAT.8.5-13.
        self.allowed = gates.pericope_allowed("MAT", "MAT-035")

    def test_flags_mat035_drift_matthew15_reference(self):
        # Reconstruct the historical drift: a non-D5 item in the Matthew-8
        # pericope carrying a Matthew-15 reference token.
        drift = _item(id="mat-35-d1-drift",
                      leader_reference={"kind": "answer_key", "text": {"en": "See MAT.15.8."},
                                        "verse": {"en": "MAT.15.8"},
                                        "provenance": {"reviewed_by": "x", "reviewed_date": "2026-07-20",
                                                       "guardrail": "WCF-1"}})
        flags = gates.refs_in_range([drift], self.allowed)
        self.assertIn("mat-35-d1-drift", flags)

    def test_in_range_reference_not_flagged(self):
        ok = _item(id="mat-35-d1-ok",
                   leader_reference={"kind": "answer_key", "text": {"en": "See MAT.8.10."},
                                     "provenance": {"reviewed_by": "x", "reviewed_date": "2026-07-20",
                                                    "guardrail": "WCF-1"}})
        self.assertEqual(gates.refs_in_range([ok], self.allowed), {})

    def test_d5_item_exempt_from_range(self):
        d5 = _item(id="mat-35-d5-x", dimension="D5",
                   text={"en": "How does this connect to MAT.15.28?"})
        self.assertEqual(gates.refs_in_range([d5], self.allowed), {})

    def test_section_thread_ref_outside_span_flagged(self):
        allowed = gates.section_allowed("PHP", "PHP-S1")
        thread = dict(id="php-s1-thread-x", dimension="D7", type="thread",
                      age_tier="all", difficulty=2, review_status="draft", version=1,
                      section="PHP-S1", text={"en": "joy motif"}, refs=["PHP.4.4"])
        # PHP-S1 spans only PHP.1.1-11; PHP.4.4 must be flagged.
        flags = gates.refs_in_range([thread], allowed)
        self.assertIn("php-s1-thread-x", flags)


class RunAllTest(unittest.TestCase):
    def test_merges_all_three_gates(self):
        allowed = gates.pericope_allowed("MAT", "MAT-035")
        bad = _item(id="bad", dimension="D9",  # schema failure
                    text={"en": 'quote "partakers of grace" and ref MAT.15.8'})
        flags = gates.run_all("MAT", [bad], allowed)
        self.assertIn("bad", flags)
        self.assertTrue(len(flags["bad"]) >= 2)  # schema + quote (+ ref)


if __name__ == "__main__":
    unittest.main()
