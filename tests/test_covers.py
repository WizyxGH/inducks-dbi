"""inducks_dbi.covers on invented data: synthetic images, an in-memory ISV subset."""
import io
import random
import sqlite3
import unittest

from PIL import Image, ImageDraw

from inducks_dbi import covers as C


def picture(seed: int, logo: str = "", shift: int = 0) -> bytes:
    """A random 'drawing' under a title band; the same seed is the same drawing."""
    rnd = random.Random(seed)
    im = Image.new("RGB", (300, 450), "white")
    d = ImageDraw.Draw(im)
    for _ in range(40):
        x, y = rnd.randrange(0, 300), rnd.randrange(130, 450)
        d.ellipse((x + shift, y, x + shift + rnd.randrange(20, 90), y + rnd.randrange(20, 90)),
                  fill=tuple(rnd.randrange(256) for _ in range(3)))
    d.rectangle((0, 0, 300, 110), fill="red" if logo else "blue")
    d.text((20, 40), logo or "LOGO", fill="white")
    out = io.BytesIO()
    im.save(out, "JPEG", quality=80)
    return out.getvalue()


def database():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE inducks_storyversion (storyversioncode TEXT, storycode TEXT);
        CREATE TABLE inducks_entry (entrycode TEXT, issuecode TEXT, storyversioncode TEXT, position TEXT);
        CREATE TABLE inducks_entryurl (entrycode TEXT, sitecode TEXT, pagenumber TEXT, url TEXT, storycode TEXT);
        INSERT INTO inducks_storyversion VALUES ('S 1','S 1'), ('S 2','S 2'), ('S 3','S 3'), ('CV A','CV A'), ('CV B','CV B');
        INSERT INTO inducks_entry VALUES
          ('dk/X 1a','dk/X 1','CV A','a'), ('dk/X 1b','dk/X 1','S 1','b'), ('dk/X 1c','dk/X 1','S 2','c'),
          ('no/Y 9a','no/Y 9','CV B','a'), ('no/Y 9b','no/Y 9','S 2','b'), ('no/Y 9c','no/Y 9','S 3','c'),
          ('se/Z 5a','se/Z 5','CV A','a'), ('se/Z 5b','se/Z 5','S 3','b');
        INSERT INTO inducks_entryurl VALUES
          ('dk/X 1a','webusers','1','x1a.jpg','CV A'), ('se/Z 5a','webusers','1','z5a.jpg','CV A'),
          ('no/Y 9a','webusers','1','y9a.jpg','CV B'), ('no/Y 9a','thumbnails','1','y9a.jpg','CV B');
    """)
    return lambda sql, params=(): conn.execute(sql, params).fetchall()


IMAGES = {C.scan_url("x1a.jpg"): picture(1, "DANSK"), C.scan_url("z5a.jpg"): picture(1, "SVENSK", 6),
          C.scan_url("y9a.jpg"): picture(2, "NORSK")}


class Covers(unittest.TestCase):
    def test_same_drawing_under_another_logo_is_close(self):
        self.assertLess(C.distance(C.dhash(picture(1)), C.dhash(picture(1, "DANSK", 6))), C.MAX_DISTANCE)
        self.assertGreater(C.distance(C.dhash(picture(1)), C.dhash(picture(2))), C.MAX_DISTANCE)

    def test_candidates_are_covers_of_issues_sharing_the_stories(self):
        found = C.cover_candidates(database(), ["S 1", "S 2", "S 3"])
        self.assertEqual(found, {"CV A": [C.scan_url("x1a.jpg"), C.scan_url("z5a.jpg")],
                                 "CV B": [C.scan_url("y9a.jpg")]})

    def test_reprinted_cover_found(self):
        code = C.find_cover_code(database(), picture(1, "LTB"), ["S 1", "S 2", "S 3"], IMAGES.get, log=lambda *_: None)
        self.assertEqual(code, "CV A")

    def test_new_cover_gets_no_code(self):
        code = C.find_cover_code(database(), picture(7, "LTB"), ["S 1", "S 2", "S 3"], IMAGES.get, log=lambda *_: None)
        self.assertIsNone(code)

    def test_unreadable_image_or_no_stories(self):
        self.assertIsNone(C.find_cover_code(database(), b"not an image", ["S 1", "S 2"], IMAGES.get, log=lambda *_: None))
        self.assertIsNone(C.find_cover_code(database(), picture(1), [], IMAGES.get, log=lambda *_: None))


if __name__ == "__main__":
    unittest.main()
