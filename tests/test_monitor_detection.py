"""Monitor-detektálás: csak a csatlakoztatott monitor látszik és működik; ki-/becsatlakoztatást a motor észreveszi."""
import copy
import unittest

from tests.stubs import default_cfg, make_engine


def two_monitors():
    cfg = default_cfg()
    second = copy.deepcopy(cfg["monitors"][0])
    second.update(id="MON2", name="Monitor 2")
    second["presets"]["Játék"]["process"] = "masikjatek"
    cfg["monitors"].append(second)
    return cfg


class MonitorDetectionTest(unittest.TestCase):
    def test_lecsatlakoztatott_monitor_nem_latszik_de_a_presetje_megmarad(self):
        eng, _ = make_engine(self, two_monitors(), plugged=["MON1"], active=None)
        self.assertEqual([m["id"] for m in eng.mons()], ["MON1"])
        self.assertEqual([m["id"] for m in eng.cfg["monitors"]], ["MON1", "MON2"])
        self.assertIn("Játék", eng.mon("MON2")["presets"])

    def test_becsatlakoztatott_monitor_megjelenik_es_jelez(self):
        eng, _ = make_engine(self, two_monitors(), plugged=["MON1"], active=None)
        calls = []
        eng.monitors_cb = lambda: calls.append(1)
        self.plugged.append("MON2")
        self.assertTrue(eng.refresh_monitors())
        self.assertEqual([m["id"] for m in eng.mons()], ["MON1", "MON2"])
        self.assertEqual(len(calls), 1)
        self.assertFalse(eng.refresh_monitors())                 # változatlan állapotra nem jelez újra
        self.assertEqual(len(calls), 1)

    def test_vadonatuj_monitor_felkerul_a_cfg_be_alap_preseettel(self):
        eng, _ = make_engine(self, default_cfg(), active=None)
        self.plugged.append("UJ123")
        eng.refresh_monitors()
        self.assertEqual([m["id"] for m in eng.mons()], ["MON1", "UJ123"])
        self.assertIn("Alap", eng.mon("UJ123")["presets"])
        self.assertEqual(eng.saves["config"], 1)

    def test_lecsatlakozaskor_a_bekapcsolt_allapot_es_az_ejszakai_mod_eldobodik(self):
        eng, _ = make_engine(self, two_monitors(), active=("MON2", "Játék"))
        eng.night_mons.add("MON2")
        self.plugged.remove("MON2")
        self.assertTrue(eng.refresh_monitors())
        self.assertNotIn("MON2", eng.active)
        self.assertNotIn("MON2", eng.night_mons)
        self.assertEqual([m["id"] for m in eng.mons()], ["MON1"])

    def test_gyorsgomb_csak_a_csatlakoztatott_monitorhoz_van(self):
        cfg = two_monitors()
        cfg["monitors"][1]["presets"]["Játék"]["hotkey"] = "ctrl+alt+2"
        eng, _ = make_engine(self, cfg, plugged=["MON1"], active=None)
        self.assertEqual(list(eng.hotkey_map().values()), ["ctrl+alt+1"])

    def test_a_figyelo_nem_kapcsol_be_presetet_lecsatlakoztatott_monitoron(self):
        eng, display = make_engine(self, two_monitors(), plugged=["MON1"], active=None)
        eng.running = {"masikjatek"}
        eng.running_t = 1e18                                     # ne frissítse a futó programokat
        eng.monitors_t = 1e18                                    # és a monitorlistát se
        eng.watch_tick()
        self.assertNotIn("MON2", eng.active)
        self.assertFalse([c for c in display.calls if c[0] == "DEV_MON2"])

    def test_ures_detektalas_nem_uriti_ki_a_listat(self):
        eng, _ = make_engine(self, two_monitors(), active=None)
        self.plugged.clear()                                     # a driver átmenetileg üres listát ad
        self.assertFalse(eng.refresh_monitors())
        self.assertEqual(len(eng.mons()), 2)

    def test_ha_a_detektalas_induláskor_nem_megy_minden_monitor_marad(self):
        eng, _ = make_engine(self, two_monitors(), plugged=[], active=None)
        self.assertEqual(len(eng.mons()), 2)


if __name__ == "__main__":
    unittest.main()
