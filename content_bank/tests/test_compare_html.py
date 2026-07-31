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

    def test_rubric_and_per_run_briefs_embedded(self):
        model = self._model()
        self.assertIn("seven axes", model["rubric"].lower())
        # every unit carries a per-run briefs map (value may be None if none on file).
        for u in model["units"]:
            self.assertIn("briefs", u)
            self.assertEqual(set(u["briefs"]), {"runA", "runB"})

    def test_section_reveal_check_flags_throughline_missing_reveal(self):
        # A throughline with no leader_reference is a HARD reveal-gate defect and
        # must reach the review page's gate_problems even when the unit's passage
        # range is unavailable (this run's units carry no corpus range at all).
        self._write("runA", "PHP-003", [_item("a-003-thr-001", "D3",
                                               type="throughline")])
        model = compare_html.build_model("PHP", ["runA", "runB"], base=self.base)
        unit = next(u for u in model["units"] if u["id"] == "PHP-003")
        cards = [c for b in unit["dimensions"] for cell in b["cells"].values()
                 for c in cell]
        card = next(c for c in cards if c["id"] == "a-003-thr-001")
        self.assertFalse(card["gate_ok"])
        self.assertTrue(any("leader_reference" in p for p in card["gate_problems"]))

    def test_new_runs_layout_resolves(self):
        # runs/<slug>/{drafts,briefs,verdicts} should be preferred over a flat dir.
        newbase = pathlib.Path(self._tmp.name) / "nested"
        rd = newbase / "PHP" / "runs" / "opus" / "drafts"
        rd.mkdir(parents=True)
        (rd / "PHP-001.json").write_text(json.dumps([_item("o-001-d1-001", "D1")]),
                                         encoding="utf-8")
        bd = newbase / "PHP" / "runs" / "opus" / "briefs"
        bd.mkdir(parents=True)
        (bd / "php-001.md").write_text("# opus brief", encoding="utf-8")
        model = compare_html.build_model("PHP", ["opus"], base=newbase)
        unit = model["units"][0]
        self.assertEqual(unit["id"], "PHP-001")
        self.assertEqual(unit["briefs"]["opus"], "# opus brief")


class LeaderRefTest(unittest.TestCase):
    def test_answer_key_extracted_onto_card(self):
        item = _item("x", "D1")
        item["leader_reference"] = {"kind": "answer_key",
                                    "text": {"en": "Paul and Timothy"},
                                    "verse": {"en": "Philippians 1:1"}}
        lr = compare_html._leader_ref(item)
        self.assertEqual(lr["kind"], "answer_key")
        self.assertEqual(lr["text_en"], "Paul and Timothy")
        self.assertEqual(lr["verse_en"], "Philippians 1:1")

    def test_none_when_absent(self):
        self.assertIsNone(compare_html._leader_ref(_item("x", "D1")))

    def test_citation_tags_kept_raw_for_highlighting(self):
        # The review page highlights <verse>/<doctrine> spans client-side, so the
        # server must pass the tagged text RAW (not stripped) to the browser.
        item = _item("x", "D1",
                     text='Who are the <verse ref="PHP.1.1">servants of Christ '
                          'Jesus</verse>?')
        item["leader_reference"] = {"kind": "answer_key",
                                    "text": {"en": 'Rests on <doctrine std="WCF" '
                                             'ref="1.4">God its author</doctrine>.'},
                                    "verse": {"en": "Philippians 1:1"}}
        card = compare_html._card(item, "runA", {}, {})
        self.assertIn('<verse ref="PHP.1.1">', card["text_en"])
        self.assertIn('<doctrine std="WCF" ref="1.4">',
                      card["leader_ref"]["text_en"])


class CitationHighlightTest(unittest.TestCase):
    def test_page_carries_highlighter_and_styles(self):
        html = compare_html.render_html(
            {"book": "PHP", "runs": [], "notes": [], "rubric": "", "units": []})
        # the client-side highlighter and its two tag styles must be present
        self.assertIn("function hlCite(", html)
        self.assertIn("hlCite(c.text_en)", html)      # item text highlighted
        self.assertIn("cite-verse", html)
        self.assertIn("cite-doctrine", html)


class RenderTests(unittest.TestCase):
    def test_single_self_contained_file(self):
        model = {"book": "PHP", "runs": ["runA"], "notes": [], "units": []}
        html = compare_html.render_html(model)
        self.assertIn('id="review-data"', html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertIn("Export decisions", html)

    def test_tooltip_titles_use_attribute_safe_escaping(self):
        # Verdict/gate notes contain double quotes; a title="..." must escape them
        # (escAttr), else the tooltip is dropped. Guard against regressing to esc().
        html = compare_html.render_html(
            {"book": "PHP", "runs": [], "notes": [], "rubric": "", "units": []})
        self.assertIn("escAttr(v.notes)", html)
        self.assertIn("escAttr(c.gate_problems", html)

    def test_js_regex_backslashes_survive_templating(self):
        # _PAGE must be a raw string, else Python turns \n in the md() JS regexes
        # into real newlines and the page throws SyntaxError on load.
        html = compare_html.render_html(
            {"book": "PHP", "runs": [], "notes": [], "rubric": "", "units": []})
        self.assertIn(r"/\n\n+/", html)
        self.assertIn(r"\*\*", html)


class ExperimentColumnsTest(unittest.TestCase):
    def _experiment(self, root, name, matrix, aggregate, items):
        d = pathlib.Path(root) / name
        run_dir = d / "PHP" / "runs" / name
        (run_dir / "drafts").mkdir(parents=True)
        (run_dir / "drafts" / "PHP-001.json").write_text(json.dumps(items))
        d.joinpath("manifest.json").write_text(json.dumps(
            {"name": name, "route_matrix": matrix, "aggregate": aggregate}))
        return d

    def test_render_shows_route_matrix_and_items(self):
        with tempfile.TemporaryDirectory() as root:
            a = self._experiment(
                root, "exp_a",
                {"draft": {"backend": "claude", "model": "opus"},
                 "review_r1": {"backend": "llm_core", "model": "gemini-3.6-flash"}},
                {"calls_total": 10, "claude_calls": 4, "evaluator_is_drafter": False},
                [_item("a-1", "D1", text="Who wrote to the Philippians?")])
            b = self._experiment(
                root, "exp_b",
                {"draft": {"backend": "llm_core", "model": "deepseek-v4-flash"}},
                {"calls_total": 6, "claude_calls": 0, "evaluator_is_drafter": True},
                [_item("b-1", "D1", text="Name the author.")])
            html = compare_html.render_experiments("PHP", [a, b])
        # both experiment names appear
        self.assertIn("exp_a", html)
        self.assertIn("exp_b", html)
        # a stage->model cell from the route matrix (static, not JS-rendered)
        self.assertIn("opus", html)
        self.assertIn("deepseek-v4-flash", html)
        self.assertIn("route matrix", html.lower())
        # item text is embedded in the page data
        self.assertIn("Who wrote to the Philippians?", html)

    def test_multiple_books_merge_into_one_page(self):
        with tempfile.TemporaryDirectory() as root:
            # one experiment spanning PHP + JON.
            d = pathlib.Path(root) / "gp"
            for book, unit, txt in (("PHP", "PHP-001", "Philippi question"),
                                    ("JON", "JON-001", "Jonah question")):
                rd = d / book / "runs" / "gp" / "drafts"
                rd.mkdir(parents=True)
                (rd / f"{unit}.json").write_text(json.dumps(
                    [_item(f"{unit}-a", "D1", text=txt)]))
            d.joinpath("manifest.json").write_text(json.dumps(
                {"name": "gp", "route_matrix": {"draft": {"backend": "claude",
                 "model": "opus"}}, "aggregate": {}}))
            html = compare_html.render_experiments(["PHP", "JON"], [d])
        # both books' units in the single page
        self.assertIn("Philippi question", html)
        self.assertIn("Jonah question", html)
        self.assertIn("PHP-001-a", html)
        self.assertIn("JON-001-a", html)


if __name__ == "__main__":
    unittest.main()
