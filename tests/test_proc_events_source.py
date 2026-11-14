"""Windows folyamat-eseményforrás: sorprotokoll értelmezése, indítás, EOF, leállítás (hamis popen-nel)."""
import threading
import unittest

from proc_events_windows import ProcessEventSource, parse_line


class FakeProc:
    """Hamis PowerShell-gyerek: iterálható stdout, poll/kill/wait. Blokkoló módban a kill oldja fel az olvasót."""

    def __init__(self, lines, block_after=False):
        self._release = threading.Event()
        self._block_after = block_after
        self._lines = list(lines)
        self.killed = False
        self.returncode = None
        self.stdout = self._gen()

    def _gen(self):
        for ln in self._lines:
            yield ln
        if self._block_after:
            self._release.wait(5)

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9
        self._release.set()

    def wait(self, timeout=None):
        return self.returncode


def make_source(proc, **kw):
    events = []
    lost = threading.Event()
    lost_calls = []

    def on_lost():
        lost_calls.append(1)
        lost.set()

    src = ProcessEventSource(lambda started, name: events.append((started, name)), on_lost,
                             popen=lambda *a, **k: proc, **kw)
    return src, events, lost, lost_calls


class ParseLineTest(unittest.TestCase):
    def test_parse_line(self):
        self.assertEqual(parse_line("start|Game.exe"), (True, "Game.exe"))
        self.assertEqual(parse_line("stop|Game.exe"), (False, "Game.exe"))
        self.assertEqual(parse_line("stop|Game.exe\r\n"), (False, "Game.exe"))
        self.assertEqual(parse_line("stop|x y.exe"), (False, "x y.exe"))
        self.assertIsNone(parse_line("ready"))
        self.assertIsNone(parse_line(""))
        self.assertIsNone(parse_line("garbage"))
        self.assertIsNone(parse_line("start|"))
        self.assertIsNone(parse_line("other|x.exe"))


class ProcessEventSourceTest(unittest.TestCase):
    def test_ready_utan_az_esemenyek_megerkeznek_es_eof_on_lost(self):
        proc = FakeProc(["ready\n", "start|A.exe\n", "garbage\n", "stop|A.exe\n"])
        src, events, lost, lost_calls = make_source(proc)
        self.assertTrue(src.start())
        self.assertTrue(lost.wait(2))
        self.assertEqual(events, [(True, "A.exe"), (False, "A.exe")])
        src._thread.join(2)
        self.assertEqual(len(lost_calls), 1)

    def test_eof_ready_elott_start_hamis(self):
        proc = FakeProc([])
        src, events, lost, lost_calls = make_source(proc)
        self.assertFalse(src.start())
        self.assertTrue(proc.killed)
        src._thread.join(2)
        self.assertEqual(lost_calls, [])
        self.assertEqual(events, [])

    def test_ready_idotullepes(self):
        proc = FakeProc([], block_after=True)
        src, events, lost, lost_calls = make_source(proc, ready_timeout=0.2)
        self.assertFalse(src.start())
        self.assertTrue(proc.killed)
        src._thread.join(2)
        self.assertEqual(lost_calls, [])

    def test_stop_leallitja_es_nem_hiv_on_lost(self):
        proc = FakeProc(["ready\n", "start|A.exe\n"], block_after=True)
        src, events, lost, lost_calls = make_source(proc)
        self.assertTrue(src.start())
        src.stop()
        self.assertTrue(proc.killed)
        src._thread.join(2)
        self.assertFalse(src._thread.is_alive())
        self.assertEqual(lost_calls, [])


if __name__ == "__main__":
    unittest.main()
