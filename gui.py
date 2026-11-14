"""A felület belépője: a motor, a gyorsgombok, a tálca, a főablak és az üzenetsor összekötése (run_app). A felület részei külön
modulokban vannak: `gui_layout` (elrendezés), `gui_panel` (a főablak viselkedése), `gui_preset_dialogs`, `gui_dialogs`,
`gui_tray`, `gui_toast`, `gui_widgets`."""
import queue
import sys
import threading
import traceback

from config import auto_backup, write_log
from consts import APP_NAME, RES_DIR, VERSION
from engine import Engine
from hw import Hotkeys, SystemEvents, foreground_monitor_id, monitor_rect, power_plans
from overlay import OverlayController
from system import (ensure_launcher, kill_old_watcher, show_signaled, signal_running, single_instance,
                    start_process_events)

HOOK = {}                                         # tesztek: a futó felület elemei (run_app tölti fel)
PUMP_INTERVAL_MS = 100                            # az üzenetsor ürítésének gyakorisága
OVERLAY_TICK_MS = 500
WINDOW_SIZE = "620x920"
WINDOW_MIN_SIZE = (580, 760)
ICON_LOAD_DELAY_MS = 300                          # az ablak ikonját a megjelenés után tölti be (korábban nem fogja meg)
SHOW_SIGNAL_TIMEOUT_MS = 1000


def log_exception(where, exc_type, exc_value, exc_traceback):
    write_log(f"Kezeletlen hiba ({where}):\n" + "".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))


def install_exception_hooks():
    """A főszál és a háttérszálak kezeletlen hibái a naplóba kerülnek."""
    sys.excepthook = lambda exc_type, exc_value, exc_traceback: log_exception(
        "főszál", exc_type, exc_value, exc_traceback)
    threading.excepthook = lambda args: log_exception(
        f"szál: {args.thread.name if args.thread else '?'}", args.exc_type, args.exc_value, args.exc_traceback)


class App:
    """A futó alkalmazás: a motor, a gyorsgombok, az ablak és a tálca, valamint az üzenetsor, amelyen a háttérszálak és a
    tálcamenü a főszálnak üzennek (a Tk-t csak a főszál használhatja)."""

    def __init__(self, show_event):
        import customtkinter as ctk
        from gui_panel import Panel
        from gui_toast import Toast
        from gui_tray import Tray
        self.show_event = show_event
        self.queue = queue.Queue()
        auto_backup()                                   # még azelőtt, hogy az indulás bármit újraírna
        self.eng = self._create_engine()
        install_exception_hooks()
        self.eng.say(f"Indul: {APP_NAME} {VERSION}")
        self.hotkeys = Hotkeys(lambda action: self.post(("hk", action)))
        self.hotkeys.start()
        self.system_events = SystemEvents(self.eng.system_event)         # ébredés / kijelzőváltás után a kép visszaállítása
        self.system_events.start()
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")
        self.root = self._create_window(ctk)
        self.overlay = OverlayController(
            self.eng, self.root, set_hotkeys=self.hotkeys.set, foreground_mid=foreground_monitor_id,
            rect_for=monitor_rect, hotkey_failed=lambda: self.hotkeys.failed,
            main_visible=lambda: self.root.state() != "withdrawn")
        self.toast = Toast(self.root, rect_for=monitor_rect)
        self.tray = Tray(self.eng, self.post)
        self.tray.start()
        self.panel = Panel(self, power_plans())
        self._handlers = {
            "panel": self.panel.show,
            "shortcuts": self._show_shortcuts,
            "toast": self.toast.show,
            "toggle": self.eng.toggle_preset,
            "night": self._toggle_night,
            "neutral": self.eng.neutral_all,
            "hk": self._run_hotkey_action,
            "monitors": self.panel.on_monitors_changed,
            "refresh": self._on_engine_refresh,
            "base_saved": self.panel.on_base_saved,
        }

    def _create_engine(self):
        eng = Engine(notify=lambda: self.post(("refresh",)))
        eng.toast_cb = lambda text, monitor_id: self.post(("toast", text, monitor_id))
        eng.monitors_cb = lambda: self.post(("monitors",))
        if not eng.set.get("migrated"):
            kill_old_watcher()
            eng.set["migrated"] = True
            eng.save_settings()
        eng.save_config()
        return eng

    def _create_window(self, ctk):
        root = ctk.CTk()
        root.report_callback_exception = lambda exc_type, exc_value, exc_traceback: log_exception(
            "felület", exc_type, exc_value, exc_traceback)
        root.title(APP_NAME)
        root.geometry(WINDOW_SIZE)
        root.minsize(*WINDOW_MIN_SIZE)
        icon_file = RES_DIR / "assets" / "icon.ico"
        if icon_file.is_file() and sys.platform == "win32":
            root.after(ICON_LOAD_DELAY_MS, lambda: root.iconbitmap(str(icon_file)))
        return root

    # ---- a Panel és a Tray szolgáltatásai

    def post(self, message):
        """Üzenet a főszálnak (bármely szálról hívható)."""
        self.queue.put(message)

    def apply_hotkeys(self):
        self.hotkeys.set(self.eng.hotkey_map())

    def refresh_tray(self):
        self.tray.refresh()

    # ---- indítás és főciklus

    def run(self, start_hidden):
        self.panel.start()
        self.eng.sync()                            # induláskor ismert (semleges) állapot
        threading.Thread(target=self.eng.fx_loop, daemon=True).start()
        threading.Thread(target=lambda: self.eng.watch_loop(start_process_events), daemon=True).start()
        threading.Thread(target=self._wait_for_second_launch, daemon=True).start()
        self.apply_hotkeys()
        self.pump()
        self.overlay_tick()
        HOOK.update(root=self.root, eng=self.eng, panel=self.panel, toast=self.toast, overlay=self.overlay,
                    hotkeys=self.hotkeys)          # csak az automatikus tesztek használják
        if start_hidden:
            self.root.withdraw()
        else:
            self.panel.show()
        self.root.mainloop()

    def _wait_for_second_launch(self):
        while not self.eng.stop:
            if show_signaled(self.show_event, SHOW_SIGNAL_TIMEOUT_MS, lambda action: self.post(("hk", action))):
                self.post(("panel",))              # a második indítás jelzett: az ablak elő

    def pump(self):
        """A főszál üzenetsorának ürítése: minden üzenet `(fajta, *paraméterek)`; ismeretlen fajtát figyelmen kívül hagy."""
        try:
            while True:
                kind, *arguments = self.queue.get_nowait()
                if kind == "quit":
                    self.quit()
                    return
                handler = self._handlers.get(kind)
                if handler:
                    handler(*arguments)
        except queue.Empty:
            pass
        self.root.after(PUMP_INTERVAL_MS, self.pump)

    def overlay_tick(self):
        try:
            self.overlay.check()
        except Exception as error:
            self.eng.say(f"Overlay hiba: {error.__class__.__name__}")
        self.root.after(OVERLAY_TICK_MS, self.overlay_tick)

    def quit(self):
        self.overlay.close()
        self.eng.shutdown()
        self.tray.stop()
        self.root.destroy()

    # ---- az üzenetek kezelői

    def _show_shortcuts(self):
        from gui_dialogs import show_shortcuts_dialog
        show_shortcuts_dialog(self.root, self.eng, on_error=self.panel.set_status)

    def _toggle_night(self, monitor_id=None):
        self.eng.toggle_night(monitor_id)

    def _run_hotkey_action(self, action):
        if action == "overlay":
            self.overlay.toggle()
        elif action.startswith("ov|"):
            self.overlay.key(action)
        else:
            self.eng.run_action(action)

    def _on_engine_refresh(self):
        self.tray.refresh()
        self.panel.on_engine_refresh()


def run_app(start_hidden):
    from gui_tray import size_xorg_icon_window
    size_xorg_icon_window()
    already_running, show_event = single_instance()
    if already_running:
        signal_running(show_event)
        return
    ensure_launcher()
    App(show_event).run(start_hidden)
