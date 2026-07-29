import json
import json as _json
import pathlib as _pl
import tempfile
import unittest
from unittest import mock
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


class TestBuildPrompt(unittest.TestCase):
    def _inputs(self):
        return {"book": "PHP", "book_name": "Philippians", "pericopes": [
            {"id": "PHP-001", "range": "PHP.1.1-11", "title_en": "Greeting",
             "grounding_work": "jfb", "grounding_text": "the inscription..."},
            {"id": "PHP-002", "range": "PHP.1.12-26", "title_en": "Imprisonment",
             "grounding_work": "jfb", "grounding_text": "his bonds..."},
        ]}

    def test_prompt_has_spine_rules_and_json(self):
        p = ss.build_prompt(self._inputs())
        self.assertIn("Philippians", p)
        self.assertIn("PHP-001", p)
        self.assertIn("PHP-002", p)
        self.assertIn("the inscription...", p)          # grounding included
        self.assertIn("Label: Description", p)           # dual-title convention
        self.assertIn("marker", p.lower())               # marker rule present
        self.assertIn("null", p)                         # marker may be null
        self.assertIn("JSON", p)                         # strict-JSON instruction
        self.assertNotIn('"id"', p)                      # model must NOT supply ids

    def test_prompt_prefers_multi_pericope_movements(self):
        # A single-pericope section carries no cross-pericope threads, so the
        # seeder should steer toward movements spanning multiple pericopes.
        p = ss.build_prompt(self._inputs()).lower()
        self.assertIn("multiple", p)
        self.assertIn("thread", p)

    def test_repair_prompt_carries_errors(self):
        base = ss.build_prompt(self._inputs())
        proposal = {"sections": [{"title_en": "X", "first_pericope": "PHP-001",
                                  "last_pericope": "PHP-001", "marker": None}]}
        rp = ss.build_repair_prompt(base, proposal, ["S?: gap/overlap ..."])
        self.assertIn("gap/overlap", rp)
        self.assertIn("PHP-001", rp)


class TestParseAndAssign(unittest.TestCase):
    def test_parse_bare_json(self):
        d = ss.parse_proposal('{"sections": [{"title_en": "A"}]}')
        self.assertEqual(len(d["sections"]), 1)

    def test_parse_fenced_json_with_prose(self):
        raw = 'Here you go:\n```json\n{"sections": [{"title_en": "A"}]}\n```\n'
        d = ss.parse_proposal(raw)
        self.assertEqual(d["sections"][0]["title_en"], "A")

    def test_parse_garbage_raises(self):
        with self.assertRaises(ValueError):
            ss.parse_proposal("no json here")

    def test_assign_ids_sequential(self):
        d = {"sections": [{"title_en": "A"}, {"title_en": "B"}]}
        ss.assign_section_ids(d, "PHP")
        self.assertEqual([s["id"] for s in d["sections"]],
                         ["PHP-S1", "PHP-S2"])

    def test_parse_tolerates_stray_braces_in_prose(self):
        raw = 'Note: total {5} items found. Here:\n{"sections": [{"title_en": "A"}]}'
        d = ss.parse_proposal(raw)
        self.assertEqual(d["sections"][0]["title_en"], "A")


class TestVerifyMarkers(unittest.TestCase):
    def _by_id(self):
        return {"PHP-001": "PHP.1.1-11", "PHP-002": "PHP.1.12-26"}

    def test_keeps_in_span_marker(self):
        secs = [{"id": "PHP-S1", "first_pericope": "PHP-001",
                 "last_pericope": "PHP-002", "marker": "PHP.1.6"}]
        _, dropped = ss.verify_markers(secs, self._by_id())
        self.assertEqual(secs[0]["marker"], "PHP.1.6")
        self.assertEqual(dropped, [])

    def test_drops_out_of_span_marker(self):
        secs = [{"id": "PHP-S1", "first_pericope": "PHP-001",
                 "last_pericope": "PHP-001", "marker": "PHP.4.1"}]
        _, dropped = ss.verify_markers(secs, self._by_id())
        self.assertIsNone(secs[0]["marker"])
        self.assertEqual(dropped[0]["id"], "PHP-S1")

    def test_drops_unparseable_marker(self):
        secs = [{"id": "PHP-S1", "first_pericope": "PHP-001",
                 "last_pericope": "PHP-001", "marker": "ZZZ.1.1"}]
        _, dropped = ss.verify_markers(secs, self._by_id())
        self.assertIsNone(secs[0]["marker"])
        self.assertEqual(len(dropped), 1)

    def test_null_marker_untouched(self):
        secs = [{"id": "PHP-S1", "first_pericope": "PHP-001",
                 "last_pericope": "PHP-001", "marker": None}]
        _, dropped = ss.verify_markers(secs, self._by_id())
        self.assertEqual(dropped, [])


class TestOutputAndReport(unittest.TestCase):
    def _secs(self):
        return [
            {"id": "PHP-S1", "title_en": "Opening: Greeting",
             "first_pericope": "PHP-001", "last_pericope": "PHP-001",
             "marker": None, "rationale": "sets the frame"},
            {"id": "PHP-S2", "title_en": "Body: The Gospel Life",
             "first_pericope": "PHP-002", "last_pericope": "PHP-002",
             "marker": "PHP.1.12", "rationale": "turns to his circumstances"},
        ]

    def test_to_output_shape(self):
        out = ss.to_output(self._secs(), "PHP")
        s0 = out["sections"][0]
        self.assertEqual(s0["title_zh"], "")
        self.assertEqual(s0["status"], "seeded")
        self.assertNotIn("rationale", s0)          # rationale never stored
        self.assertEqual(set(s0), {"id", "title_en", "title_zh",
                                   "first_pericope", "last_pericope",
                                   "marker", "status"})

    def test_written_map_validates(self):
        # Build a 2-section partition over the real first two PHP pericopes...
        # (PHP-001, PHP-002) and prove it passes the existing validator.
        from corpus.lib import sections as csecs
        from content_bank.lib import corpus_bridge as cb
        order = [p["id"] for p in cb.pericopes("PHP")]
        secs = [
            {"id": "PHP-S1", "title_en": "A", "first_pericope": order[0],
             "last_pericope": order[0], "marker": None, "rationale": "x"},
            {"id": "PHP-S2", "title_en": "B", "first_pericope": order[1],
             "last_pericope": order[-1], "marker": None, "rationale": "y"},
        ]
        out = ss.to_output(secs, "PHP")
        self.assertEqual(csecs.validate_data(out, order), [])

    def test_write_output_roundtrip(self):
        d = _pl.Path(tempfile.mkdtemp()) / "sub" / "php.json"
        ss.write_output(self._secs(), "PHP", d)
        written = _json.loads(d.read_text(encoding="utf-8"))
        self.assertEqual(written["book"], "PHP")
        self.assertNotIn("rationale", written["sections"][0])

    def test_report_has_rationale_and_dropped(self):
        rpt = ss.render_report("PHP", self._secs(),
                               [{"id": "PHP-S9", "marker": "PHP.9.9",
                                 "reason": "marker outside section span"}])
        self.assertIn("PHP-S1", rpt)
        self.assertIn("sets the frame", rpt)          # rationale surfaced
        self.assertIn("PHP.1.12", rpt)                # kept marker shown
        self.assertIn("outside section span", rpt)    # dropped note surfaced


def _valid_completion_php(order):
    # One section per pericope? No — make 2 contiguous sections covering all.
    secs = [{"title_en": "Opening: A", "first_pericope": order[0],
             "last_pericope": order[0], "marker": None, "rationale": "r1"},
            {"title_en": "Body: B", "first_pericope": order[1],
             "last_pericope": order[-1], "marker": None, "rationale": "r2"}]
    return json.dumps({"sections": secs})


class TestSeedOrchestrator(unittest.TestCase):
    def setUp(self):
        from content_bank.lib import corpus_bridge as cb
        self.order = [p["id"] for p in cb.pericopes("PHP")]
        # Credential/PATH guard is orthogonal to orchestration — neutralize it so
        # these tests never depend on ARK_API_KEY or a `claude` binary.
        g = mock.patch.object(ss, "_require_backend")
        g.start()
        self.addCleanup(g.stop)

    def test_happy_path_writes_staging(self):
        out = _pl.Path(tempfile.mkdtemp()) / "php.json"
        with mock.patch.object(ss, "llm",
                               return_value=_valid_completion_php(self.order)):
            res = ss.seed("PHP", backend="llm_core", out=out)
        self.assertTrue(out.exists())
        from corpus.lib import sections as csecs
        written = _json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(csecs.validate_data(written, self.order), [])
        self.assertEqual(written["sections"][0]["id"], "PHP-S1")

    def test_invalid_after_budget_writes_nothing(self):
        bad = json.dumps({"sections": [{"title_en": "only one",
                          "first_pericope": self.order[0],
                          "last_pericope": self.order[0], "marker": None}]})
        out = _pl.Path(tempfile.mkdtemp()) / "php.json"
        with mock.patch.object(ss, "llm", return_value=bad):
            with self.assertRaises(RuntimeError):
                ss.seed("PHP", backend="llm_core", max_repair=1, out=out)
        self.assertFalse(out.exists())          # nothing emitted

    def test_refuses_overwrite_without_force(self):
        out = _pl.Path(tempfile.mkdtemp()) / "php.json"
        out.write_text("{}", encoding="utf-8")
        with mock.patch.object(ss, "llm",
                               return_value=_valid_completion_php(self.order)):
            with self.assertRaises(FileExistsError):
                ss.seed("PHP", backend="llm_core", out=out)

    def test_default_out_is_staging(self):
        self.assertTrue(str(ss.DEFAULT_OUT("PHP")).replace("\\", "/")
                        .endswith("work/section_seeds/php.json"))
