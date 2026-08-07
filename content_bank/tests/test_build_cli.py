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


class RepairPromptCitationHintTest(unittest.TestCase):
    def test_hint_added_only_for_citation_flags(self):
        items = [{"id": "x"}]
        with_cit = build_cli._repair_prompt(
            "P", items, {"x": ["citation.untagged_quote: 'a b c d' (PHP.1.6) ..."]})
        without = build_cli._repair_prompt(
            "P", items, {"x": ["schema: missing field"]})
        self.assertIn("Fixing citation.* flags", with_cit)
        self.assertIn("<verse ref=", with_cit)
        self.assertNotIn("Fixing citation.* flags", without)


def _result(text):
    from content_bank.author.telemetry import LLMResult, TokenUsage
    return LLMResult(text=text, usage=TokenUsage(), requested_model=None,
                     actual_model=None, stop_reason=None, duration_ms=1,
                     usage_source="local_estimate")


class BackoffTest(unittest.TestCase):
    def test_retries_then_succeeds(self):
        calls = {"n": 0}

        def flaky(_p, _route):
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("rate limit")
            return _result("ok")

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

    def test_claude_backend_requires_cli_on_path(self):
        with mock.patch("content_bank.author.build_cli.shutil.which",
                        return_value=None):
            with self.assertRaises(build_cli.LLMUnavailable):
                build_cli.run("MAT", units=["MAT-035"], backend="claude")


class RouteDrivenBuildTest(unittest.TestCase):
    def test_brief_and_draft_use_their_configured_models(self):
        from content_bank.author.routing import Route, RouteConfig
        clean_draft = json.dumps([dict(id="mat-035-d1-a", dimension="D1",
                                       type="question", age_tier="child",
                                       difficulty=1, review_status="draft",
                                       version=1, passage="MAT-035",
                                       text={"en": "Who came to Jesus?"})])
        seen = []

        def fake_llm(prompt, route):
            seen.append(route.model)
            return _result("brief text" if len(seen) == 1 else clean_draft)

        routes = RouteConfig(
            brief=Route("llm_core", "brief-m"), draft=Route("claude", "draft-m"),
            repair=Route("llm_core", "repair-m"), review_r1=Route("llm_core", "r1-m"),
            review_r2=Route("llm_core", "r2-m"), revise=Route("llm_core", "revise-m"))
        with tempfile.TemporaryDirectory() as d:
            m = manifest_mod.init_manifest("MAT", ["MAT-035"])
            mpath = pathlib.Path(d) / "manifest.json"
            manifest_mod.save(mpath, m)
            with mock.patch("content_bank.author.build_cli.llm", fake_llm), \
                 mock.patch("content_bank.author.build_cli.run_all", return_value={}), \
                 mock.patch("content_bank.author.gates.dimension_cap_check",
                            return_value={}):
                build_cli.build_pericope(
                    "MAT-035", "MAT", routes=routes,
                    drafts_dir=pathlib.Path(d) / "drafts",
                    briefs_dir=pathlib.Path(d) / "briefs",
                    manifest_obj=m, manifest_path=mpath, review_on=False)
        self.assertEqual(seen[0], "brief-m")
        self.assertEqual(seen[1], "draft-m")


class TelemetryCaptureTest(unittest.TestCase):
    def test_each_stage_records_a_callrecord(self):
        from content_bank.author.routing import RouteConfig
        from content_bank.author.telemetry import TelemetrySink
        clean_draft = json.dumps([dict(id="mat-035-d1-a", dimension="D1",
                                       type="question", age_tier="child",
                                       difficulty=1, review_status="draft",
                                       version=1, passage="MAT-035",
                                       text={"en": "Who came to Jesus?"})])
        seq = iter(["brief text", clean_draft])

        def fake_llm(prompt, route):
            return _result(next(seq))

        with tempfile.TemporaryDirectory() as d:
            sink = TelemetrySink(pathlib.Path(d) / "calls.jsonl")
            m = manifest_mod.init_manifest("MAT", ["MAT-035"])
            mpath = pathlib.Path(d) / "manifest.json"
            manifest_mod.save(mpath, m)
            with mock.patch("content_bank.author.build_cli.llm", fake_llm), \
                 mock.patch("content_bank.author.build_cli.run_all", return_value={}), \
                 mock.patch("content_bank.author.gates.dimension_cap_check",
                            return_value={}):
                build_cli.build_pericope(
                    "MAT-035", "MAT", routes=RouteConfig.single("llm_core", "m"),
                    drafts_dir=pathlib.Path(d) / "drafts",
                    briefs_dir=pathlib.Path(d) / "briefs",
                    manifest_obj=m, manifest_path=mpath, review_on=False,
                    sink=sink, experiment="exp1")
            records = list(sink.records())
        stages = {r["stage"] for r in records}
        self.assertIn("brief", stages)
        self.assertIn("draft", stages)
        for r in records:
            self.assertEqual(r["experiment"], "exp1")
            self.assertEqual(r["unit_id"], "MAT-035")
            self.assertEqual(r["backend"], "llm_core")
            self.assertTrue(r["prompt_hash"])
            self.assertNotIn("prompt", r)  # never the body, only a hash


class GateTraceTest(unittest.TestCase):
    def test_trace_records_initial_and_rounds(self):
        from content_bank.author.routing import RouteConfig
        bad = json.dumps([dict(id="mat-035-d1-a", dimension="D9", type="question",
                               age_tier="child", difficulty=1, review_status="draft",
                               version=1, passage="MAT-035", text={"en": "x"})])
        good = json.dumps([dict(id="mat-035-d1-a", dimension="D1", type="question",
                                age_tier="child", difficulty=1, review_status="draft",
                                version=1, passage="MAT-035",
                                text={"en": "Who came to Jesus?"})])
        seq = iter(["brief text", bad, good])  # brief, dirty draft, repaired

        def fake_llm(prompt, route):
            return _result(next(seq))

        with tempfile.TemporaryDirectory() as d:
            traces = pathlib.Path(d) / "gate_traces"
            m = manifest_mod.init_manifest("MAT", ["MAT-035"])
            mpath = pathlib.Path(d) / "manifest.json"
            manifest_mod.save(mpath, m)
            with mock.patch("content_bank.author.build_cli.llm", fake_llm):
                build_cli.build_pericope(
                    "MAT-035", "MAT", routes=RouteConfig.single("llm_core", "m"),
                    drafts_dir=pathlib.Path(d) / "drafts",
                    briefs_dir=pathlib.Path(d) / "briefs",
                    manifest_obj=m, manifest_path=mpath, review_on=False,
                    max_repair=2, gate_trace_dir=traces)
            trace = json.loads((traces / "MAT-035.json").read_text())
        self.assertFalse(trace["first_pass_clean"])
        self.assertGreaterEqual(len(trace["rounds"]), 1)
        self.assertTrue(trace["final_pass"])


class RawDraftReuseTest(unittest.TestCase):
    def _clean(self, pid):
        return json.dumps([dict(id=f"{pid.lower()}-d1-a", dimension="D1",
                                type="question", age_tier="child", difficulty=1,
                                review_status="draft", version=1, passage=pid,
                                text={"en": "Who came to Jesus?"})])

    def test_persists_raw_draft_then_reuse_skips_brief_and_draft(self):
        from content_bank.author.routing import RouteConfig
        with tempfile.TemporaryDirectory() as d:
            src = pathlib.Path(d) / "src"
            seq = iter(["brief text", self._clean("MAT-035")])  # brief, then draft
            calls = []

            def fake_llm(prompt, route):
                calls.append(route.model)
                return _result(next(seq))

            m = manifest_mod.init_manifest("MAT", ["MAT-035"])
            mp = src / "manifest.json"
            manifest_mod.save(mp, m)
            r_pass = _result(json.dumps({"mat-035-d1-a": {"verdict": "pass",
                                                          "notes": ""}}))
            with mock.patch("content_bank.author.build_cli.llm", fake_llm), \
                 mock.patch("content_bank.author.review.llm",
                            side_effect=[r_pass, r_pass]):
                build_cli.build_pericope(
                    "MAT-035", "MAT", routes=RouteConfig.single("llm_core"),
                    drafts_dir=src / "drafts", briefs_dir=src / "briefs",
                    verdicts_dir=src / "verdicts", raw_drafts_dir=src / "raw_drafts",
                    manifest_obj=m, manifest_path=mp, review_on=True, max_repair=1)
            # raw pre-review draft was persisted
            self.assertTrue((src / "raw_drafts" / "MAT-035.json").exists())
            n_calls_first = len(calls)
            self.assertGreaterEqual(n_calls_first, 2)  # brief + draft happened

            # Now REUSE: a second experiment reads src's brief+raw draft, no build_cli.llm
            dst = pathlib.Path(d) / "dst"
            m2 = manifest_mod.init_manifest("MAT", ["MAT-035"])
            mp2 = dst / "manifest.json"
            manifest_mod.save(mp2, m2)

            def boom(prompt, route):
                raise AssertionError("reuse must not call the draft/brief seam")

            with mock.patch("content_bank.author.build_cli.llm", boom), \
                 mock.patch("content_bank.author.review.llm",
                            side_effect=[r_pass, r_pass]):
                stage = build_cli.build_pericope(
                    "MAT-035", "MAT", routes=RouteConfig.single("llm_core"),
                    drafts_dir=dst / "drafts", briefs_dir=dst / "briefs",
                    verdicts_dir=dst / "verdicts", reuse_dir=src,
                    manifest_obj=m2, manifest_path=mp2, review_on=True, max_repair=1)
            self.assertEqual(stage, "drafted")
            self.assertTrue((dst / "drafts" / "MAT-035.json").exists())
            self.assertEqual((dst / "briefs" / "mat-035.md").read_text(), "brief text")


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
        # A section throughline is now a discovery question carrying its spine as a
        # D7 leader_note reveal (section_reveal_check enforces the pairing); without
        # it the gate would flag the item and drive an extra repair-loop llm call.
        return json.dumps([dict(id="php-s1-throughline", section="PHP-S1",
                                dimension="D7", type="throughline", age_tier="all",
                                difficulty=2, review_status="draft", version=1,
                                text={"en": "Where does this section's partnership lead?"},
                                leader_reference=dict(
                                    kind="leader_note",
                                    text={"en": "The section is about gospel partnership."},
                                    provenance=dict(reviewed_by="test",
                                                    reviewed_date="2026-07-29",
                                                    guardrail="WCF-1")))])

    def test_section_briefs_then_drafts_and_saves_verdicts(self):
        with tempfile.TemporaryDirectory() as d:
            drafts = pathlib.Path(d) / "drafts"
            briefs = pathlib.Path(d) / "briefs"
            verdicts = pathlib.Path(d) / "verdicts"
            m = manifest_mod.init_manifest("PHP", [], ["PHP-S1"])
            mpath = pathlib.Path(d) / "manifest.json"
            manifest_mod.save(mpath, m)
            seq = iter(["SECTION BRIEF TEXT", self._throughline()])
            r_pass = _result(json.dumps(
                {"php-s1-throughline": {"verdict": "pass", "notes": ""}}))
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


class DraftStampTest(unittest.TestCase):
    def test_stamps_model_run_onto_draft_items(self):
        items = build_cli._stamp_draft_provenance(
            [{"id": "a"}, {"id": "b", "provenance": {"note": "x"}}],
            {"model": "opus", "backend": "claude", "run": "opus"})
        self.assertEqual(items[0]["provenance"],
                         {"model": "opus", "backend": "claude", "run": "opus"})
        # merges into any existing provenance rather than clobbering it.
        self.assertEqual(items[1]["provenance"]["note"], "x")
        self.assertEqual(items[1]["provenance"]["model"], "opus")

    def test_no_stamp_when_meta_absent(self):
        items = build_cli._stamp_draft_provenance([{"id": "a"}], None)
        self.assertNotIn("provenance", items[0])

    def test_run_writes_draft_with_model_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            drafts = pathlib.Path(d) / "drafts"
            m = manifest_mod.init_manifest("MAT", ["MAT-035"])
            mpath = pathlib.Path(d) / "manifest.json"
            manifest_mod.save(mpath, m)
            draft = json.dumps([dict(id="mat-035-d1-a", dimension="D1",
                                     type="question", age_tier="child", difficulty=1,
                                     review_status="draft", version=1, passage="MAT-035",
                                     text={"en": "Who came to Jesus?"})])
            with mock.patch("content_bank.author.build_cli._llm_with_backoff",
                            side_effect=iter(["BRIEF", draft])), \
                 mock.patch("content_bank.author.build_cli.llm_configured",
                            return_value=True):
                build_cli.run("MAT", units=["MAT-035"], kind="pericope",
                              manifest_path=mpath, drafts_dir=drafts,
                              briefs_dir=pathlib.Path(d) / "briefs", review_on=False,
                              model="deepseek-v4-pro")
            saved = json.loads((drafts / "MAT-035.json").read_text())
            self.assertEqual(saved[0]["provenance"]["model"], "deepseek-v4-pro")
            self.assertEqual(saved[0]["provenance"]["run"], "deepseek-v4-pro")


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
            r_pass = _result(json.dumps({"mat-035-d1-a": {"verdict": "pass",
                                                          "notes": ""}}))
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
