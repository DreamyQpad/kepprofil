"""A gyorsgomb-rétegek: az overlay, a menü és a térkép gombjai együtt élnek, egyik sem írja felül a másikét."""
import unittest

from hotkey_layers import HotkeyLayers


class HotkeyLayersTest(unittest.TestCase):
    def setUp(self):
        self.base = {"cycle": "F8", "overlay": "F7", "map": "F10"}
        self.applied = []
        self.layers = HotkeyLayers(lambda: self.base, self.applied.append)
        self.overlay = self.layers.setter("overlay")
        self.menu = self.layers.setter("menu")
        self.map = self.layers.setter("map")

    def test_a_reteg_gombjai_az_alap_fole_kerulnek(self):
        self.overlay({**self.base, "ov|up": "Up", "ov|close": "Esc"})
        self.assertEqual(self.applied[-1], {**self.base, "ov|up": "Up", "ov|close": "Esc"})

    def test_a_reteg_felszabadulasa_utan_csak_az_alap_marad(self):
        self.overlay({**self.base, "ov|up": "Up"})
        self.overlay(dict(self.base))
        self.assertEqual(self.applied[-1], self.base)

    def test_a_terkep_allapotvaltasa_nem_szabaditja_fel_a_nyitott_overlay_gombjait(self):
        self.overlay({**self.base, "ov|up": "Up"})
        self.map(dict(self.base))                         # raid vége, a térkép leáll
        self.assertIn("ov|up", self.applied[-1])

    def test_a_terkep_allapotvaltasa_nem_szabaditja_fel_a_nyitott_menu_gombjait(self):
        self.menu({**self.base, "mn|ok": "Enter"})
        self.map(dict(self.base))
        self.assertIn("mn|ok", self.applied[-1])

    def test_a_menu_zarasa_nem_viszi_el_a_terkep_billentyuzetes_gombjait(self):
        self.map({**self.base, "mp|left": "Left"})
        self.menu({**self.base, "mn|ok": "Enter"})
        self.menu(dict(self.base))
        self.assertEqual(self.applied[-1], {**self.base, "mp|left": "Left"})

    def test_az_alap_valtozasat_a_kovetkezo_alkalmazas_felveszi(self):
        self.base = {**self.base, "cycle": "F6"}
        self.layers.refresh()
        self.assertEqual(self.applied[-1]["cycle"], "F6")

    def test_a_frissites_a_nyitott_retegeket_megtartja(self):
        self.overlay({**self.base, "ov|up": "Up"})
        self.layers.refresh()
        self.assertIn("ov|up", self.applied[-1])


if __name__ == "__main__":
    unittest.main()
