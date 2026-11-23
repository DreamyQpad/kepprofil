"""A Tarkov logjának feldolgozása: pályaesemények a sorokból, pálya-táblázat, naplókövetés."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tarkov_log import CHOICE_SLUGS, MAP_CHOICES, MAP_SLUGS, LogTail, MapEvent, map_slug, parse_line, tarkov_install_dir

PRELOAD = "2026-11-23 14:24:11.406|1.3.0.2.48779|Info|application|scene preset path:maps/woods_preset.bundle rcid:woods.scenespreset.asset"
RAID = ("2026-11-23 14:24:23.457|1.3.0.2.48779|Debug|application|TRACE-NetworkGameCreate profileStatus: "
        "'Profileid: 000000000000000000000000, Status: Busy, RaidMode: Online, Ip: 10.0.0.1, Port: 17010, "
        "Location: TarkovStreets, Sid: x'")
TRANSIT = ("2026-11-23 22:19:20.176|1.3.0.2.48779|Info|application|[Transit] Flag:None, "
           "RaidId:aaaaaaaaaaaaaaaaaaaaaaaa, Count:0, Locations:Sandbox_high -> ")
END = "2026-11-23 16:41:47.100|1.3.0.2.48779|Info|application|BEClient exit"
END_OK = "2026-11-23 16:41:48.100|1.3.0.2.48779|Info|application|BEClient exit successfully"


class LearnedNamesTest(unittest.TestCase):
    def test_a_megtanult_nev_a_tablazatban_nem_szereplo_palyat_is_felismeri(self):
        self.assertEqual(map_slug("UjPalya", {"ujpalya": "terminal"}), "terminal")

    def test_a_tablazat_elsobbsegu_a_megtanult_nevvel_szemben(self):
        self.assertEqual(map_slug("woods", {"woods": "customs"}), "woods")

    def test_ismeretlen_nev_megtanulas_nelkul_none(self):
        self.assertIsNone(map_slug("UjPalya"))
        self.assertIsNone(map_slug("UjPalya", {}))
        self.assertIsNone(map_slug("UjPalya", None))


class MapChoicesTest(unittest.TestCase):
    def test_a_valaszthato_terkepek_azonositoi_egyediek_es_nevuk_nem_ures(self):
        slugs = [slug for slug, name in MAP_CHOICES]
        self.assertEqual(len(slugs), len(set(slugs)))
        self.assertTrue(all(name.strip() for slug, name in MAP_CHOICES))
        self.assertEqual(CHOICE_SLUGS, frozenset(slugs))

    def test_minden_felismert_palya_valaszthato_is(self):
        self.assertLessEqual(set(MAP_SLUGS.values()), CHOICE_SLUGS)


class ParseLineTest(unittest.TestCase):
    def test_preload_sor(self):
        self.assertEqual(parse_line(PRELOAD), MapEvent("preload", "woods"))

    def test_raid_sor_csak_a_nevet_veszi_ki(self):
        event = parse_line(RAID)
        self.assertEqual(event, MapEvent("raid", "TarkovStreets"))
        self.assertNotIn("Profileid", repr(event))
        self.assertNotIn("10.0.0.1", repr(event))

    def test_transit_sor_a_raid_pályaneve(self):
        event = parse_line(TRANSIT)
        self.assertEqual(event, MapEvent("raid", "Sandbox_high"))
        self.assertNotIn("aaaa", repr(event))                 # a RaidId nem kerül az eseménybe

    def test_transit_sor_tovabbi_helyekkel_az_elsot_veszi(self):
        line = TRANSIT.replace("Sandbox_high -> ", "bigmap -> Woods")
        self.assertEqual(parse_line(line), MapEvent("raid", "bigmap"))

    def test_nem_transit_sor_nem_esemeny(self):
        self.assertIsNone(parse_line("2026-11-23 22:19:20.176|1.3.0.2.48779|Info|application|Locations:Woods -> "))

    def test_end_sor(self):
        self.assertEqual(parse_line(END), MapEvent("end", ""))

    def test_end_sikeres_kilepes_sora_nem_esemeny(self):
        self.assertIsNone(parse_line(END_OK))

    def test_location_mas_sorban_nem_esemeny(self):
        self.assertIsNone(parse_line("2026-11-23 14:24:23.457|1|Info|application|Some message Location: Woods, more"))

    def test_nem_naplosor(self):
        self.assertIsNone(parse_line(""))
        self.assertIsNone(parse_line("valami teljesen mas"))


class MapSlugTest(unittest.TestCase):
    def test_ismert_nevek(self):
        self.assertEqual(map_slug("city"), "streets-of-tarkov")
        self.assertEqual(map_slug("TarkovStreets"), "streets-of-tarkov")
        self.assertEqual(map_slug("Woods"), "woods")

    def test_ground_zero_mindket_valtozata(self):
        self.assertEqual(map_slug("sandbox_high"), "ground-zero")     # a logban látott betöltési és Transit-név
        self.assertEqual(map_slug("Sandbox_high"), "ground-zero")
        self.assertEqual(map_slug("sandbox"), "ground-zero")

    def test_tobbi_ismert_palya(self):
        for name, slug in (("factory4_day", "factory"), ("factory4_night", "factory"), ("shoreline", "shoreline"),
                           ("interchange", "interchange"), ("lighthouse", "lighthouse"), ("rezervbase", "reserve"),
                           ("laboratory", "the-lab")):
            self.assertEqual(map_slug(name), slug, name)

    def test_customs_a_betoltesi_es_a_raid_nevvel_is(self):
        self.assertEqual(map_slug("customs"), "customs")          # a betöltési sorban látott név
        self.assertEqual(map_slug("bigmap"), "customs")           # a raid-sor játék-belső neve

    def test_ismeretlen_nev(self):
        self.assertIsNone(map_slug("ismeretlen"))


class InstallDirTest(unittest.TestCase):
    def test_a_beallitas_elsobbseget_elvez(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(tarkov_install_dir(tmp), Path(tmp))

    def test_nem_windowson_nincs_nyilvantartas(self):
        with mock.patch("tarkov_log.sys.platform", "linux"):
            self.assertIsNone(tarkov_install_dir(""))

    def test_nem_letezo_beallitas_nem_hasznalhato(self):
        with mock.patch("tarkov_log.sys.platform", "linux"):
            self.assertIsNone(tarkov_install_dir("/nincs/ilyen/mappa"))


class LogTailTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.install = Path(self.tmp.name)

    def log_file(self, folder="log_2026.11.23_14-22-24_1.3.0.2.48779"):
        directory = self.install / "Logs" / folder
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{folder[4:]} application_000.log"

    def append(self, path, *lines, newline=True):
        with open(path, "ab") as handle:
            for line in lines:
                handle.write(line.encode("utf-8") + (b"\n" if newline else b""))

    def test_csak_uj_sorokat_ad(self):
        path = self.log_file()
        self.append(path, PRELOAD, RAID)
        tail = LogTail(self.install)
        self.assertEqual(tail.poll(), [])                       # a csatlakozás előtti sorok nem újak
        self.append(path, END)
        self.assertEqual(tail.poll(), [MapEvent("end", "")])
        self.assertEqual(tail.poll(), [])

    def test_state_folyamatban_levo_raid(self):
        path = self.log_file()
        self.append(path, PRELOAD, RAID)
        tail = LogTail(self.install)
        tail.poll()
        self.assertEqual(tail.state(), MapEvent("raid", "TarkovStreets"))
        self.append(path, END)
        tail.poll()
        self.assertIsNone(tail.state())

    def test_state_csak_betoltes_a_betoltest_adja(self):
        path = self.log_file()
        self.append(path, PRELOAD)
        tail = LogTail(self.install)
        tail.poll()
        self.assertEqual(tail.state(), MapEvent("preload", "woods"))

    def test_state_a_raid_elkulonul_a_korabbi_betoltestol(self):
        path = self.log_file()
        self.append(path, PRELOAD, RAID)
        tail = LogTail(self.install)
        tail.poll()
        self.assertEqual(tail.state().kind, "raid")

    def test_state_vege_utan_ures(self):
        path = self.log_file()
        self.append(path, PRELOAD, END)
        tail = LogTail(self.install)
        tail.poll()
        self.assertIsNone(tail.state())

    def test_uj_log_mappa(self):
        old = self.log_file()
        self.append(old, PRELOAD, RAID)
        tail = LogTail(self.install)
        tail.poll()
        new = self.log_file("log_2026.11.23_18-00-00_1.3.0.2.48779")
        self.append(new, PRELOAD)
        self.assertEqual(tail.poll(), [MapEvent("preload", "woods")])
        self.assertEqual(tail.state(), MapEvent("preload", "woods"))      # nem a régi mappa raidje

    def test_hianyzo_mappa(self):
        tail = LogTail(self.install / "nincs")
        self.assertEqual(tail.poll(), [])
        self.assertIsNone(tail.state())

    def test_csak_teljes_sorokat_dolgoz_fel(self):
        path = self.log_file()
        self.append(path, PRELOAD)
        tail = LogTail(self.install)
        tail.poll()
        self.append(path, END[:30], newline=False)
        self.assertEqual(tail.poll(), [])
        self.append(path, END[30:])
        self.assertEqual(tail.poll(), [MapEvent("end", "")])

    def test_kisebb_lett_fajl_ujrakezdi(self):
        path = self.log_file()
        self.append(path, PRELOAD, RAID)
        tail = LogTail(self.install)
        tail.poll()
        path.write_bytes(b"")                                  # a játék újraírta a fájlt
        self.append(path, PRELOAD)
        self.assertEqual(tail.poll(), [MapEvent("preload", "woods")])


if __name__ == "__main__":
    unittest.main()
