"""Az overlay modellje: sorok, léptetés, mentés, új változat, elvetés."""
import unittest

from overlay import ROWS, OverlayModel
from tests.stubs import default_cfg, make_engine


def row_index(key):
    return next(i for i, r in enumerate(ROWS) if r.key == key)


def model_for(test, cfg=None):
    eng, display = make_engine(test, cfg)
    return OverlayModel(eng, "MON1", "Játék"), eng, display


class Loading(unittest.TestCase):
    def test_rows_order_and_ranges(self):
        self.assertEqual([r.key for r in ROWS], ["b", "c", "g", "v", "cr", "cg", "cb"])
        g = ROWS[row_index("g")]
        self.assertEqual((g.lo, g.hi, g.step, g.default), (0.30, 2.80, 0.01, 1.0))

    def test_loads_values_with_gamma_display_scale(self):
        m, _, _ = model_for(self)
        self.assertEqual(m.values["g"], 1.0)                      # belső 2,2 = 1,00 a panelen
        self.assertEqual((m.values["c"], m.values["b"], m.values["v"]), (55, 45, 60))
        self.assertEqual((m.values["cr"], m.values["cg"], m.values["cb"]), (100, 100, 100))
        self.assertEqual(m.title(), "Játék")

    def test_loads_values_of_current_variant(self):
        cfg = default_cfg()
        cfg["monitors"][0]["presets"]["Játék"]["variants"] = {
            "Alap": {"gamma": 2.2, "contrast": 55, "brightness": 45, "vibrance": 60},
            "Éjjel": {"gamma": 1.1, "contrast": 40, "brightness": 30, "vibrance": 20, "gain": [100, 90, 80]}}
        eng, _ = make_engine(self, cfg)
        eng.variant[("MON1", "Játék")] = "Éjjel"
        m = OverlayModel(eng, "MON1", "Játék")
        self.assertEqual((m.values["g"], m.values["c"], m.values["cb"]), (0.5, 40, 80))
        self.assertEqual(m.title(), "Játék · Éjjel")


class Navigation(unittest.TestCase):
    def test_move_wraps_around(self):
        m, _, _ = model_for(self)
        m.move(-1)
        self.assertEqual(m.sel, len(ROWS) - 1)
        m.move(1)
        self.assertEqual(m.sel, 0)

    def test_adjust_clamps_at_both_ends(self):
        m, _, _ = model_for(self)
        m.sel = row_index("b")
        m.adjust(+1000)
        self.assertEqual(m.values["b"], 100)
        m.adjust(-1000)
        self.assertEqual(m.values["b"], 0)

    def test_gamma_steps_do_not_drift(self):
        m, _, _ = model_for(self)
        m.sel = row_index("g")
        m.values["g"] = 0.30
        for _ in range(250):
            m.adjust(1)
        self.assertEqual(m.values["g"], 2.80)
        m.adjust(1)
        self.assertEqual(m.values["g"], 2.80)

    def test_big_step_is_five_units(self):
        m, _, _ = model_for(self)
        m.sel = row_index("c")
        m.adjust(5)
        self.assertEqual(m.values["c"], 60)

    def test_reset_row_uses_row_default(self):
        m, _, _ = model_for(self)
        for key, default in (("g", 1.0), ("c", 50), ("b", 50), ("v", 50), ("cr", 100)):
            m.sel = row_index(key)
            m.adjust(7)
            m.reset_row()
            self.assertEqual(m.values[key], default, key)


class Values(unittest.TestCase):
    def test_vals_converts_gamma_back_to_internal(self):
        m, _, _ = model_for(self)
        m.sel = row_index("g")
        m.values["g"] = 0.5
        self.assertEqual(m.vals(), (1.1, 55, 45, 60))
        self.assertEqual(m.gain(), [100, 100, 100])

    def test_dirty_follows_changes(self):
        m, _, _ = model_for(self)
        self.assertFalse(m.dirty())
        m.adjust(1)
        self.assertTrue(m.dirty())
        m.adjust(-1)
        self.assertFalse(m.dirty())

    def test_preview_calls_engine_preview_with_values_and_gain(self):
        m, eng, display = model_for(self)
        m.sel = row_index("cb")
        m.adjust(-10)
        self.assertTrue(m.preview())
        dev, vals, mult = display.calls[-1]
        self.assertEqual((dev, vals), ("DEV_MON1", (2.2, 55, 45, 60)))
        self.assertEqual(mult, (1.0, 1.0, 0.9))


class Persistence(unittest.TestCase):
    def test_save_persists_into_current_variant(self):
        m, eng, _ = model_for(self)
        m.sel = row_index("b")
        m.adjust(5)
        m.save()
        self.assertEqual(eng.preset("MON1", "Játék")["brightness"], 50)
        self.assertFalse(m.dirty())

    def test_new_variant_keeps_values_and_switches_title(self):
        m, eng, _ = model_for(self)
        m.sel = row_index("c")
        m.adjust(3)
        name = m.new_variant()
        self.assertEqual(name, "Változat 2")
        self.assertEqual(m.title(), "Játék · Változat 2")
        self.assertEqual(m.values["c"], 58)
        self.assertFalse(m.dirty())
        self.assertEqual(eng.preset("MON1", "Játék")["variants"]["Változat 2"]["contrast"], 58)

    def test_discard_restores_saved_image(self):
        m, eng, display = model_for(self)
        m.adjust(10)
        m.preview()
        m.discard()
        self.assertEqual(display.calls[-1][1], (2.2, 55, 45, 60))          # a mentett kép áll vissza
        self.assertEqual(m.values["b"], 45)

    def test_discard_after_new_variant_only_drops_later_changes(self):
        m, eng, display = model_for(self)
        m.sel = row_index("b")
        m.adjust(5)                                       # 50
        m.new_variant()
        m.adjust(10)                                      # 60, mentetlen
        m.discard()
        self.assertEqual(m.values["b"], 50)
        self.assertEqual(eng.preset("MON1", "Játék")["variants"]["Változat 2"]["brightness"], 50)
        self.assertEqual(display.calls[-1][1][2], 50)       # az új változat értéke látszik


if __name__ == "__main__":
    unittest.main()
