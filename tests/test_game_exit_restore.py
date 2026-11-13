"""Játékból kilépés: a figyelő arra a presetre áll vissza, ami a játék indulása előtt be volt kapcsolva (nem a semlegesre)."""
import unittest
from unittest import mock

from tests.stubs import default_cfg, make_engine


def cfg_alap_100():
    cfg = default_cfg()
    cfg["monitors"][0]["presets"]["Alap"]["vibrance"] = 100
    return cfg


def tick(eng, running):
    eng.running = set(running)
    eng.running_t = 1e18                                         # ne frissítse a futó programokat
    eng.monitors_t = 1e18                                        # és a monitorlistát se
    with mock.patch("engine.time.sleep"):
        eng.watch_tick()


def last_vals(display, dev="DEV_MON1"):
    return [c for c in display.calls if c[0] == dev][-1][1]


class GameExitRestoreTest(unittest.TestCase):
    def test_kilepeskor_az_indulas_elotti_preset_ter_vissza(self):
        eng, display = make_engine(self, cfg_alap_100(), active=("MON1", "Alap"))
        tick(eng, {"game"})
        self.assertEqual(eng.active["MON1"], "Játék")
        self.assertEqual(last_vals(display)[3], 60)              # a játék preset vibrance-a
        tick(eng, set())                                         # a játék kilépett
        self.assertEqual(eng.active.get("MON1"), "Alap")
        self.assertEqual(last_vals(display)[3], 100)             # az elmentett alap, nem a semleges 50

    def test_ha_indulaskor_nem_volt_preset_kilepeskor_semleges_marad(self):
        eng, display = make_engine(self, cfg_alap_100(), active=None)
        tick(eng, {"game"})
        tick(eng, set())
        self.assertNotIn("MON1", eng.active)
        self.assertEqual(last_vals(display), (2.2, 50, 50, 50))

    def test_kezzel_masik_presetre_valtas_a_jatek_alatt_nem_ules_felul_kilepeskor(self):
        cfg = cfg_alap_100()
        cfg["monitors"][0]["presets"]["Éjjel"] = {"gamma": 2.0, "contrast": 40, "brightness": 40, "vibrance": 30, "process": ""}
        eng, display = make_engine(self, cfg, active=("MON1", "Alap"))
        tick(eng, {"game"})
        eng.set_active("MON1", "Éjjel", True)                    # kézi váltás a játék alatt
        tick(eng, set())
        self.assertEqual(eng.active.get("MON1"), "Éjjel")
        self.assertEqual(last_vals(display)[3], 30)

    def test_semleges_gomb_a_jatek_alatt_nem_hoz_vissza_alapot_kilepeskor(self):
        eng, display = make_engine(self, cfg_alap_100(), active=("MON1", "Alap"))
        tick(eng, {"game"})
        eng.neutral_all()
        tick(eng, set())
        self.assertNotIn("MON1", eng.active)
        self.assertEqual(last_vals(display), (2.2, 50, 50, 50))

    def test_a_visszaallitas_csak_letezo_presetre_megy(self):
        eng, display = make_engine(self, cfg_alap_100(), active=("MON1", "Alap"))
        tick(eng, {"game"})
        del eng.mon("MON1")["presets"]["Alap"]                   # a játék alatt törölték az alapot
        tick(eng, set())
        self.assertNotIn("MON1", eng.active)
        self.assertEqual(last_vals(display), (2.2, 50, 50, 50))


if __name__ == "__main__":
    unittest.main()
