import unittest
from content_bank.lib import citation_tags as ct


class TestStrip(unittest.TestCase):
    def test_strips_verse_keeps_inner(self):
        s = 'He said <verse ref="PHP.1.6">a good work in you</verse> here.'
        self.assertEqual(ct.strip_tags(s), "He said a good work in you here.")

    def test_strips_doctrine_keeps_inner(self):
        s = 'Rests on <doctrine std="WCF" ref="1.4">God its author</doctrine>.'
        self.assertEqual(ct.strip_tags(s), "Rests on God its author.")

    def test_untagged_unchanged_and_nonstring_passthrough(self):
        self.assertEqual(ct.strip_tags("plain text"), "plain text")
        self.assertIsNone(ct.strip_tags(None))


class TestParse(unittest.TestCase):
    def test_parses_verse_and_doctrine(self):
        s = ('<verse ref="PHP.1.1">servants of Christ Jesus</verse> and '
             '<doctrine std="WSC" ref="Q1">to glorify God</doctrine>')
        verses, doctrines, malformed = ct.parse(s)
        self.assertFalse(malformed)
        self.assertEqual(verses, [ct.Verse("PHP.1.1", "servants of Christ Jesus")])
        self.assertEqual(doctrines, [ct.Doctrine("WSC", "Q1", "to glorify God")])

    def test_clean_text_not_malformed(self):
        self.assertEqual(ct.parse("no tags at all"), ([], [], False))

    def test_missing_close_is_malformed(self):
        v, d, malformed = ct.parse('<verse ref="PHP.1.1">servants')
        self.assertTrue(malformed)

    def test_missing_ref_attr_is_malformed(self):
        v, d, malformed = ct.parse('<verse>servants of Christ Jesus</verse>')
        self.assertTrue(malformed)

    def test_doctrine_missing_std_is_malformed(self):
        v, d, malformed = ct.parse('<doctrine ref="1.4">x</doctrine>')
        self.assertTrue(malformed)


if __name__ == "__main__":
    unittest.main()
