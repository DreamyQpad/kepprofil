"""A parancssori akciók (`kijelzo.py --action`): értelmezés a motor belső azonosítójára, és a gombok szövegének visszaépítése."""
import unittest

from hw_common import build_action, parse_action


class ParseAction(unittest.TestCase):
    def test_simple_actions(self):
        for text in ("night", "neutral", "cycle"):
            self.assertEqual(parse_action(text), text)

    def test_cycle_is_global_and_takes_no_arguments(self):
        self.assertEqual(parse_action("  cycle "), "cycle")
        self.assertIsNone(parse_action("cycle:MON1:Játék"))
        self.assertIsNone(parse_action("c|MON1|Játék"))

    def test_preset_and_variant(self):
        self.assertEqual(parse_action("preset:MON1:Játék"), "p|MON1|Játék")
        self.assertEqual(parse_action("variant:MON1:Játék:Éjjel"), "v|MON1|Játék|Éjjel")
        self.assertEqual(parse_action("p|MON1|Játék"), "p|MON1|Játék")

    def test_invalid_actions(self):
        for text in ("", None, "ismeretlen", "preset:MON1", "preset::Játék", "variant:MON1:Játék", "p|MON1"):
            self.assertIsNone(parse_action(text), text)

    def test_build_action_round_trip(self):
        self.assertEqual(build_action("preset", "MON1", "Játék"), "preset:MON1:Játék")
        self.assertEqual(parse_action(build_action("variant", "MON1", "Játék", "Éjjel")), "v|MON1|Játék|Éjjel")
        self.assertEqual(build_action("preset", "MON1", "A:B"), "p|MON1|A:B")      # kettőspontos névhez a belső alak
        self.assertIsNone(build_action("preset", "MON1", "A|B"))


if __name__ == "__main__":
    unittest.main()
