"""Főmenü-overlay: egy gyorsgombbal előhívható, a játék fölé tett menü (Térkép, Böngésző, Képbeállítások). Kattintható, és a
↑/↓, Enter, Esc gombokkal is vezérelhető; a nézet nem aktiválódik, így a játék megtartja a fókuszt. A billentyűk csak a menü
nyitva tartása alatt foglaltak. Három rész: modell (léptetés), nézet (tk-ablak) és vezérlő (nyitás, billentyűk, akciók)."""
from hw_common import MENU_KEYS
from overlay import ACCENT, BACKGROUND, DIM, FOREGROUND, centered_position

ITEMS = (("map", "Térkép"), ("browser", "Böngésző"), ("profile", "Képbeállítások"))
WIDTH, ALPHA = 320, 0.95
HINT = "↑↓ választ · Enter megnyit · Esc zár"


class MenuModel:
    def __init__(self):
        self.index = 0

    @property
    def selected(self):
        return ITEMS[self.index][0]

    def move(self, step):
        self.index = (self.index + step) % len(ITEMS)


class MenuView:
    """A menü tk-ablaka: nem aktiválódó (a játék megtartja a fókuszt), de kattintható."""

    def __init__(self, root):
        self.root, self.window, self._rows = root, None, {}

    @property
    def is_open(self):
        return self.window is not None

    def show(self, rect, model, on_click):
        import tkinter as tk
        from hw import menu_style
        self.close()
        window = tk.Toplevel(self.root)
        self.window = window
        window.withdraw()
        window.overrideredirect(True)
        window.configure(bg=BACKGROUND)
        window.attributes("-topmost", True)
        window.attributes("-alpha", 0.0)
        tk.Label(window, text="KÉPPROFIL · MENÜ", fg=ACCENT, bg=BACKGROUND, font=("Segoe UI", 9, "bold")).pack(
            anchor="w", padx=16, pady=(12, 6))
        self._rows = {}
        for item_id, caption in ITEMS:
            row = tk.Label(window, text=caption, bg=BACKGROUND, fg=FOREGROUND, font=("Segoe UI", 14, "bold"), anchor="w",
                           padx=12, pady=6, cursor="hand2")
            row.pack(fill="x", padx=8)
            row.bind("<Button-1>", lambda event, item_id=item_id: on_click(item_id))
            self._rows[item_id] = row
        tk.Label(window, text=HINT, bg=BACKGROUND, fg=DIM, font=("Segoe UI", 9), anchor="w").pack(
            fill="x", padx=16, pady=(8, 12))
        self.update(model)
        window.update_idletasks()
        height = window.winfo_reqheight()
        left, top = centered_position(rect, WIDTH, height)
        window.geometry(f"{WIDTH}x{height}+{left}+{top}")
        try:                                                 # még a megjelenés előtt: a tálcagomb a megjelenéskor jönne létre
            menu_style(window)
        except Exception:
            pass
        window.deiconify()
        window.update_idletasks()
        window.attributes("-alpha", ALPHA)

    def update(self, model):
        for item_id, row in self._rows.items():
            selected = item_id == model.selected
            row.configure(fg=ACCENT if selected else FOREGROUND, text=("▶ " if selected else "   ") + dict(ITEMS)[item_id])

    def close(self):
        if self.window is not None:
            try:
                self.window.destroy()
            except Exception:
                pass
        self.window, self._rows = None, {}


class MenuController:
    """actions: menüpont-azonosító -> hívható; a kiválasztáskor a menü előbb bezárul (felszabadítja a gombokat), utána fut az
    akció. before_open(): a nyitás előtt hívódik (a többi overlay lefoglalt gombjainak felszabadítására)."""

    def __init__(self, eng, root, set_hotkeys, actions, rect_for, foreground_mid, before_open=lambda: None, view=None):
        self.eng, self.root, self.set_hotkeys, self.actions = eng, root, set_hotkeys, actions
        self.rect_for, self.foreground_mid, self.before_open = rect_for, foreground_mid, before_open
        self.view, self.model = view or MenuView(root), MenuModel()

    @property
    def is_open(self):
        return self.view.is_open

    def toggle(self):
        if self.is_open:
            self.close()
        else:
            self._open()

    def _open(self):
        self.before_open()
        self.model = MenuModel()
        self.set_hotkeys({**self.eng.hotkey_map(), **MENU_KEYS})
        rect = self.rect_for(self.foreground_mid()) or (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        self.view.show(rect, self.model, self.activate)

    def key(self, action):
        if not self.is_open:
            return
        if action == "mn|up":
            self.model.move(-1)
            self.view.update(self.model)
        elif action == "mn|down":
            self.model.move(1)
            self.view.update(self.model)
        elif action == "mn|ok":
            self.activate(self.model.selected)
        elif action == "mn|close":
            self.close()

    def activate(self, item_id):
        self.close()
        try:
            self.actions[item_id]()
        except Exception as error:
            self.eng.say(f"A menüpont nem futott le: {error.__class__.__name__}")

    def close(self):
        self.view.close()
        self.set_hotkeys(self.eng.hotkey_map())
