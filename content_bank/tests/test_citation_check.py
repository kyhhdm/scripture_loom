# content_bank/tests/test_citation_check.py
import unittest
from content_bank.author import gates

_BSB_PHP_1_1 = ("Paul and Timothy, servants of Christ Jesus, To all the saints "
                "in Christ Jesus at Philippi, together with the overseers and deacons:")


def _item(text_en, itype="question", iid="PHP-001-D1-01", **extra):
    it = {"id": iid, "passage": "PHP.1.1-11", "dimension": "D1", "type": itype,
          "text": {"en": text_en}}
    it.update(extra)
    return it


class TestVerseMode(unittest.TestCase):
    def test_correct_subverse_quote_passes_by_containment(self):
        it = _item('Who are the <verse ref="PHP.1.1">servants of Christ Jesus</verse>?')
        self.assertEqual(gates.citation_check([it]), {})

    def test_altered_quote_flagged(self):
        it = _item('The <verse ref="PHP.1.1">servants of Jesus Christ</verse>.')
        flags = gates.citation_check([it])["PHP-001-D1-01"]
        self.assertTrue(any("verse_mismatch" in f for f in flags))

    def test_memory_verse_requires_full_equality(self):
        # a sub-verse phrase is NOT the whole verse -> equality fails
        it = _item('<verse ref="PHP.1.1">servants of Christ Jesus</verse>',
                   itype="memory_verse")
        flags = gates.citation_check([it])["PHP-001-D1-01"]
        self.assertTrue(any("verse_mismatch" in f for f in flags))

    def test_memory_verse_full_verse_equality_passes(self):
        it = _item(f'<verse ref="PHP.1.1">{_BSB_PHP_1_1}</verse>',
                   itype="memory_verse")
        self.assertEqual(gates.citation_check([it]), {})

    def test_bad_ref_grammar_flagged_malformed(self):
        it = _item('<verse ref="Philippians 1:1">servants of Christ Jesus</verse>')
        flags = gates.citation_check([it])["PHP-001-D1-01"]
        self.assertTrue(any("malformed" in f for f in flags))

    def test_unbalanced_tag_flagged_malformed(self):
        it = _item('<verse ref="PHP.1.1">servants of Christ Jesus')
        flags = gates.citation_check([it])["PHP-001-D1-01"]
        self.assertTrue(any("malformed" in f for f in flags))


class TestBasisMode(unittest.TestCase):
    def test_resolvable_doctrine_passes(self):
        it = _item('Rests on <doctrine std="WCF" ref="1.4">God its author</doctrine>.')
        self.assertEqual(gates.citation_check([it]), {})

    def test_unresolvable_doctrine_flagged(self):
        it = _item('Rests on <doctrine std="WCF" ref="1.99">nonsense</doctrine>.')
        flags = gates.citation_check([it])["PHP-001-D1-01"]
        self.assertTrue(any("basis_unresolved" in f for f in flags))

    def test_unknown_standard_flagged(self):
        it = _item('Rests on <doctrine std="XYZ" ref="1.1">nope</doctrine>.')
        flags = gates.citation_check([it])["PHP-001-D1-01"]
        self.assertTrue(any("basis_unresolved" in f for f in flags))


class TestRecallNetAndLangs(unittest.TestCase):
    def test_untagged_verbatim_quote_flagged(self):
        # a 4+ word BSB span left untagged -> recall net flags it
        it = _item("The phrase servants of Christ Jesus appears here.")
        flags = gates.citation_check([it])["PHP-001-D1-01"]
        self.assertTrue(any("untagged_quote" in f for f in flags))

    def test_same_quote_when_tagged_not_flagged(self):
        it = _item('The phrase <verse ref="PHP.1.1">servants of Christ Jesus</verse> here.')
        self.assertEqual(gates.citation_check([it]), {})

    def test_zh_verse_verified_against_cuv(self):
        it = _item("q", iid="PHP-001-D1-02")
        it["text"]["zh"] = '谁是<verse ref="PHP.1.1">基督耶稣的仆人</verse>？'
        self.assertEqual(gates.citation_check([it]), {})

    def test_langs_filter_skips_en_recall_net(self):
        it = _item("servants of Christ Jesus appears untagged in english")
        it["text"]["zh"] = "干净的中文没有标签"
        # zh-only: en recall net is skipped, so no flags
        self.assertEqual(gates.citation_check([it], langs={"zh"}), {})


class TestZhNestedFormAndRecallNet(unittest.TestCase):
    """ZH Scripture form is <verse ref>「…verbatim CUV…」</verse> (tag + brackets);
    a bare 「…」 verbatim-CUV span (dropped tag) is flagged for repair."""
    _CUV = "基督耶稣的仆人"  # verbatim CUV substring of PHP.1.1

    def _zh(self, zh):
        return {"id": "PHP-001-D1-01", "passage": "PHP.1.1-11", "dimension": "D1",
                "type": "question", "text": {"en": "q", "zh": zh}}

    def test_nested_tag_and_brackets_verifies_clean(self):
        it = self._zh(f'谁是<verse ref="PHP.1.1">「{self._CUV}」</verse>？')
        self.assertEqual(gates.citation_check([it]), {})

    def test_tag_without_brackets_still_verifies(self):
        it = self._zh(f'谁是<verse ref="PHP.1.1">{self._CUV}</verse>？')
        self.assertEqual(gates.citation_check([it]), {})

    def test_bare_cuv_brackets_without_tag_flagged(self):
        it = self._zh(f'谁是「{self._CUV}」？')   # dropped tag
        flags = gates.citation_check([it])["PHP-001-D1-01"]
        self.assertTrue(any("untagged_quote" in f for f in flags))

    def test_non_cuv_brackets_not_flagged_by_recall_net(self):
        # a 「…」 span that is NOT verbatim CUV is cuv_quote_check's concern, not
        # the citation recall net — the net only fires on real dropped Scripture.
        it = self._zh("他说「今天天气很好」。")
        self.assertEqual(gates.citation_check([it]), {})


class TestCuvPoetryWhitespace(unittest.TestCase):
    """CUV poetry/psalms carry Hebrew-cola spacing (a space mid-line) that correct
    Chinese prose omits. _norm must ignore whitespace adjacent to CJK characters so
    a verbatim quote still verifies, while Latin word-spacing stays intact."""

    def test_norm_drops_cjk_adjacent_whitespace_keeps_latin(self):
        # CJK: the mid-line cola space is removed so the two forms are equal.
        self.assertEqual(gates._norm("虽被驱逐， 我仍要仰望"),
                         gates._norm("虽被驱逐，我仍要仰望"))
        # Latin: word-spacing is preserved (removing it would merge words).
        self.assertEqual(gates._norm("servants of Christ"), "servants of christ")
        self.assertNotEqual(gates._norm("servants of Christ"),
                            gates._norm("servantsofchrist"))

    def test_cuv_quote_verifies_despite_cola_spacing(self):
        # CUV JON.2.4 in the corpus is "我说：我从你眼前虽被驱逐， 我仍要仰望你的圣殿。"
        # (note the space). The spoken quote, rendered without that space, must pass.
        quote = "我从你眼前虽被驱逐，我仍要仰望你的圣殿。"
        it = {"id": "JON-004-x", "passage": "JON.2.1-10", "dimension": "D5",
              "type": "question",
              "text": {"en": "q", "zh": f'约拿：<verse ref="JON.2.4">「{quote}」</verse>'}}
        self.assertEqual(gates.citation_check([it], langs={"zh"}), {})


class TestRunAllIncludesCitation(unittest.TestCase):
    def test_run_all_surfaces_verse_mismatch(self):
        it = _item('<verse ref="PHP.1.1">servants of Jesus Christ</verse>',
                   itype="memory_verse")
        allowed = [("PHP", 1, 1, 11)]
        merged = gates.run_all("PHP", [it], allowed)
        self.assertIn("PHP-001-D1-01", merged)
        self.assertTrue(any("verse_mismatch" in f for f in merged["PHP-001-D1-01"]))


if __name__ == "__main__":
    unittest.main()
