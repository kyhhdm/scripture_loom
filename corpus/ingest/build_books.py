"""Generate canon/structure/books.json from the canonical 66-book table."""
import json
from pathlib import Path

# code, English name, Chinese name (简体), chapter count — Protestant canon order
TABLE = [
    ("GEN", "Genesis", "创世记", 50), ("EXO", "Exodus", "出埃及记", 40),
    ("LEV", "Leviticus", "利未记", 27), ("NUM", "Numbers", "民数记", 36),
    ("DEU", "Deuteronomy", "申命记", 34), ("JOS", "Joshua", "约书亚记", 24),
    ("JDG", "Judges", "士师记", 21), ("RUT", "Ruth", "路得记", 4),
    ("1SA", "1 Samuel", "撒母耳记上", 31), ("2SA", "2 Samuel", "撒母耳记下", 24),
    ("1KI", "1 Kings", "列王纪上", 22), ("2KI", "2 Kings", "列王纪下", 25),
    ("1CH", "1 Chronicles", "历代志上", 29), ("2CH", "2 Chronicles", "历代志下", 36),
    ("EZR", "Ezra", "以斯拉记", 10), ("NEH", "Nehemiah", "尼希米记", 13),
    ("EST", "Esther", "以斯帖记", 10), ("JOB", "Job", "约伯记", 42),
    ("PSA", "Psalms", "诗篇", 150), ("PRO", "Proverbs", "箴言", 31),
    ("ECC", "Ecclesiastes", "传道书", 12), ("SNG", "Song of Songs", "雅歌", 8),
    ("ISA", "Isaiah", "以赛亚书", 66), ("JER", "Jeremiah", "耶利米书", 52),
    ("LAM", "Lamentations", "耶利米哀歌", 5), ("EZK", "Ezekiel", "以西结书", 48),
    ("DAN", "Daniel", "但以理书", 12), ("HOS", "Hosea", "何西阿书", 14),
    ("JOL", "Joel", "约珥书", 3), ("AMO", "Amos", "阿摩司书", 9),
    ("OBA", "Obadiah", "俄巴底亚书", 1), ("JON", "Jonah", "约拿书", 4),
    ("MIC", "Micah", "弥迦书", 7), ("NAM", "Nahum", "那鸿书", 3),
    ("HAB", "Habakkuk", "哈巴谷书", 3), ("ZEP", "Zephaniah", "西番雅书", 3),
    ("HAG", "Haggai", "哈该书", 2), ("ZEC", "Zechariah", "撒迦利亚书", 14),
    ("MAL", "Malachi", "玛拉基书", 4),
    ("MAT", "Matthew", "马太福音", 28), ("MRK", "Mark", "马可福音", 16),
    ("LUK", "Luke", "路加福音", 24), ("JHN", "John", "约翰福音", 21),
    ("ACT", "Acts", "使徒行传", 28), ("ROM", "Romans", "罗马书", 16),
    ("1CO", "1 Corinthians", "哥林多前书", 16), ("2CO", "2 Corinthians", "哥林多后书", 13),
    ("GAL", "Galatians", "加拉太书", 6), ("EPH", "Ephesians", "以弗所书", 6),
    ("PHP", "Philippians", "腓立比书", 4), ("COL", "Colossians", "歌罗西书", 4),
    ("1TH", "1 Thessalonians", "帖撒罗尼迦前书", 5), ("2TH", "2 Thessalonians", "帖撒罗尼迦后书", 3),
    ("1TI", "1 Timothy", "提摩太前书", 6), ("2TI", "2 Timothy", "提摩太后书", 4),
    ("TIT", "Titus", "提多书", 3), ("PHM", "Philemon", "腓利门书", 1),
    ("HEB", "Hebrews", "希伯来书", 13), ("JAS", "James", "雅各书", 5),
    ("1PE", "1 Peter", "彼得前书", 5), ("2PE", "2 Peter", "彼得后书", 3),
    ("1JN", "1 John", "约翰一书", 5), ("2JN", "2 John", "约翰二书", 1),
    ("3JN", "3 John", "约翰三书", 1), ("JUD", "Jude", "犹大书", 1),
    ("REV", "Revelation", "启示录", 22),
]


def main():
    out = {code: {"n": i + 1, "name_en": en, "name_zh": zh, "chapters": ch}
           for i, (code, en, zh, ch) in enumerate(TABLE)}
    dest = Path(__file__).resolve().parents[1] / "canon" / "structure" / "books.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                    encoding="utf-8")
    print(f"wrote {dest} ({len(out)} books)")


if __name__ == "__main__":
    main()
