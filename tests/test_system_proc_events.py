"""A platform-réteg `start_process_events` belépési pontja: hiba esetén None, Linuxon mindig None."""
import unittest
from unittest import mock

import system_linux
import system_windows


class SystemProcEventsTest(unittest.TestCase):
    def test_windows_returns_source_from_platform_module(self):
        src = object()
        with mock.patch("proc_events_windows.start_process_events", return_value=src):
            self.assertIs(system_windows.start_process_events(lambda *a: None, lambda: None), src)

    def test_windows_swallows_start_error(self):
        with mock.patch("proc_events_windows.start_process_events", side_effect=OSError("nincs powershell")):
            self.assertIsNone(system_windows.start_process_events(lambda *a: None, lambda: None))

    def test_linux_has_no_event_source(self):
        self.assertIsNone(system_linux.start_process_events(lambda *a: None, lambda: None))


if __name__ == "__main__":
    unittest.main()
