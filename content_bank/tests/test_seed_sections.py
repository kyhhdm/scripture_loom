import unittest
from content_bank.author import seed_sections as ss


class TestGatherInputs(unittest.TestCase):
    def test_snippet_prefers_jfb_and_truncates(self):
        work, text = ss.commentary_snippet("PHP.1.1-11", "PHP", max_chars=80)
        self.assertIn(work, ("jfb", "mhc"))       # PHP has commentary coverage
        self.assertTrue(text)                      # non-empty grounding
        self.assertLessEqual(len(text), 80)        # truncated
        self.assertNotIn("\n", text)               # newlines flattened

    def test_snippet_missing_returns_none(self):
        # A syntactically valid but uncovered range yields no grounding, no raise.
        work, text = ss.commentary_snippet("PHP.99.1-2", "PHP")
        self.assertIsNone(work)
        self.assertEqual(text, "")

    def test_gather_inputs_php_shape(self):
        data = ss.gather_inputs("PHP")
        self.assertEqual(data["book"], "PHP")
        self.assertEqual(data["book_name"], "Philippians")
        ps = data["pericopes"]
        self.assertEqual(ps[0]["id"], "PHP-001")
        self.assertEqual(ps[0]["range"], "PHP.1.1-11")
        self.assertIn("title_en", ps[0])
        self.assertIn("grounding_work", ps[0])
        self.assertIn("grounding_text", ps[0])
        # order preserved and complete
        self.assertEqual([p["id"] for p in ps],
                         [p["id"] for p in __import__(
                             "content_bank.lib.corpus_bridge",
                             fromlist=["pericopes"]).pericopes("PHP")])
