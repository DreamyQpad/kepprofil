"""A főmenü: modell (léptetés), vezérlő (nyitás/zárás, billentyűfoglalás, akciók) hamis nézettel."""
import unittest

from hw_common import MENU_KEYS
from menu_overlay import ITEMS, MenuController, MenuModel
from tests.stubs import make_engine


class ModelTest(unittest.TestCase):
    def test_lepteto_korbe_er(self):
        model = MenuModel()
        self.assertEqual(model.selected, ITEMS[0][0])
        model.move(1)
        model.move(1)
        model.move(1)
        self.assertEqual(model.selected, ITEMS[0][0])
        model.move(-1)
        self.assertEqual(model.selected, ITEMS[-1][0])

    def test_menupontok(self):
        self.assertEqual([item_id for item_id, _ in ITEMS], ["map", "browser", "profile"])
        self.assertEqual([caption for _, caption in ITEMS], ["Térkép", "Böngésző", "Képbeállítások"])


class FakeView:
    def __init__(self):
        self.is_open, self.rect, self.sel_history, self.on_click = False, None, [], None

    def show(self, rect, model, on_click):
        self.is_open, self.rect, self.on_click = True, rect, on_click
        self.sel_history.append(model.selected)

    def update(self, model):
        self.sel_history.append(model.selected)

    def close(self):
        self.is_open = False


class FakeRoot:
    def winfo_screenwidth(self):
        return 1920

    def winfo_screenheight(self):
        return 1080


def build(test, fg=None, settings=None):
    eng, _ = make_engine(test, settings=settings or {"menu_hotkey": "Shift+Tab"})
    view, calls, hotkeys, order = FakeView(), [], [], []
    actions = {item_id: (lambda item_id=item_id: calls.append(item_id)) for item_id, _ in ITEMS}
    controller = MenuController(eng, FakeRoot(), set_hotkeys=lambda mapping: hotkeys.append(dict(mapping)), actions=actions,
                                rect_for=lambda mid: (0, 0, 1920, 1080), foreground_mid=lambda: fg,
                                before_open=lambda: order.append("before_open"), view=view)
    controller.t = type("T", (), {"eng": eng, "view": view, "calls": calls, "hotkeys": hotkeys, "order": order})
    return controller


class OpenCloseTest(unittest.TestCase):
    def test_nyitas_foglalja_a_menu_gombokat_es_megtartja_a_meglevoket(self):
        controller = build(self)
        controller.toggle()
        t = controller.t
        self.assertTrue(controller.is_open and t.view.is_open)
        self.assertTrue(set(MENU_KEYS) <= set(t.hotkeys[-1]))
        self.assertEqual(t.hotkeys[-1]["menu"], "Shift+Tab")

    def test_nyitas_elott_a_masik_overlay_gombjai_felszabadulnak(self):
        controller = build(self)
        controller.toggle()
        self.assertEqual(controller.t.order, ["before_open"])

    def test_zaras_felszabadítja_a_gombokat(self):
        controller = build(self)
        controller.toggle()
        controller.toggle()
        t = controller.t
        self.assertFalse(controller.is_open or t.view.is_open)
        self.assertFalse(any(key.startswith("mn|") for key in t.hotkeys[-1]))
        self.assertEqual(t.hotkeys[-1]["menu"], "Shift+Tab")

    def test_esc_zar(self):
        controller = build(self)
        controller.toggle()
        controller.key("mn|close")
        self.assertFalse(controller.is_open)

    def test_a_menu_kozepre_kerul_a_monitoron(self):
        controller = build(self)
        controller.toggle()
        self.assertEqual(controller.t.view.rect, (0, 0, 1920, 1080))


class NavigationTest(unittest.TestCase):
    def test_nyilak_leptetnek_es_frissitik_a_nezetet(self):
        controller = build(self)
        controller.toggle()
        controller.key("mn|down")
        controller.key("mn|down")
        controller.key("mn|up")
        self.assertEqual(controller.t.view.sel_history, ["map", "browser", "profile", "browser"])

    def test_enter_a_kijelolt_akciot_hivja_bezaras_utan(self):
        controller = build(self)
        controller.toggle()
        controller.key("mn|down")
        controller.key("mn|ok")
        t = controller.t
        self.assertEqual(t.calls, ["browser"])
        self.assertFalse(controller.is_open or t.view.is_open)
        self.assertFalse(any(key.startswith("mn|") for key in t.hotkeys[-1]))

    def test_kattintas_az_adott_akciot_hivja(self):
        controller = build(self)
        controller.toggle()
        controller.t.view.on_click("profile")
        self.assertEqual(controller.t.calls, ["profile"])
        self.assertFalse(controller.is_open)

    def test_zart_menu_billentyuit_figyelmen_kivul_hagyja(self):
        controller = build(self)
        controller.key("mn|ok")
        controller.key("mn|down")
        self.assertEqual(controller.t.calls, [])

    def test_akcio_kivetele_nem_hagyja_nyitva_a_menut(self):
        controller = build(self)
        controller.actions["map"] = lambda: (_ for _ in ()).throw(RuntimeError("hiba"))
        controller.toggle()
        controller.key("mn|ok")
        self.assertFalse(controller.is_open)
        self.assertFalse(any(key.startswith("mn|") for key in controller.t.hotkeys[-1]))


class RealViewTest(unittest.TestCase):
    def test_a_menu_a_monitor_kozepen_jelenik_meg_a_valodi_stilussal_is(self):
        """A menü stílusa (nem aktiválódó, nincs tálcagomb) nem jelenítheti meg az ablakot a helyre tétele előtt: a bal felső
        sarokban maradna."""
        import tkinter
        from menu_overlay import WIDTH, MenuView
        from overlay import centered_position
        try:
            root = tkinter.Tk()
        except tkinter.TclError as error:                    # nincs képernyő
            self.skipTest(str(error))
        self.addCleanup(root.destroy)
        view = MenuView(root)
        rect = (200, 100, 1800, 1000)
        view.show(rect, MenuModel(), lambda item_id: None)
        self.addCleanup(view.close)
        for _ in range(5):
            root.update()
        window = view.window
        expected = centered_position(rect, WIDTH, window.winfo_height())
        self.assertEqual((window.winfo_rootx(), window.winfo_rooty()), expected)

    def test_a_nem_aktivalodo_stilus_meg_a_megjelenes_elott_lep_eletbe(self):
        """A tálcagomb a megjelenéskor jön létre: a stílusnak a rejtett ablakon kell beállnia, utólag már késő."""
        import tkinter
        from unittest import mock
        try:
            root = tkinter.Tk()
        except tkinter.TclError as error:                    # nincs képernyő
            self.skipTest(str(error))
        self.addCleanup(root.destroy)
        from menu_overlay import MenuView
        states = []
        with mock.patch("hw.menu_style", lambda window: states.append(window.state())):
            view = MenuView(root)
            view.show((0, 0, 1920, 1080), MenuModel(), lambda item_id: None)
        self.addCleanup(view.close)
        self.assertEqual(states, ["withdrawn"])
        self.assertEqual(view.window.state(), "normal")


    def test_valodi_tk_ablak_megjelenik_frissul_kattintas_es_zaras(self):
        import tkinter
        try:
            root = tkinter.Tk()
        except tkinter.TclError as error:                    # nincs képernyő
            self.skipTest(str(error))
        self.addCleanup(root.destroy)
        from menu_overlay import MenuView
        view, model, clicks = MenuView(root), MenuModel(), []
        view.show((0, 0, 1920, 1080), model, clicks.append)
        self.assertTrue(view.is_open)
        texts = {item_id: row.cget("text") for item_id, row in view._rows.items()}
        self.assertEqual(texts["map"], "▶ Térkép")
        model.move(1)
        view.update(model)
        self.assertEqual(view._rows["browser"].cget("text"), "▶ Böngésző")
        self.assertEqual(view._rows["map"].cget("text"), "   Térkép")
        root.update()
        view._rows["profile"].event_generate("<Button-1>", x=5, y=5)
        root.update()
        self.assertEqual(clicks, ["profile"])
        view.close()
        self.assertFalse(view.is_open)


if __name__ == "__main__":
    unittest.main()
