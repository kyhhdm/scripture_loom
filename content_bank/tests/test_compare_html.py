"""Tests for the multi-run comparison page generator (compare_html)."""
import json
import pathlib
import tempfile
import unittest

from content_bank.author import compare_html, gates


def _item(iid, dim, text="Some question text.", **extra):
    it = {
        "id": iid,
        "passage": "PHP.1.1-11",
        "dimension": dim,
        "type": "question",
        "age_tier": "child",
        "difficulty": 1,
        "review_status": "draft",
        "text": {"en": text},
        "version": 1,
    }
    it.update(extra)
    return it


class BuildModelTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self._tmp.name)
        self.book_dir = self.base / "PHP"
        # run A: unit 001 has 2 D1 items + 1 D2; unit 002 has 1 D1 item
        self._write("runA", "PHP-001", [_item("a-001-d1-001", "D1"),
                                        _item("a-001-d1-002", "D1"),
                                        _item("a-001-d2-001", "D2")])
        self._write("runA", "PHP-002", [_item("a-002-d1-001", "D1")])
        # run B: unit 001 has 0 D1 items (only D2); unit 002 file MISSING
        self._write("runB", "PHP-001", [_item("b-001-d2-001", "D2")])

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, run, unit, items):
        d = self.book_dir / run
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{unit}.json").write_text(json.dumps(items), encoding="utf-8")

    def _model(self, runs=("runA", "runB")):
        return compare_html.build_model("PHP", list(runs), base=self.base)

    def test_ragged_alignment(self):
        model = self._model()
        unit = next(u for u in model["units"] if u["id"] == "PHP-001")
        d1 = next(b for b in unit["dimensions"] if b["dimension"] == "D1")
        self.assertEqual(len(d1["cells"]["runA"]), 2)
        self.assertEqual(d1["cells"].get("runB", []), [])
        self.assertEqual(d1["counts"]["runA"], 2)
        self.assertEqual(d1["counts"]["runB"], 0)

    def test_missing_unit_file_is_zero_not_error(self):
        model = self._model()
        unit = next(u for u in model["units"] if u["id"] == "PHP-002")
        d1 = next(b for b in unit["dimensions"] if b["dimension"] == "D1")
        self.assertEqual(len(d1["cells"]["runA"]), 1)
        self.assertEqual(d1["cells"].get("runB", []), [])

    def test_verdict_id_match_only(self):
        (self.book_dir / "verdicts").mkdir(parents=True, exist_ok=True)
        (self.book_dir / "verdicts" / "PHP-001.json").write_text(json.dumps({
            "a-001-d1-001": [{"reviewer": "r1", "verdict": "pass", "notes": "ok"}],
            "some-slug-that-matches-nothing": [{"reviewer": "r1", "verdict": "fail",
                                                "notes": "x"}],
        }), encoding="utf-8")
        model = self._model()
        cards = {c["id"]: c for u in model["units"] for b in u["dimensions"]
                 for cell in b["cells"].values() for c in cell}
        self.assertIsNotNone(cards["a-001-d1-001"]["verdict"])
        self.assertEqual(cards["a-001-d1-001"]["verdict"][0]["verdict"], "pass")
        self.assertIsNone(cards["a-001-d1-002"]["verdict"])

    def test_gate_best_effort_degrades_and_notes(self):
        def _boom(*a, **k):
            raise RuntimeError("corpus text unavailable")
        orig = gates.quote_check
        gates.quote_check = _boom
        try:
            model = self._model()
        finally:
            gates.quote_check = orig
        self.assertTrue(any("quote" in n.lower() for n in model["notes"]))
        # schema gate still ran: every card carries a gate verdict.
        cards = [c for u in model["units"] for b in u["dimensions"]
                 for cell in b["cells"].values() for c in cell]
        self.assertTrue(cards)
        self.assertTrue(all("gate_ok" in c for c in cards))

    def test_missing_run_dir_errors(self):
        with self.assertRaises(FileNotFoundError):
            compare_html.build_model("PHP", ["runA", "nope"], base=self.base)


class RenderTests(unittest.TestCase):
    def test_single_self_contained_file(self):
        model = {"book": "PHP", "runs": ["runA"], "notes": [], "units": []}
        html = compare_html.render_html(model)
        self.assertIn('id="review-data"', html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertIn("Export decisions", html)


if __name__ == "__main__":
    unittest.main()
