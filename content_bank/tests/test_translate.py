import unittest
from unittest import mock
from content_bank.author import translate
from content_bank.author.routing import Route

ITEM = {"id": "PHP-001-D1-01", "passage": "PHP.1.1-11", "dimension": "D1",
        "type": "question", "review_status": "reviewed",
        "text": {"en": "Who are the servants of Christ Jesus?"},
        "leader_reference": {"kind": "answer_key",
                             "text": {"en": "Paul and Timothy."},
                             "verse": {"en": "Philippians 1:1"}}}

LLM_JSON = ('{"text": {"zh": "谁是「基督耶稣的仆人」？"},'
            ' "leader_reference": {"text": {"zh": "保罗和提摩太。"},'
            ' "verse": {"zh": "腓立比书 1:1"}},'
            ' "terms": [{"en": "saints", "zh": "圣徒"}],'
            ' "uncertain": []}')


class TestTranslateSeamRouting(unittest.TestCase):
    def test_route_reaches_seam_and_sink_records(self):
        import pathlib
        import tempfile
        from content_bank.author.telemetry import (LLMResult, TelemetrySink,
                                                    TokenUsage)
        seen = {}

        def fake_llm(prompt, route):
            seen["model"] = route.model
            return LLMResult(text=LLM_JSON, usage=TokenUsage(input=5, output=9),
                             requested_model=route.model, actual_model=route.model,
                             stop_reason=None, duration_ms=1, usage_source="provider")

        with tempfile.TemporaryDirectory() as d:
            sink = TelemetrySink(pathlib.Path(d) / "calls.jsonl")
            with mock.patch.object(translate, "llm", fake_llm):
                translate.translate_item(ITEM, "PHP", glossary=[],
                                         route=Route("llm_core", "flash"),
                                         sink=sink, attr={"experiment": "e",
                                                          "unit_id": "PHP-001-D1-01"})
            records = list(sink.records())
        self.assertEqual(seen["model"], "flash")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["stage"], "translate")
        self.assertEqual(records[0]["unit_id"], "PHP-001-D1-01")


class TestTranslateItem(unittest.TestCase):
    def test_merges_zh_preserves_en_and_structured(self):
        with mock.patch.object(translate, "llm", return_value=LLM_JSON):
            out = translate.translate_item(ITEM, "PHP", glossary=[])
        item = out["item"]
        self.assertEqual(item["text"]["zh"], "谁是「基督耶稣的仆人」？")
        self.assertEqual(item["text"]["en"], ITEM["text"]["en"])  # unchanged
        self.assertEqual(item["leader_reference"]["text"]["zh"], "保罗和提摩太。")
        self.assertEqual(item["id"], ITEM["id"])                  # structured intact
        self.assertEqual(item["review_status"], "reviewed")
        self.assertEqual(out["terms"], [{"en": "saints", "zh": "圣徒"}])
        # original item object not mutated
        self.assertNotIn("zh", ITEM["text"])

    def test_merges_category_zh(self):
        item = {"id": "PHP-001-D1-03", "passage": "PHP.1.1-11", "dimension": "D1",
                "type": "pre_reading_quest",
                "text": {"en": "Who is named?"},
                "category": {"en": "People & roles"}}
        resp = ('{"text": {"zh": "谁被提名？"}, '
                '"category": {"zh": "人物与角色"}, "terms": [], "uncertain": []}')
        with mock.patch.object(translate, "llm", return_value=resp):
            out = translate.translate_item(item, "PHP", glossary=[])
        self.assertEqual(out["item"]["category"]["zh"], "人物与角色")
        self.assertEqual(out["item"]["category"]["en"], "People & roles")  # kept
        self.assertNotIn("zh", item["category"])  # original not mutated

    def test_applicable_glossary_filters_by_english(self):
        gloss = [{"en_term": "saints", "zh_term": "圣徒", "sources": ["x"]},
                 {"en_term": "predestination", "zh_term": "预定", "sources": ["y"]}]
        got = translate._applicable_glossary(ITEM, gloss)
        self.assertEqual([e["en_term"] for e in got], [])  # neither term in EN text

    def test_applicable_glossary_matches_present_term(self):
        item = {"id": "x", "text": {"en": "A question about justification."}}
        gloss = [{"en_term": "justification", "zh_term": "称义", "sources": ["z"]}]
        got = translate._applicable_glossary(item, gloss)
        self.assertEqual([e["en_term"] for e in got], ["justification"])


# ZH Scripture form: <verse ref>「…verbatim CUV…」</verse> (tag + brackets nested).
GOOD = ('{"text": {"zh": "<verse ref=\\"PHP.1.1\\">「基督耶稣的仆人」</verse>保罗和提摩太。"},'
        ' "terms": [], "uncertain": []}')
# BAD keeps a bare 「…」 whose wording is NOT verbatim CUV (门徒≠仆人) — fails the gate.
BAD = ('{"text": {"zh": "「基督耶稣的门徒」保罗和提摩太。"}, "terms": [], "uncertain": []}')


class TestTranslateWithGates(unittest.TestCase):
    def _item(self):
        return {"id": "PHP-001-D1-01", "passage": "PHP.1.1-11", "dimension": "D1",
                "type": "question",
                "text": {"en": 'the <verse ref="PHP.1.1">servants of Christ Jesus</verse>?'}}

    def test_clean_translation_passes_gate(self):
        with mock.patch.object(translate, "llm", return_value=GOOD):
            out = translate.translate_with_gates(self._item(), "PHP", glossary=[])
        self.assertTrue(out["gate_ok"])
        self.assertEqual(out["gate_flags"], [])

    def test_bad_span_repaired_on_second_round(self):
        # first call returns a non-CUV 「…」 span, repair returns a clean one
        with mock.patch.object(translate, "llm", side_effect=[BAD, GOOD]):
            out = translate.translate_with_gates(self._item(), "PHP", glossary=[],
                                                 max_repair=2)
        self.assertTrue(out["gate_ok"])

    def test_unrepaired_bad_span_reported_not_raised(self):
        with mock.patch.object(translate, "llm", side_effect=[BAD, BAD, BAD]):
            out = translate.translate_with_gates(self._item(), "PHP", glossary=[],
                                                 max_repair=2)
        self.assertFalse(out["gate_ok"])
        self.assertTrue(out["gate_flags"])


class TestZhCitationGate(unittest.TestCase):
    def _item(self):
        return {"id": "PHP-001-D1-01", "passage": "PHP.1.1-11", "dimension": "D1",
                "type": "question",
                "text": {"en": 'the <verse ref="PHP.1.1">servants of Christ Jesus</verse>?'}}

    def test_bad_zh_verse_tag_is_gate_flagged(self):
        # zh <verse> whose inner text is NOT the CUV wording -> flagged
        bad = ('{"text": {"zh": "谁是<verse ref=\\"PHP.1.1\\">错误的经文</verse>？"}, '
               '"terms": [], "uncertain": []}')
        with mock.patch.object(translate, "llm", side_effect=[bad, bad, bad]):
            out = translate.translate_with_gates(self._item(), "PHP", glossary=[],
                                                 max_repair=2)
        self.assertFalse(out["gate_ok"])
        self.assertTrue(any("citation" in f for f in out["gate_flags"]))

    def test_good_zh_verse_tag_passes(self):
        good = ('{"text": {"zh": "谁是<verse ref=\\"PHP.1.1\\">基督耶稣的仆人</verse>？"}, '
                '"terms": [], "uncertain": []}')
        with mock.patch.object(translate, "llm", return_value=good):
            out = translate.translate_with_gates(self._item(), "PHP", glossary=[])
        self.assertTrue(out["gate_ok"])


class TestSuggestDriftFix(unittest.TestCase):
    ITEM = {"id": "PSA-003-i14", "passage": "PSA.3.1-8", "dimension": "D7",
            "type": "question", "text": {"en": "But You, O LORD.", "zh": "但你耶和华。"}}

    def test_no_drift_returns_none_without_calling_llm(self):
        m = mock.Mock()
        with mock.patch.object(translate, "llm", m):
            out = translate.suggest_drift_fix(self.ITEM, "PSA",
                                              {"drift": False, "notes": ""}, glossary=[])
        self.assertIsNone(out)
        m.assert_not_called()

    def test_changed_fix_is_regated_and_redrifted(self):
        # A genuine fix produces DIFFERENT text -> the changed branch (re-gate + re-drift).
        fix = ('{"changed": true, "reason": "removed added imagery",'
               ' "text": {"zh": "但你耶和华啊。"}, "terms": [], "uncertain": []}')
        redrift = '{"drift": false, "notes": "resolved"}'
        with mock.patch.object(translate, "llm", side_effect=[fix, redrift]):
            out = translate.suggest_drift_fix(
                self.ITEM, "PSA", {"drift": True, "notes": "adds shield imagery"},
                glossary=[])
        self.assertTrue(out["changed"])
        self.assertEqual(out["rationale"], "removed added imagery")
        self.assertEqual(out["item"]["text"]["zh"], "但你耶和华啊。")
        self.assertFalse(out["drift"]["drift"])       # re-drift ran
        self.assertIn("gate_ok", out)                 # re-gate ran
        # the TRIGGERING drift notes are preserved so the fix is auditable
        self.assertEqual(out["addresses"], "adds shield imagery")
        self.assertNotIn("cuv_note", out)             # real fix -> no CUV-inherent note
        self.assertNotIn("zh_mutated", self.ITEM)     # original untouched key-wise
        self.assertEqual(self.ITEM["text"]["zh"], "但你耶和华。")  # original object intact

    def test_declined_fix_returns_original_unchanged(self):
        # Declined = CUV-inherent, so a leader-prep divergence note is generated.
        fix = ('{"changed": false, "reason": "CUV renders it this way",'
               ' "text": {"zh": "但你耶和华。"}, "terms": [], "uncertain": []}')
        note = '{"note": "英文强调因果与次序，CUV译得较概括"}'
        with mock.patch.object(translate, "llm", side_effect=[fix, note]):
            out = translate.suggest_drift_fix(
                self.ITEM, "PSA", {"drift": True, "notes": "guards -> knows"},
                glossary=[])
        self.assertFalse(out["changed"])
        self.assertEqual(out["rationale"], "CUV renders it this way")
        self.assertEqual(out["item"], self.ITEM)      # original returned
        self.assertEqual(out["drift"], {"drift": True, "notes": "guards -> knows"})
        self.assertEqual(out["addresses"], "guards -> knows")  # triggering notes kept
        self.assertEqual(out["cuv_note"], "英文强调因果与次序，CUV译得较概括")

    def test_cuv_inherent_noop_changed_fix_gets_note(self):
        # The i09 "kept the CUV" case: model returns changed=true but the text is
        # identical -> no usable change -> no re-drift; triggering drift persists ->
        # CUV-inherent -> a divergence note is generated. Calls: [fix, note].
        fix = ('{"changed": true, "reason": "tried",'
               ' "text": {"zh": "但你耶和华。"}, "terms": [], "uncertain": []}')  # identical
        note = '{"note": "英文的次序在CUV中被拉平"}'
        with mock.patch.object(translate, "llm", side_effect=[fix, note]):
            out = translate.suggest_drift_fix(
                self.ITEM, "PSA", {"drift": True, "notes": "wake again -> awake"},
                glossary=[])
        self.assertFalse(out["changed"])               # no usable change
        self.assertTrue(out["drift"]["drift"])         # triggering drift persists
        self.assertEqual(out["cuv_note"], "英文的次序在CUV中被拉平")

    def test_cuv_departing_fix_discarded_and_noted(self):
        # The i09 "left the CUV" case: fix changes the <verse> span to non-CUV to
        # match the English (verse_mismatch). The revision is DISCARDED (CUV kept),
        # and a divergence note is generated. Calls: [fix, note] (no re-drift).
        item = {"id": "MV", "passage": "PSA-003", "dimension": "D4", "type": "question",
                "text": {"en": 'Ps 3:5 — <verse ref="PSA.3.5">I wake again</verse>',
                         "zh": 'Ps 3:5 — <verse ref="PSA.3.5">「我醒着」</verse>'}}
        fix = ('{"changed": true, "reason": "matched English",'
               ' "text": {"zh": "Ps 3:5 — <verse ref=\\"PSA.3.5\\">「我醒过来」</verse>"},'
               ' "terms": [], "uncertain": []}')   # 我醒过来 is NOT verbatim CUV
        note = '{"note": "英文次序在CUV中被拉平"}'
        with mock.patch.object(translate, "llm", side_effect=[fix, note]):
            out = translate.suggest_drift_fix(
                item, "PSA", {"drift": True, "notes": "wake again -> awake"}, glossary=[])
        self.assertFalse(out["changed"])              # CUV-leaving revision discarded
        self.assertEqual(out["item"], item)           # the CUV is kept
        self.assertEqual(out["cuv_note"], "英文次序在CUV中被拉平")

    def test_gloss_injecting_fix_that_still_drifts_is_discarded_and_noted(self):
        # The i09 "inject a gloss" case: fix keeps the CUV span but prepends a prose
        # paraphrase (gate-clean); re-drift STILL flags -> not a resolving fix ->
        # discard the gloss, keep the CUV, emit the note. Calls: [fix, redrift, note].
        item = {"id": "MV", "passage": "PSA-003", "dimension": "D4", "type": "question",
                "text": {"en": 'Ps 3:5 — <verse ref="PSA.3.5">I wake again</verse>',
                         "zh": 'Ps 3:5 — <verse ref="PSA.3.5">「我醒着」</verse>'}}
        fix = ('{"changed": true, "reason": "glossed",'
               ' "text": {"zh": "Ps 3:5 — 我再次醒来。<verse ref=\\"PSA.3.5\\">「我醒着」</verse>"},'
               ' "terms": [], "uncertain": []}')   # CUV kept, prose gloss prepended
        redrift = '{"drift": true, "notes": "still diverges"}'
        note = '{"note": "英文强调次序"}'
        with mock.patch.object(translate, "llm", side_effect=[fix, redrift, note]):
            out = translate.suggest_drift_fix(
                item, "PSA", {"drift": True, "notes": "n"}, glossary=[])
        self.assertFalse(out["changed"])          # gloss discarded, not shipped
        self.assertEqual(out["item"], item)       # CUV kept verbatim
        self.assertEqual(out["cuv_note"], "英文强调次序")

    def test_cuv_note_uses_drift_model_not_translation_model(self):
        # The divergence note is a drift-ANALYSIS task, so it must use --drift-model
        # (like the drift review), not the cheap translation --model.
        seq = iter(['{"changed": false, "reason": "CUV"}', '{"note": "n"}'])
        seen = []

        def rec(prompt, route=None):
            seen.append(route.model)
            return next(seq)

        with mock.patch.object(translate, "llm", side_effect=rec):
            translate.suggest_drift_fix(self.ITEM, "PSA", {"drift": True, "notes": "x"},
                                        glossary=[], route=Route("llm_core", "flash"),
                                        drift_route=Route("llm_core", "pro"))
        self.assertEqual(seen[0], "flash")   # the fix attempt uses the translation model
        self.assertEqual(seen[1], "pro")     # the CUV-divergence note uses the drift model

    def test_bad_fix_recorded_gate_false_not_raised(self):
        # A changed fix that emits a bare 「…」 with no <verse> tag -> citation flag.
        bad = ('{"changed": true, "reason": "x",'
               ' "text": {"zh": "「耶和华是我四围的盾牌」"}, "terms": [], "uncertain": []}')
        redrift = '{"drift": false, "notes": ""}'
        with mock.patch.object(translate, "llm", side_effect=[bad, redrift]):
            out = translate.suggest_drift_fix(
                self.ITEM, "PSA", {"drift": True, "notes": "n"}, glossary=[])
        self.assertTrue(out["changed"])
        self.assertFalse(out["gate_ok"])              # re-gate caught it
        self.assertTrue(out["gate_flags"])            # recorded, not dropped
