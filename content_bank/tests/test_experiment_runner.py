import json
import pathlib
import tempfile
import unittest
from unittest import mock

from content_bank.author import experiment_cli as ex

CONFIG = {
    "schema_version": 1, "name": "t1", "book": "PHP", "units": ["PHP-001"],
    "routes": {s: {"backend": "llm_core", "model": "m"} for s in
               ("brief", "draft", "repair", "review_r1", "review_r2", "revise")},
    "gates": {"max_repair": 2, "dim_cap": 6},
    "evaluator": {"backend": "llm_core", "model": "m"},
}


class RunnerTest(unittest.TestCase):
    def _write_cfg(self, d):
        p = pathlib.Path(d) / "t1.json"
        p.write_text(json.dumps(CONFIG))
        return p

    def test_run_writes_manifest_and_passes_routes(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._write_cfg(d)
            with mock.patch("content_bank.author.build_cli.run",
                            return_value={"ok": ["PHP-001"], "failed": {}}) as run, \
                 mock.patch("content_bank.author.quality_eval.evaluate",
                            return_value={"runs": {}}), \
                 mock.patch("content_bank.author.experiment_cli._seed_run_manifest"):
                man = ex.run_experiment(cfg, out_root=d + "/out",
                                        now="2026-07-31T00:00:00Z", corpus_rev="abc")
            out = pathlib.Path(d) / "out" / "t1"
            self.assertTrue((out / "manifest.json").exists())
            self.assertTrue((out / "report.json").exists())
            self.assertIn("config_hash", man)
            self.assertEqual(man["corpus_rev"], "abc")
            self.assertEqual(man["route_matrix"]["evaluate"]["backend"], "llm_core")
            run.assert_called_once()
            self.assertIn("routes", run.call_args.kwargs)
            self.assertEqual(run.call_args.kwargs["experiment"], "t1")

    def test_resume_refuses_changed_config(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._write_cfg(d)
            out = pathlib.Path(d) / "out" / "t1"
            out.mkdir(parents=True)
            (out / "manifest.json").write_text(json.dumps({"config_hash": "DIFFERENT"}))
            with self.assertRaises(ValueError):
                ex.run_experiment(cfg, out_root=d + "/out",
                                  now="2026-07-31T00:00:00Z", corpus_rev="abc")

    def test_identical_config_resumes(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._write_cfg(d)
            h = __import__("content_bank.author.experiment_config", fromlist=["x"]) \
                .config_hash(CONFIG, corpus_rev="abc", prompt_version="1")
            out = pathlib.Path(d) / "out" / "t1"
            out.mkdir(parents=True)
            (out / "manifest.json").write_text(json.dumps({"config_hash": h}))
            with mock.patch("content_bank.author.build_cli.run",
                            return_value={"ok": [], "failed": {}}), \
                 mock.patch("content_bank.author.quality_eval.evaluate",
                            return_value={"runs": {}}), \
                 mock.patch("content_bank.author.experiment_cli._seed_run_manifest"):
                man = ex.run_experiment(cfg, out_root=d + "/out", resume=True,
                                        now="2026-07-31T00:00:00Z", corpus_rev="abc")
            self.assertEqual(man["config_hash"], h)

    def test_multibook_runs_each_book_once(self):
        cfg_dict = {k: v for k, v in CONFIG.items() if k != "book"}
        cfg_dict["name"] = "mb"
        cfg_dict["units"] = ["PHP-002", "JON-002", "PHP-005"]
        with tempfile.TemporaryDirectory() as d:
            cfg = pathlib.Path(d) / "mb.json"
            cfg.write_text(json.dumps(cfg_dict))
            with mock.patch("content_bank.author.build_cli.run",
                            return_value={"ok": [], "failed": {}}) as run, \
                 mock.patch("content_bank.author.quality_eval.evaluate",
                            return_value={"runs": {}}), \
                 mock.patch("content_bank.author.experiment_cli._seed_run_manifest"):
                man = ex.run_experiment(cfg, out_root=d + "/out",
                                        now="2026-07-31T00:00:00Z", corpus_rev="abc")
            books = {c.args[0] for c in run.call_args_list}
            units_for = {c.args[0]: c.kwargs["units"] for c in run.call_args_list}
            self.assertEqual(books, {"PHP", "JON"})
            self.assertEqual(units_for["PHP"], ["PHP-002", "PHP-005"])
            self.assertEqual(units_for["JON"], ["JON-002"])
            self.assertEqual(man["books"], ["JON", "PHP"])
            self.assertIsNone(man["book"])

    def test_translate_experiment_walks_books_and_writes_proposals(self):
        with tempfile.TemporaryDirectory() as d:
            out = pathlib.Path(d) / "out" / "gp"
            # Minimal experiment: manifest with two books + a draft file each.
            manifest = {"name": "gp", "books": ["PHP", "JON"],
                        "config": {"translate": {"backend": "llm_core",
                                                 "model": "deepseek-v4-flash"}}}
            (out).mkdir(parents=True)
            (out / "manifest.json").write_text(json.dumps(manifest))
            for book, unit in (("PHP", "PHP-002"), ("JON", "JON-002")):
                dd = out / book / "runs" / "gp" / "drafts"
                dd.mkdir(parents=True)
                (dd / f"{unit}.json").write_text(json.dumps(
                    [{"id": f"{unit}-i1", "text": {"en": "Q?"}}]))
            calls = []

            def fake_run_proposals(items, book, **kw):
                calls.append((book, kw.get("route").model, kw.get("sink") is not None))
                return [{"id": items[0]["id"], "item": items[0], "gate_ok": True,
                         "gate_flags": [], "drift": {"drift": False}, "cuv_refs": [],
                         "terms": [], "uncertain": [], "en": "Q?"}]

            with mock.patch("content_bank.author.translate_cli.run_proposals",
                            side_effect=fake_run_proposals), \
                 mock.patch("content_bank.author.glossary.load_glossary",
                            return_value=[]):
                res = ex.translate_experiment("gp", out_root=str(pathlib.Path(d) / "out"))
            self.assertEqual({b for b, _, _ in calls}, {"PHP", "JON"})
            self.assertTrue(all(model == "deepseek-v4-flash" for _, model, _ in calls))
            self.assertTrue(all(has_sink for _, _, has_sink in calls))
            self.assertEqual(res["translate_model"], "deepseek-v4-flash")
            prop = (out / "PHP" / "runs" / "gp" / "translations"
                    / "deepseek-v4-flash" / "PHP-002-i1.json")
            self.assertTrue(prop.exists())

    def test_books_across_discovers_and_filters(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            # exp gp spans PHP+JON; baseline php only PHP.
            for name, books in (("gp", ["PHP", "JON"]), ("php_base", ["PHP"])):
                ed = root / name
                ed.mkdir(parents=True)
                (ed / "manifest.json").write_text(json.dumps(
                    {"name": name, "books": books}))
                for b in books:
                    (ed / b / "runs" / name / "drafts").mkdir(parents=True)
            gp, php = root / "gp", root / "php_base"
            self.assertEqual(ex._books_across([gp, php], None), ["JON", "PHP"])
            self.assertEqual(ex._books_across([gp, php], "PHP"), ["PHP"])
            self.assertTrue(ex._experiment_has_book(php, "PHP"))
            self.assertFalse(ex._experiment_has_book(php, "JON"))

    def test_compare_filename_reflects_inputs(self):
        # single output file named from the experiment list (+ book when narrowed)
        self.assertEqual(
            ex._compare_filename("compare", ["a", "b"], ["PHP", "JON"]),
            "compare_a__b.html")
        self.assertEqual(
            ex._compare_filename("compare", ["a", "b"], ["PHP"]),
            "compare_a__b__PHP.html")
        long = [f"experiment_number_{i}" for i in range(9)]
        self.assertTrue(
            ex._compare_filename("compare", long, ["PHP"]).startswith(
                "compare_experiment_number_0__and_8_more"))

    def test_evaluate_fit_runs_independent_judge_on_units(self):
        with tempfile.TemporaryDirectory() as d:
            out = pathlib.Path(d) / "out" / "php_opus_baseline"
            out.mkdir(parents=True)
            (out / "manifest.json").write_text(json.dumps({
                "name": "php_opus_baseline", "books": ["PHP"],
                "config": {"routes": {s: {"backend": "claude", "model": "opus"}
                                     for s in ("brief", "draft", "repair",
                                               "review_r1", "review_r2", "revise")},
                           "evaluator": {"backend": "claude", "model": "opus"}}}))
            seen = {}

            def fake_eval(book, runs, **kw):
                seen["units"] = kw.get("units")
                seen["evaluator"] = kw.get("evaluator_route")
                return {"runs": {"php_opus_baseline": {"units": {"PHP-002": {
                    "dimension_fit": {"status_counts": {"accurate": 3, "mixed": 0,
                                                        "misclassified": 1},
                                      "adjusted_missing_dimensions": ["D5"]}}},
                    "aggregate": {}}}}

            with mock.patch("content_bank.author.quality_eval.evaluate",
                            side_effect=fake_eval):
                rep = ex.evaluate_experiment(
                    "php_opus_baseline", out_root=str(pathlib.Path(d) / "out"),
                    fit=True, fit_route=ex.Route("llm_core", "gemini-3.6-flash"),
                    units=["PHP-002"])
            # ran the independent judge (gemini), not the config's opus evaluator
            self.assertEqual(seen["evaluator"].model, "gemini-3.6-flash")
            self.assertEqual(seen["units"], ["PHP-002"])
            # report.json rewritten with the fit results + independence flag
            written = json.loads((out / "report.json").read_text())
            self.assertFalse(written["metrics"]["evaluator_is_drafter"])
            self.assertEqual(written["metrics"]["evaluator"]["fit_misclassified"], 1)

    def test_snapshot_reports_unavailable_honestly(self):
        snap = ex._subscription_snapshot()
        self.assertFalse(snap["available"])
        self.assertIn("reason", snap)

    def test_validate_rejects_credential_leak(self):
        from content_bank.author import experiment_config as ec
        bad = {**CONFIG, "routes": {**CONFIG["routes"],
               "draft": {"backend": "claude", "token": "x"}}}
        with self.assertRaises(ValueError):
            ec.validate(bad)


if __name__ == "__main__":
    unittest.main()
