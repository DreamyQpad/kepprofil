"""Escape from Tarkov: a játék saját logjából kiolvassa, melyik pályán játszik a felhasználó.

Csak a pálya neve és az esemény fajtája jön ki a sorokból: a log profilazonosítót és IP-címet is tartalmaz, ezek
sosem kerülnek eseménybe, naplóba vagy kivételüzenetbe. A fájlt a játék közben is írja, ezért csak olvasunk, megosztva."""
import re
import sys
from pathlib import Path
from typing import NamedTuple

LOG_FILE_PATTERN = "*application_000.log"
TARKOV_DISPLAY_NAME = "Escape from Tarkov"


class MapEvent(NamedTuple):
    kind: str          # "preload" (a pálya betöltése indul) | "raid" (a raid indul) | "end" (a raid véget ért)
    name: str          # a játék-belső pályanév; "end" esetén üres


# Játék-belső név (kisbetűs) -> tarkov.dev térkép-azonosító. A betöltési sorban és a raid-sorokban a név eltérhet.
# A gép logjából igazolt nevek: customs (betöltés), bigmap (helyi raid; Customs), woods, shoreline, sandbox_high (Ground Zero), city és
# tarkovstreets (Streets). A többi a játék ismert belső neve, logból még nem láttuk; ismeretlen raid-névnél a vezérlő az
# előtte betöltött térképet használja.
MAP_SLUGS = {
    "customs": "customs",
    "bigmap": "customs",
    "woods": "woods",
    "city": "streets-of-tarkov",
    "tarkovstreets": "streets-of-tarkov",
    "sandbox_high": "ground-zero",
    "sandbox": "ground-zero",
    "factory4_day": "factory",
    "factory4_night": "factory",
    "shoreline": "shoreline",
    "interchange": "interchange",
    "lighthouse": "lighthouse",
    "rezervbase": "reserve",
    "laboratory": "the-lab",
}

_PRELOAD = re.compile(r"\|application\|scene preset path:maps/(\w+)_preset\.bundle")
_RAID = re.compile(r"\|application\|TRACE-NetworkGameCreate .*?Location: (\w+),")
# Helyi (offline) raidnél nincs `TRACE-NetworkGameCreate` sor, a raid nevét ez jelzi (a `RaidId` nem kerül az eseménybe): `[Transit] ..., Locations:<név> ->`
_TRANSIT = re.compile(r"\|application\|\[Transit\] .*?Locations:(\w+)")
_END = re.compile(r"\|application\|BEClient exit\s*$")


def parse_line(line):
    """Egy naplósor -> MapEvent, vagy None, ha a sor nem pályaesemény."""
    match = _PRELOAD.search(line)
    if match:
        return MapEvent("preload", match.group(1))
    match = _RAID.search(line) or _TRANSIT.search(line)
    if match:
        return MapEvent("raid", match.group(1))
    if _END.search(line):
        return MapEvent("end", "")
    return None


def map_slug(name):
    """Játék-belső pályanév -> tarkov.dev azonosító; ismeretlen névre None."""
    return MAP_SLUGS.get(name.lower())


def tarkov_install_dir(setting=""):
    """A játék telepítési mappája: a beállított útvonal, különben a Windows-eltávolítási nyilvántartás; egyébként None."""
    if setting and Path(setting).is_dir():
        return Path(setting)
    if sys.platform != "win32":
        return None
    import winreg                                       # csak Windowson létezik
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    views = ((winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY), (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
             (winreg.HKEY_CURRENT_USER, 0))
    for hive, view in views:
        try:
            with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ | view) as uninstall:
                for index in range(winreg.QueryInfoKey(uninstall)[0]):
                    try:
                        with winreg.OpenKey(uninstall, winreg.EnumKey(uninstall, index)) as entry:
                            if winreg.QueryValueEx(entry, "DisplayName")[0] == TARKOV_DISPLAY_NAME:
                                location = winreg.QueryValueEx(entry, "InstallLocation")[0]
                                if location and Path(location).is_dir():
                                    return Path(location)
                    except OSError:
                        continue
        except OSError:
            continue
    return None


class LogTail:
    """A legfrissebb Tarkov-log követése. Az első poll() csak a már meglévő tartalomból számolja a state()-et (eseményt nem ad),
    utána csak az új, teljes sorok eseményeit adja. Új log-mappa (a játék újraindult) vagy lerövidült fájl: újrakezdés."""

    def __init__(self, install_dir):
        self.install_dir = Path(install_dir)
        self._file = None
        self._offset = 0
        self._pending = b""
        self._state = None
        self._attached = False

    def state(self):
        """Az utolsó "preload" vagy "raid" esemény, ha utána nem jött "end"; különben None."""
        return self._state

    def poll(self):
        path = self._latest_file()
        if path is None:
            return []
        if path != self._file:
            self._file, self._offset, self._pending, self._state = path, 0, b"", None      # új játékindítás: nincs folyamatban lévő raid
        events = self._read_new()
        first_attach, self._attached = not self._attached, True
        return [] if first_attach else events

    def _latest_file(self):
        logs = self.install_dir / "Logs"
        try:
            folders = sorted(folder for folder in logs.iterdir() if folder.is_dir() and folder.name.startswith("log_"))
            for folder in reversed(folders):
                files = sorted(folder.glob(LOG_FILE_PATTERN))
                if files:
                    return files[0]
        except OSError:
            pass
        return None

    def _read_new(self):
        try:
            with open(self._file, "rb") as handle:
                handle.seek(0, 2)
                if handle.tell() < self._offset:                # a játék újraírta a fájlt
                    self._offset, self._pending = 0, b""
                    self._state = None
                handle.seek(self._offset)
                data = handle.read()
        except OSError:
            return []
        self._offset += len(data)
        data = self._pending + data
        cut = data.rfind(b"\n") + 1
        data, self._pending = data[:cut], data[cut:]
        events = []
        for line in data.decode("utf-8", "replace").splitlines():
            event = parse_line(line)
            if event:
                events.append(event)
                if event.kind in ("preload", "raid"):
                    self._state = event
                elif event.kind == "end":
                    self._state = None
        return events
