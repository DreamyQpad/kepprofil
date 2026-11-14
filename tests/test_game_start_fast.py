"""Játék indulása: azonnali bekapcsolás (nincs vakvárakozás), időzített utánellenőrzés, a figyelő-ciklus és az eseményforrás kezelése."""
import threading
import time
import unittest
from unittest import mock

from engine import Engine
from tests.stubs import make_engine


def last_vals(display, dev="DEV_MON1"):
    return [c for c in display.calls if c[0] == dev][-1][1]


def log_text(eng):
    return "\n".join(t for _, t in eng.log)


class FakeSource:
    def __init__(self, on_event, on_lost):
        self.on_event, self.on_lost = on_event, on_lost
        self.stopped = False

    def stop(self):
        self.stopped = True


def started_engine(test):
    """Eseménymódban álló motor (a figyelő-ciklus a már leállított motoron csak az indítást végzi el)."""
    eng, display = make_engine(test, active=None)
    made = []

    def start_events(on_event, on_lost):
        made.append(FakeSource(on_event, on_lost))
        return made[0]

    eng.stop = True
    eng.watch_loop(start_events=start_events)
    eng.stop = False
    return eng, display, made[0]


class GameStartFastTest(unittest.TestCase):
    def test_inditaskor_nincs_vakvarakozas(self):
        eng, display = make_engine(self, active=None)
        eng.running = {"game"}
        eng.running_t = 1e18
        eng.monitors_t = 1e18
        with mock.patch("engine.time.sleep") as sleep:
            eng.watch_tick()
        sleep.assert_not_called()
        self.assertEqual(last_vals(display)[3], 60)              # a Játék preset vibrance-a

    def test_inditas_utan_utanellenorzes_idozitve(self):
        eng, _ = make_engine(self, active=None)
        eng.START_DELAYS = (1.5, 4.0)
        eng.running = {"game"}
        eng.running_t = 1e18
        eng.monitors_t = 1e18
        with mock.patch("engine.threading.Timer") as timer:
            eng.watch_tick()
        self.assertEqual(timer.call_count, 2)
        self.assertEqual([c.args[0] for c in timer.call_args_list], [1.5, 4.0])
        for c in timer.call_args_list:
            self.assertEqual(c.args[1], eng.reapply)
            self.assertEqual(tuple(c.kwargs["args"]), ("start",))
        self.assertTrue(timer.return_value.daemon)
        self.assertEqual(timer.return_value.start.call_count, 2)

    def test_utanellenorzes_visszaallitja_a_nullazott_gorbet(self):
        eng, display = make_engine(self, active=None)
        eng.running = {"game"}
        eng.running_t = 1e18
        eng.monitors_t = 1e18
        eng.watch_tick()
        display.calls.clear()
        eng.reapplied_t = 0.0
        eng.reapply("start")                                     # a görbe ép: nincs új hívás
        self.assertEqual(display.calls, [])
        display.drifted = lambda *a, **k: True                   # a játék nullázta a görbét
        eng.reapplied_t = 0.0
        eng.reapply("start")
        self.assertTrue(display.calls)
        self.assertEqual(last_vals(display)[3], 60)

    def test_esemenymodban_a_tick_csak_resyncre_kerdezi_le_a_programokat(self):
        eng, _ = make_engine(self, active=None)
        eng.monitors_t = 1e18
        eng.refresh_running = mock.Mock()
        eng.event_mode = True
        eng.running_t = time.time()
        eng.watch_tick()
        eng.refresh_running.assert_not_called()
        eng.running_t = time.time() - 10
        eng.watch_tick()
        self.assertEqual(eng.refresh_running.call_count, 1)

    def test_lekerdezes_modban_a_tick_mindig_lekerdez(self):
        eng, _ = make_engine(self, active=None)
        eng.monitors_t = 1e18
        eng.refresh_running = mock.Mock()
        eng.event_mode = False
        eng.running_t = time.time()
        eng.watch_tick()
        self.assertEqual(eng.refresh_running.call_count, 1)

    def test_watch_interval(self):
        eng, _ = make_engine(self, active=None)
        eng.event_mode = False
        self.assertEqual(eng.watch_interval(), Engine.POLL_SECONDS)
        eng.event_mode = True
        self.assertEqual(eng.watch_interval(), Engine.POLL_SECONDS)

    def test_esemenymodban_a_varakozas_poll_ritmusu_a_teljes_pillanatkep_viszont_ritkabb(self):
        """Eseménymódban is POLL_SECONDS-onként fut a tick (enforce, csendes forrás-romlás), de a teljes pillanatkép
        csak RESYNC_SECONDS után."""
        eng, _ = make_engine(self, active=None)
        eng.monitors_t = 1e18
        eng.refresh_running = mock.Mock()
        eng.event_mode = True
        eng.running_t = 1000.0
        waits = []

        def wait(timeout):
            waits.append(timeout)
            eng.stop = True
            return False

        eng.watch_wake = mock.Mock(wait=wait)
        with mock.patch("engine.time.time", return_value=1000.0 + Engine.RESYNC_SECONDS - 0.1):
            eng.watch_loop()
        self.assertEqual(waits, [Engine.POLL_SECONDS])
        eng.refresh_running.assert_not_called()                  # a pillanatkép még nem esedékes
        with mock.patch("engine.time.time", return_value=1000.0 + Engine.RESYNC_SECONDS + 0.1):
            eng.watch_tick()
        self.assertEqual(eng.refresh_running.call_count, 1)      # lejárt a RESYNC_SECONDS: újraolvas

    def test_watch_loop_esemenyre_azonnal_fut(self):
        eng, _ = make_engine(self, active=None)
        eng.POLL_SECONDS = 60
        eng.watch_tick = mock.Mock()
        th = threading.Thread(target=eng.watch_loop, daemon=True)
        th.start()
        end = time.time() + 2
        while eng.watch_tick.call_count < 1 and time.time() < end:
            time.sleep(0.01)
        self.assertEqual(eng.watch_tick.call_count, 1)
        eng.watch_wake.set()
        end = time.time() + 0.5
        while eng.watch_tick.call_count < 2 and time.time() < end:
            time.sleep(0.01)
        self.assertGreaterEqual(eng.watch_tick.call_count, 2)
        eng.stop = True
        eng.watch_wake.set()
        th.join(2)
        self.assertFalse(th.is_alive())

    def test_watch_loop_tick_hiba_nem_allitja_le_a_ciklust(self):
        eng, _ = make_engine(self, active=None)
        eng.POLL_SECONDS = 0.01
        calls = []

        def tick():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("hopp")
            eng.stop = True

        eng.watch_tick = tick
        eng.watch_loop()
        self.assertEqual(len(calls), 2)
        self.assertIn("Figyelő hiba: hopp", log_text(eng))

    def test_forras_sikeres_inditasa_esemenymodba_visz(self):
        eng, _, src = started_engine(self)
        self.assertTrue(eng.event_mode)
        self.assertIs(eng.events, src)
        src.on_event(True, "game.exe")
        self.assertTrue(eng.proc_running("game"))
        self.assertIn("Játékfigyelő: események", log_text(eng))

    def test_forras_hiba_eseten_lekerdezes_marad(self):
        eng, _ = make_engine(self, active=None)
        eng.stop = True
        eng.watch_loop(start_events=lambda on_event, on_lost: None)
        self.assertFalse(eng.event_mode)
        self.assertIn("Játékfigyelő: lekérdezés", log_text(eng))
        self.assertIn("nincs emelt jog", log_text(eng))

    def test_forras_inditasi_kivetele_utan_a_lekerdezes_marad_es_a_ciklus_fut(self):
        eng, _ = make_engine(self, active=None)
        eng.POLL_SECONDS = 0.01
        ticks = []

        def tick():
            ticks.append(1)
            if len(ticks) >= 2:
                eng.stop = True

        def boom(on_event, on_lost):
            raise OSError("nincs jog")

        eng.watch_tick = tick
        eng.watch_loop(start_events=boom)
        self.assertFalse(eng.event_mode)
        self.assertIsNone(eng.events)
        self.assertIn("Játékfigyelő: lekérdezés", log_text(eng))
        self.assertEqual(len(ticks), 2)

    def test_indulo_pillanatkep_hibaja_leallitja_a_forrast_es_a_ciklus_fut(self):
        eng, _ = make_engine(self, active=None)
        eng.POLL_SECONDS = 0.01
        made = []

        def start_events(on_event, on_lost):
            made.append(FakeSource(on_event, on_lost))
            return made[0]

        def snapshot_boom():
            raise RuntimeError("psutil hiba")

        ticks = []

        def tick():
            ticks.append(1)
            eng.stop = True

        eng.refresh_running = snapshot_boom
        eng.watch_tick = tick
        eng.watch_loop(start_events=start_events)
        self.assertFalse(eng.event_mode)
        self.assertTrue(made[0].stopped)
        self.assertIsNone(eng.events)
        self.assertIn("Játékfigyelő: lekérdezés", log_text(eng))
        self.assertEqual(len(ticks), 1)

    def test_eseményfolyam_megszakadasa_visszaall_lekerdezesre(self):
        eng, _, src = started_engine(self)
        eng.watch_wake.clear()
        eng.running_t = time.time()
        src.on_lost()
        self.assertFalse(eng.event_mode)
        self.assertEqual(eng.running_t, 0.0)
        self.assertTrue(eng.watch_wake.is_set())
        self.assertIn("lekérdezés", log_text(eng).split("Játékfigyelő: események")[-1])

    def test_shutdown_leallitja_a_forrast(self):
        eng, _, src = started_engine(self)
        eng.shutdown()
        self.assertTrue(src.stopped)

    def test_esemenymodban_a_kihagyott_leallitasi_esemenyt_a_resync_javitja(self):
        """Hamis „él még" (elveszett stop-esemény): a profil nem ragad be, a következő teljes pillanatkép után kikapcsol,
        és az indulás előtti alap tér vissza."""
        eng, display = make_engine(self, active=("MON1", "Alap"))
        eng.event_mode = True
        eng.monitors_t = 1e18
        eng.running_t = time.time()                              # friss pillanatkép: a tick nem olvas újra
        eng.refresh_running = mock.Mock()
        with mock.patch("engine.threading.Timer"):
            eng.proc_event(True, "game.exe")
            eng.watch_tick()
        self.assertEqual(eng.active["MON1"], "Játék")
        self.assertEqual(last_vals(display)[3], 60)
        eng.refresh_running.assert_not_called()

        eng.refresh_running = mock.Mock(side_effect=lambda: eng.set_running([]))   # a valóság: a játék már nem fut
        eng.running_t = time.time() - Engine.RESYNC_SECONDS - 1
        eng.watch_tick()
        eng.refresh_running.assert_called_once()
        self.assertEqual(eng.active.get("MON1"), "Alap")
        self.assertNotIn(("MON1", "Játék"), eng.auto)

    def test_proc_event_ebresztese_nem_var_a_zarra(self):
        """A figyelt név eseménye akkor is felébreszti a figyelőt, ha a `lock`-ot épp másik szál tartja (szinkron közben)."""
        eng, _ = make_engine(self, active=None)
        eng.watch_wake.clear()
        done = threading.Event()
        held, release = threading.Event(), threading.Event()

        def holder():
            with eng.lock:
                held.set()
                release.wait(3)

        h = threading.Thread(target=holder, daemon=True)
        h.start()
        held.wait(1)

        def ev():
            eng.proc_event(True, "game.exe")
            done.set()

        threading.Thread(target=ev, daemon=True).start()
        finished = done.wait(1)
        release.set()
        h.join(2)
        self.assertTrue(finished)
        self.assertTrue(eng.watch_wake.is_set())


if __name__ == "__main__":
    unittest.main()
