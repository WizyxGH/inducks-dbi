"""inducks_dbi.lines and inducks_dbi.story_rules, on invented data."""
import sqlite3
import unittest

from inducks_dbi import lines as L
from inducks_dbi.story_rules import (
    apply_story_rules,
    known_story,
    cover_story_xref,
    serial_part_from_previous_issue,
)


class Lines(unittest.TestCase):
    def test_columns_and_overriding_tags(self):
        e = L.parse_entry("LTB 610p005 I TL 3583-1P  26 3                  --  Marco Polo [part:1]")
        self.assertEqual((e["entrycode"], e["storycode"], e["pages"], e["pagel"], e["hero"], e["title"], e["part"]),
                         ("LTB 610p005", "I TL 3583-1P", "26", "3", "--", "Marco Polo", "1"))
        self.assertEqual(L.parse_entry("LTB 611p005 I TL 3681-1P     3                  --  Fifa [pages:104]")["pages"], "104")

    def test_tag_names_are_kept_as_written(self):
        self.assertEqual(L.tags_of("x [desc-de:US und DD] [Real Places: Venice]"),
                         {"desc-de": "US und DD", "Real Places": " Venice"})

    def test_entry_belongs_to_its_issue_only(self):
        self.assertEqual([L.belongs("de/LTB 613p005", "de/LTB  613"), L.belongs("de/LTB 6130", "de/LTB 613"),
                          L.belongs("de/LTB 613A", "de/LTB 613")], [True, False, False])

    def test_split_blocks_round_trip(self):
        text = ["LTB          h1 X", "", "LTB 609A     h3 A", "LTB 609Aa   D 1           1 c", "LTB 610      h3 B"]
        blocks = L.split_blocks(text)
        self.assertEqual([line for b in blocks for line in b.lines], text)
        self.assertEqual([b.code for b in blocks], ["", "LTB 609A", "LTB 610"])

    def test_compare_matches_a_variant_by_entry_suffix(self):
        gen = L.split_blocks(["LTB 609      h3 A", "LTB 609p005 D 2025-052    21                        T"])[0]
        off = L.split_blocks(["LTB 609A     h3 A", "LTB 609Ap005D 2025-052    21 3                  --  T"])[0]
        self.assertEqual(L.compare_blocks(gen, off), ["LTB 609p005 : pagel «  » au lieu de « 3 » ; hero «  » au lieu de « -- »"])

    def test_code_and_pages(self):
        self.assertEqual(L.code_and_pages("I TL 3583-1P", "26"), ("I TL 3583-1P  ", "26", []))
        self.assertEqual(L.code_and_pages("I TL 3583-1P", "104"), ("I TL 3583-1P  ", "  ", ["[pages:104]"]))
        self.assertEqual(L.code_and_pages("ABCDEFGHIJKLMNO", "1")[0].strip(), "->")

    def test_format_header(self):
        line = L.format_header("DVBH  88", 3, {"issdate": "1998-09-21", "pages": "36"})
        self.assertTrue(L.is_header(line))
        self.assertEqual(line[13:15], "h3")
        self.assertEqual(L.header_code(line), "DVBH 88")
        self.assertEqual(L.tags_of(line), {"issdate": "1998-09-21", "pages": "36"})

    def test_format_entry_and_round_trip(self):
        entry = {
            "entrycode": "DVBH  88p02",
            "storycode": "D 93332",
            "pages": 2,
            "hero": "MIM",
            "title": "Dọn rác",
            "tags": {"trans": "Đông Quỳnh"},
        }
        line = L.format_entry(entry)
        self.assertEqual(len(line[:52]), 52)
        parsed = L.parse_entry(line)
        self.assertEqual(parsed["entrycode"], "DVBH  88p02")
        self.assertEqual(parsed["storycode"], "D 93332")
        self.assertEqual(parsed["pages"], "2")
        self.assertEqual(parsed["hero"], "MIM")
        self.assertEqual(parsed["title"], "Dọn rác")
        self.assertEqual(parsed.get("trans"), "Đông Quỳnh")

    def test_format_entry_overflow(self):
        entry = {
            "entrycode": "VERY_LONG_ISSUE_CODE_p1234",
            "storycode": "VERY_LONG_STORY_CODE_12345",
            "pages": 128,
            "title": "Novel",
        }
        line = L.format_entry(entry)
        self.assertEqual(len(line[:52]), 52)
        parsed = L.parse_entry(line)
        self.assertEqual(parsed["entrycode"], "VERY_LONG_ISSUE_CODE_p1234")
        self.assertEqual(parsed["storycode"], "VERY_LONG_STORY_CODE_12345")
        self.assertEqual(parsed["pages"], "128")


def database():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE inducks_storyversion (storyversioncode TEXT, storycode TEXT, entirepages TEXT, rowsperpage TEXT);
        CREATE TABLE inducks_entry (entrycode TEXT, issuecode TEXT, storyversioncode TEXT, position TEXT, part TEXT);
    """)
    conn.executemany("INSERT INTO inducks_storyversion VALUES (?,?,?,?)", [
        ("X 1", "X 1", 52, 3), ("a/A 1p009", "X 1", 26, 3), ("a/A 1p037", "X 1", 26, 3),
        ("Y 1", "Y 1", 40, 3), ("b/B 1p005", "Y 1", 20, 3), ("b/B 1p045", "Y 1", 20, 3), ("b/B 1p089", "Y 1", 24, 3),
        ("Z 1", "Z 1", 20, 3), ("Z 2", "Z 2", 24, 4), ("Z 3", "Z 3", 30, 3),
        ("foreign_ver", "FOREIGN 1", 14, 4)])
    conn.executemany("INSERT INTO inducks_entry VALUES (?,?,?,?,?)", [
        ("a/A 1p009", "a/A 1", "a/A 1p009", "p009", "1"), ("a/A 1p037", "a/A 1", "a/A 1p037", "p037", "2"),
        ("b/B 1p005", "b/B 1", "b/B 1p005", "p005", "1"), ("b/B 1p025", "b/B 1", "Z 1", "p025", ""),
        ("b/B 1p045", "b/B 1", "b/B 1p045", "p045", "2"), ("b/B 1p065", "b/B 1", "Z 2", "p065", ""),
        ("b/B 1p089", "b/B 1", "b/B 1p089", "p089", "3")])
    return lambda sql, params=(): conn.execute(sql, params).fetchall()


def story(code, start, pages):
    return {"title": "T", "story_code": code, "start_page": start, "pages": pages}


class StoryRules(unittest.TestCase):
    def setUp(self):
        self.query = database()

    def test_serial_split_into_agreed_parts(self):
        out = apply_story_rules([story("X 1", 5, 52), story("Z 3", 57, 30)], self.query)
        self.assertEqual([(e["start_page"], e["pages"], e.get("part"), e.get("pagel")) for e in out],
                         [(5, 26, "1", "3"), (31, 26, "2", "3"), (57, 30, None, "3")])

    def test_interleaved_chapters_and_invented_code(self):
        out = apply_story_rules([story("SITE-123", 5, 64), story("Z 1", 25, 20), story("Z 2", 65, 24)],
                                self.query, log=lambda *_: None)
        parts = [(e["story_code"], e["start_page"], e["pages"], e["part"]) for e in out if e.get("part")]
        self.assertEqual(parts, [("Y 1", 5, 20, "1"), ("Y 1", 45, 20, "2"), ("Y 1", 89, 24, "3")])

    def test_pagel_only_when_length_kept(self):
        out = apply_story_rules([story("Z 3", 5, 30), story("Z 2", 35, 20)], self.query)
        self.assertEqual([e.get("pagel") for e in out], ["3", None])

    def test_unknown_code_without_equivalent_left_empty(self):
        out = apply_story_rules([story("Q 9", 5, 10), story("Z 3", 15, 30)], self.query, log=lambda *_: None)
        self.assertEqual(out[0]["story_code"], "")

    def test_without_the_tables_nothing_changes(self):
        empty = sqlite3.connect(":memory:")
        stories = [story("X 1", 5, 52)]
        self.assertEqual(apply_story_rules(stories, lambda s, p=(): empty.execute(s, p).fetchall()), stories)

    def test_known_story_fallback(self):
        self.assertEqual(known_story(self.query, "FOREIGN 1"), {"pages": 14, "rowsperpage": 4})

    def test_serial_part_from_previous_issue(self):
        # Story Z 1 was printed in b/B 1
        part_num = serial_part_from_previous_issue(self.query, "Z 1", "b/B 1")
        self.assertEqual(part_num, 2)
        # Story Z 1 was NOT printed in a/A 1
        part_num = serial_part_from_previous_issue(self.query, "Z 1", "a/A 1")
        self.assertEqual(part_num, 1)

    def test_cover_story_xref(self):
        stories = [
            {"title": "The Phantom of Notre Duck", "story_code": "W US   60-01"},
            {"title": "Picnic", "story_code": "D 93332"},
        ]
        self.assertEqual(
            cover_story_xref("The Phantom of Notre Duck", stories),
            "W US   60-01(story)"
        )
        self.assertIsNone(cover_story_xref("Unrelated Title", stories))


if __name__ == "__main__":
    unittest.main()
