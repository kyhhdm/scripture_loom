import json
import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.author import build_cli


class ParseItemsTest(unittest.TestCase):
    def test_strips_json_fence(self):
        text = 'Here you go:\n```json\n[{"id": "a"}]\n```\nDone.'
        self.assertEqual(build_cli._parse_items(text), [{"id": "a"}])

    def test_bare_array(self):
        self.assertEqual(build_cli._parse_items('[{"id":"b"}]'), [{"id": "b"}])

    def test_unparseable_raises(self):
        with self.assertRaises(ValueError):
            build_cli._parse_items("no json here")


class BackoffTest(unittest.TestCase):
    def test_retries_then_succeeds(self):
        calls = {"n": 0}

        def flaky(_p):
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("rate limit")
            return "ok"

        with mock.patch("content_bank.author.build_cli.llm", side_effect=flaky), \
             mock.patch("content_bank.author.build_cli.time.sleep"):
            out = build_cli._llm_with_backoff("p", tries=4)
        self.assertEqual(out, "ok")
        self.assertEqual(calls["n"], 3)

    def test_gives_up_after_tries(self):
        with mock.patch("content_bank.author.build_cli.llm",
                        side_effect=RuntimeError("rate limit")), \
             mock.patch("content_bank.author.build_cli.time.sleep"):
            with self.assertRaises(RuntimeError):
                build_cli._llm_with_backoff("p", tries=2)


class RepairLoopTest(unittest.TestCase):
    def _allowed(self):
        from content_bank.author import gates
        return gates.pericope_allowed("MAT", "MAT-035")

    def test_dirty_then_clean(self):
        good = json.dumps([dict(id="m-d1-a", dimension="D1", type="question",
                                age_tier="child", difficulty=1, review_status="draft",
                                version=1, passage="MAT-035",
                                text={"en": "Who came to Jesus?"})])
        bad = json.dumps([dict(id="m-d1-a", dimension="D9", type="question",
                               age_tier="child", difficulty=1, review_status="draft",
                               version=1, passage="MAT-035", text={"en": "x"})])
        seq = [bad, good]
        with mock.patch("content_bank.author.build_cli._llm_with_backoff",
                        side_effect=seq):
            items = build_cli._draft_with_repair("PROMPT", "MAT", self._allowed(),
                                                 max_repair=2)
        self.assertEqual(items[0]["dimension"], "D1")

    def test_never_clean_raises_gateerror(self):
        bad = json.dumps([dict(id="m-d1-a", dimension="D9", type="question",
                               age_tier="child", difficulty=1, review_status="draft",
                               version=1, passage="MAT-035", text={"en": "x"})])
        with mock.patch("content_bank.author.build_cli._llm_with_backoff",
                        return_value=bad):
            with self.assertRaises(build_cli.GateError):
                build_cli._draft_with_repair("PROMPT", "MAT", self._allowed(),
                                             max_repair=1)

    def _four_d2(self):
        return json.dumps([dict(id=f"m-d2-{i}", dimension="D2", type="question",
                                age_tier="child", difficulty=1, review_status="draft",
                                version=1, passage="MAT-035",
                                text={"en": "Then what happened next?"})
                           for i in range(4)])

    def test_soft_padding_only_logs_and_proceeds(self):
        # 4 D2 items = over cap 3, but schema/quote/ref clean (soft flag only).
        # After the repair budget the model still returns 4 -> must NOT raise.
        with mock.patch("content_bank.author.build_cli._llm_with_backoff",
                        return_value=self._four_d2()):
            items = build_cli._draft_with_repair("PROMPT", "MAT", self._allowed(),
                                                 max_repair=1, dim_cap=3)
        self.assertEqual(len(items), 4)  # returned, not raised

    def test_soft_padding_feeds_repair_then_clean(self):
        over = self._four_d2()
        clean = json.dumps([dict(id=f"m-d2-{i}", dimension="D2", type="question",
                                 age_tier="child", difficulty=1, review_status="draft",
                                 version=1, passage="MAT-035",
                                 text={"en": "Then what happened next?"})
                            for i in range(3)])
        with mock.patch("content_bank.author.build_cli._llm_with_backoff",
                        side_effect=[over, clean]):
            items = build_cli._draft_with_repair("PROMPT", "MAT", self._allowed(),
                                                 max_repair=2, dim_cap=3)
        self.assertEqual(len(items), 3)  # pruned to cap


import tempfile
from content_bank.author import manifest as manifest_mod


class OrchestratorTest(unittest.TestCase):
    def _draft_json(self, pid):
        return json.dumps([dict(id=f"{pid.lower()}-d1-a", dimension="D1",
                                type="question", age_tier="child", difficulty=1,
                                review_status="draft", version=1, passage=pid,
                                text={"en": "Who came to Jesus?"})])

    def test_pericope_writes_draft_and_bumps_stage(self):
        with tempfile.TemporaryDirectory() as d:
            drafts = pathlib.Path(d) / "drafts"
            briefs = pathlib.Path(d) / "briefs"
            m = manifest_mod.init_manifest("MAT", ["MAT-035"])
            mpath = pathlib.Path(d) / "manifest.json"
            manifest_mod.save(mpath, m)
            outputs = iter(["BRIEF TEXT", self._draft_json("MAT-035")])
            with mock.patch("content_bank.author.build_cli._llm_with_backoff",
                            side_effect=lambda *_a, **_k: next(outputs)):
                stage = build_cli.build_pericope(
                    "MAT-035", "MAT", drafts_dir=drafts, briefs_dir=briefs,
                    manifest_obj=m, manifest_path=mpath, review_on=False, max_repair=2)
            self.assertEqual(stage, "drafted")
            self.assertTrue((drafts / "MAT-035.json").exists())
            self.assertEqual(m["units"]["MAT-035"]["stage"], "drafted")

    def test_failure_isolated_stage_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            drafts = pathlib.Path(d) / "drafts"
            m = manifest_mod.init_manifest("MAT", ["MAT-035", "MAT-036"])
            mpath = pathlib.Path(d) / "manifest.json"
            manifest_mod.save(mpath, m)

            def boom(*_a, **_k):
                raise RuntimeError("llm exploded")

            with mock.patch("content_bank.author.build_cli._llm_with_backoff",
                            side_effect=boom):
                res = build_cli.run("MAT", units=["MAT-035"], kind="pericope",
                                    manifest_path=mpath, drafts_dir=drafts,
                                    briefs_dir=pathlib.Path(d) / "briefs")
            self.assertIn("MAT-035", res["failed"])
            self.assertEqual(m["units"]["MAT-035"]["stage"], "pending")

    def test_run_fails_fast_when_unconfigured(self):
        with mock.patch("content_bank.author.build_cli.llm_configured",
                        return_value=False):
            with self.assertRaises(build_cli.LLMUnavailable):
                build_cli.run("MAT", units=["MAT-035"])

    def test_claude_backend_skips_llm_core_config_gate(self):
        # backend=claude must NOT require ARK_API_KEY (subscription path);
        # llm_configured() is llm_core-specific and returns False here. Empty
        # work queue (unit already drafted) so no real build/LLM call happens.
        import os
        with tempfile.TemporaryDirectory() as d:
            m = manifest_mod.init_manifest("MAT", ["MAT-035"])
            manifest_mod.set_stage(m, "MAT-035", "drafted")
            mpath = pathlib.Path(d) / "manifest.json"
            manifest_mod.save(mpath, m)
            with mock.patch("content_bank.author.build_cli.llm_configured",
                            return_value=False), \
                 mock.patch("content_bank.author.build_cli.shutil.which",
                            return_value="/usr/bin/claude"):
                res = build_cli.run("MAT", kind="pericope", manifest_path=mpath,
                                    drafts_dir=pathlib.Path(d) / "drafts",
                                    backend="claude")
            self.assertEqual(res, {"ok": [], "failed": {}})
            self.assertEqual(os.environ.get("SCRIPTURE_LOOM_LLM_BACKEND"), "claude")
        os.environ.pop("SCRIPTURE_LOOM_LLM_BACKEND", None)

    def test_claude_backend_requires_cli_on_path(self):
        with mock.patch("content_bank.author.build_cli.shutil.which",
                        return_value=None):
            with self.assertRaises(build_cli.LLMUnavailable):
                build_cli.run("MAT", units=["MAT-035"], backend="claude")


class RunSlugTest(unittest.TestCase):
    def test_defaults_and_overrides(self):
        self.assertEqual(build_cli._run_slug("llm_core", None), "deepseek-v4-flash")
        self.assertEqual(build_cli._run_slug("llm_core", "deepseek-v4-pro"),
                         "deepseek-v4-pro")
        self.assertEqual(build_cli._run_slug("claude", None), "opus")
        self.assertEqual(build_cli._run_slug("claude", "Sonnet"), "sonnet")

    def test_slug_is_dir_safe(self):
        self.assertEqual(build_cli._run_slug("llm_core", "Weird/Model v2"),
                         "weird-model-v2")


class VerdictsByItemTest(unittest.TestCase):
    def test_reviewer_keyed_becomes_item_keyed(self):
        review_out = [
            {"reviewer": "r1", "verdicts": {"x": {"verdict": "pass", "notes": "ok"}}},
            {"reviewer": "r2", "verdicts": {"x": {"verdict": "fail", "notes": "D7"}}},
        ]
        by_item = build_cli._verdicts_by_item(review_out)
        self.assertEqual([v["reviewer"] for v in by_item["x"]], ["r1", "r2"])
        self.assertEqual(by_item["x"][1]["verdict"], "fail")
        self.assertEqual(by_item["x"][1]["notes"], "D7")


class SectionBuildTest(unittest.TestCase):
    def _throughline(self):
        return json.dumps([dict(id="php-s1-throughline", section="PHP-S1",
                                dimension="D7", type="throughline", age_tier="all",
                                difficulty=2, review_status="draft", version=1,
                                text={"en": "The section is about gospel partnership."})])

    def test_section_briefs_then_drafts_and_saves_verdicts(self):
        with tempfile.TemporaryDirectory() as d:
            drafts = pathlib.Path(d) / "drafts"
            briefs = pathlib.Path(d) / "briefs"
            verdicts = pathlib.Path(d) / "verdicts"
            m = manifest_mod.init_manifest("PHP", [], ["PHP-S1"])
            mpath = pathlib.Path(d) / "manifest.json"
            manifest_mod.save(mpath, m)
            seq = iter(["SECTION BRIEF TEXT", self._throughline()])
            r_pass = json.dumps({"php-s1-throughline": {"verdict": "pass", "notes": ""}})
            with mock.patch("content_bank.author.build_cli._llm_with_backoff",
                            side_effect=lambda *_a, **_k: next(seq)), \
                 mock.patch("content_bank.author.review.llm",
                            side_effect=[r_pass, r_pass]):
                stage = build_cli.build_section(
                    "PHP-S1", "PHP", drafts_dir=drafts, briefs_dir=briefs,
                    verdicts_dir=verdicts, manifest_obj=m, manifest_path=mpath,
                    review_on=True, max_repair=1)
            self.assertEqual(stage, "drafted")
            self.assertEqual((briefs / "php-s1.md").read_text(), "SECTION BRIEF TEXT")
            self.assertTrue((drafts / "PHP-S1.json").exists())
            saved = json.loads((verdicts / "PHP-S1.json").read_text())
            self.assertEqual([v["reviewer"] for v in saved["php-s1-throughline"]],
                             ["r1", "r2"])


class ReviewFlowTest(unittest.TestCase):
    def test_review_on_runs_review_then_regate_then_writes(self):
        with tempfile.TemporaryDirectory() as d:
            drafts = pathlib.Path(d) / "drafts"
            briefs = pathlib.Path(d) / "briefs"
            m = manifest_mod.init_manifest("MAT", ["MAT-035"])
            mpath = pathlib.Path(d) / "manifest.json"
            manifest_mod.save(mpath, m)
            clean = json.dumps([dict(id="mat-035-d1-a", dimension="D1",
                                     type="question", age_tier="child", difficulty=1,
                                     review_status="draft", version=1, passage="MAT-035",
                                     text={"en": "Who came to Jesus?"})])
            r_pass = json.dumps({"mat-035-d1-a": {"verdict": "pass", "notes": ""}})
            # _llm_with_backoff yields brief + draft; review.llm yields the two verdicts.
            seq = iter(["BRIEF", clean])
            with mock.patch("content_bank.author.build_cli._llm_with_backoff",
                            side_effect=lambda *_a, **_k: next(seq)), \
                 mock.patch("content_bank.author.review.llm",
                            side_effect=[r_pass, r_pass]):
                stage = build_cli.build_pericope(
                    "MAT-035", "MAT", drafts_dir=drafts, briefs_dir=briefs,
                    manifest_obj=m, manifest_path=mpath, review_on=True, max_repair=1)
            self.assertEqual(stage, "drafted")
            self.assertTrue((drafts / "MAT-035.json").exists())


if __name__ == "__main__":
    unittest.main()
