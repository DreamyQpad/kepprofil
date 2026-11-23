"""A térkép-overlay bekötése: a logfigyelő és a vezérlő összekapcsolása (MapFeed), a gyorsgomb-akciók a GUI-ban."""
import unittest
from types import SimpleNamespace

from map_overlay import MapFeed
from tarkov_log import MapEvent


class FakeTail:
    def __init__(self, polls=(), state=None):
        self.polls, self._state = list(polls), state

    def poll(self):
        return self.polls.pop(0) if self.polls else []

    def state(self):
        return self._state


class FakeController:
    def __init__(self):
        self.events, self.checks = [], 0

    def on_event(self, event):
        self.events.append(event)

    def check(self):
        self.checks += 1


class MapFeedTest(unittest.TestCase):
    def feed(self, tail, setting=""):
        self.controller, self.made = FakeController(), []

        def make_tail(path):
            self.made.append(path)
            return tail
        return MapFeed(self.controller, SimpleNamespace(set={"tarkov_path": setting}), make_tail=make_tail)

    def test_az_esemenyeket_a_vezerlonek_adja_es_hivja_a_checket(self):
        feed = self.feed(FakeTail(polls=[[], [MapEvent("preload", "woods")]]))
        feed.tick()
        feed.tick()
        self.assertEqual(self.controller.events, [MapEvent("preload", "woods")])
        self.assertEqual(self.controller.checks, 2)

    def test_csatlakozaskor_a_folyamatban_levo_raidet_is_atadja(self):
        raid = MapEvent("raid", "Woods")
        feed = self.feed(FakeTail(polls=[[], [MapEvent("end", "")]], state=raid))
        feed.tick()
        self.assertEqual(self.controller.events, [raid])
        feed.tick()
        self.assertEqual(self.controller.events, [raid, MapEvent("end", "")])

    def test_csatlakozaskor_nincs_raid_nincs_esemeny(self):
        feed = self.feed(FakeTail(polls=[[]]))
        feed.tick()
        self.assertEqual(self.controller.events, [])

    def test_nincs_telepites_nem_dob_es_ritkan_keres(self):
        feed = self.feed(None)
        for _ in range(70):
            feed.tick()
        self.assertEqual(len(self.made), 3)
        self.assertEqual(self.controller.checks, 70)

    def test_a_beallitott_utat_adja_tovabb(self):
        feed = self.feed(FakeTail(), setting="D:/Games/Tarkov")
        feed.tick()
        self.assertEqual(self.made, ["D:/Games/Tarkov"])

    def test_a_telepites_kesobb_is_megtalalhato(self):
        results = [None, FakeTail(polls=[[], [MapEvent("preload", "woods")]])]
        self.controller = FakeController()
        feed = MapFeed(self.controller, SimpleNamespace(set={}), make_tail=lambda path: results.pop(0))
        for _ in range(32):                                    # az első keresés sikertelen, a második a 31. ütemben jön
            feed.tick()
        self.assertEqual(self.controller.events, [MapEvent("preload", "woods")])


class Calls:
    """Minden metódushívást a közös naplóba ír."""

    def __init__(self, name, log):
        self._name, self._log = name, log

    def __getattr__(self, method):
        return lambda *args: self._log.append((self._name, method) + args)


try:
    import gui
except ImportError:                                     # pragma: no cover - a környezetben nincs GUI-csomag
    gui = None


@unittest.skipIf(gui is None, "nincs customtkinter")
class HotkeyActionTest(unittest.TestCase):
    def app(self, with_map=True, menu_open=False):
        self.log = []
        menu = Calls("menu", self.log)
        menu.is_open = menu_open
        app = SimpleNamespace(overlay=Calls("overlay", self.log), map=Calls("map", self.log) if with_map else None,
                              menu=menu if with_map else None, browser=Calls("browser", self.log) if with_map else None,
                              eng=Calls("eng", self.log), tray=Calls("tray", self.log), root=Calls("root", self.log),
                              hotkey_layers=Calls("layers", self.log))
        app.overlay.is_open = False
        app._close_menu = lambda: gui.App._close_menu(app)
        app._run_handler = lambda kind, handler, arguments: gui.App._run_handler(app, kind, handler, arguments)
        app.pump = lambda: None
        return app

    def test_terkep_akciok_a_vezerlore_kotve(self):
        app = self.app()
        gui.App._run_hotkey_action(app, "map")
        gui.App._run_hotkey_action(app, "map_interact")
        gui.App._run_hotkey_action(app, "mp|left")
        self.assertEqual(self.log, [("map", "toggle"), ("map", "cycle_mode"), ("map", "key", "mp|left")])

    def test_billentyuzetes_modba_lepve_a_nyitott_profil_overlay_bezarodik(self):
        """Mindkettő a nyilakat és az Esc-et kérné."""
        app = self.app()
        app.overlay.is_open = True
        gui.App._run_hotkey_action(app, "map_interact")
        self.assertLess(self.log.index(("overlay", "close")), self.log.index(("map", "cycle_mode")))

    def test_a_gyorsgomb_alkalmazas_a_retegeken_at_megy(self):
        app = self.app()
        gui.App.apply_hotkeys(app)
        self.assertEqual(self.log, [("layers", "refresh")])

    def test_a_profil_overlay_nyitasa_elott_a_billentyuzetes_modbol_kilep(self):
        app = self.app()
        gui.App._run_hotkey_action(app, "overlay")
        self.assertEqual(self.log, [("map", "leave_keys"), ("overlay", "toggle")])

    def test_terkep_nelkul_a_terkep_akciok_hatastalanok(self):
        app = self.app(with_map=False)
        for action in ("map", "map_interact", "mp|up"):
            gui.App._run_hotkey_action(app, action)
        gui.App._run_hotkey_action(app, "overlay")
        self.assertEqual(self.log, [("overlay", "toggle")])

    def test_fonablak_elrejtese_az_overlay_elott_mentetlen_modositast_nem_dob_el(self):
        for dirty, expected_hides in ((False, [("panel", "hide")]), (True, [])):
            log = []
            app = SimpleNamespace(panel=SimpleNamespace(is_dirty=lambda: dirty, hide=lambda: log.append(("panel", "hide"))))
            self.assertIs(gui.App.hide_main_window(app), not dirty)
            self.assertEqual(log, expected_hides)

    def test_menu_akciok_a_menure_kotve(self):
        app = self.app()
        gui.App._run_hotkey_action(app, "menu")
        gui.App._run_hotkey_action(app, "mn|down")
        self.assertEqual(self.log, [("menu", "toggle"), ("menu", "key", "mn|down")])

    def test_menu_nelkul_a_menu_akciok_hatastalanok(self):
        app = self.app(with_map=False)
        gui.App._run_hotkey_action(app, "menu")
        gui.App._run_hotkey_action(app, "mn|ok")
        self.assertEqual(self.log, [])

    def test_nyitott_menu_bezarodik_ha_masik_overlay_gombja_jon(self):
        for action, expected in (("overlay", ("overlay", "toggle")), ("map", ("map", "toggle")),
                                 ("map_interact", ("map", "cycle_mode"))):
            app = self.app(menu_open=True)
            gui.App._run_hotkey_action(app, action)
            self.assertEqual(self.log[0], ("menu", "close"), action)
            self.assertIn(expected, self.log)

    def test_zart_menu_nem_kap_zarasi_hivast(self):
        app = self.app(menu_open=False)
        gui.App._run_hotkey_action(app, "map")
        self.assertNotIn(("menu", "close"), self.log)

    def test_menu_megnyitasa_elott_a_masik_overlay_gombjai_felszabadulnak(self):
        app = self.app()
        app.overlay.is_open = True
        gui.App._before_menu_open(app)
        self.assertEqual(self.log, [("map", "leave_keys"), ("overlay", "close")])

    def test_aktiv_jatek_a_kepernyon_elol_levo_monitor_presetje(self):
        from unittest import mock
        cases = ((("MON1", "Tarkov"), "Tarkov"), (("MON1", "Alap"), ""), (None, ""))
        for target, expected in cases:
            app = SimpleNamespace(eng=SimpleNamespace(overlay_target=lambda mid, target=target: target))
            with mock.patch.object(gui, "foreground_monitor_id", lambda: "MON1"):
                self.assertEqual(gui.App._active_game(app), expected, target)

    def test_aktiv_jatek_az_elol_levo_monitort_kerdezi(self):
        from unittest import mock
        asked = []
        app = SimpleNamespace(eng=SimpleNamespace(overlay_target=lambda mid: asked.append(mid)))
        with mock.patch.object(gui, "foreground_monitor_id", lambda: "MON2"):
            gui.App._active_game(app)
        self.assertEqual(asked, ["MON2"])

    def test_kilepeskor_leall_a_bongeszo(self):
        app = self.app()
        gui.App.quit(app)
        self.assertIn(("browser", "stop"), self.log)

    def test_a_kezelo_hibaja_nem_allitja_le_az_uzenetsor_ciklusat(self):
        import queue
        app = self.app()
        app.queue = queue.Queue()
        app.root = SimpleNamespace(after=lambda ms, fn: self.log.append(("root", "after")))
        seen = []

        def boom():
            raise RuntimeError("kezelő hiba")
        app._handlers = {"boom": boom, "ok": lambda: seen.append("ok")}
        app.eng = SimpleNamespace(say=lambda text: self.log.append(("say", text)))
        app.queue.put(("boom",))
        app.queue.put(("ok",))
        gui.App.pump(app)
        self.assertEqual(seen, ["ok"])                        # a hibás után a következő üzenet is lefut
        self.assertIn(("root", "after"), self.log)            # és a ciklus újraütemeződik

    def test_kilepeskor_leall_a_terkepfolyamat(self):
        app = self.app()
        gui.App.quit(app)
        self.assertIn(("map", "stop"), self.log)


if __name__ == "__main__":
    unittest.main()
