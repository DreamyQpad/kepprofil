"""Gyorsgomb-réteg: nyers (módosító nélküli) gombok az overlay-hez, az előtér-monitor azonosítása."""
import sys
import unittest
from unittest import mock

WIN = sys.platform == "win32"
if WIN:
    import hw_windows
    from hw_windows import Hotkeys, user32
from hw_common import OVERLAY_KEYS

VK_F24 = 0x87                     # a teszt ezt használja: ritkán foglalt, és nem zavarja a user gépelését


class OverlayKeyTable(unittest.TestCase):
    def test_table_covers_all_overlay_actions(self):
        self.assertEqual(set(OVERLAY_KEYS), {"ov|up", "ov|down", "ov|left", "ov|right", "ov|sleft", "ov|sright",
                                             "ov|reset", "ov|save", "ov|new", "ov|close"})
        self.assertEqual(OVERLAY_KEYS["ov|save"], (0, 0x0D, False))
        self.assertEqual(OVERLAY_KEYS["ov|sleft"], (0x4, 0x25, True))
        self.assertTrue(all(len(v) == 3 for v in OVERLAY_KEYS.values()))


@unittest.skipUnless(WIN, "Windows-gyorsgombok")
class RawKeys(unittest.TestCase):
    def setUp(self):
        self.hk = Hotkeys(lambda action: None)
        self.hk.start()
        self.addCleanup(self.hk.set, {})

    def test_raw_keys_register_and_release(self):
        self.hk.set({"ov|f24": (0, VK_F24, True)})
        self.assertFalse(user32.RegisterHotKey(None, 9001, 0, VK_F24), "a gomb nincs lefoglalva")
        self.hk.set({})
        self.assertTrue(user32.RegisterHotKey(None, 9001, 0, VK_F24), "zárás után a gomb nem szabadult fel")
        user32.UnregisterHotKey(None, 9001)

    def test_failed_set_reports_action(self):
        self.assertTrue(user32.RegisterHotKey(None, 9002, 0, VK_F24))
        self.addCleanup(user32.UnregisterHotKey, None, 9002)
        self.hk.set({"ov|f24": (0, VK_F24, False)})
        self.assertIn("ov|f24", self.hk.failed)

    def test_text_hotkeys_still_work(self):
        self.hk.set({"x": "ctrl+alt+shift+f24"})
        self.assertEqual(self.hk.failed, set())
        self.assertFalse(user32.RegisterHotKey(None, 9003, 0x2 | 0x1 | 0x4, VK_F24))

    def test_repeat_flag_only_when_asked(self):
        calls = []
        real = user32.RegisterHotKey

        def spy(hwnd, i, mods, vk):
            calls.append((vk, mods))
            return real(hwnd, i, mods, vk)

        with mock.patch.object(user32, "RegisterHotKey", spy):
            self.hk.set({"rep": (0, VK_F24, True), "norep": (0, VK_F24 - 1, False), "text": "ctrl+alt+shift+f22"})
        flags = dict(calls)
        self.assertEqual(flags[VK_F24], 0)                       # ismétlődhet: nincs MOD_NOREPEAT
        self.assertEqual(flags[VK_F24 - 1], 0x4000)
        self.assertEqual(flags[VK_F24 - 2], 0x4000 | 0x2 | 0x1 | 0x4)   # a szöveges gomb NOREPEAT-tel megy


@unittest.skipUnless(WIN, "Windows-függvény")
class Foreground(unittest.TestCase):
    def test_foreground_monitor_id_is_known_monitor(self):
        mid = hw_windows.foreground_monitor_id()
        self.assertTrue(mid is None or mid in [m["id"] for m in hw_windows.list_monitors()])


if __name__ == "__main__":
    unittest.main()
