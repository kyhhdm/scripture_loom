import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import books


class TestBooks(unittest.TestCase):
    def test_sixty_six_books_in_order(self):
        b = books.load()
        self.assertEqual(len(b), 66)
        self.assertEqual(books.BOOK_ORDER[0], "GEN")
        self.assertEqual(books.BOOK_ORDER[39], "MAT")
        self.assertEqual(books.BOOK_ORDER[65], "REV")

    def test_total_chapters_is_1189(self):
        b = books.load()
        self.assertEqual(sum(v["chapters"] for v in b.values()), 1189)

    def test_matthew_entry(self):
        b = books.load()
        self.assertEqual(b["MAT"],
            {"n": 40, "name_en": "Matthew", "name_zh": "马太福音", "chapters": 28})


if __name__ == "__main__":
    unittest.main()
