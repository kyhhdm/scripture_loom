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
