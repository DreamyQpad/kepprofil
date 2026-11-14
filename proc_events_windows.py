"""Windows folyamat-eseményforrás: egy PowerShell gyerek a WMI Win32_ProcessStartTrace / Win32_ProcessStopTrace
eseményeit sorokban adja át (`ready`, majd `start|<név>` / `stop|<név>`), a Python oldal ebből hív `on_event`-et.

Emelt jog kell hozzá (a WMI process trace csak rendszergazdának érhető el); jog nélkül a gyerek a `ready` előtt
kilép, a `start()` hamis, a `start_process_events` pedig `None`-t ad, és a hívó lekérdezésre esik vissza.

Ismert, elfogadott korlát: a motor a névszámlálóját ~5 másodpercenként egy teljes folyamat-pillanatképből építi újra,
ezért egy pillanatkép közben érkező esemény elveszhet vagy duplán számolódhat a következő pillanatképig. Ezt nem ez
a modul oldja meg."""
import ctypes
import os
import subprocess
import threading

from consts import CREATE_NO_WINDOW

# A gyerek minden iterációban megnézi, él-e a szülő: így akkor is leáll, ha a programot `taskkill /F` lövi le
# (ilyenkor nincs lehetőségünk kill()-t hívni). A Wait-Event 3 mp-es időkorlátja adja a legrosszabb esetű késést.
SCRIPT_TEMPLATE = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Register-WmiEvent -Query 'SELECT * FROM Win32_ProcessStartTrace' -SourceIdentifier 'kj_start' | Out-Null
Register-WmiEvent -Query 'SELECT * FROM Win32_ProcessStopTrace' -SourceIdentifier 'kj_stop' | Out-Null
[Console]::Out.WriteLine('ready')
while ($true) {
    if (-not (Get-Process -Id __PARENT_PID__ -ErrorAction SilentlyContinue)) { exit }
    foreach ($e in @(Wait-Event -Timeout 3)) {
        $name = $e.SourceEventArgs.NewEvent.ProcessName
        if ($e.SourceIdentifier -eq 'kj_start') { [Console]::Out.WriteLine('start|' + $name) }
        elseif ($e.SourceIdentifier -eq 'kj_stop') { [Console]::Out.WriteLine('stop|' + $name) }
        Remove-Event -EventIdentifier $e.EventIdentifier
    }
}
"""


def parse_line(line):
    """`start|Game.exe` -> (True, "Game.exe"), `stop|Game.exe` -> (False, "Game.exe"); minden más sor -> None."""
    line = (line or "").rstrip("\r\n")
    kind, sep, name = line.partition("|")
    if not sep or not name or kind not in ("start", "stop"):
        return None
    return kind == "start", name


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


class ProcessEventSource:
    def __init__(self, on_event, on_lost, popen=subprocess.Popen, ready_timeout=8.0):
        self._on_event = on_event
        self._on_lost = on_lost
        self._popen = popen
        self._ready_timeout = ready_timeout
        self._proc = None
        self._thread = None
        self._ready = False
        self._ready_or_eof = threading.Event()
        self._stopped = False

    def start(self):
        """Elindítja a gyereket; igaz, ha a `ready` jelzés a határidőn belül megjött."""
        script = SCRIPT_TEMPLATE.replace("__PARENT_PID__", str(os.getpid()))
        try:
            self._proc = self._popen(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                creationflags=CREATE_NO_WINDOW)
        except OSError:
            self._proc = None
            return False
        self._thread = threading.Thread(target=self._read_loop, name="proc-events", daemon=True)
        self._thread.start()
        if self._ready_or_eof.wait(self._ready_timeout) and self._ready:
            return True
        self._kill()
        return False

    def stop(self):
        self._kill()

    def _kill(self):
        # A _stopped jelzőt a kill előtt kell beállítani: a pipe lezárása EOF-ot ad az olvasónak, és az nem "elvesztés".
        self._stopped = True
        proc = self._proc
        if proc is None:
            return
        try:
            proc.kill()
        except OSError:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            pass

    def _read_loop(self):
        try:
            for raw in self._proc.stdout:
                line = raw.lstrip("﻿")
                if not self._ready:
                    if line.rstrip("\r\n") == "ready":
                        self._ready = True
                        self._ready_or_eof.set()
                    continue
                parsed = parse_line(line)
                if parsed is not None and not self._stopped:
                    try:
                        self._on_event(*parsed)
                    except Exception:
                        # Egy hibás kezelő ne ölje meg az olvasót: a további események még kellenek.
                        pass
        except (OSError, ValueError):
            pass
        finally:
            self._ready_or_eof.set()
        if self._ready and not self._stopped:
            self._stopped = True
            self._on_lost()


def start_process_events(on_event, on_lost):
    """Elindítja az eseményforrást; `None`, ha nincs emelt jog vagy a gyerek nem lett kész (a hívó lekérdez)."""
    if not is_admin():
        return None
    src = ProcessEventSource(on_event, on_lost)
    return src if src.start() else None
