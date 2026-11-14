"""A tálcaikon: a rajza, az indítása és a menüje (pystray). A pystray-t csak a `Tray` és a `size_xorg_icon_window` tölti be,
így az ikon rajzolása (`make_icon`) tálca nélkül is használható."""
import sys
import threading

from consts import APP_NAME
from system import SHORTCUT_HELP

TRAY_ICON_PX = 32                                 # Linux, xorg-backend (tartalék): a tálcaikon-ablak kezdőmérete

ICON_LIGHT = (229, 231, 235, 255)
ICON_DARK = (30, 41, 59, 255)
ICON_BRIGHT = (245, 197, 66, 255)
ICON_ACTIVE_MARK = (249, 115, 22, 255)
WHITE = (255, 255, 255, 255)


def make_icon(active=False, size=64):
    """Tálcaikon: kijelző, fél-fényes/fél-sötét képernyővel (szögletes), bekapcsolt állapotban narancs jelzéssel."""
    from PIL import Image, ImageDraw
    scale = size / 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def box(left, top, right, bottom):
        return [round(left * scale), round(top * scale), round(right * scale) - 1, round(bottom * scale) - 1]

    draw.rectangle(box(4, 8, 60, 46), fill=ICON_LIGHT)                 # keret
    draw.rectangle(box(8, 12, 56, 42), fill=ICON_DARK)                 # sötét képernyő
    draw.rectangle(box(8, 12, 32, 42), fill=ICON_BRIGHT)               # a fényes fél
    draw.rectangle(box(26, 46, 38, 54), fill=ICON_LIGHT)               # talp nyaka
    draw.rectangle(box(16, 54, 48, 59), fill=ICON_LIGHT)               # talp
    if active:
        draw.rectangle(box(44, 2, 62, 20), fill=ICON_ACTIVE_MARK, outline=WHITE, width=max(1, round(2 * scale)))
    return image


def start_tray(icon):
    """Elindítja a tálcaikont (pystray `run_detached`). A GTK-s backendek (appindicator, gtk) a menü- és ikonműveleteket
    GLib idle-ben futtatják, de a `run_detached` nem indít GLib-főciklust, a mi főciklusunk pedig a Tk: főciklus nélkül az
    ikon sosem jön létre. Ezért a GLib-főciklus külön szálon fut."""
    if icon.__class__.__module__.rsplit(".", 1)[-1] in ("_appindicator", "_gtk"):
        from gi.repository import GLib
        threading.Thread(target=GLib.MainLoop().run, daemon=True, name="glib-tray").start()
    icon.run_detached()


def size_xorg_icon_window():
    """Linux, pystray xorg backend: az ikon ablakát 1x1-esre hozza létre, és egy valódi tálcakezelő méretezi át. Plasma
    Waylanden az xembedsniproxy nem méretez, ezért az ikon 1x1 pixeles (egyszínű négyzet) maradna: az ablakot itt állítjuk be."""
    import pystray
    if not (sys.platform.startswith("linux") and pystray.Icon.__module__.endswith("_xorg")):
        return
    create_window = pystray.Icon._create_window

    def create_sized_window(self):
        window = create_window(self)
        window.configure(width=TRAY_ICON_PX, height=TRAY_ICON_PX)
        self._display.flush()
        return window

    pystray.Icon._create_window = create_sized_window


class Tray:
    """A tálcaikon és a menüje. A menü a motor mostani állapotát mutatja; a kattintások üzenetként (`post`) mennek a
    főszál üzenetsorába."""

    def __init__(self, eng, post):
        import pystray
        self.eng = eng
        self.post = post
        self.icon = pystray.Icon("kepprofil", make_icon(False), APP_NAME, pystray.Menu(self._menu_items))

    def start(self):
        start_tray(self.icon)

    def stop(self):
        try:
            self.icon.stop()
        except Exception:
            pass

    def refresh(self):
        """Az ikon (bekapcsolt jelzés) és a menü újrarajzolása."""
        try:
            self.icon.icon = make_icon(bool(self.eng.active) or bool(self.eng.night_mons))
            self.icon.update_menu()
        except Exception:
            pass

    def _menu_items(self):
        import pystray
        items = [pystray.MenuItem("Panel megnyitása", lambda icon, item: self.post(("panel",)), default=True),
                 pystray.Menu.SEPARATOR]
        for monitor in self.eng.mons():
            items.append(pystray.MenuItem(monitor["name"], lambda icon, item: None, enabled=False))
            items += self._preset_items(monitor)
            items.append(pystray.MenuItem("Éjszakai mód", self._night_toggler(monitor["id"]),
                                          checked=self._night_checker(monitor["id"])))
        items += [pystray.Menu.SEPARATOR,
                  pystray.MenuItem("Éjszakai mód (minden monitor)", lambda icon, item: self.post(("night",)),
                                   checked=lambda item: bool(self.eng.night_mons)),
                  pystray.MenuItem("Semleges kép (minden kikapcsol)", lambda icon, item: self.post(("neutral",)))]
        if SHORTCUT_HELP:
            items.append(pystray.MenuItem("Gyorsbillentyűk (KDE)…", lambda icon, item: self.post(("shortcuts",))))
        items += [pystray.Menu.SEPARATOR,
                  pystray.MenuItem("Kilépés", lambda icon, item: self.post(("quit",)))]
        return items

    def _preset_items(self, monitor):
        import pystray
        items = []
        for name, preset in monitor["presets"].items():
            hotkey_suffix = f"   ({preset['hotkey']})" if preset.get("hotkey") else ""
            items.append(pystray.MenuItem(name + hotkey_suffix, self._preset_toggler(monitor["id"], name),
                                          checked=self._preset_checker(monitor["id"], name)))
        return items

    def _preset_toggler(self, monitor_id, preset_name):
        return lambda icon, item: self.post(("toggle", monitor_id, preset_name))

    def _preset_checker(self, monitor_id, preset_name):
        return lambda item: self.eng.active.get(monitor_id) == preset_name

    def _night_toggler(self, monitor_id):
        return lambda icon, item: self.post(("night", monitor_id))

    def _night_checker(self, monitor_id):
        return lambda item: monitor_id in self.eng.night_mons
