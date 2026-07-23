import unittest
from content_bank.lib import standards


class TestResolve(unittest.TestCase):
    def test_wcf_section_resolves(self):
        text = standards.resolve("WCF", "1.4")
        self.assertIsInstance(text, str)
        self.assertIn("authority", text.lower())

    def test_wcf_out_of_range_is_none(self):
        self.assertIsNone(standards.resolve("WCF", "1.99"))
        self.assertIsNone(standards.resolve("WCF", "99.1"))

    def test_wcf_bad_ref_shape_is_none(self):
        self.assertIsNone(standards.resolve("WCF", "Q1"))
        self.assertIsNone(standards.resolve("WCF", "1"))

    def test_wsc_and_wlc_question_resolves(self):
        self.assertIn("glorify", standards.resolve("WSC", "Q1").lower())
        self.assertIsInstance(standards.resolve("WLC", "Q1"), str)

    def test_question_out_of_range_is_none(self):
        self.assertIsNone(standards.resolve("WSC", "Q9999"))
        self.assertIsNone(standards.resolve("WSC", "1.4"))

    def test_unknown_standard_is_none(self):
        self.assertIsNone(standards.resolve("XYZ", "1.1"))


if __name__ == "__main__":
    unittest.main()
