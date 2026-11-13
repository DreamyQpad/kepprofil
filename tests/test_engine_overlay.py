"""A motor overlay-hoz kellő részei: cél, mentés, új változat, gyorsgomb-térkép."""
import unittest

from tests.stubs import default_cfg, make_engine


def two_monitor_cfg():
    cfg = default_cfg()
    cfg["monitors"].append({"id": "MON2", "name": "Monitor 2", "presets": {
        "Alap": {"gamma": 2.2, "contrast": 50, "brightness": 50, "vibrance": 50, "process": ""},
        "Másik": {"gamma": 2.0, "contrast": 50, "brightness": 50, "vibrance": 50, "process": "other"}}})
    return cfg


def with_variants(cfg, names):
    p = cfg["monitors"][0]["presets"]["Játék"]
    p["variants"] = {n: {"gamma": 2.2, "contrast": 55, "brightness": 45, "vibrance": 60, "gain": [100, 100, 100]}
                     for n in names}
    return cfg


class OverlayTarget(unittest.TestCase):
    def test_overlay_target_prefers_foreground_monitor(self):
        eng, _ = make_engine(self, two_monitor_cfg())
        eng.active["MON2"] = "Másik"
        self.assertEqual(eng.overlay_target("MON2"), ("MON2", "Másik"))

    def test_overlay_target_falls_back_to_first_active(self):
        eng, _ = make_engine(self, two_monitor_cfg())
        eng.active["MON2"] = "Másik"
        self.assertEqual(eng.overlay_target(None), ("MON1", "Játék"))
        self.assertEqual(eng.overlay_target("NINCSILYEN"), ("MON1", "Játék"))

    def test_overlay_target_none_without_active(self):
        eng, _ = make_engine(self, active=None)
        self.assertIsNone(eng.overlay_target("MON1"))


class SaveValues(unittest.TestCase):
    def test_save_values_without_variants_writes_top_level(self):
        eng, _ = make_engine(self)
        eng.save_values("MON1", "Játék", (1.1, 60, 40, 70), [100, 90, 80])
        p = eng.preset("MON1", "Játék")
        self.assertEqual((p["gamma"], p["contrast"], p["brightness"], p["vibrance"], p["gain"]), (1.1, 60, 40, 70, [100, 90, 80]))
        self.assertEqual(eng.saves["config"], 1)

    def test_save_values_writes_current_variant_and_mirrors_first(self):
        eng, _ = make_engine(self, with_variants(default_cfg(), ["Alap", "Éjjel"]))
        eng.variant[("MON1", "Játék")] = "Éjjel"
        eng.save_values("MON1", "Játék", (1.5, 61, 41, 71), [90, 90, 90])
        p = eng.preset("MON1", "Játék")
        self.assertEqual(p["variants"]["Éjjel"]["gamma"], 1.5)
        self.assertEqual(p["variants"]["Alap"]["gamma"], 2.2)           # az első változat nem változott
        self.assertEqual(p["gamma"], 2.2)                               # a felső szint az elsőt tükrözi

    def test_save_values_writes_first_variant_and_mirrors_it(self):
        eng, _ = make_engine(self, with_variants(default_cfg(), ["Alap", "Éjjel"]))
        eng.save_values("MON1", "Játék", (1.5, 61, 41, 71), [90, 90, 90])
        p = eng.preset("MON1", "Játék")
        self.assertEqual(p["variants"]["Alap"]["gamma"], 1.5)
        self.assertEqual(p["gamma"], 1.5)

    def test_save_values_keeps_hotkey_and_process(self):
        eng, _ = make_engine(self)
        eng.save_values("MON1", "Játék", (1.1, 60, 40, 70), [100, 100, 100])
        p = eng.preset("MON1", "Játék")
        self.assertEqual((p["hotkey"], p["process"]), ("ctrl+alt+1", "game"))


class AddVariant(unittest.TestCase):
    def test_add_variant_first_time_creates_alap_and_valtozat_2(self):
        eng, _ = make_engine(self)
        name = eng.add_variant("MON1", "Játék", (1.3, 70, 30, 80), [100, 95, 90])
        p = eng.preset("MON1", "Játék")
        self.assertEqual(name, "Változat 2")
        self.assertEqual(list(p["variants"]), ["Alap", "Változat 2"])
        self.assertEqual(p["variants"]["Alap"]["contrast"], 55)          # az eddigi mentett érték
        self.assertEqual(p["variants"]["Változat 2"]["contrast"], 70)    # a mostani csúszkaállás
        self.assertEqual(p["variants"]["Változat 2"]["gain"], [100, 95, 90])
        self.assertEqual(eng.variant[("MON1", "Játék")], "Változat 2")
        self.assertEqual(eng.saves["config"], 1)

    def test_add_variant_name_collision_gives_next_free(self):
        eng, _ = make_engine(self, with_variants(default_cfg(), ["Alap", "Változat 2", "Változat 4"]))
        self.assertEqual(eng.add_variant("MON1", "Játék", (1.0, 50, 50, 50), [100, 100, 100]), "Változat 3")

    def test_add_variant_does_not_change_first_variant_mirror(self):
        eng, _ = make_engine(self, with_variants(default_cfg(), ["Alap"]))
        eng.add_variant("MON1", "Játék", (1.0, 10, 10, 10), [100, 100, 100])
        p = eng.preset("MON1", "Játék")
        self.assertEqual(p["contrast"], 55)


class HotkeyMap(unittest.TestCase):
    def test_hotkey_map_has_overlay_when_set(self):
        eng, _ = make_engine(self, settings={"overlay_hotkey": "ctrl+alt+o"})
        self.assertEqual(eng.hotkey_map()["overlay"], "ctrl+alt+o")

    def test_hotkey_map_has_no_overlay_when_empty(self):
        eng, _ = make_engine(self)
        self.assertNotIn("overlay", eng.hotkey_map())

    def test_overlay_hotkey_is_persisted_setting(self):
        from config import DEFAULT_SETTINGS, SETTINGS_KEYS
        self.assertEqual(DEFAULT_SETTINGS["overlay_hotkey"], "")
        self.assertIn("overlay_hotkey", SETTINGS_KEYS)


if __name__ == "__main__":
    unittest.main()
