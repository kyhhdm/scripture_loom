import unittest

from content_bank.author import experiment_config as ec

VALID = {
    "schema_version": 1, "name": "e1", "book": "PHP", "units": ["PHP-001"],
    "routes": {s: {"backend": "llm_core", "model": "m"} for s in
               ("brief", "draft", "repair", "review_r1", "review_r2", "revise")},
    "gates": {"max_repair": 2, "dim_cap": 6},
    "evaluator": {"backend": "claude", "model": "sonnet"},
}


class ConfigTest(unittest.TestCase):
    def test_valid_passes(self):
        ec.validate(VALID)  # no raise

    def test_missing_stage_rejected(self):
        bad = {**VALID, "routes": {"brief": {"backend": "llm_core"}}}
        with self.assertRaises(ValueError):
            ec.validate(bad)

    def test_missing_required_key_rejected(self):
        bad = {k: v for k, v in VALID.items() if k != "evaluator"}
        with self.assertRaises(ValueError):
            ec.validate(bad)

    def test_credential_field_rejected(self):
        bad = {**VALID, "routes": {**VALID["routes"],
               "draft": {"backend": "claude", "api_key": "sk-x"}}}
        with self.assertRaises(ValueError):
            ec.validate(bad)

    def test_unknown_backend_rejected(self):
        bad = {**VALID, "evaluator": {"backend": "openai", "model": "x"}}
        with self.assertRaises(ValueError):
            ec.validate(bad)

    def test_bad_max_repair_rejected(self):
        bad = {**VALID, "gates": {"max_repair": 99, "dim_cap": 6}}
        with self.assertRaises(ValueError):
            ec.validate(bad)

    def test_hash_stable_and_sensitive(self):
        h1 = ec.config_hash(VALID, corpus_rev="abc", prompt_version="1")
        h2 = ec.config_hash(VALID, corpus_rev="abc", prompt_version="1")
        h3 = ec.config_hash(VALID, corpus_rev="DEF", prompt_version="1")
        h4 = ec.config_hash(VALID, corpus_rev="abc", prompt_version="2")
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, h3)
        self.assertNotEqual(h1, h4)

    def test_book_of_unit(self):
        self.assertEqual(ec.book_of_unit("PHP-002"), "PHP")
        self.assertEqual(ec.book_of_unit("PSA-003"), "PSA")
        self.assertEqual(ec.book_of_unit("PHP-S1"), "PHP")

    def test_multibook_config_validates(self):
        cfg = {k: v for k, v in VALID.items() if k != "book"}
        cfg["units"] = ["PSA-003", "PHP-002", "JON-002", "ECC-018"]
        ec.validate(cfg)  # no raise

    def test_multibook_requires_units(self):
        cfg = {k: v for k, v in VALID.items() if k != "book"}
        cfg["units"] = None
        with self.assertRaises(ValueError):
            ec.validate(cfg)

    def test_multibook_rejects_unit_without_prefix(self):
        cfg = {k: v for k, v in VALID.items() if k != "book"}
        cfg["units"] = ["PHP-002", "nodash"]
        with self.assertRaises(ValueError):
            ec.validate(cfg)

    def test_books_and_units_single_book(self):
        self.assertEqual(ec.books_and_units(VALID), {"PHP": ["PHP-001"]})

    def test_books_and_units_multibook_groups_by_prefix(self):
        cfg = {k: v for k, v in VALID.items() if k != "book"}
        cfg["units"] = ["PSA-003", "PHP-002", "JON-002", "PHP-005"]
        groups = ec.books_and_units(cfg)
        self.assertEqual(groups["PHP"], ["PHP-002", "PHP-005"])
        self.assertEqual(groups["PSA"], ["PSA-003"])
        self.assertEqual(groups["JON"], ["JON-002"])

    def test_immutable_guard(self):
        ec.check_immutable(None, "h")                   # first run ok
        ec.check_immutable({"config_hash": "h"}, "h")   # resume ok
        with self.assertRaises(ValueError):
            ec.check_immutable({"config_hash": "h"}, "OTHER")


if __name__ == "__main__":
    unittest.main()
