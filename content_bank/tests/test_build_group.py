import json
import tempfile
import unittest
from unittest import mock

import pathlib

from content_bank.author import build_group, manifest as manifest_mod, routing
from content_bank.author.telemetry import LLMResult, TokenUsage
from content_bank.lib import corpus_bridge


def _seed_canonical_manifest(run_root, book):
    """Write the canonical book manifest _load_run_manifest seeds each run from."""
    groups = build_group.groups_for_book(book)
    pericopes = [p for _, pids in groups for p in pids]
    sections = [sid for sid, _ in groups]
    m = manifest_mod.init_manifest(book, pericopes, sections)
    manifest_mod.save(pathlib.Path(run_root) / book / "manifest.json", m)


def _res(text, stop="end_turn"):
    return LLMResult(text=text, usage=TokenUsage(), requested_model="opus",
                     actual_model="opus", stop_reason=stop, duration_ms=1,
                     usage_source="provider")


class TestGroupsForBook(unittest.TestCase):
    def test_php_groups_partition_pericopes(self):
        groups = build_group.groups_for_book("PHP")
        self.assertTrue(groups)
        for sid, pids in groups:
            self.assertTrue(sid.startswith("PHP-S"))
            self.assertTrue(all(p.startswith("PHP-") and "-S" not in p for p in pids))
        all_peris = [p["id"] for p in corpus_bridge.pericopes("PHP")]
        seen = [p for _, pids in groups for p in pids]
        self.assertEqual(sorted(seen), sorted(all_peris))


class TestParseUnits(unittest.TestCase):
    def test_valid_envelope(self):
        text = '```json\n{"units": {"A": [1], "B": [2]}}\n```'
        self.assertEqual(build_group.parse_units(text, ["A", "B"]),
                         {"A": [1], "B": [2]})

    def test_missing_unit_raises_truncated(self):
        with self.assertRaises(build_group.Truncated):
            build_group.parse_units('{"units": {"A": [1]}}', ["A", "B"])

    def test_unparseable_raises_truncated(self):
        with self.assertRaises(build_group.Truncated):
            build_group.parse_units('{"units": {"A": [1', ["A"])


class TestGroupCall(unittest.TestCase):
    def test_group_call_returns_units(self):
        env = '{"units": {"A": [1], "B": [2]}}'
        with mock.patch("content_bank.author.build_group.llm",
                        return_value=_res(env)) as m:
            out = build_group.group_call(lambda ids: "P:" + ",".join(ids),
                                         ["A", "B"],
                                         route=routing.Route("claude", "opus"))
            self.assertEqual(out, {"A": [1], "B": [2]})
            self.assertEqual(m.call_count, 1)

    def test_group_call_bisects_on_truncation(self):
        def fake(prompt, route):
            ids = prompt.split("P:")[1].split(",")
            if len(ids) > 1:
                return _res('{"units": {}}', stop="max_tokens")
            u = ids[0]
            return _res(json.dumps({"units": {u: [u]}}))
        with mock.patch("content_bank.author.build_group.llm", side_effect=fake) as m:
            out = build_group.group_call(lambda ids: "P:" + ",".join(ids),
                                         ["A", "B"],
                                         route=routing.Route("claude", "opus"))
            self.assertEqual(out, {"A": ["A"], "B": ["B"]})
            self.assertGreaterEqual(m.call_count, 3)

    def test_group_call_singleton_truncation_raises(self):
        with mock.patch("content_bank.author.build_group.llm",
                        return_value=_res('{"units": {}}', stop="max_tokens")):
            with self.assertRaises(build_group.Truncated):
                build_group.group_call(lambda ids: "P:" + ",".join(ids), ["A"],
                                       route=routing.Route("claude", "opus"))


class TestDraftChunking(unittest.TestCase):
    def test_draft_chunks_uncapped(self):
        ids = ["a", "b", "c"]
        for bs in (None, 0, -1, 3, 9):
            self.assertEqual(build_group._draft_chunks(ids, bs), [ids])

    def test_draft_chunks_capped(self):
        ids = ["a", "b", "c", "d", "e", "f"]
        self.assertEqual(build_group._draft_chunks(ids, 4),
                         [["a", "b", "c", "d"], ["e", "f"]])

    def test_group_draft_items_issues_one_call_per_chunk(self):
        ids = ["u0", "u1", "u2", "u3", "u4", "u5"]
        seen = []

        def fake_group_call(build_prompt, chunk, **kw):
            seen.append(list(chunk))
            return {u: [u] for u in chunk}
        with mock.patch.object(build_group, "group_call",
                               side_effect=fake_group_call):
            out = build_group.group_draft_items(
                ids, "PHP", {u: "b" for u in ids},
                route=routing.Route("claude", "opus"), batch_size=4)
        self.assertEqual(seen, [["u0", "u1", "u2", "u3"], ["u4", "u5"]])
        self.assertEqual(set(out), set(ids))         # all units merged back

    def test_group_draft_items_uncapped_single_call(self):
        ids = ["u0", "u1", "u2", "u3", "u4", "u5"]
        calls = {"n": 0}

        def fake_group_call(build_prompt, chunk, **kw):
            calls["n"] += 1
            return {u: [u] for u in chunk}
        with mock.patch.object(build_group, "group_call",
                               side_effect=fake_group_call):
            build_group.group_draft_items(
                ids, "PHP", {u: "b" for u in ids},
                route=routing.Route("claude", "opus"), batch_size=0)
        self.assertEqual(calls["n"], 1)


class TestBuildGroupStages(unittest.TestCase):
    def test_drafts_gate_each_unit(self):
        ids = ["PHP-S1", "PHP-001"]
        briefs = {u: "brief-" + u for u in ids}
        drafts_env = {u: [{"id": u + "-1"}] for u in ids}
        with mock.patch.object(build_group, "group_call", return_value=drafts_env), \
             mock.patch("content_bank.author.build_cli.run_all", return_value={}), \
             mock.patch("content_bank.author.gates.dimension_cap_check",
                        return_value={}):
            out = build_group.build_group_drafts(
                ids, "PHP", briefs,
                routes=routing.RouteConfig.single("claude", "opus"), max_repair=0)
            self.assertEqual(set(out), set(ids))
            self.assertEqual(out["PHP-001"], [{"id": "PHP-001-1"}])


def _stage_llm(counter):
    """A fake llm that answers each batched stage by sniffing its header."""
    def fake(prompt, route):
        counter["n"] += 1
        if "GROUP BRIEF BATCH" in prompt:
            units = {"PHP-S1": "arc", "PHP-001": "peri"}
        elif "GROUP DRAFT BATCH" in prompt:
            units = {"PHP-S1": [{"id": "php-s1-throughline"}],
                     "PHP-001": [{"id": "PHP-001-1"}]}
        else:  # review lenses / revise
            units = {"PHP-S1": {}, "PHP-001": {}}
        return _res(json.dumps({"units": units}))
    return fake


class TestGroupRun(unittest.TestCase):
    def test_one_group_uses_batched_calls(self):
        counter = {"n": 0}
        fake = _stage_llm(counter)
        with tempfile.TemporaryDirectory() as d, \
             mock.patch("content_bank.author.build_group.llm", side_effect=fake), \
             mock.patch("content_bank.author.build_cli.run_all", return_value={}), \
             mock.patch("content_bank.author.gates.dimension_cap_check",
                        return_value={}), \
             mock.patch("content_bank.author.review.llm", side_effect=fake), \
             mock.patch("content_bank.author.build_cli._check_routes_available"):
            _seed_canonical_manifest(d, "PHP")
            res = build_group.group_run("PHP", units=["PHP-S1"], review_on=True,
                                        run_root=d, backend="claude", model="opus")
        self.assertIn("PHP-001", res["ok"])
        self.assertIn("PHP-S1", res["ok"])
        self.assertFalse(res["failed"])
        # 1 brief + 1 draft + 2 review = 4 (no revise: nothing failed).
        self.assertLessEqual(counter["n"], 4)

    def test_already_drafted_units_skipped(self):
        counter = {"n": 0}
        fake = _stage_llm(counter)
        with tempfile.TemporaryDirectory() as d, \
             mock.patch("content_bank.author.build_group.llm", side_effect=fake), \
             mock.patch("content_bank.author.build_cli.run_all", return_value={}), \
             mock.patch("content_bank.author.gates.dimension_cap_check",
                        return_value={}), \
             mock.patch("content_bank.author.review.llm", side_effect=fake), \
             mock.patch("content_bank.author.build_cli._check_routes_available"):
            _seed_canonical_manifest(d, "PHP")
            # First run drafts the whole group.
            build_group.group_run("PHP", units=["PHP-S1"], review_on=False,
                                  run_root=d, backend="claude", model="opus")
            first = counter["n"]
            self.assertGreater(first, 0)
            # Second run: everything already drafted -> no new llm calls.
            res2 = build_group.group_run("PHP", units=["PHP-S1"], review_on=False,
                                         run_root=d, backend="claude", model="opus")
        self.assertEqual(counter["n"], first)
        self.assertEqual(res2["ok"], [])


class TestGroupRunExplicitDirs(unittest.TestCase):
    def test_explicit_dirs_and_gate_traces(self):
        counter = {"n": 0}
        fake = _stage_llm(counter)
        with tempfile.TemporaryDirectory() as d, \
             mock.patch("content_bank.author.build_group.llm", side_effect=fake), \
             mock.patch("content_bank.author.build_cli.run_all", return_value={}), \
             mock.patch("content_bank.author.gates.dimension_cap_check",
                        return_value={}), \
             mock.patch("content_bank.author.review.llm", side_effect=fake), \
             mock.patch("content_bank.author.build_cli._check_routes_available"):
            base = pathlib.Path(d)
            run_rel = base / "PHP" / "runs" / "exp1"
            mpath = run_rel / "manifest.json"
            # seed the run manifest the experiment runner would create
            groups = build_group.groups_for_book("PHP")
            m = manifest_mod.init_manifest(
                "PHP", [p for _, pids in groups for p in pids],
                [sid for sid, _ in groups])
            manifest_mod.save(mpath, m)
            res = build_group.group_run(
                "PHP", units=["PHP-S1"], review_on=True, backend="claude",
                model="opus", manifest_path=mpath, drafts_dir=run_rel / "drafts",
                briefs_dir=run_rel / "briefs", verdicts_dir=run_rel / "verdicts",
                gate_trace_dir=base / "gate_traces")
            self.assertIn("PHP-001", res["ok"])
            # drafts written to the EXPLICIT dir, not runs/<slug>/
            self.assertTrue((run_rel / "drafts" / "PHP-001.json").exists())
            # gate traces written per unit with the report's required keys
            trace = json.loads(
                (base / "gate_traces" / "PHP-001.json").read_text())
            self.assertIn("first_pass_clean", trace)
            self.assertIn("final_pass", trace)


class TestCliGroupDispatch(unittest.TestCase):
    def test_group_flag_calls_group_run(self):
        from content_bank.author import build_cli
        with mock.patch("content_bank.author.build_group.group_run",
                        return_value={"ok": ["PHP-S1"], "failed": {}}) as g:
            rc = build_cli.main(["--book", "PHP", "--group", "--backend", "claude",
                                 "--model", "opus", "--units", "PHP-S1"])
        self.assertEqual(rc, 0)
        g.assert_called_once()
        self.assertEqual(g.call_args.kwargs["draft_batch_size"], 4)  # default

    def test_group_flag_passes_draft_batch_size(self):
        from content_bank.author import build_cli
        with mock.patch("content_bank.author.build_group.group_run",
                        return_value={"ok": ["PHP-S1"], "failed": {}}) as g:
            build_cli.main(["--book", "PHP", "--group", "--units", "PHP-S1",
                            "--draft-batch-size", "2"])
        self.assertEqual(g.call_args.kwargs["draft_batch_size"], 2)


if __name__ == "__main__":
    unittest.main()
