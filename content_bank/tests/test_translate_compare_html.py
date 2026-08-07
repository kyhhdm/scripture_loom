import json
import pathlib
import tempfile
import unittest
from content_bank.author import translate_compare_html as tch


def _proposal(iid, zh, gate_ok=True, leader_reference=None):
    item = {"id": iid, "text": {"en": "servants of Christ Jesus?", "zh": zh}}
    if leader_reference is not None:
        item["leader_reference"] = leader_reference
    return {"id": iid, "en": "servants of Christ Jesus?",
            "item": item,
            "cuv_refs": ["PHP.1.1-11"], "terms": [], "uncertain": [],
            "gate_ok": gate_ok, "gate_flags": [], "drift": {"drift": False, "notes": ""}}


class TestExperimentTranslations(unittest.TestCase):
    def _write(self, root, exp, book, slug, iid, zh):
        d = (pathlib.Path(root) / exp / book / "runs" / exp / "translations" / slug)
        d.mkdir(parents=True)
        (d / f"{iid}.json").write_text(json.dumps(_proposal(iid, zh)),
                                       encoding="utf-8")

    def test_renders_one_zh_column_per_experiment(self):
        with tempfile.TemporaryDirectory() as root:
            self._write(root, "exp_a", "PHP", "deepseek-v4-flash", "PHP-001-i1", "甲译")
            self._write(root, "exp_b", "PHP", "opus", "PHP-001-i1", "乙译")
            html = tch.render_experiment_translations(
                "PHP", [pathlib.Path(root) / "exp_a", pathlib.Path(root) / "exp_b"])
        self.assertIn("exp_a", html)
        self.assertIn("exp_b", html)
        self.assertIn("甲译", html)
        self.assertIn("乙译", html)
        self.assertIn("servants of Christ Jesus?", html)  # English column


class TestFlagTooltips(unittest.TestCase):
    def _cell(self, **over):
        cell = {"gate_ok": True, "gate_flags": [], "drift": False,
                "drift_notes": "", "uncertain": []}
        cell.update(over)
        return cell

    def test_gate_badge_carries_flag_text_as_tooltip(self):
        html = tch._flag_badges(self._cell(
            gate_ok=False,
            gate_flags=["citation.verse_mismatch: 'PSA.3.2'", "context span"]))
        self.assertIn(">gate<", html)
        self.assertIn("citation.verse_mismatch: &#x27;PSA.3.2&#x27;", html)  # escaped
        self.assertIn("context span", html)

    def test_drift_badge_carries_notes_as_tooltip(self):
        html = tch._flag_badges(self._cell(drift=True, drift_notes="adds shield imagery"))
        self.assertIn('title="adds shield imagery"', html)

    def test_clean_cell_has_no_tooltip(self):
        html = tch._flag_badges(self._cell())
        self.assertIn(">ok<", html)
        self.assertNotIn("title=", html)

    def test_double_quotes_in_notes_are_escaped(self):
        html = tch._flag_badges(self._cell(drift=True, drift_notes='he said "myriads"'))
        self.assertNotIn('title="he said "', html)  # raw quote would break the attr
        self.assertIn("&quot;myriads&quot;", html)


class TestTranslateComparePage(unittest.TestCase):
    def _root(self):
        root = tempfile.mkdtemp()
        base = pathlib.Path(root) / "PHP" / "runs" / "opus" / "translations"
        for tr, zh in (("deepseek-v4-flash", "「基督耶稣的仆人」甲"),
                       ("opus", "「基督耶稣的仆人」乙")):
            d = base / tr
            d.mkdir(parents=True)
            (d / "PHP-001-D1-01.json").write_text(
                json.dumps(_proposal("PHP-001-D1-01", zh)), encoding="utf-8")
        return root

    def test_build_page_collects_translators(self):
        page = tch.build_page("PHP", "opus", ["deepseek-v4-flash", "opus"],
                              root=self._root())
        self.assertEqual(page["translators"], ["deepseek-v4-flash", "opus"])
        row = page["rows"][0]
        self.assertEqual(row["id"], "PHP-001-D1-01")
        self.assertIn("基督耶稣的仆人", row["cuv"])  # CUV source verse pulled
        self.assertEqual(row["cells"]["deepseek-v4-flash"]["zh"], "「基督耶稣的仆人」甲")
        self.assertEqual(row["cells"]["opus"]["zh"], "「基督耶稣的仆人」乙")

    def test_render_html_is_self_contained(self):
        page = tch.build_page("PHP", "opus", ["deepseek-v4-flash", "opus"],
                              root=self._root())
        html = tch.render_html(page)
        self.assertIn("servants of Christ Jesus?", html)   # en
        self.assertIn("「基督耶稣的仆人」甲", html)            # translator zh
        self.assertIn("「基督耶稣的仆人」乙", html)
        self.assertNotIn("http://", html)                  # no external refs
        self.assertNotIn("https://", html)

    def test_tags_kept_raw_and_highlighted_on_render(self):
        # Review instrument: the model keeps citation tags RAW, and render_html
        # turns them into highlighted spans (never leaking raw markup, never
        # stripping the citation from view).
        root = tempfile.mkdtemp()
        d = pathlib.Path(root) / "PHP" / "runs" / "opus" / "translations" / "deepseek-v4-flash"
        d.mkdir(parents=True)
        p = _proposal("PHP-001-D1-01",
                      '谁是<verse ref="PHP.1.1">基督耶稣的仆人</verse>？')
        p["en"] = 'the <verse ref="PHP.1.1">servants of Christ Jesus</verse>'
        (d / "PHP-001-D1-01.json").write_text(json.dumps(p), encoding="utf-8")
        page = tch.build_page("PHP", "opus", ["deepseek-v4-flash"], root=root)
        row = page["rows"][0]
        # model carries the raw tag (so render can highlight it)
        self.assertIn('<verse ref="PHP.1.1">', row["en"])
        self.assertIn('<verse ref="PHP.1.1">', row["cells"]["deepseek-v4-flash"]["zh"])
        html = tch.render_html(page)
        # rendered page shows a highlighted span with the ref, not raw markup
        self.assertIn("cite-verse", html)
        self.assertIn(">PHP.1.1<", html)                 # ref badge
        self.assertNotIn('<verse ref="PHP.1.1">', html)  # raw tag never leaks


class TestLeaderReferenceRendered(unittest.TestCase):
    """The answer/notes translation (leader_reference) must reach the page."""

    def _root_with_ref(self):
        root = tempfile.mkdtemp()
        base = pathlib.Path(root) / "PHP" / "runs" / "opus" / "translations"
        d = base / "deepseek-v4-flash"
        d.mkdir(parents=True)
        lr = {"kind": "answer_key",
              "text": {"en": "He is confident of completion.",
                       "zh": "他有信心必成全这工。"},
              "verse": {"en": "Philippians 1:6", "zh": "腓立比书 1:6"}}
        (d / "PHP-001-D1-01.json").write_text(
            json.dumps(_proposal("PHP-001-D1-01", "「基督耶稣的仆人」甲",
                                 leader_reference=lr)), encoding="utf-8")
        return root

    def test_build_page_carries_leader_reference(self):
        page = tch.build_page("PHP", "opus", ["deepseek-v4-flash"],
                              root=self._root_with_ref())
        row = page["rows"][0]
        self.assertEqual(row["ref_label"], "Answer")
        self.assertEqual(row["ref_en"], "He is confident of completion.")
        self.assertEqual(row["verse_en"], "Philippians 1:6")
        cell = row["cells"]["deepseek-v4-flash"]
        self.assertEqual(cell["ref_zh"], "他有信心必成全这工。")
        self.assertEqual(cell["verse_zh"], "腓立比书 1:6")

    def test_render_html_shows_answer_and_verse(self):
        page = tch.build_page("PHP", "opus", ["deepseek-v4-flash"],
                              root=self._root_with_ref())
        html = tch.render_html(page)
        self.assertIn("Answer:", html)               # label
        self.assertIn("他有信心必成全这工。", html)      # translated answer
        self.assertIn("腓立比书 1:6", html)            # translated verse
        self.assertIn("He is confident of completion.", html)  # en source


class TestCategoryRendered(unittest.TestCase):
    """pre_reading_quest category translation must reach the page."""

    def _root_with_cat(self):
        root = tempfile.mkdtemp()
        d = pathlib.Path(root) / "PHP" / "runs" / "opus" / "translations" / "deepseek-v4-flash"
        d.mkdir(parents=True)
        p = _proposal("PHP-001-D1-03", "谁被提名？")
        p["item"]["category"] = {"en": "People & roles", "zh": "人物与角色"}
        (d / "PHP-001-D1-03.json").write_text(json.dumps(p), encoding="utf-8")
        return root

    def test_category_carried_and_rendered(self):
        page = tch.build_page("PHP", "opus", ["deepseek-v4-flash"],
                              root=self._root_with_cat())
        row = page["rows"][0]
        self.assertEqual(row["cat_en"], "People & roles")
        self.assertEqual(row["cells"]["deepseek-v4-flash"]["cat_zh"], "人物与角色")
        html = tch.render_html(page)
        self.assertIn("Category:", html)
        self.assertIn("人物与角色", html)
        self.assertIn("People &amp; roles", html)  # escaped en source


class TestSuggestedFixRendering(unittest.TestCase):
    def _cell_with_fix(self, fix):
        return {"zh": "但你。", "ref_zh": "", "verse_zh": "", "cat_zh": "",
                "gate_ok": True, "gate_flags": [], "drift": True,
                "drift_notes": "adds shield imagery", "uncertain": [],
                "suggested_fix": fix}

    def test_changed_fix_renders_revised_zh_and_rationale(self):
        fix = {"changed": True, "rationale": "removed added imagery",
               "item": {"text": {"zh": "但你耶和华。"}},
               "gate_ok": True, "gate_flags": [], "drift": {"drift": False}}
        html = tch._suggested_block(self._cell_with_fix(fix))
        self.assertIn("但你耶和华。", html)
        self.assertIn("removed added imagery", html)

    def test_addresses_triggering_drift_rendered(self):
        # The fix carries the drift notes that triggered it, so the reviewer sees
        # triggering-drift -> revision -> re-check in one place.
        fix = {"changed": True, "rationale": "restored imperative force",
               "item": {"text": {"zh": "应当直说。"}},
               "gate_ok": True, "gate_flags": [], "drift": {"drift": False},
               "addresses": "softens the confessional duty"}
        html = tch._suggested_block(self._cell_with_fix(fix))
        self.assertIn("Addresses drift:", html)
        self.assertIn("softens the confessional duty", html)

    def test_no_addresses_no_block(self):
        fix = {"changed": True, "rationale": "r", "item": {"text": {"zh": "x"}},
               "gate_ok": True, "gate_flags": [], "drift": {"drift": False}}
        self.assertNotIn("Addresses drift:", tch._suggested_block(self._cell_with_fix(fix)))

    def test_cuv_inherent_note_rendered_no_revised_zh(self):
        # CUV-inherent drift: show the teaching note, and the "CUV stands" head,
        # not a (misleadingly identical) revised zh.
        fix = {"changed": True, "rationale": "tried",
               "item": {"text": {"zh": "我醒着，耶和华都保佑我"}},
               "gate_ok": True, "gate_flags": [], "drift": {"drift": True},
               "addresses": "wake again -> awake",
               "cuv_note": "英文强调因果与次序，CUV译得较概括"}
        html = tch._suggested_block(self._cell_with_fix(fix))
        self.assertIn("CUV divergence (teach):", html)
        self.assertIn("英文强调因果与次序，CUV译得较概括", html)
        self.assertIn("CUV stands", html)

    def test_revised_leader_note_rendered(self):
        # When the fix lands in the leader_reference (answer/notes) and the question
        # text is unchanged, the revised note must still be shown (the i14 case).
        fix = {"changed": True, "rationale": "restored imperative",
               "item": {"text": {"zh": "问题不变"},
                        "leader_reference": {"kind": "leader_note",
                                             "text": {"zh": "修订后的答案笔记"}}},
               "gate_ok": True, "gate_flags": [], "drift": {"drift": False}}
        html = tch._suggested_block(self._cell_with_fix(fix))
        self.assertIn("修订后的答案笔记", html)   # the revised note is visible

    def test_declined_fix_renders_no_fix_note(self):
        fix = {"changed": False, "rationale": "CUV renders it this way",
               "item": {"text": {"zh": "但你。"}},
               "gate_ok": True, "gate_flags": [], "drift": {"drift": True}}
        html = tch._suggested_block(self._cell_with_fix(fix))
        self.assertIn("CUV renders it this way", html)
        self.assertNotIn("但你耶和华", html)  # no revised text shown

    def test_cell_without_fix_renders_empty_block(self):
        cell = {"zh": "x", "gate_ok": True, "gate_flags": [], "drift": False,
                "drift_notes": "", "uncertain": []}
        self.assertEqual(tch._suggested_block(cell), "")

    def test_fix_uncertain_surfaces_as_badge(self):
        # The revision's own model-flagged uncertainty must reach the badges,
        # not be dropped (regression: _suggested_block hardcoded uncertain=[]).
        fix = {"changed": True, "rationale": "r",
               "item": {"text": {"zh": "但你耶和华。"}},
               "gate_ok": True, "gate_flags": [], "drift": {"drift": False},
               "uncertain": ["盾牌 rendering unsure"]}
        html = tch._suggested_block(self._cell_with_fix(fix))
        self.assertIn(">uncertain<", html)
        self.assertIn("盾牌 rendering unsure", html)  # carried as tooltip text
