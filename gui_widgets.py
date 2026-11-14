"""Önálló felületi elemek (customtkinter): gyorsgomb-mező, RGB-választó, értékmező, csúszka-sor, szakaszcím.
A modul a customtkinter-t importálja, ezért a `gui.run_app` csak a felület indításakor tölti be."""
import re
from tkinter import colorchooser

import customtkinter as ctk

from hw import parse_hotkey

MUTED_TEXT = ("gray40", "gray60")
GREY_BUTTON = dict(fg_color=("gray75", "gray30"), hover_color=("gray65", "gray40"), text_color=("gray10", "gray90"))
RGB_MODES = {"Nem változtat": "none", "Kikapcsolva": "off", "Szín": "color", "Mentett állapot": "snapshot",
             "OpenRGB-profil": "profile"}

MODIFIER_KEYSYMS = ("Control_L", "Control_R", "Alt_L", "Alt_R", "Shift_L", "Shift_R", "Win_L", "Win_R", "Caps_Lock")
KEY_NAMES = {"Escape": "Esc", "space": "Space", "Insert": "Insert", "Delete": "Delete", "Home": "Home", "End": "End",
             "Prior": "PageUp", "Next": "PageDown", "Up": "Up", "Down": "Down", "Left": "Left", "Right": "Right",
             "Pause": "Pause"}
CTRL_MASK, ALT_MASK, SHIFT_MASK = 0x4, 0x20000, 0x1                   # a Tk `event.state` módosító-bitjei


class HotkeyEntry(ctk.CTkFrame):
    """Beviteli mező, amelybe a gyorsgombot a billentyűk lenyomásával kell megadni (legalább egy Ctrl/Alt/Shift kell)."""

    def __init__(self, parent, on_change=None):
        super().__init__(parent, fg_color="transparent")
        self.on_change, self.value = on_change, ""
        self.entry = ctk.CTkEntry(self, width=200, placeholder_text="kattints ide, és nyomd meg a gombokat")
        self.entry.pack(side="left")
        self.entry.bind("<KeyPress>", self._on_key)
        ctk.CTkButton(self, text="Törlés", width=64, command=lambda: self.set("", True), **GREY_BUTTON).pack(
            side="left", padx=(8, 0))

    def set(self, text, notify=False):
        self.value = text
        self.entry.delete(0, "end")
        if text:
            self.entry.insert(0, text)
        if notify and self.on_change:
            self.on_change(text)

    def get(self):
        return self.value

    def _on_key(self, event):
        keysym = event.keysym
        if keysym in MODIFIER_KEYSYMS:
            return "break"
        if keysym == "BackSpace":
            self.set("", True)
            return "break"
        if keysym in KEY_NAMES:
            key = KEY_NAMES[keysym]
        elif re.fullmatch(r"F\d{1,2}", keysym):
            key = keysym
        elif re.fullmatch(r"KP_\d", keysym):
            key = "Num" + keysym[-1]
        elif len(keysym) == 1 and keysym.isalnum():
            key = keysym.upper()
        else:
            return "break"
        modifiers = (["Ctrl"] if event.state & CTRL_MASK else []) + (["Alt"] if event.state & ALT_MASK else []) + \
                    (["Shift"] if event.state & SHIFT_MASK else [])
        text = "+".join(modifiers + [key])
        if parse_hotkey(text):
            self.set(text, True)
        else:
            self.entry.delete(0, "end")
            self.entry.insert(0, "legalább egy Ctrl/Alt/Shift kell")
        return "break"


class RgbPicker(ctk.CTkFrame):
    """RGB-beállítás: mód (nem változtat / ki / szín / mentett állapot / OpenRGB-profil) és a módhoz tartozó érték."""

    def __init__(self, parent, on_change=None):
        super().__init__(parent, fg_color="transparent")
        self.on_change, self.color, self.snapshot = on_change, "#ff8800", None
        self.mode_menu = ctk.CTkOptionMenu(self, values=list(RGB_MODES), width=150, command=self._on_mode)
        self.mode_menu.pack(side="left")
        self.swatch = ctk.CTkButton(self, text="", width=60, command=self._pick_color, fg_color=self.color,
                                    hover_color=self.color)
        self.profile_entry = ctk.CTkEntry(self, width=150, placeholder_text="profil neve")
        self.profile_entry.bind("<KeyRelease>", lambda e: self._notify())
        self._on_mode(self.mode_menu.get(), notify=False)

    def _on_mode(self, label, notify=True):
        mode = RGB_MODES[label]
        self.swatch.pack_forget()
        self.profile_entry.pack_forget()
        if mode == "color":
            self.swatch.pack(side="left", padx=(8, 0))
        elif mode == "profile":
            self.profile_entry.pack(side="left", padx=(8, 0))
        if notify:
            self._notify()

    def _pick_color(self):
        chosen = colorchooser.askcolor(color=self.color, title="RGB-szín", parent=self.winfo_toplevel())
        if chosen and chosen[1]:
            self.color = chosen[1]
            self.swatch.configure(fg_color=self.color, hover_color=self.color)
            self._notify()

    def _notify(self):
        if self.on_change:
            self.on_change(self.get())

    def get(self):
        mode = RGB_MODES[self.mode_menu.get()]
        value = {"color": self.color, "profile": self.profile_entry.get().strip(), "snapshot": self.snapshot}.get(mode, "")
        return {"mode": mode, "value": value}

    def set(self, spec):
        mode = (spec or {}).get("mode", "none")
        label = next(k for k, v in RGB_MODES.items() if v == mode) if mode in RGB_MODES.values() else "Nem változtat"
        self.mode_menu.set(label)
        value = (spec or {}).get("value", "")
        if mode == "snapshot":
            self.snapshot = value or None
        if mode == "color" and re.fullmatch(r"#[0-9a-fA-F]{6}", value or ""):
            self.color = value
            self.swatch.configure(fg_color=value, hover_color=value)
        self.profile_entry.delete(0, "end")
        if mode == "profile" and value:
            self.profile_entry.insert(0, value)
        self._on_mode(label, notify=False)


class ValueBox(ctk.CTkEntry):
    """A csúszka értéke: mutatja, és beírható (Enter / mezőelhagyás véglegesíti). configure(text=) mint a címkénél."""

    def __init__(self, parent, commit):
        super().__init__(parent, width=68, height=26, justify="right")
        self._commit = commit
        self.bind("<Return>", lambda e: self._done(True))
        self.bind("<FocusOut>", lambda e: self._done(False))

    def configure(self, **options):
        if "text" in options:
            text = options.pop("text")
            if self.focus_get() is not self._entry:           # gépelés közben ne írjuk felül
                state = self.cget("state")
                super().configure(state="normal")                # tiltott mezőbe sem lehet írni, ezért átmenetileg engedjük
                self.delete(0, "end")
                self.insert(0, text)
                super().configure(state=state)
        if options:
            super().configure(**options)

    def _done(self, enter):
        self._commit(self.get())
        if enter:
            self.winfo_toplevel().focus_set()


def build_slider(parent, caption, low, high, steps, format_value, on_change, default=None):
    """Címkével és beírható értékmezővel ellátott csúszka. `on_change()` fut, ha a csúszka értéke változik; dupla kattintás
    a `default` értékre állít. Visszaad: (csúszka, értékmező, formázó függvény)."""
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", pady=(16, 0))
    ctk.CTkLabel(row, text=caption).pack(side="left")
    slider = ctk.CTkSlider(parent, from_=low, to=high, number_of_steps=steps, command=lambda value: on_change())

    def set_and_notify(value):
        if slider.cget("state") == "disabled":
            return
        slider.set(value)
        command = slider.cget("command")
        (command or (lambda v: on_change()))(value)

    def on_typed(text):
        try:
            value = float(text.replace("%", "").replace(",", ".").strip())
        except ValueError:
            value_box.configure(text=format_value(slider.get()))     # érvénytelen: marad a régi
            return
        set_and_notify(max(low, min(high, value)))

    value_box = ValueBox(row, on_typed)
    value_box.pack(side="right")
    slider.pack(fill="x", pady=(5, 0))
    if default is not None:
        slider.bind("<Double-Button-1>", lambda e: set_and_notify(default))     # dupla kattintás: alapérték
    return slider, value_box, format_value


def section_title(parent, text):
    ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(14, 4))
