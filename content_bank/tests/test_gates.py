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


if __name__ == "__main__":
    unittest.main()
