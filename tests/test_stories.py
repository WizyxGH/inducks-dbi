import unittest
from inducks_dbi.stories import format_fsb_story, format_dbs_story


class StoriesTest(unittest.TestCase):
    def test_format_fsb_story_basic(self):
        story = format_fsb_story(
            story_code="I TL 3704-1",
            title="River Sharks",
            pages=34,
            creation_date="18-11-2026",
            writ="Francesco Testi",
            art="Nicolino Picone",
            characters=["Dan Hermine (1st)", "Dollie Wonderduck", "Zio Paperone"],
            color="Manuel Giarolli",
            series="P.d.P.",
            printed_code="IP-3704-1",
        )
        lines = story.split("\n")
        self.assertEqual(lines[0], "I TL 3704-1 (18-11-2026)")
        self.assertEqual(lines[1], "River Sharks")
        self.assertEqual(lines[2], "/Francesco Testi/Nicolino Picone/")
        self.assertEqual(lines[3], "34//;Dan Hermine (1st), Dollie Wonderduck, Zio Paperone")
        self.assertIn("[colore: Manuel Giarolli]", lines)
        self.assertIn("[serie: P.d.P.]", lines)
        self.assertIn("[codice: IP-3704-1]", lines)

    def test_format_fsb_story_with_hero_and_plot(self):
        story = format_fsb_story(
            story_code="I TL 3704-2",
            title="Ciccio e il trattore intellettuale",
            pages=20,
            creation_date="18-11-2026",
            writ="Giovanni Eccher",
            art="Graziano Barbaro",
            hero="Ciccio",
            characters=["Archimede", "Billy la capra", "Nonna Papera"],
            color="Debora Grazio",
            printed_code="IP-3704-2",
        )
        lines = story.split("\n")
        self.assertEqual(lines[0], "I TL 3704-2 (18-11-2026)")
        self.assertEqual(lines[1], "Ciccio e il trattore intellettuale")
        self.assertEqual(lines[2], "/Giovanni Eccher/Graziano Barbaro/")
        self.assertEqual(lines[3], "20//Ciccio;Archimede, Billy la capra, Nonna Papera")
        self.assertIn("[colore: Debora Grazio]", lines)
        self.assertIn("[codice: IP-3704-2]", lines)

    def test_format_dbs_story_basic(self):
        story = format_dbs_story(
            story_code="S 90006",
            title="Mythology Land And Back",
            pages=6,
            characters=["WTP", "Piglet", "Tigger", "CR"],
            description="unicorn takes WTP and friends to a land of mythological creatures",
        )
        # Positions: code 14 chars, pages 2 chars (right aligned), etc.
        self.assertTrue(story.startswith("S 90006        6"))
        self.assertIn("Mythology Land And Back", story)
        self.assertIn("[xapp:WTP, Piglet, Tigger, CR]", story)
        self.assertIn("[desc:unicorn takes WTP and friends to a land of mythological creatures]", story)


if __name__ == "__main__":
    unittest.main()
