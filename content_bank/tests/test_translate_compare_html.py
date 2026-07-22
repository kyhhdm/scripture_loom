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
