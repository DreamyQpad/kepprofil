"""A térkép-overlay szülő oldali vezérlője: pályaesemények, módok, a billentyűzetes mód nyers gombjai, a folyamat életciklusa."""
import io
import subprocess
import unittest

from hw_common import MAP_KEYS
from map_overlay import MapController, map_argv
from tarkov_log import MapEvent
from tests.stubs import make_engine


class FakeStdin:
    def __init__(self, events, broken=False):
        self.events, self.closed, self.broken = events, False, broken

    def write(self, text):
        if self.broken:
            raise BrokenPipeError()
        self.events.append(("write", text.strip()))

    def flush(self):
        pass

    def close(self):
        self.closed = True


class FakeProc:
    def __init__(self, events, output="", hang=False):
        self.stdin, self.stdout = FakeStdin(events), io.StringIO(output)
        self.returncode, self.hang, self.killed, self.pid = None, hang, False, 4242

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if self.hang and not self.killed:
            raise subprocess.TimeoutExpired("map", timeout)
        self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -9

    def writes(self, events):
        return [text for kind, text in events if kind == "write"]


class Base(unittest.TestCase):
    def setUp(self):
        self.events, self.procs, self.hotkeys, self.spawn_error = [], [], [], None
        self.next_output, self.next_hang = "", False

    def spawn(self, argv, **kwargs):
        if self.spawn_error:
            raise self.spawn_error
        proc = FakeProc(self.events, self.next_output, self.next_hang)
        proc.argv = argv
        self.procs.append(proc)
        return proc

    def make(self, settings=None):
        eng, _ = make_engine(self, settings=settings)
        eng.said = []
        eng.say = eng.said.append
        controller = MapController(eng, set_hotkeys=self.hotkeys.append, spawn=self.spawn, argv_for=lambda slug: ["map", slug],
                                   allow_foreground=lambda: self.events.append(("allow", "")))
        self.eng = eng
        return controller

    def writes(self):
        return [text for kind, text in self.events if kind == "write"]

    def shown(self, controller, name="woods"):
        controller.on_event(MapEvent("preload", name))
        controller.on_event(MapEvent("raid", {"woods": "Woods"}.get(name, name)))
        return controller


class EventsTest(Base):
    def test_preload_ismert_palyara_elinditja_rejtve(self):
        controller = self.make()
        controller.on_event(MapEvent("preload", "woods"))
        self.assertEqual([p.argv for p in self.procs], [["map", "woods"]])
        self.assertEqual(self.writes(), [])
        self.assertEqual(controller.mode, "hidden")

    def test_preload_ismeretlen_nevet_naploz_es_nem_indit(self):
        controller = self.make()
        controller.on_event(MapEvent("preload", "ismeretlen"))
        controller.on_event(MapEvent("preload", "ismeretlen"))
        self.assertEqual(self.procs, [])
        self.assertEqual(len([line for line in self.eng.said if "ismeretlen" in line]), 1)

    def test_raid_auto_megjelenit(self):
        controller = self.shown(self.make())
        self.assertEqual(self.writes(), ["show"])
        self.assertEqual(controller.mode, "glance")

    def test_raid_auto_kikapcsolva_nem_jelenit_meg(self):
        controller = self.shown(self.make({"map_auto": False}))
        self.assertEqual(self.writes(), [])
        self.assertEqual(controller.mode, "hidden")
        self.assertEqual(len(self.procs), 1)

    def test_raid_mas_palya_parancsot_kuld(self):
        controller = self.make()
        controller.on_event(MapEvent("preload", "woods"))
        controller.on_event(MapEvent("raid", "TarkovStreets"))
        self.assertEqual(self.writes(), ["map streets-of-tarkov", "show"])

    def test_raid_elozetes_betoltes_nelkul_is_elinditja_es_mutatja(self):
        controller = self.make()
        controller.on_event(MapEvent("raid", "TarkovStreets"))
        self.assertEqual([p.argv for p in self.procs], [["map", "streets-of-tarkov"]])
        self.assertEqual(self.writes(), ["show"])

    def test_raid_ismeretlen_nev_az_elozetesen_betoltott_terkepet_hasznalja(self):
        controller = self.make()
        controller.on_event(MapEvent("preload", "woods"))
        controller.on_event(MapEvent("raid", "MegIsmeretlenNev"))
        self.assertEqual(self.writes(), ["show"])
        self.assertEqual(controller.mode, "glance")
        self.assertEqual(len(self.procs), 1)
        self.assertEqual(len([line for line in self.eng.said if "MegIsmeretlenNev" in line]), 1)

    def test_raid_ismeretlen_nev_betoltes_nelkul_nem_jelenit_meg(self):
        controller = self.make()
        controller.on_event(MapEvent("raid", "MegIsmeretlenNev"))
        self.assertEqual(self.procs, [])
        self.assertEqual(controller.mode, "hidden")

    def test_a_raid_vege_utan_nem_marad_ervenyes_az_elozo_betoltes(self):
        controller = self.shown(self.make())
        controller.on_event(MapEvent("end", ""))
        controller.on_event(MapEvent("raid", "MegIsmeretlenNev"))
        self.assertEqual(len(self.procs), 1)
        self.assertEqual(controller.mode, "hidden")

    def test_end_leallitja(self):
        controller = self.shown(self.make())
        controller.on_event(MapEvent("end", ""))
        self.assertTrue(self.procs[0].stdin.closed)
        self.assertEqual(controller.mode, "hidden")


class LearningTest(Base):
    """A kézi választás megtanítja a programnak a logban látott, ismeretlen pályanevet."""

    def test_a_kezi_valasztas_megtanulja_az_ismeretlen_nevet(self):
        controller = self.make()
        controller.on_event(MapEvent("preload", "UjPalya"))
        controller.handle_output("selected terminal")
        self.assertEqual(self.eng.set["map_learned"], {"ujpalya": "terminal"})

    def test_a_megtanult_nev_kovetkezo_alkalommal_magatol_felismerodik(self):
        controller = self.make(settings={"map_learned": {"ujpalya": "terminal"}})
        controller.on_event(MapEvent("preload", "UjPalya"))
        self.assertEqual(controller.slug, "terminal")
        self.assertEqual([p.argv for p in self.procs], [["map", "terminal"]])

    def test_a_raid_es_a_betoltes_neve_is_megtanulodik(self):
        controller = self.make()
        controller.on_event(MapEvent("preload", "ujpalya_betoltes"))
        controller.on_event(MapEvent("raid", "UjPalya"))
        controller.handle_output("selected terminal")
        self.assertEqual(self.eng.set["map_learned"], {"ujpalya_betoltes": "terminal", "ujpalya": "terminal"})

    def test_ismert_palya_utan_a_kezi_valasztas_nem_tanul_semmit(self):
        controller = self.shown(self.make())
        controller.handle_output("selected terminal")
        self.assertFalse(self.eng.set.get("map_learned"))

    def test_a_raid_vege_utan_a_valasztas_mar_nem_a_regi_ismeretlen_nevet_tanitja(self):
        controller = self.make()
        controller.on_event(MapEvent("preload", "UjPalya"))
        controller.on_event(MapEvent("end", ""))
        controller.handle_output("selected terminal")
        self.assertFalse(self.eng.set.get("map_learned"))

    def test_a_tanulas_egyszer_tortenik_a_masodik_valasztas_nem_ir_felul(self):
        controller = self.make()
        controller.on_event(MapEvent("preload", "UjPalya"))
        controller.handle_output("selected terminal")
        controller.handle_output("selected woods")
        self.assertEqual(self.eng.set["map_learned"], {"ujpalya": "terminal"})

    def test_ismeretlen_betoltes_utan_nem_marad_a_regi_terkep(self):
        """A régi raid térképét nem mutatjuk az új, ismeretlen pályán."""
        controller = self.shown(self.make())
        controller.on_event(MapEvent("end", ""))
        controller.on_event(MapEvent("preload", "UjPalya"))
        self.assertIsNone(controller.slug)

    def test_ismeretlen_raid_nev_ismert_betoltes_utan_megtartja_a_pályát(self):
        controller = self.make()
        controller.on_event(MapEvent("preload", "customs"))
        controller.on_event(MapEvent("raid", "bigmap2"))
        self.assertEqual(controller.slug, "customs")

    def test_a_megtanult_nevek_szama_korlatos(self):
        controller = self.make(settings={"map_learned": {f"n{i}": "customs" for i in range(50)}})
        controller.on_event(MapEvent("preload", "UjPalya"))
        controller.handle_output("selected terminal")
        self.assertNotIn("ujpalya", self.eng.set["map_learned"])
        self.assertEqual(len(self.eng.set["map_learned"]), 50)


class PickerTest(Base):
    """Ha a program nem tudja, melyik pályán vagy, a térképablakban kézzel választhatsz."""

    def test_ismeretlen_palyanal_a_toggle_egeres_modban_nyitja_meg_a_valasztohoz(self):
        controller = self.make()
        controller.toggle()
        self.assertEqual(self.procs[0].argv, ["map", "ground-zero"])      # nincs korábbi választás: a lista első térképe
        self.assertEqual(self.writes(), ["show", "mode mouse"])
        self.assertEqual(controller.mode, "mouse")
        self.assertEqual(len(self.eng.toasts), 1)                         # a súgó: válassz a térkép tetején

    def test_ismeretlen_palyanal_az_utoljara_valasztott_terkepet_nyitja(self):
        controller = self.make(settings={"map_last": "woods"})
        controller.toggle()
        self.assertEqual(self.procs[0].argv, ["map", "woods"])

    def test_ervenytelen_mentett_palya_nem_indit_ismeretlen_terkepet(self):
        controller = self.make(settings={"map_last": "../x"})
        controller.toggle()
        self.assertEqual(self.procs[0].argv, ["map", "ground-zero"])

    def test_ismert_palyanal_nincs_kenyszeritett_egeres_mod(self):
        controller = self.shown(self.make())
        controller.toggle()                                                # elrejt
        controller.toggle()                                                # újra megjelenik pillantás módban
        self.assertEqual(controller.mode, "glance")

    def test_a_folyamat_kivalasztott_palyaja_lesz_az_aktualis_es_mentodik(self):
        controller = self.make()
        controller.toggle()
        controller.handle_output("selected shoreline")
        self.assertEqual(controller.slug, "shoreline")
        self.assertEqual(self.eng.set["map_last"], "shoreline")
        controller.toggle()                                                # elrejt
        controller.toggle()                                                # ugyanazzal a folyamattal, új betöltés nélkül
        self.assertEqual(len(self.procs), 1)
        self.assertFalse(any(text.startswith("map ") for text in self.writes()))

    def test_a_kivalasztas_utan_a_kovetkezo_raid_esemeny_felulirja(self):
        controller = self.make()
        controller.toggle()
        controller.handle_output("selected shoreline")
        controller.on_event(MapEvent("preload", "woods"))
        self.assertEqual(controller.slug, "woods")
        self.assertIn("map woods", self.writes())

    def test_ismeretlen_vagy_hibas_kivalasztas_sort_figyelmen_kivul_hagyja(self):
        controller = self.make()
        for line in ("selected", "selected evil", "selected ../x", "selected woods extra"):
            controller.handle_output(line)
        self.assertIsNone(controller.slug)
        self.assertIsNone(self.eng.set.get("map_last"))


class ModesTest(Base):

    def test_toggle_ciklus(self):
        controller = self.make()
        controller.on_event(MapEvent("preload", "woods"))
        controller.toggle()
        self.assertEqual(controller.mode, "glance")
        controller.toggle()
        self.assertEqual(controller.mode, "hidden")
        self.assertEqual(self.writes(), ["show", "hide"])

    def test_cycle_mode_sorrend_es_az_elter_engedelyezese_az_egeres_mod_elott(self):
        controller = self.shown(self.make())
        controller.cycle_mode()
        self.assertEqual(controller.mode, "keys")
        controller.cycle_mode()
        self.assertEqual(controller.mode, "mouse")
        controller.cycle_mode()
        self.assertEqual(controller.mode, "glance")
        self.assertEqual(self.writes(), ["show", "mode keys", "mode mouse", "mode glance"])
        self.assertLess(self.events.index(("allow", "")), self.events.index(("write", "mode mouse")))

    def test_cycle_mode_rejtettbol_elohozza(self):
        controller = self.make()
        controller.on_event(MapEvent("preload", "woods"))
        controller.cycle_mode()
        self.assertEqual(controller.mode, "glance")
        self.assertEqual(self.writes(), ["show"])

    def test_key_pan_es_zoom_es_kilepes(self):
        controller = self.shown(self.make())
        controller.cycle_mode()
        for action in ("mp|left", "mp|zin", "mp|zout", "mp|exit"):
            controller.key(action)
        self.assertEqual(self.writes()[2:], ["pan left", "zoom in", "zoom out", "mode glance"])
        self.assertEqual(controller.mode, "glance")

    def test_key_atlatszosag_lepes_kuldi_menti_es_korlatozza(self):
        controller = self.shown(self.make({"map_alpha": 0.85}))
        controller.cycle_mode()
        controller.key("mp|adown")
        self.assertEqual(self.writes()[-1], "alpha 0.8")
        self.assertEqual(self.eng.set["map_alpha"], 0.8)
        self.assertEqual(self.eng.saves["settings"], 1)
        for _ in range(4):                                      # 0,8 → 0,85 → 0,9 → 0,95 → 1,0
            controller.key("mp|aup")
        self.assertEqual(self.writes()[-1], "alpha 1.0")
        self.assertEqual(self.eng.set["map_alpha"], 1.0)

    def test_key_atlatszosag_also_hatara(self):
        controller = self.shown(self.make({"map_alpha": 0.25}))
        controller.cycle_mode()
        controller.key("mp|adown")
        controller.key("mp|adown")
        self.assertEqual(self.writes()[-1], "alpha 0.2")
        self.assertEqual(self.eng.set["map_alpha"], 0.2)

    def test_key_nem_keys_modban_nem_csinal_semmit(self):
        controller = self.shown(self.make())
        controller.key("mp|left")
        self.assertEqual(self.writes(), ["show"])

    def test_leave_keys(self):
        controller = self.shown(self.make())
        controller.leave_keys()
        self.assertEqual(controller.mode, "glance")
        self.assertEqual(self.writes(), ["show"])
        controller.cycle_mode()
        controller.leave_keys()
        self.assertEqual(controller.mode, "glance")
        self.assertFalse(any(key.startswith("mp|") for key in self.hotkeys[-1]))

    def test_alfa_futo_folyamatnak_kuldi(self):
        controller = self.shown(self.make())
        controller.set_alpha(0.5)
        self.assertEqual(self.writes()[-1], "alpha 0.5")


class HotkeysTest(Base):
    def test_keys_modban_a_nyers_gombok_foglaltak_es_kilepeskor_felszabadulnak(self):
        controller = self.shown(self.make({"map_hotkey": "Ctrl+Alt+M"}))
        controller.cycle_mode()
        self.assertTrue(all(key in self.hotkeys[-1] for key in MAP_KEYS))
        self.assertEqual(self.hotkeys[-1]["map"], "Ctrl+Alt+M")
        controller.cycle_mode()
        self.assertFalse(any(key.startswith("mp|") for key in self.hotkeys[-1]))
        self.assertEqual(self.hotkeys[-1]["map"], "Ctrl+Alt+M")

    def test_halott_folyamat_visszaallitja_a_gombokat(self):
        controller = self.shown(self.make())
        controller.cycle_mode()
        self.procs[0].returncode = 1
        controller.check()
        self.assertEqual(controller.mode, "hidden")
        self.assertFalse(any(key.startswith("mp|") for key in self.hotkeys[-1]))

    def test_hidden_sor_a_folyamat_elrejtesekor_felszabaditja_a_gombokat(self):
        controller = self.shown(self.make())
        controller.cycle_mode()
        controller.cycle_mode()                                  # egér mód
        writes_before = list(self.writes())
        controller.handle_output("hidden")
        self.assertEqual(controller.mode, "hidden")
        self.assertEqual(self.writes(), writes_before)           # a folyamat már elrejtette magát: nem küld újabb hide-ot
        self.assertFalse(any(key.startswith("mp|") for key in self.hotkeys[-1]))

    def test_hidden_sor_rejtett_allapotban_nem_csinal_semmit(self):
        controller = self.make()
        calls_before = len(self.hotkeys)
        controller.handle_output("hidden")
        self.assertEqual(controller.mode, "hidden")
        self.assertEqual(len(self.hotkeys), calls_before)

    def test_hidden_utan_a_toggle_ujra_megjelenit(self):
        controller = self.shown(self.make())
        controller.handle_output("hidden")
        controller.toggle()
        self.assertEqual(controller.mode, "glance")
        self.assertEqual(self.writes()[-1], "show")

    def test_toro_cso_halott_folyamatnak_szamit(self):
        controller = self.shown(self.make())
        controller.cycle_mode()
        self.procs[0].stdin.broken = True
        controller.key("mp|left")
        self.assertEqual(controller.mode, "hidden")
        self.assertFalse(any(key.startswith("mp|") for key in self.hotkeys[-1]))


class LifecycleTest(Base):
    def test_stop_felszabadit_es_nem_hagy_arva_folyamatot(self):
        controller = self.shown(self.make())
        controller.cycle_mode()
        controller.stop()
        self.assertTrue(self.procs[0].stdin.closed)
        self.assertIsNotNone(self.procs[0].returncode)
        self.assertEqual(controller.mode, "hidden")
        self.assertFalse(any(key.startswith("mp|") for key in self.hotkeys[-1]))

    def test_stop_elobb_elrejt_hogy_egeres_modbol_a_hely_mentodjon(self):
        controller = self.shown(self.make())
        controller.stop()
        self.assertEqual(self.writes()[-1], "hide")

    def test_stop_wait_nelkul_nem_var_es_nem_kuld_parancsot(self):
        controller = self.shown(self.make())
        before = len(self.writes())
        controller.stop(wait=False)
        self.assertEqual(len(self.writes()), before)
        self.assertTrue(self.procs[0].stdin.closed)

    def test_stop_ha_a_folyamat_nem_all_le_kilovi(self):
        self.next_hang = True
        controller = self.shown(self.make())
        controller.stop()
        self.assertTrue(self.procs[0].killed)

    def test_toggle_ujraindit_halott_folyamat_utan(self):
        controller = self.shown(self.make())
        self.procs[0].returncode = 1
        controller.check()
        controller.toggle()
        self.assertEqual(len(self.procs), 2)
        self.assertEqual(controller.mode, "glance")

    def test_spawn_hiba_nem_dob_kivetelt(self):
        self.spawn_error = OSError("nincs")
        controller = self.make()
        controller.on_event(MapEvent("raid", "Woods"))
        controller.toggle()
        self.assertEqual(controller.mode, "hidden")
        self.assertTrue(self.eng.said)

    def test_rect_sor_mentodik(self):
        controller = self.make()
        controller.handle_output("rect 1 2 3 4")
        self.assertEqual(self.eng.set["map_rect"], [1, 2, 3, 4])
        self.assertEqual(self.eng.saves["settings"], 1)
        controller.handle_output("rect a b c d")
        controller.handle_output("loaded")
        self.assertEqual(self.eng.saves["settings"], 1)

    def test_a_kimeneti_szal_sorait_a_check_dolgozza_fel(self):
        self.next_output = "loaded\nrect 5 6 7 8\n"
        controller = self.make()
        controller.on_event(MapEvent("preload", "woods"))
        controller._reader.join(2)
        controller.check()
        self.assertEqual(self.eng.set["map_rect"], [5, 6, 7, 8])


class ArgvTest(unittest.TestCase):
    def test_forrasbol_futva_a_belepesi_pontot_hivja(self):
        argv = map_argv("woods")
        self.assertEqual(argv[-2:], ["--map", "woods"])
        self.assertTrue(any(part.endswith("kijelzo.py") for part in argv))


if __name__ == "__main__":
    unittest.main()
