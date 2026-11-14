"""A preset- és változatműveletek (preset_ops) viselkedése a stubolt motoron: név-ellenőrzés, változat-létrehozás, átnevezés,
törlés, másolat, export/import."""
import json
import tempfile
import unittest
from pathlib import Path

import preset_ops
from tests.stubs import make_engine

NEW_VALUES = preset_ops.values_dict(2.0, 60, 40, 70, [100, 90, 80])


class CleanNameTest(unittest.TestCase):
    def test_szokozok_levagva(self):
        self.assertEqual(preset_ops.clean_name("  Új  ", {"Alap"}, "preset"), ("Új", None))

    def test_ures_vagy_mege_nem_hiba(self):
        self.assertEqual(preset_ops.clean_name("   ", {}, "preset"), (None, None))
        self.assertEqual(preset_ops.clean_name(None, {}, "preset"), (None, None))

    def test_csohuzo_tilos(self):
        self.assertEqual(preset_ops.clean_name("a|b", {}, "preset"), (None, "A névben nem lehet | jel."))

    def test_foglalt_nev_a_fajtat_emliti(self):
        self.assertEqual(preset_ops.clean_name("Alap", {"Alap": 1}, "preset"), (None, "Ilyen nevű preset már van."))
        self.assertEqual(preset_ops.clean_name("Alap", ["Alap"], "változat"), (None, "Ilyen nevű változat már van."))


class VariantOpsTest(unittest.TestCase):
    def setUp(self):
        self.eng, _ = make_engine(self)

    def variants(self, name="Játék"):
        return self.eng.preset("MON1", name).get("variants")

    def test_elso_valtozat_az_eddigi_ertekekbol_lesz(self):
        self.assertIsNone(preset_ops.add_variant(self.eng, "MON1", "Játék", "Pálya1", NEW_VALUES))
        variants = self.variants()
        self.assertEqual(list(variants), ["Alap", "Pálya1"])
        self.assertEqual((variants["Alap"]["contrast"], variants["Alap"]["brightness"], variants["Alap"]["vibrance"]),
                         (55, 45, 60))
        self.assertEqual(variants["Pálya1"], NEW_VALUES)
        self.assertEqual(self.eng.variant[("MON1", "Játék")], "Pálya1")
        self.assertEqual(self.eng.saves["config"], 1)

    def test_elso_valtozat_neve_nem_lehet_alap(self):
        error = preset_ops.add_variant(self.eng, "MON1", "Játék", "Alap", NEW_VALUES)
        self.assertIn("Ilyen nevű változat már van", error)
        self.assertIsNone(self.variants())
        self.assertEqual(self.eng.saves["config"], 0)

    def test_atnevezes_megtartja_a_sorrendet_es_az_aktiv_valtozatot(self):
        preset_ops.add_variant(self.eng, "MON1", "Játék", "Pálya1", NEW_VALUES)
        preset_ops.add_variant(self.eng, "MON1", "Játék", "Pálya2", NEW_VALUES)
        preset_ops.rename_variant(self.eng, "MON1", "Játék", "Pálya1", "Első")
        self.assertEqual(list(self.variants()), ["Alap", "Első", "Pálya2"])
        self.assertEqual(self.variants()["Első"], NEW_VALUES)
        self.assertEqual(self.eng.variant[("MON1", "Játék")], "Pálya2")           # nem az átnevezett volt az aktív
        preset_ops.rename_variant(self.eng, "MON1", "Játék", "Pálya2", "Utolsó")
        self.assertEqual(self.eng.variant[("MON1", "Játék")], "Utolsó")

    def test_torles_az_elsot_tukrozi_es_az_elso_valtozat_lesz_az_ervenyes(self):
        preset_ops.add_variant(self.eng, "MON1", "Játék", "Pálya1", NEW_VALUES)
        self.eng.variant[("MON1", "Játék")] = "Alap"
        self.assertEqual(preset_ops.delete_variant(self.eng, "MON1", "Játék", "Alap"), "Pálya1")
        preset = self.eng.preset("MON1", "Játék")
        self.assertEqual(list(preset["variants"]), ["Pálya1"])
        self.assertEqual((preset["gamma"], preset["contrast"], preset["brightness"], preset["vibrance"]),
                         (2.0, 60, 40, 70))                                       # a preset szintű értékek az elsőt követik
        self.assertNotIn(("MON1", "Játék"), self.eng.variant)


class PresetOpsTest(unittest.TestCase):
    def setUp(self):
        self.eng, _ = make_engine(self)

    def names(self):
        return list(self.eng.mon("MON1")["presets"])

    def test_atnevezes_atviszi_az_allapotot_es_megtartja_a_sorrendet(self):
        self.eng.auto.add(("MON1", "Játék"))
        self.eng.manual_off.add(("MON1", "Játék"))
        self.eng.variant[("MON1", "Játék")] = "x"
        preset_ops.rename_preset(self.eng, "MON1", "Játék", "Új név")
        self.assertEqual(self.names(), ["Alap", "Új név"])
        self.assertEqual(self.eng.active["MON1"], "Új név")
        self.assertEqual(self.eng.auto, {("MON1", "Új név")})
        self.assertEqual(self.eng.manual_off, {("MON1", "Új név")})
        self.assertEqual(self.eng.variant, {("MON1", "Új név"): "x"})
        self.assertEqual(self.eng.preset("MON1", "Új név")["process"], "game")

    def test_atnevezes_masik_presetet_nem_erint(self):
        preset_ops.rename_preset(self.eng, "MON1", "Alap", "Alap2")
        self.assertEqual(self.eng.active["MON1"], "Játék")

    def test_torles_kikapcsolja_es_kiveszi(self):
        preset_ops.delete_preset(self.eng, "MON1", "Játék")
        self.assertEqual(self.names(), ["Alap"])
        self.assertNotIn("MON1", self.eng.active)
        self.assertEqual(self.eng.saves["config"], 1)

    def test_uj_preset_alapertekei_a_mostani_ertekek(self):
        values = (2.0, 60, 40, 70, [100, 90, 80])
        preset = preset_ops.blank_preset(values, "bf6")
        self.assertEqual(preset["process"], "bf6")
        self.assertEqual(preset["gain"], [100, 90, 80])
        self.assertEqual(preset["default"], preset_ops.values_dict(*values))
        self.assertEqual((preset["gamma"], preset["contrast"], preset["brightness"], preset["vibrance"]),
                         (2.0, 60, 40, 70))

    def test_masolat_nem_visz_gyorsgombot_es_jatekot(self):
        collected = {"gamma": 2.2, "process": "game", "hotkey": "ctrl+alt+1", "rgb": {"mode": "off", "value": ""},
                     "variants": {"A": {"gamma": 2.2, "hotkey": "ctrl+1"}, "B": {"gamma": 2.0}}}
        copy = preset_ops.copy_of_preset(collected, (1.8, 50, 50, 50, [100, 100, 100]))
        self.assertEqual(copy["process"], "")
        self.assertNotIn("hotkey", copy)
        self.assertEqual([("hotkey" in v) for v in copy["variants"].values()], [False, False])
        self.assertEqual(copy["rgb"], {"mode": "off", "value": ""})
        self.assertEqual(copy["default"]["gamma"], 1.8)
        self.assertEqual(collected["hotkey"], "ctrl+alt+1")                       # az eredeti érintetlen
        self.assertIn("hotkey", collected["variants"]["A"])


class ExportImportTest(unittest.TestCase):
    def setUp(self):
        self.eng, _ = make_engine(self, settings={"night_strength": 30})
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))

    def test_export_tartalmazza_a_konfigot_es_a_beallitasokat(self):
        data = preset_ops.export_data(self.eng)
        self.assertEqual(data["kepprofil_backup"], 1)
        self.assertIs(data["config"], self.eng.cfg)
        self.assertEqual(data["settings"]["night_strength"], 30)
        json.dumps(data)                                                           # fájlba írható

    def test_importalhato_konfig_mentesbol_es_nyers_konfigbol_is(self):
        data = preset_ops.export_data(self.eng)
        self.assertIsNotNone(preset_ops.importable_config(data))
        self.assertIsNotNone(preset_ops.importable_config(self.eng.cfg))

    def test_serult_vagy_idegen_fajl_nem_importalhato(self):
        for bad in (None, [1, 2], "szöveg", {"config": 5}, {"monitors": "nem lista"}):
            self.assertIsNone(preset_ops.importable_config(bad), bad)

    def test_import_lecsereli_a_presetet_menti_a_regit_es_torli_az_allapotot(self):
        data = preset_ops.export_data(self.eng)
        exported = json.loads(json.dumps(data))
        exported["config"]["monitors"][0]["presets"].pop("Játék")
        exported["settings"]["night_strength"] = 55
        self.eng.auto.add(("MON1", "Játék"))
        backup = self.tmp / "regi.json"
        preset_ops.import_config(self.eng, exported, preset_ops.importable_config(exported), backup)
        self.assertEqual(list(self.eng.mon("MON1")["presets"]), ["Alap"])
        self.assertEqual(self.eng.set["night_strength"], 55)
        self.assertEqual((self.eng.active, self.eng.auto, self.eng.manual_off), ({}, set(), set()))
        self.assertEqual(list(json.loads(backup.read_text(encoding="utf-8"))["monitors"][0]["presets"]), ["Alap", "Játék"])
        self.assertEqual((self.eng.saves["config"], self.eng.saves["settings"]), (1, 1))

    def test_import_nyers_konfigbol_a_beallitasokat_nem_bantja(self):
        raw = json.loads(json.dumps(self.eng.cfg))
        preset_ops.import_config(self.eng, raw, preset_ops.importable_config(raw), self.tmp / "regi.json")
        self.assertEqual(self.eng.set["night_strength"], 30)


if __name__ == "__main__":
    unittest.main()
