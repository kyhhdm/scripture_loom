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
