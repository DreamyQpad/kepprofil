"""A böngésző szülő oldali vezérlője: a menüből indított, külön folyamatban futó, minimális böngészőablak (`kijelzo.py --web`).
Csak akkor fut, amíg használod (a WebView2 folyamat memóriaigényes); a bezáráskor a folyamat kilép. A parancsok soronként
mennek a folyamat stdin-jére, a kimenetét egy olvasószál sorba teszi, amit a `check()` dolgoz fel."""
import json
import queue
import subprocess
import sys
import threading

import bookmarks
from consts import CREATE_NO_WINDOW
from map_overlay import EXIT_WAIT_SECONDS, HERE, allow_foreground


def browser_argv():
    """A böngészőfolyamat indítóparancsa: csomagolt futásnál a saját exe, forrásból a belépési pont."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--web"]
    return [sys.executable, str(HERE / "kijelzo.py"), "--web"]


class BrowserController:
    """spawn és allow_foreground kívülről cserélhető, így folyamat nélkül tesztelhető. `game()`: az aktív játék azonosítója
    (üres: nincs aktív játék); a könyvjelzősáv játékonként külön van, és a megnyitáskor aktív játéké marad a böngésző
    bezárásáig."""

    def __init__(self, eng, spawn=subprocess.Popen, argv_for=browser_argv, allow_foreground=allow_foreground,
                 game=lambda: bookmarks.GENERAL):
        self.eng, self.spawn, self.argv_for, self.allow_foreground, self.game = eng, spawn, argv_for, allow_foreground, game
        self._proc, self._reader, self._output = None, None, queue.Queue()
        self.is_open, self._game = False, bookmarks.GENERAL

    def toggle(self):
        if self.is_open:
            self.close()
        else:
            self.open()

    def open(self):
        if self.is_open and self._alive():
            return
        if not self._alive() and not self._start():
            return
        self.allow_foreground()                     # a háttérfolyamat csak engedéllyel kaphat fókuszt
        self._game = self.game() or bookmarks.GENERAL
        self._send_bookmarks()
        if self._send("show"):
            self.is_open = True

    def close(self, wait=True):
        """Bezárja a böngészőt: elrejtés (a játék visszakapja a fókuszt), majd az stdin lezárása; ha nem áll le, kilövi."""
        proc, self._proc = self._proc, None
        self.is_open = False
        if proc is None:
            return
        if wait:
            try:
                proc.stdin.write("hide\n")
                proc.stdin.flush()
            except (OSError, ValueError):
                pass
        try:
            proc.stdin.close()
        except (OSError, ValueError):
            pass
        if wait:
            try:
                proc.wait(timeout=EXIT_WAIT_SECONDS)
            except subprocess.TimeoutExpired:
                proc.kill()

    def stop(self):
        self.close(wait=True)

    def check(self):
        while not self._output.empty():
            self.handle_output(self._output.get_nowait())
        if self._proc is not None and self._proc.poll() is not None:
            self._proc, self.is_open = None, False
            self.eng.say("A böngésző folyamata leállt")

    def handle_output(self, line):
        """A folyamat egy kimeneti sora: `closed` (Bezár gomb) lezárja; `rect x y w h` az ablak helyét menti."""
        parts = line.split()
        if parts == ["closed"]:
            self.close(wait=False)
        elif parts[:2] == ["bookmark", "add"] and self._alive():
            self._add_bookmark(line.split(None, 2)[2] if len(parts) > 2 else "")
        elif len(parts) == 3 and parts[:2] == ["bookmark", "remove"] and self._alive():
            self._remove_bookmark(parts[2])
        elif len(parts) == 5 and parts[0] == "rect":
            try:
                self.eng.set["web_rect"] = [int(value) for value in parts[1:]]
            except ValueError:
                return
            self.eng.save_settings()

    def _store(self):
        return self.eng.set.setdefault("bookmarks", {})

    def _send_bookmarks(self):
        self._send("bookmarks " + json.dumps(bookmarks.payload(self._store(), self._game)))

    def _add_bookmark(self, text):
        try:
            entry = json.loads(text)
        except ValueError:
            return
        if not isinstance(entry, dict):
            return
        if not bookmarks.add(self._store(), self._game, entry.get("title"), entry.get("url")):
            self.eng.toast("Nem menthető: már szerepel, tele a sáv vagy érvénytelen oldal")
            return
        self.eng.save_settings()
        self._send_bookmarks()

    def _remove_bookmark(self, text):
        try:
            index = int(text)
        except ValueError:
            return
        if bookmarks.remove(self._store(), self._game, index):
            self.eng.save_settings()
            self._send_bookmarks()

    def _alive(self):
        return self._proc is not None and self._proc.poll() is None

    def _start(self):
        flags = {"creationflags": CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        try:
            proc = self.spawn(self.argv_for(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, text=True, encoding="utf-8", **flags)
        except OSError as error:
            self.eng.say(f"A böngésző nem indítható: {error.__class__.__name__}")
            return False
        self._proc = proc
        self._reader = threading.Thread(target=self._read, args=(proc,), daemon=True)
        self._reader.start()
        return True

    def _read(self, proc):
        try:
            for line in proc.stdout:
                self._output.put(line.strip())
        except (OSError, ValueError):
            pass

    def _send(self, text):
        if not self._alive():
            return False
        try:
            self._proc.stdin.write(text + "\n")
            self._proc.stdin.flush()
        except (OSError, ValueError):
            self._proc, self.is_open = None, False
            self.eng.say("A böngésző folyamata leállt")
            return False
        return True
