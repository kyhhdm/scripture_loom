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
