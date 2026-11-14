"""A felület tiszta részei: a toast animációja és a gyorsbillentyű-súgó sorai (Tk-képernyő nélkül)."""
import unittest

from tests.stubs import make_engine

try:
    import customtkinter  # noqa: F401
    from gui_dialogs import shortcut_rows
    from gui_toast import FADE_FRAME_MS, HOLD_END_STEP, HOLD_FRAME_MS, MAX_ALPHA, alpha_at, frame_delay_ms
except ImportError:                                     # pragma: no cover - a környezetben nincs GUI-csomag
    shortcut_rows = None


@unittest.skipIf(shortcut_rows is None, "nincs customtkinter")
class ToastAnimationTest(unittest.TestCase):
    def test_elotunes_noveli_majd_teljes_majd_halvanyodik(self):
        self.assertAlmostEqual(alpha_at(1), 0.23)
        self.assertLess(alpha_at(2), alpha_at(3))
        self.assertEqual(alpha_at(10), MAX_ALPHA)
        self.assertEqual(alpha_at(HOLD_END_STEP - 1), MAX_ALPHA)
        self.assertLess(alpha_at(HOLD_END_STEP + 1), MAX_ALPHA)

    def test_a_halvanyodas_nullan_er_veget(self):
        self.assertEqual(alpha_at(HOLD_END_STEP + 20), 0.0)

    def test_a_latszo_szakasz_lepesei_lassabbak_mint_az_elo_es_eltunes(self):
        self.assertEqual(frame_delay_ms(1), FADE_FRAME_MS)
        self.assertEqual(frame_delay_ms(10), HOLD_FRAME_MS)
        self.assertEqual(frame_delay_ms(HOLD_END_STEP + 1), FADE_FRAME_MS)


@unittest.skipIf(shortcut_rows is None, "nincs customtkinter")
class ShortcutRowsTest(unittest.TestCase):
    def test_a_sorok_az_altalanos_akciokkal_kezdodnek_majd_monitoronkent_presetek_es_valtozatok(self):
        eng, _ = make_engine(self)
        eng.mon("MON1")["presets"]["Alap"]["variants"] = {"Első": {}, "Második": {}}
        rows = shortcut_rows(eng)
        labels = [label for label, _ in rows]
        self.assertEqual(rows[:3], [("Éjszakai mód (minden monitor)", "night"),
                                    ("Semleges kép (minden kikapcsol)", "neutral"),
                                    ("Következő változat (az aktív játéknál, minden monitoron)", "cycle")])
        self.assertIn("Monitor 1 – Alap", labels)
        self.assertIn("Monitor 1 – Alap: Első", labels)
        self.assertIn("Monitor 1 – Alap: Második", labels)
        self.assertIn("Monitor 1 – Játék", labels)


if __name__ == "__main__":
    unittest.main()
