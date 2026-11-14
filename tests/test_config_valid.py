"""A presets.json alakjának ellenőrzése (valid_config): mit fogad el és mit utasít el az importálás és a betöltés."""
import unittest

from config import valid_config


def preset(**extra):
    return {"gamma": 2.2, "contrast": 50, "brightness": 50, **extra}


def config_with(*presets, monitor_id="MON1"):
    return {"monitors": [{"id": monitor_id, "presets": {f"P{index}": item for index, item in enumerate(presets)}}]}


class ValidConfigTest(unittest.TestCase):
    def test_ervenyes_konfig_elfogadott(self):
        self.assertTrue(valid_config(config_with(preset(), preset(gain=[100, 90, 80],
                                                                   variants={"Másik": preset(gain=[50, 50, 50])}))))

    def test_monitor_preset_nelkul_is_ervenyes(self):
        self.assertTrue(valid_config({"monitors": [{"id": "MON1"}]}))
        self.assertTrue(valid_config({"monitors": []}))

    def test_nem_szotar_vagy_monitorlista_nelkuli_elutasitott(self):
        for config in (None, [], "x", {}, {"monitors": {}}, {"monitors": [5]}):
            self.assertFalse(valid_config(config), config)

    def test_monitor_azonosito_es_presetek_alakja(self):
        self.assertFalse(valid_config({"monitors": [{"id": 5, "presets": {}}]}))
        self.assertFalse(valid_config({"monitors": [{"id": "MON1", "presets": []}]}))

    def test_hianyzo_vagy_nem_szam_alapertek_elutasitott(self):
        self.assertFalse(valid_config(config_with({"gamma": 2.2, "contrast": 50})))
        self.assertFalse(valid_config(config_with(preset(brightness="50"))))
        self.assertFalse(valid_config(config_with(preset(gamma=True))))

    def test_hibas_valtozat_elutasitott(self):
        self.assertFalse(valid_config(config_with(preset(variants=[]))))
        self.assertFalse(valid_config(config_with(preset(variants={"Hibás": {"gamma": 1}}))))

    def test_a_szincsatorna_erosites_harom_szazalekertek(self):
        for gain in ([100, 100], [101, 0, 0], [-1, 0, 0], [True, 1, 1], "abc"):
            self.assertFalse(valid_config(config_with(preset(gain=gain))), gain)
        self.assertFalse(valid_config(config_with(preset(variants={"V": preset(gain=[1, 2])}))))


if __name__ == "__main__":
    unittest.main()
