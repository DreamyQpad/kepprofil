"""A térkép-overlay beállításai és gyorsgombjai a motorban."""
import unittest

from config import DEFAULT_SETTINGS, SETTINGS_KEYS
from tests.stubs import make_engine


class MapHotkeys(unittest.TestCase):
    def test_hotkey_map_tartalmazza_a_terkep_gombokat(self):
        eng, _ = make_engine(self, settings={"map_hotkey": "Ctrl+Alt+M", "map_interact_hotkey": "Ctrl+Alt+N"})
        hotkeys = eng.hotkey_map()
        self.assertEqual(hotkeys["map"], "Ctrl+Alt+M")
        self.assertEqual(hotkeys["map_interact"], "Ctrl+Alt+N")

    def test_ures_gomb_nem_kerul_be(self):
        eng, _ = make_engine(self)
        hotkeys = eng.hotkey_map()
        self.assertNotIn("map", hotkeys)
        self.assertNotIn("map_interact", hotkeys)


class MapSettings(unittest.TestCase):
    def test_alapertekek(self):
        self.assertEqual(DEFAULT_SETTINGS["map_hotkey"], "")
        self.assertEqual(DEFAULT_SETTINGS["map_interact_hotkey"], "")
        self.assertIs(DEFAULT_SETTINGS["map_auto"], True)
        self.assertEqual(DEFAULT_SETTINGS["map_alpha"], 0.85)
        self.assertIsNone(DEFAULT_SETTINGS["map_rect"])
        self.assertEqual(DEFAULT_SETTINGS["tarkov_path"], "")

    def test_a_mentesbe_exportba_kerulo_kulcsok_tartalmazzak_az_ujakat(self):
        for key in ("map_hotkey", "map_interact_hotkey", "map_auto", "map_alpha", "map_rect", "tarkov_path"):
            self.assertIn(key, SETTINGS_KEYS)


if __name__ == "__main__":
    unittest.main()
