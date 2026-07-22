import json
import pathlib
import tempfile
import unittest
from content_bank.author import translate_compare_html as tch


def _proposal(iid, zh, gate_ok=True):
    return {"id": iid, "en": "servants of Christ Jesus?",
            "item": {"id": iid, "text": {"en": "servants of Christ Jesus?",
                                         "zh": zh}},
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
