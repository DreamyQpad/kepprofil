"""A főmenü gyorsgombjai: a Tab felismerése, a menu_hotkey alapértéke és a motor gombtérképe."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import config
from config import DEFAULT_SETTINGS, SETTINGS_KEYS
from hw_common import MENU_KEYS, parse_hotkey
from tests.stubs import make_engine


class TabKey(unittest.TestCase):
    def test_shift_tab_ertelmezheto(self):
        self.assertEqual(parse_hotkey("Shift+Tab"), (0x4, 0x09))

    def test_tab_modosito_nelkul_nem_gyorsgomb(self):
        self.assertIsNone(parse_hotkey("Tab"))

    def test_menu_gombok(self):
        self.assertEqual(set(MENU_KEYS), {"mn|up", "mn|down", "mn|ok", "mn|close"})
        self.assertEqual(MENU_KEYS["mn|ok"], (0, 0x0D, False))
        self.assertEqual(MENU_KEYS["mn|close"], (0, 0x1B, False))


class MenuSetting(unittest.TestCase):
    def test_alapertek_shift_tab(self):
        self.assertEqual(DEFAULT_SETTINGS["menu_hotkey"], "Shift+Tab")
        self.assertIn("menu_hotkey", SETTINGS_KEYS)

    def test_regi_beallitasfajl_is_megkapja_az_alapot(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        old = tmp / "settings.json"
        old.write_text(json.dumps({"night_strength": 10}), encoding="utf-8")
        with mock.patch.object(config, "SETTINGS_FILE", old):
            self.assertEqual(config.load_settings()["menu_hotkey"], "Shift+Tab")

    def test_hotkey_map_tartalmazza_a_menut(self):
        eng, _ = make_engine(self, settings={"menu_hotkey": "Shift+Tab"})
        self.assertEqual(eng.hotkey_map()["menu"], "Shift+Tab")

    def test_ures_menu_gomb_nem_kerul_be(self):
        eng, _ = make_engine(self, settings={"menu_hotkey": ""})
        self.assertNotIn("menu", eng.hotkey_map())


try:
    from gui_widgets import HotkeyEntry
    import customtkinter as ctk
except ImportError:                                     # pragma: no cover
    HotkeyEntry = None


@unittest.skipIf(HotkeyEntry is None, "nincs customtkinter")
class HotkeyEntryTab(unittest.TestCase):
    def test_shift_tab_lenyomasa_rogzitheto(self):
        try:
            root = ctk.CTk()
        except Exception as error:                      # nincs képernyő
            self.skipTest(str(error))
        self.addCleanup(root.destroy)
        changes = []
        entry = HotkeyEntry(root, on_change=changes.append)
        for keysym in ("Tab", "ISO_Left_Tab"):
            event = type("E", (), {"keysym": keysym, "state": 0x1})()
            entry._on_key(event)
            self.assertEqual(entry.get(), "Shift+Tab", keysym)
        self.assertEqual(changes, ["Shift+Tab", "Shift+Tab"])


if __name__ == "__main__":
    unittest.main()
