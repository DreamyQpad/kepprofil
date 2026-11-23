"""A térkép-overlay szülő oldali vezérlője: a Tarkov pályaeseményeiből és a gyorsgombokból vezérli a térképfolyamatot
(`kijelzo.py --map`), annak stdin-jére soronként írva. Minden a tk főszálon fut; a folyamat kimenetét egy olvasószál
sorba teszi, amit a `check()` dolgoz fel.

Módok: hidden (rejtett), glance (áttetsző, átkattintható), keys (billentyűzetes: a MAP_KEYS gombok csak ekkor foglaltak),
mouse (az ablak fókuszt kap, kattintható)."""
import queue
import subprocess
import sys
import threading
from pathlib import Path

from consts import CREATE_NO_WINDOW
from hw_common import MAP_KEYS
from tarkov_log import CHOICE_SLUGS, MAP_CHOICES, LogTail, map_slug, tarkov_install_dir

HERE = Path(__file__).resolve().parent
EXIT_WAIT_SECONDS = 3
ALPHA_STEP, ALPHA_MIN, ALPHA_MAX = 0.05, 0.2, 1.0
ASFW_ANY = 0xFFFFFFFF
RETRY_TICKS = 30                       # a telepítés keresése ennyi ütemenként ismétlődik (a nyilvántartás olvasása nem ingyen van)
MODE_CYCLE = {"glance": "keys", "keys": "mouse", "mouse": "glance"}
KEY_COMMANDS = {"mp|up": "pan up", "mp|down": "pan down", "mp|left": "pan left", "mp|right": "pan right",
                "mp|zin": "zoom in", "mp|zout": "zoom out"}


def map_argv(slug):
    """A térképfolyamat indítóparancsa: csomagolt futásnál a saját exe, forrásból a belépési pont."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--map", slug]
    return [sys.executable, str(HERE / "kijelzo.py"), "--map", slug]


def allow_foreground():
    """A térképfolyamat egeres módba váltása előtt kell: háttérfolyamat csak engedéllyel kaphat fókuszt (ASFW_ANY: a fejlesztői
    futásnál a Popen pid-je az indító stub, nem az értelmező)."""
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.AllowSetForegroundWindow(ASFW_ANY)


MAX_LEARNED = 50                                  # a kézzel megtanított pályanevek legnagyobb száma


class MapController:
    """set_hotkeys(mapping): a teljes gyorsgomb-térkép cseréje (mint az OverlayControllernél); spawn és allow_foreground
    kívülről cserélhető, így folyamat nélkül tesztelhető."""

    def __init__(self, eng, set_hotkeys, spawn=subprocess.Popen, argv_for=map_argv, allow_foreground=allow_foreground):
        self.eng, self.set_hotkeys, self.spawn = eng, set_hotkeys, spawn
        self.argv_for, self.allow_foreground = argv_for, allow_foreground
        self.mode, self.slug, self._preloaded = "hidden", None, False
        self._proc, self._running_slug, self._reader = None, None, None
        self._output, self._unknown, self._unrecognized = queue.Queue(), set(), []

    # ---- pályaesemények

    def on_event(self, event):
        if event.kind == "end":
            self._preloaded, self._unrecognized = False, []
            self.stop(wait=False)
            return
        slug = map_slug(event.name, self.eng.set.get("map_learned"))
        if event.kind == "preload":
            self._preloaded = slug is not None
        if slug is None:
            if event.name not in self._unknown:
                self._unknown.add(event.name)
                self.eng.say(f"Ismeretlen Tarkov-pálya: {event.name}")
            if event.name.lower() not in self._unrecognized:
                self._unrecognized.append(event.name.lower())     # ezt tanítja meg a kézi választás
            if event.kind != "raid" or not self._preloaded or self.slug is None:
                self.slug = None                  # új, ismeretlen pálya: a régi raid térképét nem mutatjuk helyette
                return
            slug = self.slug                      # a raid-sor neve ismeretlen, de közvetlenül előtte ismert pálya töltődött be
        self.slug = slug
        self._ensure(slug)
        if event.kind == "raid" and self.eng.set.get("map_auto", True):
            self._show()

    # ---- gyorsgombok

    def toggle(self):
        if self.mode != "hidden":
            self._send("hide")
            self._set_state("hidden")
        else:
            self._open()

    def cycle_mode(self):
        if self.mode == "hidden":
            self._open()
            return
        self._set_mode(MODE_CYCLE[self.mode])

    def key(self, action):
        if self.mode != "keys":
            return
        if action == "mp|exit":
            self._set_mode("glance")
        elif action in KEY_COMMANDS:
            self._send(KEY_COMMANDS[action])
        elif action in ("mp|aup", "mp|adown"):
            self._step_alpha(ALPHA_STEP if action == "mp|aup" else -ALPHA_STEP)

    def leave_keys(self):
        """A billentyűzetes módból pillantásba lép (pl. mielőtt más overlay lefoglalná ugyanezeket a gombokat)."""
        if self.mode == "keys":
            self._set_mode("glance")

    def set_alpha(self, alpha):
        self._send(f"alpha {alpha}")

    def _step_alpha(self, delta):
        """Játékból állított átlátszóság: a beállításba is mentődik, így a Program fül csúszkája és az újraindítás is ezt látja."""
        alpha = round(min(ALPHA_MAX, max(ALPHA_MIN, self.eng.set.get("map_alpha", 0.85) + delta)), 2)
        self.eng.set["map_alpha"] = alpha
        self.eng.save_settings()
        self.set_alpha(alpha)

    # ---- időzített ellenőrzés, kimenet, leállítás

    def check(self):
        while not self._output.empty():
            self.handle_output(self._output.get_nowait())
        if self._proc is not None and self._proc.poll() is not None:
            self._died()

    def handle_output(self, line):
        """A térképfolyamat egy kimeneti sora: `rect x y w h` az ablak helyét a beállításba menti, `hidden` jelzi, hogy a folyamat
        (Esc-re) maga elrejtette az ablakot, `selected <térkép>`: a pályaválasztóból kézzel választott pálya."""
        parts = line.split()
        if parts == ["hidden"]:
            if self.mode != "hidden":                   # a folyamat Esc-re maga rejtette el az ablakot
                self._set_state("hidden")
        elif len(parts) == 2 and parts[0] == "selected" and parts[1] in CHOICE_SLUGS:
            self.slug = self._running_slug = parts[1]   # a folyamat már betöltötte; a következő raid-esemény felülírja
            self.eng.set["map_last"] = parts[1]
            self._learn(parts[1])
            self.eng.save_settings()
        elif len(parts) == 5 and parts[0] == "rect":
            try:
                self.eng.set["map_rect"] = [int(value) for value in parts[1:]]
            except ValueError:
                return
            self.eng.save_settings()

    def _learn(self, slug):
        """A kézi választás megtanítja az ebben a raidben látott, ismeretlen pályaneveket (betöltés és raid neve), hogy
        legközelebb a program magától felismerje. Egy raidben egyszer tanul; a megtanult nevek száma korlátos."""
        names, self._unrecognized = self._unrecognized, []
        if not names:
            return
        learned = self.eng.set.setdefault("map_learned", {})
        for name in names:
            if name not in learned and len(learned) < MAX_LEARNED:
                learned[name] = slug
        self.eng.say(f"Megtanult pálya: {', '.join(names)} = {slug}")

    def stop(self, wait=True):
        """Leállítja a folyamatot: az stdin lezárása (EOF) a kilépési jel; ha nem áll le, kilövi."""
        proc, self._proc = self._proc, None
        self._running_slug = None
        if proc is not None:
            if wait:                                    # egér módban a hely csak az elrejtéskor mentődik (`rect` sor)
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
        self._set_state("hidden")

    # ---- belső

    def _open(self):
        """Megjeleníti a térképet. Ha a pálya nem ismert, az utoljára választott (vagy az első) térképpel nyitja meg egér
        módban, hogy a térkép tetején lévő választóval kézzel lehessen pályát választani."""
        if self.slug is not None:
            if self._ensure(self.slug):
                self._show()
            return
        slug = self.eng.set.get("map_last")
        if slug not in CHOICE_SLUGS:
            slug = MAP_CHOICES[0][0]
        if self._ensure(slug):
            self._show()
            self._set_mode("mouse")
            self.eng.toast("Nincs ismert pálya: válassz a térkép tetején")

    def _show(self):
        if self._send("show"):
            self._set_state("glance")

    def _set_mode(self, mode):
        if mode == "mouse":
            self.allow_foreground()
        if self._send(f"mode {mode}"):
            self._set_state(mode)

    def _set_state(self, mode):
        self.mode = mode
        mapping = self.eng.hotkey_map()
        self.set_hotkeys({**mapping, **MAP_KEYS} if mode == "keys" else mapping)

    def _alive(self):
        return self._proc is not None and self._proc.poll() is None

    def _ensure(self, slug):
        """Fut a folyamat az adott térképpel (rejtve indítja vagy átváltja); False, ha nem indítható."""
        if self._alive():
            if self._running_slug != slug and self._send(f"map {slug}"):
                self._running_slug = slug
            return self._alive()
        flags = {"creationflags": CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        try:
            proc = self.spawn(self.argv_for(slug), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, text=True, encoding="utf-8", **flags)
        except OSError as error:
            self.eng.say(f"A térkép nem indítható: {error.__class__.__name__}")
            return False
        self._proc, self._running_slug = proc, slug
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
            self._died()
            return False
        return True

    def _died(self):
        self._proc, self._running_slug = None, None
        self.eng.say("A térkép folyamata leállt")
        self._set_state("hidden")


def _default_make_tail(setting):
    directory = tarkov_install_dir(setting)
    return LogTail(directory) if directory else None


class MapFeed:
    """A logfigyelőt köti a vezérlőhöz; másodpercenként hívandó tick(). A figyelőt lustán hozza létre, mert a játék később is
    települhet; csatlakozáskor a már folyamatban lévő raidet is átadja, hogy a térkép a Képprofil közbeni indításakor is megjelenjen."""

    def __init__(self, controller, eng, make_tail=_default_make_tail):
        self.controller, self.eng, self._make_tail = controller, eng, make_tail
        self._tail, self._attached, self._wait = None, False, 0

    def tick(self):
        if self._tail is None:
            if self._wait <= 0:
                self._tail = self._make_tail(self.eng.set.get("tarkov_path", ""))
                self._wait = RETRY_TICKS
            self._wait -= 1
        if self._tail is not None:
            events = self._tail.poll()
            if not self._attached:
                self._attached = True
                state = self._tail.state()
                if state:
                    self.controller.on_event(state)
            for event in events:
                self.controller.on_event(event)
        self.controller.check()
