"""A térképfolyamat: parancs-szókincs, a parancshurok (EOF = kilép), az oldalba küldött szkriptek, a módváltás logikája."""
import io
import json
import sys
import unittest
from unittest import mock

from map_window import (WEB_TITLE, MapApi, WindowModes, WebApi, escape_script, add_bookmark_line, nav_buttons_script, remove_bookmark_line,
                        web_bar_script, web_url, parse_command, pan_script, read_commands, serve_commands, tarkov_url, to_logical_rect,
                        wait_until, zoom_script)


class ParseCommandTest(unittest.TestCase):
    def test_ervenyes_parancsok(self):
        self.assertEqual(parse_command("map woods"), ("map", "woods"))
        self.assertEqual(parse_command("show"), ("show",))
        self.assertEqual(parse_command("hide"), ("hide",))
        self.assertEqual(parse_command("mode keys"), ("mode", "keys"))
        self.assertEqual(parse_command("pan left"), ("pan", "left"))
        self.assertEqual(parse_command("zoom out"), ("zoom", "out"))
        self.assertEqual(parse_command("alpha 0.5"), ("alpha", 0.5))
        self.assertEqual(parse_command("rect 10 20 800 600"), ("rect", 10, 20, 800, 600))
        self.assertEqual(parse_command("quit"), ("quit",))

    def test_ervenytelen_parancsok(self):
        for text in ("", "mode xyz", "alpha 5", "alpha 0.1", "rect a b c d", "rect 1 2 3", "pan", "pan sideways",
                     "zoom", "map", "map ../x", "valami"):
            self.assertIsNone(parse_command(text), text)

    def test_a_terkepazonosito_csak_biztonsagos_karakter(self):
        self.assertIsNone(parse_command("map woods;alert(1)"))
        self.assertEqual(parse_command("map streets-of-tarkov"), ("map", "streets-of-tarkov"))


class BookmarksCommandTest(unittest.TestCase):
    def test_ervenyes_savot_tisztit_es_atad(self):
        payload = {"game": "Tarkov", "items": [{"title": "Wiki", "url": "https://wiki.example"},
                                               {"title": "rossz", "url": "javascript:alert(1)"}, "nem szótár"]}
        command = parse_command("bookmarks " + json.dumps(payload))
        self.assertEqual(command, ("bookmarks", {"game": "Tarkov", "items": [{"title": "Wiki", "url": "https://wiki.example"}]}))

    def test_hibas_json_nem_parancs(self):
        for line in ("bookmarks", "bookmarks nem json", "bookmarks [1]", 'bookmarks {"game": 3, "items": []}',
                     'bookmarks {"game": "G", "items": "x"}'):
            self.assertIsNone(parse_command(line), line)

    def test_ures_sav_ervenyes(self):
        self.assertEqual(parse_command('bookmarks {"game": "", "items": []}'), ("bookmarks", {"game": "", "items": []}))


class TarkovUrlTest(unittest.TestCase):
    def test_url(self):
        self.assertEqual(tarkov_url("woods"), "https://tarkov.dev/map/woods")


class ReadCommandsTest(unittest.TestCase):
    def run_loop(self, text):
        seen = []
        read_commands(io.StringIO(text), seen.append)
        return seen

    def test_a_parancsokat_a_kezelonek_adja(self):
        self.assertEqual(self.run_loop("show\nhide\n"), [("show",), ("hide",)])

    def test_az_ervenytelen_sort_kihagyja(self):
        self.assertEqual(self.run_loop("show\nkamu\nhide\n"), [("show",), ("hide",)])

    def test_quit_utan_nem_olvas_tovabb(self):
        self.assertEqual(self.run_loop("show\nquit\nhide\n"), [("show",)])

    def test_a_kezelo_hibaja_nem_allitja_le_a_hurkot(self):
        seen = []

        def handle(command):
            seen.append(command)
            if command == ("show",):
                raise RuntimeError("az oldal nem válaszol")
        read_commands(io.StringIO("show\nhide\n"), handle)
        self.assertEqual(seen, [("show",), ("hide",)])

    def test_stream_vege_kilep(self):
        self.assertEqual(self.run_loop(""), [])                 # a szülő meghalt: a hurok visszatér, nem lóg


class WaitUntilTest(unittest.TestCase):
    def test_addig_var_amig_az_allapot_igaz_nem_var_tovabb(self):
        states, sleeps = iter([False, False, True]), []
        self.assertTrue(wait_until(lambda: next(states), timeout=5, interval=0.1, sleep=sleeps.append, clock=lambda: 0))
        self.assertEqual(sleeps, [0.1, 0.1])

    def test_idokorlat_utan_feladja(self):
        now = [0.0]

        def sleep(seconds):
            now[0] += seconds
        self.assertFalse(wait_until(lambda: False, timeout=1, interval=0.25, sleep=sleep, clock=lambda: now[0]))
        self.assertAlmostEqual(now[0], 1.0)


class ServeCommandsTest(unittest.TestCase):
    def test_a_parancsok_csak_az_ablak_meglete_utan_futnak(self):
        ready = {"polls": 0}

        def window_ready():
            ready["polls"] += 1
            return ready["polls"] >= 3
        seen = []
        serve_commands(io.StringIO("show\n"), lambda command: seen.append((command, ready["polls"])), window_ready,
                       wait=lambda predicate: [predicate() for _ in range(3)])
        self.assertEqual(seen, [(("show",), 3)])

    def test_ablak_nelkul_is_feldolgozza_a_sorokat_az_idokorlat_utan(self):
        seen = []
        serve_commands(io.StringIO("hide\n"), seen.append, lambda: False, wait=lambda predicate: False)
        self.assertEqual(seen, [("hide",)])


class LogicalRectTest(unittest.TestCase):
    def test_a_fizikai_helyet_logikaira_osztja_a_skalazassal(self):
        self.assertEqual(to_logical_rect((150, 300, 1440, 960), 144), (100, 200, 960, 640))

    def test_szazalekos_skalazas_nelkul_valtozatlan(self):
        self.assertEqual(to_logical_rect((10, 20, 800, 600), 96), (10, 20, 800, 600))

    def test_ismeretlen_dpi_nem_ront(self):
        self.assertEqual(to_logical_rect((10, 20, 800, 600), 0), (10, 20, 800, 600))


class ScriptTest(unittest.TestCase):
    def test_nyilak_billentyukodja(self):
        for direction, code in (("left", 37), ("up", 38), ("right", 39), ("down", 40)):
            self.assertIn(f"keyCode:{code}", pan_script(direction).replace(" ", ""))

    def test_nagyitas_a_zoom_gombokat_nyomja(self):
        self.assertIn(".leaflet-control-zoom-in", zoom_script("in"))
        self.assertIn(".leaflet-control-zoom-out", zoom_script("out"))


class WebWindowTest(unittest.TestCase):
    def test_kezdooldal_a_google(self):
        self.assertEqual(web_url(), "https://www.google.com")

    def test_a_bongeszo_cime_kulon_van_a_terkepetol(self):
        from map_window import TITLE
        self.assertNotEqual(WEB_TITLE, TITLE)

    def api(self, lines=None, calls=None, page=("https://wiki.example/a", "Wiki")):
        lines = [] if lines is None else lines
        calls = [] if calls is None else calls
        return WebApi(lambda: calls.append("closed"), lines.append, lambda: page, token="titok")

    def test_web_api_close_a_visszahivast_hivja(self):
        calls = []
        self.api(calls=calls).close("titok")
        self.assertEqual(calls, ["closed"])

    def test_web_api_konyvjelzo_muveletek_sorokat_adnak(self):
        lines = []
        api = self.api(lines)
        api.add_bookmark("titok")
        api.remove_bookmark(2, "titok")
        self.assertEqual(lines, [add_bookmark_line("Wiki", "https://wiki.example/a"), remove_bookmark_line(2)])

    def test_az_oldal_csak_onmagat_menthet_a_cimet_es_az_url_t_a_folyamat_adja(self):
        lines = []
        self.api(lines, page=("https://igazi.example/", "Igazi")).add_bookmark("titok")
        self.assertEqual(lines, [add_bookmark_line("Igazi", "https://igazi.example/")])

    def test_rossz_vagy_hianyzo_token_semmit_sem_csinal(self):
        lines, calls = [], []
        api = self.api(lines, calls)
        for token in ("rossz", "", None):
            api.close(token)
            api.add_bookmark(token)
            api.remove_bookmark(0, token)
        self.assertEqual((lines, calls), ([], []))

    def test_a_token_veletlen_es_folyamatonkent_kulonbozo(self):
        from map_window import new_token
        self.assertNotEqual(new_token(), new_token())
        self.assertGreaterEqual(len(new_token()), 16)

    def test_konyvjelzo_sorok_formatuma(self):
        self.assertEqual(remove_bookmark_line(3), "bookmark remove 3")
        line = add_bookmark_line("Cím \"idézőjellel\" és ő", "https://a.example/?q=1&x=2")
        self.assertTrue(line.startswith("bookmark add "))
        self.assertEqual(json.loads(line[len("bookmark add "):]), {"title": "Cím \"idézőjellel\" és ő", "url": "https://a.example/?q=1&x=2"})
        self.assertNotIn("\n", line)

    def test_web_api_hibas_bemenet_nem_dob(self):
        lines = []
        api = self.api(lines, page=(None, None))
        api.add_bookmark("titok")
        api.remove_bookmark("x", "titok")
        self.assertEqual(lines, [])


class WebBarScriptTest(unittest.TestCase):
    PAYLOAD = {"game": "Tarkov", "items": [{"title": "Wiki", "url": "https://wiki.example"}]}

    def test_a_konyvjelzok_json_kent_agyazodnak(self):
        self.assertIn(json.dumps(self.PAYLOAD), web_bar_script(True, self.PAYLOAD))

    def test_veszelyes_cim_nem_szakitja_ki_a_scriptet(self):
        payload = {"game": "G", "items": [{"title": "</script>'\"\\", "url": "https://a.example"}]}
        script = web_bar_script(True, payload)
        self.assertIn(json.dumps(payload), script)

    def test_gombok_es_hivasok(self):
        compact = web_bar_script(True, self.PAYLOAD).replace(" ", "")
        for part in ("history.go(-1)", "history.go(1)", "pywebview.api.add_bookmark(token)",
                     "pywebview.api.remove_bookmark(i,token)", "pywebview.api.close(token)", "Bezár", "☆"):
            self.assertIn(part, compact, part)

    def test_a_token_json_kent_kerul_a_szkriptbe(self):
        self.assertIn("vartoken=" + json.dumps("ab12") + ";", web_bar_script(True, self.PAYLOAD, "ab12").replace(" ", ""))

    def test_a_cimben_levo_helyorzo_nem_cserelodik(self):
        payload = {"game": "G", "items": [{"title": "a __MARGIN__ b __DISPLAY__ c __TOKEN__", "url": "https://a.example"}]}
        script = web_bar_script(True, payload, "tok")
        self.assertIn(json.dumps(payload), script)

    def test_a_cim_nem_html_kent_kerul_az_oldalba(self):
        self.assertNotIn("innerHTML", web_bar_script(True, self.PAYLOAD))

    def test_lathatosag_es_oldaleltolas(self):
        shown, hidden = web_bar_script(True, self.PAYLOAD), web_bar_script(False, self.PAYLOAD)
        self.assertIn("display='flex'", shown)
        self.assertIn("marginTop='44px'", shown)
        self.assertIn("display='none'", hidden)
        self.assertIn("marginTop=''", hidden)

    def test_ujrafuttatva_a_regi_savot_cserli(self):
        self.assertIn("getElementById('kp-web-bar')", web_bar_script(True, self.PAYLOAD))

    def test_ures_jatek_neve_altalanos(self):
        compact = web_bar_script(True, {"game": "", "items": []}).replace(" ", "")
        self.assertIn("Általános", compact)


class NavButtonsScriptTest(unittest.TestCase):
    def test_visszat_es_elorelep_a_naploban(self):
        script = nav_buttons_script(True).replace(" ", "")
        self.assertIn("history.go(x[1])", script)
        self.assertIn("['\u2190Vissza',-1]", script)
        self.assertIn("['El\u0151re\u2192',1]", script)

    def test_lathatosag_a_parameter_szerint(self):
        self.assertIn("style.display='flex'", nav_buttons_script(True))
        self.assertIn("style.display='none'", nav_buttons_script(False))

    def test_ujrafuttatva_ugyanazt_a_gombsort_frissiti(self):
        self.assertIn("getElementById('kp-nav')", nav_buttons_script(True))


class FakeWin32:
    """A Win32-réteg hamis változata: a hívásokat rögzíti."""

    def __init__(self, foreground=111, own=999, rect=(10, 20, 800, 600), dpi=96):
        self.calls, self._foreground, self._own, self._rect, self._dpi = [], foreground, own, rect, dpi

    def dpi(self):
        return self._dpi

    def apply(self, mode, alpha):
        self.calls.append(("apply", mode, alpha))

    def own(self):
        return self._own

    def foreground(self):
        return self._foreground

    def set_foreground(self, handle):
        self.calls.append(("set_foreground", handle))

    def rect(self):
        return self._rect

    def show(self):
        self.calls.append(("show",))

    def hide(self):
        self.calls.append(("hide",))


class WindowModesTest(unittest.TestCase):
    def test_egeres_modba_lepve_megjegyzi_az_elozo_elteret_es_fokuszt_kap(self):
        win32 = FakeWin32()
        modes = WindowModes(win32, alpha=0.8)
        modes.set_mode("mouse")
        self.assertEqual(win32.calls, [("apply", "mouse", 0.8), ("set_foreground", 999)])

    def test_egeres_modbol_kilepve_visszaadja_az_elozo_elteret_es_a_helyet(self):
        win32 = FakeWin32()
        modes = WindowModes(win32, alpha=0.8)
        modes.set_mode("mouse")
        win32.calls.clear()
        line = modes.set_mode("glance")
        self.assertEqual(line, "rect 10 20 800 600")
        self.assertEqual(win32.calls, [("apply", "glance", 0.8), ("set_foreground", 111)])

    def test_a_rect_sor_logikai_pixelt_ad_skalazott_kijelzon_is(self):
        win32 = FakeWin32(rect=(150, 300, 1440, 960), dpi=144)
        modes = WindowModes(win32, alpha=0.8)
        modes.set_mode("mouse")
        self.assertEqual(modes.set_mode("glance"), "rect 100 200 960 640")

    def test_mas_modok_kozott_nincs_fokuszvaltas_es_rect_sor(self):
        win32 = FakeWin32()
        modes = WindowModes(win32, alpha=0.8)
        self.assertIsNone(modes.set_mode("keys"))
        self.assertEqual(win32.calls, [("apply", "keys", 0.8)])

    def test_ketszer_egymas_utan_egeres_mod_nem_irja_felul_az_elozo_elteret(self):
        win32 = FakeWin32()
        modes = WindowModes(win32, alpha=0.8)
        modes.set_mode("mouse")
        win32._foreground = 999                                  # most már a térkép az előtér
        modes.set_mode("mouse")
        win32.calls.clear()
        modes.set_mode("glance")
        self.assertIn(("set_foreground", 111), win32.calls)

    def test_ha_mar_a_terkep_az_elter_nincs_mit_visszaadni(self):
        win32 = FakeWin32(foreground=999)
        modes = WindowModes(win32, alpha=0.8)
        modes.set_mode("mouse")
        win32.calls.clear()
        modes.set_mode("glance")
        self.assertEqual(win32.calls, [("apply", "glance", 0.8)])

    def test_megjelenites_elobb_a_stilust_alkalmazza_aztan_fokusz_nelkul_mutat(self):
        win32 = FakeWin32()
        modes = WindowModes(win32, alpha=0.8)
        modes.show()
        self.assertEqual(win32.calls, [("apply", "glance", 0.8), ("show",)])

    def test_elrejtes_egeres_modbol_visszaadja_a_fokuszt_es_a_helyet(self):
        win32 = FakeWin32()
        modes = WindowModes(win32, alpha=0.8)
        modes.set_mode("mouse")
        win32.calls.clear()
        line = modes.hide()
        self.assertEqual(line, "rect 10 20 800 600")
        self.assertEqual(win32.calls, [("apply", "glance", 0.8), ("set_foreground", 111), ("hide",)])

    def test_elrejtes_mas_modbol_csak_elrejt(self):
        win32 = FakeWin32()
        modes = WindowModes(win32, alpha=0.8)
        self.assertIsNone(modes.hide())
        self.assertEqual(win32.calls, [("hide",)])

    def test_alfa_valtas_ujraalkalmazza_a_jelenlegi_modot(self):
        win32 = FakeWin32()
        modes = WindowModes(win32, alpha=0.8)
        modes.set_mode("keys")
        win32.calls.clear()
        modes.set_alpha(0.5)
        self.assertEqual(win32.calls, [("apply", "keys", 0.5)])


class EscapeTest(unittest.TestCase):
    def test_a_script_az_escape_billentyure_hiv(self):
        script = escape_script().replace(" ", "")
        self.assertIn("e.key==='Escape'", script)
        self.assertIn("pywebview.api.escape()", script)
        self.assertIn("window.__kpEsc", script)                  # betöltésenként egyszer köt be

    def test_map_api_escape_a_visszahivast_hivja(self):
        calls = []
        MapApi(lambda: calls.append("esc")).escape()
        self.assertEqual(calls, ["esc"])


@unittest.skipUnless(sys.platform == "win32", "a folyamat a Windows-os ablakréteget tölti be")
class CreateWindowTest(unittest.TestCase):
    """A pywebview-ablak létrehozási beállításai (hamis webview-modullal, ablak nélkül)."""

    def create_kwargs(self, web):
        import map_window
        captured = {}

        class Hook:
            def __iadd__(self, handler):
                return self

        class Events:
            loaded = Hook()

        fake = mock.MagicMock()
        fake.settings = self.settings = {}

        def create_window(*args, **kwargs):
            captured.update(kwargs)
            window = mock.MagicMock()
            window.events = Events()
            return window

        fake.create_window = create_window
        with mock.patch.dict(sys.modules, {"webview": fake}):
            map_window._run_window("https://example.test", "teszt", "webview-teszt", 0.9, None, web=web)
        return captured

    def test_az_oldal_belsejebol_nem_huzhato_az_ablak(self):
        for web in (False, True):
            self.assertIs(self.create_kwargs(web)["easy_drag"], False, f"web={web}")

    def test_a_terkep_ablak_kap_escape_felületet_a_bongeszo_nem(self):
        self.assertIsInstance(self.create_kwargs(False)["js_api"], MapApi)
        self.assertIsInstance(self.create_kwargs(True)["js_api"], WebApi)

    def test_az_uj_ablakot_nyito_linkek_ugyanabban_az_ablakban_nyilnak(self):
        """Különben a rendszer alapböngészője ugrana elő, és a játék elveszítené a fókuszt."""
        for web in (False, True):
            self.create_kwargs(web)
            self.assertIs(self.settings.get("OPEN_EXTERNAL_LINKS_IN_BROWSER"), False, f"web={web}")

    def test_keret_nelkuli_legfelso_ablak_marad(self):
        kwargs = self.create_kwargs(False)
        self.assertIs(kwargs["frameless"], True)
        self.assertIs(kwargs["on_top"], True)
        self.assertIs(kwargs["hidden"], True)


class WebEntryPointTest(unittest.TestCase):
    def test_web_kapcsolo_a_bongeszofolyamatot_inditja_a_mentett_hellyel(self):
        import kijelzo
        with mock.patch.object(sys, "argv", ["kijelzo.py", "--web"]),                 mock.patch("config.load_settings", return_value={"web_rect": [5, 6, 700, 500]}),                 mock.patch("map_window.run_web") as run_web:
            kijelzo.main()
        run_web.assert_called_once_with([5, 6, 700, 500])


class MapEntryPointTest(unittest.TestCase):
    def test_map_kapcsolo_a_terkepfolyamatot_inditja_a_beallitasokkal(self):
        import kijelzo
        settings = {"map_alpha": 0.7, "map_rect": [1, 2, 3, 4]}
        with mock.patch.object(sys, "argv", ["kijelzo.py", "--map", "woods"]),                 mock.patch("config.load_settings", return_value=settings),                 mock.patch("map_window.run") as run:
            kijelzo.main()
        run.assert_called_once_with("woods", 0.7, [1, 2, 3, 4])

    def test_map_kapcsolo_ervenytelen_azonosito_nem_indit_ablakot(self):
        import kijelzo
        with mock.patch.object(sys, "argv", ["kijelzo.py", "--map", "woods;x"]), mock.patch("map_window.run") as run,                 self.assertRaises(SystemExit) as raised:
            kijelzo.main()
        run.assert_not_called()
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
