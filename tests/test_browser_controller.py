"""A böngésző szülő oldali vezérlője: indítás, bezárás, a folyamat életciklusa."""
import unittest

from browser_overlay import BrowserController, browser_argv
from tests.stubs import make_engine
from tests.test_map_controller import FakeProc


class Base(unittest.TestCase):
    def setUp(self):
        self.events, self.procs, self.spawn_error, self.next_output = [], [], None, ""

    def spawn(self, argv, **kwargs):
        if self.spawn_error:
            raise self.spawn_error
        proc = FakeProc(self.events, self.next_output)
        proc.argv = argv
        self.procs.append(proc)
        return proc

    def make(self, settings=None):
        eng, _ = make_engine(self, settings=settings)
        eng.said = []
        eng.say = eng.said.append
        self.eng = eng
        return BrowserController(eng, spawn=self.spawn, argv_for=lambda: ["web"],
                                 allow_foreground=lambda: self.events.append(("allow", "")))

    def raw_writes(self):
        return [text for kind, text in self.events if kind == "write"]

    def writes(self):
        """A folyamatnak írt parancsok a `bookmarks` sorok nélkül (azokat a BookmarksTest vizsgálja)."""
        return [text for text in self.raw_writes() if not text.startswith("bookmarks ")]


class OpenCloseTest(Base):
    def test_megnyitas_elinditja_es_mutatja_az_elter_engedelyezese_utan(self):
        controller = self.make()
        controller.open()
        self.assertEqual([p.argv for p in self.procs], [["web"]])
        self.assertEqual(self.writes(), ["show"])
        self.assertTrue(controller.is_open)
        self.assertLess(self.events.index(("allow", "")), self.events.index(("write", "show")))

    def test_ketszeri_megnyitas_egy_folyamat(self):
        controller = self.make()
        controller.open()
        controller.open()
        self.assertEqual(len(self.procs), 1)
        self.assertEqual(self.writes(), ["show"])

    def test_toggle_nyit_es_zar(self):
        controller = self.make()
        controller.toggle()
        self.assertTrue(controller.is_open)
        controller.toggle()
        self.assertFalse(controller.is_open)
        self.assertEqual(self.writes(), ["show", "hide"])
        self.assertTrue(self.procs[0].stdin.closed)

    def test_zaras_utan_ujranyitas_uj_folyamat(self):
        controller = self.make()
        controller.open()
        controller.close()
        controller.open()
        self.assertEqual(len(self.procs), 2)

    def test_closed_sor_lezarja_a_folyamatot(self):
        controller = self.make()
        controller.open()
        controller.handle_output("closed")
        self.assertFalse(controller.is_open)
        self.assertTrue(self.procs[0].stdin.closed)
        self.assertNotIn("hide", self.writes())

    def test_rect_sor_mentodik_web_rect_kulcsra(self):
        controller = self.make()
        controller.handle_output("rect 1 2 3 4")
        self.assertEqual(self.eng.set["web_rect"], [1, 2, 3, 4])
        self.assertEqual(self.eng.saves["settings"], 1)
        controller.handle_output("rect a b c d")
        controller.handle_output("loaded")
        self.assertEqual(self.eng.saves["settings"], 1)

    def test_a_bezaras_utan_erkezo_rect_sort_is_feldolgozza(self):
        self.next_output = "loaded\nrect 9 8 7 6\n"
        controller = self.make()
        controller.open()
        controller._reader.join(2)
        controller.close()
        controller.check()
        self.assertEqual(self.eng.set["web_rect"], [9, 8, 7, 6])


class LifecycleTest(Base):
    def test_halott_folyamat_bezartnak_szamit(self):
        controller = self.make()
        controller.open()
        self.procs[0].returncode = 1
        controller.check()
        self.assertFalse(controller.is_open)
        self.assertTrue(self.eng.said)

    def test_toro_cso_bezartnak_szamit(self):
        controller = self.make()
        controller.open()
        self.procs[0].stdin.broken = True
        controller.close()
        self.assertFalse(controller.is_open)

    def test_stop_nem_hagy_arva_folyamatot(self):
        controller = self.make()
        controller.open()
        controller.stop()
        self.assertTrue(self.procs[0].stdin.closed)
        self.assertIsNotNone(self.procs[0].returncode)
        self.assertFalse(controller.is_open)

    def test_stop_ha_nem_all_le_kilovi(self):
        self.next_hang = True
        controller = self.make()
        controller.open()
        self.procs[0].hang = True
        controller.stop()
        self.assertTrue(self.procs[0].killed)

    def test_spawn_hiba_nem_dob_kivetelt(self):
        self.spawn_error = OSError("nincs")
        controller = self.make()
        controller.open()
        self.assertFalse(controller.is_open)
        self.assertTrue(self.eng.said)


class ArgvTest(unittest.TestCase):
    def test_forrasbol_futva_a_belepesi_pontot_hivja(self):
        argv = browser_argv()
        self.assertEqual(argv[-1], "--web")
        self.assertTrue(any(part.endswith("kijelzo.py") for part in argv))


if __name__ == "__main__":
    unittest.main()


class BookmarksTest(Base):
    def make_game(self, game="Tarkov", settings=None):
        controller = self.make(settings)
        controller.game = lambda: game
        return controller

    def bookmark_writes(self):
        import json
        return [json.loads(text[len("bookmarks "):]) for text in self.raw_writes() if text.startswith("bookmarks ")]

    def test_megnyitaskor_a_jatek_savja_megy_a_show_elott(self):
        controller = self.make_game(settings={"bookmarks": {"Tarkov": [{"title": "Wiki", "url": "https://wiki.example"}]}})
        controller.open()
        writes = self.raw_writes()
        self.assertEqual(self.bookmark_writes(), [{"game": "Tarkov", "items": [{"title": "Wiki", "url": "https://wiki.example"}]}])
        self.assertLess([i for i, t in enumerate(writes) if t.startswith("bookmarks ")][0], writes.index("show"))

    def test_masik_jatek_masik_sav(self):
        settings = {"bookmarks": {"Tarkov": [{"title": "Wiki", "url": "https://wiki.example"}],
                                  "Más": [{"title": "Guide", "url": "https://guide.example"}]}}
        controller = self.make_game("Más", settings)
        controller.open()
        self.assertEqual([item["title"] for item in self.bookmark_writes()[0]["items"]], ["Guide"])

    def test_nincs_aktiv_jatek_kozos_sav(self):
        controller = self.make_game("", {"bookmarks": {"": [{"title": "Közös", "url": "https://k.example"}]}})
        controller.open()
        self.assertEqual(self.bookmark_writes()[0], {"game": "", "items": [{"title": "Közös", "url": "https://k.example"}]})

    def test_hozzaadas_ment_es_visszakuldi_a_savot(self):
        controller = self.make_game()
        controller.open()
        controller.handle_output('bookmark add {"title": "Wiki", "url": "https://wiki.example/a"}')
        self.assertEqual(self.eng.set["bookmarks"]["Tarkov"], [{"title": "Wiki", "url": "https://wiki.example/a"}])
        self.assertEqual(self.eng.saves["settings"], 1)
        self.assertEqual(self.bookmark_writes()[-1]["items"], [{"title": "Wiki", "url": "https://wiki.example/a"}])

    def test_a_hozzaadas_a_megnyitaskori_jatekhoz_kerul_akkor_is_ha_kozben_valtozik(self):
        game = {"now": "Tarkov"}
        controller = self.make()
        controller.game = lambda: game["now"]
        controller.open()
        game["now"] = "Más"
        controller.handle_output('bookmark add {"title": "x", "url": "https://x.example"}')
        self.assertIn("Tarkov", self.eng.set["bookmarks"])
        self.assertNotIn("Más", self.eng.set["bookmarks"])

    def test_torles_index_szerint_ment_es_visszakuld(self):
        controller = self.make_game(settings={"bookmarks": {"Tarkov": [{"title": "a", "url": "https://a.example"},
                                                                    {"title": "b", "url": "https://b.example"}]}})
        controller.open()
        controller.handle_output("bookmark remove 0")
        self.assertEqual([item["title"] for item in self.eng.set["bookmarks"]["Tarkov"]], ["b"])
        self.assertEqual([item["title"] for item in self.bookmark_writes()[-1]["items"]], ["b"])

    def test_ervenytelen_vagy_duplikalt_nem_ment_es_ertesit(self):
        controller = self.make_game(settings={"bookmarks": {"Tarkov": [{"title": "a", "url": "https://a.example"}]}})
        controller.open()
        saves = self.eng.saves["settings"]
        for line in ('bookmark add {"title": "x", "url": "javascript:alert(1)"}',
                     'bookmark add {"title": "dup", "url": "https://a.example"}'):
            controller.handle_output(line)
        self.assertEqual(self.eng.saves["settings"], saves)
        self.assertEqual(len(self.eng.set["bookmarks"]["Tarkov"]), 1)
        self.assertEqual(len(self.eng.toasts), 2)

    def test_hibas_konyvjelzo_sorok_nem_dobnak(self):
        controller = self.make_game()
        controller.open()
        for line in ("bookmark", "bookmark add", "bookmark add nem json", 'bookmark add [1]', 'bookmark add {"title": 1}',
                     "bookmark remove", "bookmark remove x", "bookmark remove -1", "bookmark remove 99", "bookmark torol 1"):
            controller.handle_output(line)
        self.assertEqual(self.eng.saves["settings"], 0)
        self.assertEqual(self.eng.set.get("bookmarks", {}).get("Tarkov", []), [])

    def test_zart_bongeszonel_a_sor_nem_ment_semmit(self):
        controller = self.make_game()
        controller.handle_output('bookmark add {"title": "x", "url": "https://x.example"}')
        self.assertEqual(self.eng.saves["settings"], 0)
