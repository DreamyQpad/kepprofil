"""Az overlay vezérlője: nyitás/zárás, billentyűk, előnézet, mentés, elvetés, automatikus zárás."""
import copy
import unittest

from hw_common import OVERLAY_KEYS
from overlay import OverlayController
from tests.stubs import default_cfg, make_engine


class FakeRoot:
    """A tk.after üteme: a várakozó hívásokat a teszt futtatja le (flush)."""

    def __init__(self):
        self.jobs, self.n = {}, 0

    def after(self, ms, fn):
        self.n += 1
        self.jobs[self.n] = fn
        return self.n

    def after_cancel(self, job):
        self.jobs.pop(job, None)

    def flush(self):
        while self.jobs:
            _, fn = self.jobs.popitem()
            fn()

    def winfo_screenwidth(self):
        return 1920

    def winfo_screenheight(self):
        return 1080


class FakeView:
    def __init__(self):
        self.is_open = False
        self.shown, self.titles, self.warning = 0, [], ""

    def show(self, rect, model, warning=""):
        self.is_open, self.rect, self.warning = True, rect, warning
        self.shown += 1
        self.titles.append(model.title())

    def update(self, model, warning=""):
        self.titles.append(model.title())

    def close(self):
        self.is_open = False


def build(test, cfg=None, active=("MON1", "Játék"), fg=None, main=False, failed=()):
    eng, display = make_engine(test, cfg, active=active)
    root, view = FakeRoot(), FakeView()
    state = {"fg": fg, "main": main, "failed": set(failed)}
    hk_calls, rect_calls = [], []

    def rect_for(mid):
        rect_calls.append(mid)
        return (0, 0, 1920, 1080)

    ctl = OverlayController(eng, root, set_hotkeys=lambda m: hk_calls.append(dict(m)),
                           foreground_mid=lambda: state["fg"], rect_for=rect_for,
                           hotkey_failed=lambda: state["failed"], main_visible=lambda: state["main"], view=view)
    ctl.t = type("T", (), {"eng": eng, "display": display, "root": root, "view": view, "state": state,
                           "hk": hk_calls, "rects": rect_calls})
    return ctl


def brightness(display):
    return display.calls[-1][1][2]


class Opening(unittest.TestCase):
    def test_toggle_opens_and_registers_overlay_keys(self):
        ctl = build(self)
        ctl.toggle()
        t = ctl.t
        self.assertTrue(ctl.is_open and t.view.is_open and t.eng.panel_open)
        self.assertTrue(set(OVERLAY_KEYS) <= set(t.hk[-1]))
        self.assertIn("p|MON1|Játék", t.hk[-1])                  # a meglévő gyorsgombok megmaradnak
        self.assertEqual(t.view.titles[-1], "Játék")

    def test_no_active_preset_does_not_open_and_toasts(self):
        ctl = build(self, active=None)
        ctl.toggle()
        t = ctl.t
        self.assertFalse(ctl.is_open or t.view.is_open or t.eng.panel_open)
        self.assertEqual(t.eng.toasts, ["Nincs aktív preset"])
        self.assertEqual(t.hk, [])

    def test_main_window_visible_does_not_open(self):
        ctl = build(self, main=True)
        ctl.toggle()
        self.assertFalse(ctl.is_open or ctl.t.eng.panel_open)
        self.assertEqual(ctl.t.eng.toasts, [])

    def test_foreground_monitor_is_preferred(self):
        cfg = default_cfg()
        second = copy.deepcopy(cfg["monitors"][0])
        second["id"], second["name"] = "MON2", "Monitor 2"
        cfg["monitors"].append(second)
        ctl = build(self, cfg)
        ctl.t.eng.active["MON2"] = "Játék"
        ctl.t.state["fg"] = "MON2"
        ctl.toggle()
        self.assertEqual(ctl.t.rects[-1], "MON2")

    def test_warning_lists_unregistered_keys(self):
        ctl = build(self, failed={"ov|new", "ov|save", "p|MON1|Játék"})
        ctl.toggle()
        w = ctl.t.view.warning
        self.assertIn("Enter", w)
        self.assertIn("N", w)
        self.assertNotIn("p|MON1", w)

    def test_no_warning_when_all_keys_work(self):
        ctl = build(self)
        ctl.toggle()
        self.assertEqual(ctl.t.view.warning, "")


class Editing(unittest.TestCase):
    def test_arrow_keys_preview_on_display(self):
        ctl = build(self)
        ctl.toggle()
        ctl.key("ov|right")
        ctl.t.root.flush()
        self.assertEqual(brightness(ctl.t.display), 46)
        ctl.key("ov|sright")
        ctl.t.root.flush()
        self.assertEqual(brightness(ctl.t.display), 51)
        ctl.key("ov|down")
        ctl.key("ov|left")                                       # a kontraszt sora
        ctl.t.root.flush()
        self.assertEqual(ctl.t.display.calls[-1][1][1], 54)

    def test_repeated_keys_coalesce_into_one_preview(self):
        ctl = build(self)
        ctl.toggle()
        before = len(ctl.t.display.calls)
        for _ in range(10):
            ctl.key("ov|right")
        self.assertEqual(len(ctl.t.display.calls), before)       # a késleltetés alatt nincs hívás
        ctl.t.root.flush()
        self.assertEqual(len(ctl.t.display.calls), before + 1)
        self.assertEqual(brightness(ctl.t.display), 55)

    def test_reset_row_key(self):
        ctl = build(self)
        ctl.toggle()
        ctl.key("ov|down")
        ctl.key("ov|reset")                                      # kontraszt: 55 -> 50
        ctl.t.root.flush()
        self.assertEqual(ctl.t.display.calls[-1][1][1], 50)


class Closing(unittest.TestCase):
    def test_save_key_persists_closes_and_toasts(self):
        ctl = build(self)
        ctl.toggle()
        ctl.key("ov|right")
        ctl.key("ov|save")
        t = ctl.t
        self.assertEqual(t.eng.preset("MON1", "Játék")["brightness"], 46)
        self.assertGreaterEqual(t.eng.saves["config"], 1)
        self.assertFalse(ctl.is_open or t.view.is_open or t.eng.panel_open)
        self.assertEqual(t.hk[-1], t.eng.hotkey_map())
        self.assertEqual(len(t.eng.toasts), 1)
        self.assertIn("Játék", t.eng.toasts[0])
        t.root.flush()
        self.assertEqual(brightness(t.display), 46)              # a mentett kép látszik

    def test_escape_discards_and_restores_saved_image(self):
        ctl = build(self)
        ctl.toggle()
        ctl.key("ov|right")
        ctl.t.root.flush()
        self.assertEqual(brightness(ctl.t.display), 46)
        ctl.key("ov|close")
        t = ctl.t
        self.assertEqual(brightness(t.display), 45)
        self.assertEqual(t.eng.preset("MON1", "Játék")["brightness"], 45)
        self.assertFalse(ctl.is_open or t.view.is_open or t.eng.panel_open)
        self.assertEqual(t.hk[-1], t.eng.hotkey_map())

    def test_second_toggle_closes_and_restores_hotkeys(self):
        ctl = build(self)
        ctl.toggle()
        ctl.toggle()
        t = ctl.t
        self.assertFalse(ctl.is_open or t.view.is_open or t.eng.panel_open)
        self.assertEqual(t.hk[-1], t.eng.hotkey_map())

    def test_close_cancels_pending_preview(self):
        ctl = build(self)
        ctl.toggle()
        ctl.key("ov|right")
        ctl.toggle()
        n = len(ctl.t.display.calls)
        ctl.t.root.flush()
        self.assertEqual(len(ctl.t.display.calls), n)
        self.assertEqual(brightness(ctl.t.display), 45)

    def test_keys_after_close_are_ignored(self):
        ctl = build(self)
        ctl.toggle()
        ctl.toggle()
        saves, calls = dict(ctl.t.eng.saves), len(ctl.t.display.calls)
        for action in OVERLAY_KEYS:
            ctl.key(action)
        ctl.t.root.flush()
        self.assertEqual(ctl.t.eng.saves, saves)
        self.assertEqual(len(ctl.t.display.calls), calls)
        self.assertFalse(ctl.is_open)


class NewVariant(unittest.TestCase):
    def test_new_variant_keeps_panel_open_and_updates_title(self):
        ctl = build(self)
        ctl.toggle()
        ctl.key("ov|right")
        ctl.key("ov|new")
        t = ctl.t
        self.assertTrue(ctl.is_open and t.view.is_open)
        self.assertEqual(t.view.titles[-1], "Játék · Változat 2")
        variants = t.eng.preset("MON1", "Játék")["variants"]
        self.assertEqual(set(variants), {"Alap", "Változat 2"})
        self.assertEqual(variants["Változat 2"]["brightness"], 46)
        self.assertEqual(variants["Alap"]["brightness"], 45)

    def test_escape_after_new_variant_drops_only_later_changes(self):
        ctl = build(self)
        ctl.toggle()
        ctl.key("ov|right")
        ctl.key("ov|new")
        ctl.key("ov|sright")
        ctl.t.root.flush()
        ctl.key("ov|close")
        t = ctl.t
        self.assertEqual(t.eng.preset("MON1", "Játék")["variants"]["Változat 2"]["brightness"], 46)
        self.assertEqual(brightness(t.display), 46)


class AutoClose(unittest.TestCase):
    def test_check_keeps_open_while_nothing_changes(self):
        ctl = build(self)
        ctl.toggle()
        ctl.check()
        self.assertTrue(ctl.is_open)

    def test_game_quits_closes_panel(self):
        ctl = build(self)
        ctl.toggle()
        ctl.key("ov|right")
        ctl.t.root.flush()
        del ctl.t.eng.active["MON1"]
        ctl.check()
        t = ctl.t
        self.assertFalse(ctl.is_open or t.view.is_open or t.eng.panel_open)
        self.assertEqual(t.hk[-1], t.eng.hotkey_map())
        self.assertEqual(t.eng.preset("MON1", "Játék")["brightness"], 45)

    def test_preset_switch_closes_panel(self):
        ctl = build(self)
        ctl.toggle()
        ctl.t.eng.active["MON1"] = "Alap"
        ctl.check()
        self.assertFalse(ctl.is_open)

    def test_main_window_opening_closes_panel(self):
        ctl = build(self)
        ctl.toggle()
        ctl.t.state["main"] = True
        ctl.check()
        self.assertFalse(ctl.is_open or ctl.t.eng.panel_open)

    def test_check_when_closed_is_noop(self):
        ctl = build(self)
        ctl.check()
        self.assertFalse(ctl.is_open)
        self.assertEqual(ctl.t.hk, [])


if __name__ == "__main__":
    unittest.main()
