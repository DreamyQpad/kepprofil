"""Játék-overlay: az aktuális játék profiljának szerkesztése a játék fölött, billentyűzettel, fókuszlopás nélkül.
Három rész: a modell (értékek, léptetés, mentés), a megjelenítő (nem aktiválódó tk-ablak) és a vezérlő (nyitás, billentyűk)."""
from typing import NamedTuple

from config import pgain, pvals
from hw_common import OVERLAY_KEYS

GAMMA_SCALE = 2.2                     # a panelen NVIDIA-skálás gamma (1,00 = semleges); a mentett belső érték ennek 2,2-szerese


class Row(NamedTuple):
    key: str
    caption: str
    lo: float
    hi: float
    step: float
    default: float


ROWS = (Row("b", "Fényerő", 0, 100, 1, 50),
        Row("c", "Kontraszt", 0, 100, 1, 50),
        Row("g", "Gamma", 0.30, 2.80, 0.01, 1.0),
        Row("v", "Vibrance", 0, 100, 1, 50),
        Row("cr", "Vörös", 0, 100, 1, 100),
        Row("cg", "Zöld", 0, 100, 1, 100),
        Row("cb", "Kék", 0, 100, 1, 100))


class OverlayModel:
    """Egy preset (egy monitoron) érvényes változatának szerkesztett állapota. A motorhoz csak a nyilvános műveletein át nyúl."""

    def __init__(self, eng, mid, name):
        self.eng, self.mid, self.name = eng, mid, name
        self.sel = 0
        self.variant = eng.cur_variant(mid, name)
        p = eng.preset(mid, name)
        g, c, b, v = pvals(p, self.variant)
        r, gr, bl = pgain(p, self.variant)
        self.values = {"b": b, "c": c, "g": round(g / GAMMA_SCALE, 2), "v": v, "cr": r, "cg": gr, "cb": bl}
        self.baseline = dict(self.values)

    def title(self):
        return f"{self.name} · {self.variant}" if self.variant else self.name

    def move(self, d):
        self.sel = (self.sel + d) % len(ROWS)

    def adjust(self, steps):
        row = ROWS[self.sel]
        self.values[row.key] = round(max(row.lo, min(row.hi, self.values[row.key] + steps * row.step)), 2)

    def reset_row(self):
        row = ROWS[self.sel]
        self.values[row.key] = row.default

    def vals(self):
        """(gamma a belső skálán, kontraszt, fényerő, vibrance) — a motor és a mentés formátuma."""
        v = self.values
        return round(v["g"] * GAMMA_SCALE, 4), round(v["c"]), round(v["b"]), round(v["v"])

    def gain(self):
        return [round(self.values[k]) for k in ("cr", "cg", "cb")]

    def dirty(self):
        return self.values != self.baseline

    def preview(self):
        return self.eng.preview(self.mid, self.vals(), self.gain())

    def save(self):
        self.eng.save_values(self.mid, self.name, self.vals(), self.gain())
        self.baseline = dict(self.values)

    def new_variant(self):
        self.variant = self.eng.add_variant(self.mid, self.name, self.vals(), self.gain())
        self.baseline = dict(self.values)
        return self.variant

    def discard(self):
        """Eldobja a mentetlen módosítást: a kijelzőn újra a mentett állapot látszik."""
        self.values = dict(self.baseline)
        self.eng.sync(self.mid)


BG, FG, DIM, ACCENT, WARN = "#14161a", "#ffffff", "#8a93a0", "#7fb2ff", "#ffb454"
WIDTH, MARGIN, ALPHA = 340, 24, 0.92
HINT = "↑↓ sor · ←→ állít (Shift ×5) · Del alap\nEnter mentés · N új változat · Esc elvet"


def format_value(row, value):
    return f"{value:.2f}" if row.key == "g" else f"{round(value)}%"


class OverlayView:
    """A játék fölé tett, fókuszt nem lopó, átkattintható szerkesztőpanel. Csak megjelenít; a billentyűket a vezérlő kezeli."""

    def __init__(self, root):
        self.root = root
        self.window = None
        self.hwnd = None
        self._marks, self._values = [], []
        self._title = self._dirty = self._warn = None

    @property
    def is_open(self):
        return self.window is not None

    def show(self, rect, model, warning=""):
        import tkinter as tk
        from hw import overlay_style
        self.close()
        w = tk.Toplevel(self.root)
        self.window = w
        w.withdraw()
        w.overrideredirect(True)
        w.configure(bg=BG)
        w.attributes("-topmost", True)
        w.attributes("-alpha", 0.0)
        tk.Label(w, text="KÉPPROFIL · OVERLAY", fg=ACCENT, bg=BG, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=16, pady=(12, 0))
        self._title = tk.Label(w, bg=BG, fg=FG, font=("Segoe UI", 15, "bold"), anchor="w")
        self._title.pack(fill="x", padx=16, pady=(0, 8))
        grid = tk.Frame(w, bg=BG)
        grid.pack(fill="x", padx=16)
        self._marks, self._values = [], []
        for i, row in enumerate(ROWS):
            mark = tk.Label(grid, bg=BG, fg=ACCENT, font=("Segoe UI", 12, "bold"), width=2, anchor="w")
            mark.grid(row=i, column=0)
            tk.Label(grid, text=row.caption, bg=BG, fg=FG, font=("Segoe UI", 12), anchor="w").grid(row=i, column=1, sticky="w")
            val = tk.Label(grid, bg=BG, fg=FG, font=("Segoe UI", 12, "bold"), anchor="e", width=7)
            val.grid(row=i, column=2, sticky="e")
            grid.columnconfigure(1, weight=1)
            self._marks.append(mark)
            self._values.append(val)
        self._dirty = tk.Label(w, bg=BG, fg=WARN, font=("Segoe UI", 10), anchor="w")
        self._dirty.pack(fill="x", padx=16, pady=(8, 0))
        self._warn = tk.Label(w, bg=BG, fg=WARN, font=("Segoe UI", 9), anchor="w", justify="left", wraplength=WIDTH - 32)
        self._warn.pack(fill="x", padx=16)
        tk.Label(w, text=HINT, bg=BG, fg=DIM, font=("Segoe UI", 9), anchor="w", justify="left").pack(fill="x", padx=16, pady=(8, 12))
        self.update(model, warning)
        w.update_idletasks()
        wh = w.winfo_reqheight()
        l, t, r, b = rect
        w.geometry(f"{WIDTH}x{wh}+{r - WIDTH - MARGIN}+{t + max(0, (b - t - wh) // 2)}")
        w.deiconify()
        w.update_idletasks()
        try:                                                  # átkattintható, nem aktiválódik, nincs tálcagomb
            overlay_style(w)
        except Exception:
            pass
        self.hwnd = self._find_hwnd(w)
        w.attributes("-alpha", ALPHA)

    @staticmethod
    def _find_hwnd(w):
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.GetParent.restype = ctypes.c_void_p
            return user32.GetParent(w.winfo_id()) or w.winfo_id()
        except Exception:
            return w.winfo_id()

    def update(self, model, warning=""):
        if self.window is None:
            return
        self._title.configure(text=model.title())
        for i, row in enumerate(ROWS):
            self._marks[i].configure(text="▶" if i == model.sel else "")
            self._values[i].configure(text=format_value(row, model.values[row.key]), fg=ACCENT if i == model.sel else FG)
        self._dirty.configure(text="● mentetlen módosítás" if model.dirty() else "")
        self._warn.configure(text=warning)

    def close(self):
        if self.window is not None:
            try:
                self.window.destroy()
            except Exception:
                pass
        self.window = self.hwnd = None


KEY_NAMES = {"ov|up": "↑", "ov|down": "↓", "ov|left": "←", "ov|right": "→", "ov|sleft": "Shift+←", "ov|sright": "Shift+→",
             "ov|reset": "Del", "ov|save": "Enter", "ov|new": "N", "ov|close": "Esc"}
PREVIEW_DELAY_MS = 40                 # a nyomva tartott nyíl ne terhelje a kijelző-meghajtót minden ismétlésnél


class OverlayController:
    """Az overlay nyitása/zárása és billentyűkezelése. A billentyűk csak nyitva tartás alatt vannak lefoglalva; a lefoglalást,
    az ablakokat és a környezetet kívülről kapja, így ablak nélkül is tesztelhető.
    set_hotkeys(mapping): a teljes gyorsgomb-térkép cseréje; foreground_mid(): az előtérbeli ablak monitorja vagy None;
    rect_for(mid): a monitor téglalapja vagy None; hotkey_failed(): a nem lefoglalható műveletek; main_visible(): látszik-e a főablak."""

    def __init__(self, eng, root, set_hotkeys, foreground_mid, rect_for, hotkey_failed, main_visible, view=None):
        self.eng, self.root = eng, root
        self.set_hotkeys, self.foreground_mid, self.rect_for = set_hotkeys, foreground_mid, rect_for
        self.hotkey_failed, self.main_visible = hotkey_failed, main_visible
        self.view = view or OverlayView(root)
        self.model = None
        self._job = None

    @property
    def is_open(self):
        return self.model is not None

    def toggle(self):
        if self.is_open:
            self.close()
        else:
            self._open()

    def _open(self):
        if self.main_visible():
            return
        target = self.eng.overlay_target(self.foreground_mid())
        if target is None:
            self.eng.toast("Nincs aktív preset")
            return
        mid, name = target
        self.model = OverlayModel(self.eng, mid, name)
        self.eng.panel_open = True
        self.set_hotkeys({**self.eng.hotkey_map(), **OVERLAY_KEYS})
        rect = self.rect_for(mid) or (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        self.view.show(rect, self.model, self._warning())

    def _warning(self):
        failed = self.hotkey_failed()
        bad = [KEY_NAMES[a] for a in OVERLAY_KEYS if a in failed]
        return "Foglalt gomb, nem működik: " + ", ".join(bad) if bad else ""

    def key(self, action):
        if not self.is_open:
            return
        m = self.model
        if action == "ov|save":
            m.save()
            self._finish(saved=True)
            return
        if action == "ov|close":
            self.close()
            return
        if action == "ov|new":
            m.new_variant()
        elif action in ("ov|up", "ov|down"):
            m.move(-1 if action == "ov|up" else 1)
        elif action == "ov|reset":
            m.reset_row()
            self._schedule_preview()
        elif action in ("ov|left", "ov|right", "ov|sleft", "ov|sright"):
            m.adjust((-1 if "left" in action else 1) * (5 if action.startswith("ov|s") else 1))
            self._schedule_preview()
        self.view.update(m, self._warning())

    def _schedule_preview(self):
        if self._job is None:
            self._job = self.root.after(PREVIEW_DELAY_MS, self._do_preview)

    def _do_preview(self):
        self._job = None
        if self.is_open:
            self.model.preview()

    def close(self):
        """Elveti a mentetlen módosítást, és bezár (a mentett kép áll vissza)."""
        if self.is_open:
            self._finish(saved=False)

    def _finish(self, saved):
        m, self.model = self.model, None
        if self._job is not None:
            self.root.after_cancel(self._job)
            self._job = None
        try:
            self.view.close()
        finally:
            try:
                self.set_hotkeys(self.eng.hotkey_map())
            finally:
                self.eng.panel_open = False
        if saved:
            self.eng.sync(m.mid)
            self.eng.toast(f"Mentve: {self.eng.label(m.mid, m.name)}", m.mid)
        else:
            m.discard()

    def check(self):
        """Időzítve hívandó: bezár, ha a szerkesztett preset már nem az aktív (a játék kilépett, preset-váltás), vagy a főablak látszik."""
        if not self.is_open:
            return
        m = self.model
        if self.eng.active.get(m.mid) != m.name or self.eng.preset(m.mid, m.name) is None or self.main_visible():
            self.close()
