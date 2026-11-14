"""Folyamat-események: névszámláló, esemény-belépési pont, figyelt nevekre ébresztés."""
import unittest
from unittest import mock

from engine import norm_proc
from tests.stubs import make_engine


class ProcEventTest(unittest.TestCase):
    def test_norm_proc(self):
        self.assertEqual(norm_proc("Game.EXE"), "game")
        self.assertEqual(norm_proc("game"), "game")
        self.assertEqual(norm_proc(""), "")
        self.assertEqual(norm_proc(None), "")

    def test_ket_pelda_egyik_kilep_a_jatek_fut_marad(self):
        eng, _ = make_engine(self)
        eng.proc_event(True, "game.exe")
        eng.proc_event(True, "game.exe")
        eng.proc_event(False, "game.exe")
        self.assertTrue(eng.proc_running("game"))
        eng.proc_event(False, "game.exe")
        self.assertFalse(eng.proc_running("game"))

    def test_stop_nem_megy_nulla_ala(self):
        eng, _ = make_engine(self)
        eng.proc_event(False, "x.exe")
        self.assertEqual(eng.proc_counts.get("x", 0), 0)
        eng.proc_event(True, "x.exe")
        self.assertTrue(eng.proc_running("x"))

    def test_set_running_ujraepiti_a_szamlalot(self):
        eng, _ = make_engine(self)
        eng.set_running(["Game.exe", "game.exe", "x.exe"])
        self.assertEqual(eng.proc_counts, {"game": 2, "x": 1})
        self.assertEqual(eng.running, {"game", "x"})
        eng.set_running(["x.exe"])
        self.assertFalse(eng.proc_running("game"))

    def test_csak_figyelt_nevre_ebreszt(self):
        eng, _ = make_engine(self)
        eng.watch_wake.clear()
        eng.proc_event(True, "conhost.exe")
        self.assertFalse(eng.watch_wake.is_set())
        eng.proc_event(True, "GAME.exe")
        self.assertTrue(eng.watch_wake.is_set())

    def test_watched_names_az_osszes_preset_neve(self):
        eng, _ = make_engine(self)
        self.assertEqual(eng.watched_names(), {"game"})

    def test_esemenymodban_nincs_gyorsitotar_frissites(self):
        eng, _ = make_engine(self)
        eng.refresh_running = mock.Mock()
        eng.event_mode = True
        eng.running_t = 0.0
        eng.proc_running("game")
        eng.refresh_running.assert_not_called()
        eng.event_mode = False
        eng.running_t = 0.0
        eng.proc_running("game")
        eng.refresh_running.assert_called_once()


if __name__ == "__main__":
    unittest.main()
