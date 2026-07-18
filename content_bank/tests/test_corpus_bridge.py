import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from content_bank.lib import corpus_bridge as cb


class TestCorpusBridge(unittest.TestCase):
    def test_pericope_ids_include_known_matthew_ids(self):
        ids = cb.pericope_ids("MAT")
        self.assertIn("MAT-009", ids)
        self.assertIn("MAT-014", ids)
        self.assertIn("MAT-015", ids)

    def test_pericope_records_have_ranges(self):
        by_id = {p["id"]: p for p in cb.pericopes("MAT")}
        self.assertEqual(by_id["MAT-014"]["range"], "MAT.5.3-12")

    def test_book_name_en_and_zh(self):
        self.assertEqual(cb.book_name("MAT", "en"), "Matthew")
        self.assertTrue(cb.book_name("MAT", "zh"))  # non-empty Chinese name

    def test_wcf_chapter1_mentions_scripture(self):
        text = cb.wcf_chapter1_text()
        self.assertIn("1.1", text)            # section numbering present
        self.assertIn("Holy Scripture", text)  # chapter 1 title "Of the Holy Scripture"

    def test_passage_text_returns_verses(self):
        text = cb.passage_text("MAT.5.13-16", version="BSB")
        self.assertIn("salt", text.lower())


class TestCommentary(unittest.TestCase):
    def test_exact_block_returned(self):
        from content_bank.lib import corpus_bridge
        c = corpus_bridge.commentary("MAT.4.1-11")
        self.assertTrue(c["mhc"] and "range" in c["mhc"][0] and "text" in c["mhc"][0])

    def test_per_verse_jfb_overlaps_pericope(self):
        from content_bank.lib import corpus_bridge
        self.assertTrue(corpus_bridge.commentary("MAT.5.1-2")["jfb"])  # e.g. MAT.5.2

    def test_no_overlap_is_graceful_empty(self):
        from content_bank.lib import corpus_bridge
        c = corpus_bridge.commentary("MAT.28.99-99")
        self.assertEqual(c["mhc"], [])
        self.assertEqual(c["jfb"], [])


class TestCrossrefs(unittest.TestCase):
    def test_refs_in_range_ranked_and_capped(self):
        from content_bank.lib import corpus_bridge
        refs = corpus_bridge.crossrefs("MAT.5.3-12", limit=5)
        self.assertTrue(refs and len(refs) <= 5)
        weights = [r["weight"] for r in refs]
        self.assertEqual(weights, sorted(weights, reverse=True))
        self.assertTrue(all(r["from"].startswith("MAT.5.") for r in refs))

    def test_empty_range_is_graceful(self):
        from content_bank.lib import corpus_bridge
        self.assertEqual(corpus_bridge.crossrefs("MAT.999.1-2"), [])


class TestConfessionalRefs(unittest.TestCase):
    def test_beatitudes_hits_wcf_and_wlc(self):
        from content_bank.lib import corpus_bridge
        c = corpus_bridge.confessional_refs("MAT.5.3-12")
        refs = [h["ref"] for h in c["wcf"]] + [h["ref"] for h in c["wlc"]]
        self.assertIn("WCF 19.6", refs)
        self.assertIn("WLC Q172", refs)
        wcf = next(h for h in c["wcf"] if h["ref"] == "WCF 19.6")
        self.assertIn("text", wcf)
        self.assertIn("via", wcf)

    def test_setup_pericope_has_no_hits(self):
        from content_bank.lib import corpus_bridge
        c = corpus_bridge.confessional_refs("MAT.5.1-2")
        self.assertEqual(c["wcf"] + c["wlc"] + c["wsc"], [])


if __name__ == "__main__":
    unittest.main()


class TestPassageOrdering(unittest.TestCase):
    def test_verses_served_in_canonical_order(self):
        from content_bank.lib import corpus_bridge
        text = corpus_bridge.passage_text("MAT.4.1-11")
        verses = [line.split()[0] for line in text.splitlines() if line.strip()]
        nums = [int(v.split(".")[2]) for v in verses]
        self.assertEqual(nums, sorted(nums))  # 4.1,4.2,...,4.11 not 4.1,4.10,4.11,4.2
