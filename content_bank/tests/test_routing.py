import unittest

from content_bank.author.routing import Route, RouteConfig, STAGES


class RoutingTest(unittest.TestCase):
    def test_single_fills_every_stage_with_same_route(self):
        rc = RouteConfig.single("claude", "opus")
        for stage in STAGES:
            r = getattr(rc, stage)
            self.assertEqual((r.backend, r.model), ("claude", "opus"))

    def test_single_default_model_is_none(self):
        rc = RouteConfig.single("llm_core")
        self.assertIsNone(rc.draft.model)

    def test_from_experiment_maps_each_stage(self):
        rc = RouteConfig.from_experiment({
            "brief": {"backend": "llm_core", "model": "gemini-3.6-flash"},
            "draft": {"backend": "claude", "model": "opus",
                      "settings": {"effort": "high"}},
            "repair": {"backend": "claude", "model": "sonnet"},
            "review_r1": {"backend": "llm_core", "model": "gemini-3.6-flash"},
            "review_r2": {"backend": "llm_core", "model": "gemini-3.6-flash"},
            "revise": {"backend": "claude", "model": "sonnet"},
        })
        self.assertEqual(rc.draft.model, "opus")
        self.assertEqual(rc.draft.settings, {"effort": "high"})
        self.assertEqual(rc.review_r1.backend, "llm_core")

    def test_from_experiment_rejects_missing_stage(self):
        with self.assertRaises(ValueError):
            RouteConfig.from_experiment({"brief": {"backend": "llm_core"}})

    def test_stages_constant(self):
        self.assertEqual(
            STAGES,
            ("brief", "draft", "repair", "review_r1", "review_r2", "revise"))


if __name__ == "__main__":
    unittest.main()
