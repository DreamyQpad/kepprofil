"""A térképfolyamat: egy pywebview-ablak a tarkov.dev térképével, soronkénti szöveges parancsokkal vezérelve (stdin).

A Képprofil külön folyamatként indítja (`kijelzo.py --map <azonosító>`): a pywebview-nak saját főszál kell, a tk-nak is.
Az ablak Win32-stílusát ez a folyamat váltja, mert övé a HWND. Ha az stdin lezárul (a Képprofil kilépett vagy összeomlott),
a folyamat is kilép, így nem marad árva ablak.

Parancsok: map <azonosító> | show | hide | mode glance|keys|mouse | pan up|down|left|right | zoom in|out |
alpha <0,2–1,0> | rect <x> <y> <szélesség> <magasság> | bookmarks <json> (csak a böngészőben) | quit.
Kimenet (stdout, soronként): `loaded`; egeres módból kilépéskor `rect <x> <y> <szélesség> <magasság>` (logikai pixel);
`hidden` (a térkép Esc-re maga elrejtette az ablakot); `selected <térkép>` (a pályaválasztóból kézzel választott pálya); `closed` (a böngésző Bezár gombja); `bookmark add <json>` és
`bookmark remove <sorszám>` (a böngésző könyvjelzősávja)."""
import json
import os
import re
import secrets
import sys
import threading
import time

from tarkov_log import CHOICE_SLUGS, MAP_CHOICES
from web_bar import add_bookmark_line, parse_bookmarks_command, remove_bookmark_line, web_bar_script  # noqa: F401

TITLE = "Képprofil térkép"
WEB_TITLE = "Képprofil böngésző"
DEFAULT_RECT = (120, 80, 960, 640)
EXIT_TIMEOUT_SECONDS = 3
WINDOW_WAIT_SECONDS = 15                      # ennyit vár a folyamat az ablak létrejöttére, mielőtt parancsot dolgozna fel
MODES = ("glance", "keys", "mouse")
PAN_KEYS = {"left": ("ArrowLeft", 37), "up": ("ArrowUp", 38), "right": ("ArrowRight", 39), "down": ("ArrowDown", 40)}
_SLUG = re.compile(r"[a-z0-9-]+")


def web_url():
    """A böngésző kezdőoldala (a keresőmotor)."""
    return "https://www.google.com"


def tarkov_url(slug):
    return f"https://tarkov.dev/map/{slug}"


def parse_command(line):
    """Egy parancssor -> tuple, vagy None, ha a sor nem érvényes parancs."""
    parts = line.split()
    if not parts:
        return None
    command, args = parts[0], parts[1:]
    if command == "bookmarks":
        return parse_bookmarks_command(line.split(None, 1)[1]) if len(parts) > 1 else None
    try:
        if command == "map" and len(args) == 1 and _SLUG.fullmatch(args[0]):
            return ("map", args[0])
        if command in ("show", "hide", "quit") and not args:
            return (command,)
        if command == "mode" and len(args) == 1 and args[0] in MODES:
            return ("mode", args[0])
        if command == "pan" and len(args) == 1 and args[0] in PAN_KEYS:
            return ("pan", args[0])
        if command == "zoom" and len(args) == 1 and args[0] in ("in", "out"):
            return ("zoom", args[0])
        if command == "alpha" and len(args) == 1 and 0.2 <= float(args[0]) <= 1.0:
            return ("alpha", float(args[0]))
        if command == "rect" and len(args) == 4:
            return ("rect", *(int(value) for value in args))
    except ValueError:
        return None
    return None


def read_commands(stream, handle):
    """A parancsokat a kezelőnek adja; `quit`-nál vagy a folyam végén (EOF) visszatér. A kezelő hibája (például egy oldal, amely
    nem válaszol a szkriptre) csak az adott parancsot dobja el, a hurok és vele a folyamat megy tovább."""
    for line in stream:
        command = parse_command(line)
        if command is None:
            continue
        if command == ("quit",):
            return
        try:
            handle(command)
        except Exception as error:
            print(f"parancs hiba: {command[0]}: {error.__class__.__name__}", file=sys.stderr, flush=True)


def wait_until(predicate, timeout=WINDOW_WAIT_SECONDS, interval=0.05, sleep=time.sleep, clock=time.monotonic):
    """Addig vár, amíg a `predicate` igaz; az időkorlát után False-szal visszatér."""
    deadline = clock() + timeout
    while not predicate():
        if clock() >= deadline:
            return False
        sleep(interval)
    return True


def serve_commands(stream, handle, window_ready, wait=wait_until):
    """A parancshurok az ablak létrejötte után indul: a szülő az indítás után azonnal küldhet `show`-t, és az ablak nélkül
    hatástalan lenne. Ha az ablak az időkorlátig sem jön létre, a parancsokat így is feldolgozza."""
    wait(window_ready)
    read_commands(stream, handle)


def to_logical_rect(rect, dpi):
    """A fizikai pixelben mért (x, y, szélesség, magasság) logikai pixelre váltva: az ablakkeretrendszer a megadott helyet és
    méretet logikai pixelnek veszi, a `GetWindowRect` viszont fizikait ad; 100%-tól eltérő skálázásnál ez nélkül az ablak
    minden mentés-betöltés körben nőne és elvándorolna."""
    if not dpi or dpi == 96:
        return tuple(rect)
    return tuple(round(value * 96 / dpi) for value in rect)


def new_token():
    """A böngészőfolyamat titka (folyamatonként új): a sáv ezzel hívja a `js_api`-t."""
    return secrets.token_hex(16)


def pan_script(direction):
    """A Leaflet-tartály billentyűkezelője mozgatja a térképet: az oldalon belüli fókusz, nem operációs rendszer-szintű."""
    key, code = PAN_KEYS[direction]
    return ("(function(){var c=document.querySelector('.leaflet-container');if(!c){return false;}c.focus();"
            f"c.dispatchEvent(new KeyboardEvent('keydown',{{key:'{key}',keyCode:{code},which:{code},bubbles:true}}));return true;}})()")


def zoom_script(direction):
    return (f"(function(){{var b=document.querySelector('.leaflet-control-zoom-{direction}');"
            "if(b){b.click();return true;}return false;})()")


def nav_buttons_script(visible):
    """A „← Vissza”, „Előre →” gomb és a pályaválasztó a térkép oldalában (bal felső sarok): az előző/következő oldalra lép,
    illetve kézzel pályát vált, ha a program nem tudja, melyiken vagy. Újrafuttatva a meglévő sort frissíti (a választó az oldal
    címéből veszi az aktuális pályát), így a módváltás és az oldalbetöltés is ugyanezt hívja."""
    display = "flex" if visible else "none"
    choices = json.dumps([[slug, name] for slug, name in MAP_CHOICES])
    return ("(function(){var d=document.getElementById('kp-nav');if(!d){d=document.createElement('div');d.id='kp-nav';"
            "d.style.cssText='position:fixed;top:8px;left:8px;z-index:2147483647;gap:6px';"
            "[['\u2190 Vissza',-1],['El\u0151re \u2192',1]].forEach(function(x){var b=document.createElement('button');"
            "b.textContent=x[0];b.onclick=function(){history.go(x[1]);};"
            "b.style.cssText='padding:6px 12px;font:14px sans-serif;background:#222;color:#fff;border:1px solid #888;"
            "border-radius:4px;cursor:pointer';d.appendChild(b);});"
            "var s=document.createElement('select');s.id='kp-map-select';s.title='P\u00e1lya kiv\u00e1laszt\u00e1sa';"
            "s.style.cssText='padding:6px 8px;font:14px sans-serif;background:#222;color:#fff;border:1px solid #888;"
            "border-radius:4px;cursor:pointer';"
            f"{choices}.forEach(function(c){{var o=document.createElement('option');o.value=c[0];o.textContent=c[1];"
            "s.appendChild(o);});"
            "s.onchange=function(){if(window.pywebview&&window.pywebview.api){window.pywebview.api.select_map(s.value)"
            ".then(function(){location.assign('https://tarkov.dev/map/'+s.value);});}};"
            "d.appendChild(s);"
            "(document.body||document.documentElement).appendChild(d);}"
            "var m=location.pathname.match(/\\/map\\/([a-z0-9-]+)/);var sel=document.getElementById('kp-map-select');"
            "if(m&&sel){sel.value=m[1];}"
            f"d.style.display='{display}';}})()")


def escape_script():
    """A térkép oldalába kötött Esc-figyelő: egér módban (ekkor van az ablaknál a fókusz) az Esc elrejti a térképet.
    Betöltésenként egyszer kötődik be."""
    return ("(function(){if(window.__kpEsc){return;}window.__kpEsc=true;"
            "window.addEventListener('keydown',function(e){if(e.key==='Escape'&&window.pywebview&&window.pywebview.api)"
            "{window.pywebview.api.escape();}},true);})()")


class MapApi:
    """A térkép oldalából hívható felület (pywebview `js_api`): az Esc-figyelő és a pályaválasztó ezen át szól a folyamatnak.
    A választott pálya csak az ismert térképek azonosítója lehet."""

    def __init__(self, on_escape, on_select=lambda slug: None):
        self._on_escape, self._on_select = on_escape, on_select

    def escape(self):
        self._on_escape()

    def select_map(self, slug):
        if isinstance(slug, str) and slug in CHOICE_SLUGS:
            self._on_select(slug)


class WebApi:
    """A böngészőoldalból hívható felület (pywebview `js_api`): a sáv gombjai ezen át szólnak a folyamatnak. A `js_api` minden
    betöltött weboldalnak elérhető, ezért minden hívás a folyamat titkát (`token`) kéri, és a mentendő oldal címét és URL-jét a
    folyamat maga kérdezi le (`current_page()` -> (url, cím)), nem az oldaltól kapja. `on_close()` a Bezár gombra,
    `emit_line(sor)` a könyvjelző-műveletek kimeneti soraihoz."""

    def __init__(self, on_close, emit_line, current_page, token):
        self._on_close, self._emit_line, self._current_page, self._token = on_close, emit_line, current_page, token

    def _allowed(self, token):
        return isinstance(token, str) and bool(self._token) and token == self._token

    def close(self, token=None):
        if self._allowed(token):
            self._on_close()

    def add_bookmark(self, token=None):
        if not self._allowed(token):
            return
        url, title = self._current_page()
        if isinstance(url, str) and isinstance(title, str):
            self._emit_line(add_bookmark_line(title, url))

    def remove_bookmark(self, index, token=None):
        if self._allowed(token) and isinstance(index, int) and not isinstance(index, bool):
            self._emit_line(remove_bookmark_line(index))


class WindowModes:
    """A három ablakmód és az átmenetek: egeres módba lépéskor megjegyzi az előző előtérablakot (a játékot), kilépéskor
    visszaadja neki a fókuszt, és jelenti az ablak helyét. A Win32-réteget (`win32`) kívülről kapja, így hamissal tesztelhető."""

    def __init__(self, win32, alpha):
        self.win32, self.alpha, self.mode, self._previous = win32, alpha, "glance", 0

    def set_mode(self, mode):
        """Módváltás; egeres módból kilépve a `rect x y w h` sort adja vissza, egyébként None."""
        entering = mode == "mouse" and self.mode != "mouse"
        leaving = self.mode == "mouse" and mode != "mouse"
        line = None
        if entering:
            foreground = self.win32.foreground()
            self._previous = 0 if foreground == self.win32.own() else foreground
        if leaving:
            left, top, width, height = to_logical_rect(self.win32.rect(), self.win32.dpi())
            line = f"rect {left} {top} {width} {height}"
        self.mode = mode
        self.win32.apply(mode, self.alpha)
        if entering:
            self.win32.set_foreground(self.win32.own())
        if leaving and self._previous:
            self.win32.set_foreground(self._previous)
            self._previous = 0
        return line

    def set_alpha(self, alpha):
        self.alpha = alpha
        self.refresh()

    def refresh(self):
        self.win32.apply(self.mode, self.alpha)

    def show(self):
        """Megjelenítés fókusz nélkül: a nem aktiválódó stílus előbb áll be, és az ablakkezelő aktiválás nélkül mutatja."""
        self.win32.apply(self.mode, self.alpha)
        self.win32.show()

    def hide(self):
        """Elrejtés; egeres módból az előző előtérablakot visszaadja, és a `rect` sort adja vissza (egyébként None)."""
        line = self.set_mode("glance") if self.mode == "mouse" else None
        self.win32.hide()
        return line


def emit(text):
    print(text, flush=True)


def run(slug, alpha, rect):
    """A térkép folyamata: az ablak a tarkov.dev oldalával; a parancsok és módok lent, `_run_window`-ban."""
    _run_window(tarkov_url(slug), TITLE, "webview", alpha, rect, web=False)


def run_web(rect):
    """A böngésző folyamata: kezdőoldal a keresőmotor, megjelenítéskor egeres módba lép (gépelni kell), Bezár gombbal."""
    _run_window(web_url(), WEB_TITLE, "webview-browser", 1.0, rect, web=True)


def _run_window(url, title, storage_name, alpha, rect, web):
    """Az ablak létrehozása és a parancshurok; a pywebview főszálon fut, a parancsokat háttérszál olvassa. Külön
    `storage_name` profilmappa kell a két folyamatnak, hogy a sütik ne keveredjenek és ne ütközzenek."""
    import webview
    from consts import DATA_DIR
    from hw_windows import MapWindowApi
    left, top, width, height = rect or DEFAULT_RECT
    modes = WindowModes(MapWindowApi(title), alpha)

    def close_from_page():
        line = modes.hide()
        if line:
            emit(line)
        emit("closed")

    def escape_from_page():
        """Esc a térképen: csak egér módban (fókusszal) rejt; a játék visszakapja a fókuszt, a szülő a `hidden` sort kapja."""
        if modes.mode != "mouse":
            return
        line = modes.hide()
        refresh_nav_buttons()
        if line:
            emit(line)
        emit("hidden")

    def select_from_page(slug):
        """A pályaválasztó: jelzi a szülőnek, hogy innentől ez az aktuális pálya. A betöltést az oldal végzi a hívás
        visszatérése után (ha itt töltenénk be, az oldal újratöltődne, mielőtt a hívás visszatérne)."""
        current["url"] = tarkov_url(slug)
        emit(f"selected {slug}")

    def current_page():
        return window.get_current_url(), window.evaluate_js("document.title")

    token = new_token() if web else ""
    # Az új ablakot nyitó linkek ugyanabban az ablakban töltődnek be: az alapértelmezett (rendszerböngésző) elvenné a játék fókuszát.
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = False
    window = webview.create_window(title, url, x=left, y=top, width=width, height=height, frameless=True, easy_drag=False, on_top=True,
                                   hidden=True,
                                   js_api=WebApi(close_from_page, emit, current_page, token) if web else MapApi(escape_from_page, select_from_page))
    current = {"url": url, "bookmarks": {"game": "", "items": []}}

    def handle(command):
        name = command[0]
        if name == "map" and not web and tarkov_url(command[1]) != current["url"]:
            current["url"] = tarkov_url(command[1])
            window.load_url(current["url"])
        elif name == "show":
            modes.show()
            if web:
                line = modes.set_mode("mouse")
                refresh_nav_buttons()
                if line:
                    emit(line)
        elif name == "hide":
            line = modes.hide()
            refresh_nav_buttons()
            if line:
                emit(line)
        elif name == "mode":
            line = modes.set_mode(command[1])
            refresh_nav_buttons()
            if line:
                emit(line)
        elif name == "pan":
            window.evaluate_js(pan_script(command[1]))
        elif name == "zoom":
            window.evaluate_js(zoom_script(command[1]))
        elif name == "bookmarks" and web:
            current["bookmarks"] = command[1]
            refresh_nav_buttons()
        elif name == "alpha":
            modes.set_alpha(command[1])
        elif name == "rect":
            window.move(command[1], command[2])
            window.resize(command[3], command[4])

    def serve():
        try:
            if sys.stdin is not None:
                serve_commands(sys.stdin, handle, lambda: bool(modes.win32.own()))
        finally:
            threading.Timer(EXIT_TIMEOUT_SECONDS, os._exit, args=(0,)).start()      # ha a tiszta leállás elakad
            window.destroy()

    def refresh_nav_buttons():
        if web:
            window.evaluate_js(web_bar_script(modes.mode == "mouse", current["bookmarks"], token))
        else:
            window.evaluate_js(nav_buttons_script(modes.mode == "mouse"))

    def on_loaded():
        refresh_nav_buttons()
        if not web:
            window.evaluate_js(escape_script())
        emit("loaded")

    window.events.loaded += on_loaded
    # private_mode=False kell, különben a pywebview figyelmen kívül hagyja a storage_path-t, és a süti-beállítás nem marad meg
    webview.start(lambda: threading.Thread(target=serve, daemon=True).start(), private_mode=False,
                  storage_path=str(DATA_DIR / storage_name))
