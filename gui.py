"""A felület: tálcaikon, panel, toast, és a motor/gyorsgombok összekötése (run_app)."""
import ctypes
import json
import os
import queue
import re
import sys
import threading
import time
import traceback
from pathlib import Path

from config import (BACKUP_DIR, write_log, SETTINGS_KEYS, _read_json, _write_json, auto_backup, mirror_first, new_preset,
                    normalize_config, pgain, pvals, valid_config)
from consts import APP_NAME, DATA_DIR, LOG_FILE, NEUTRAL, RES_DIR, VERSION
from engine import Engine
from hw import Hotkeys, SystemEvents, find_dev, kernel32, monitor_rect, parse_hotkey, power_plans, user32
from system import (autostart_enabled, kill_old_watcher, set_autostart, single_instance, visible_programs)

HOOK = {}                                         # tesztek: a futó felület elemei (run_app tölti fel)

def make_icon(active=False, size=64):
    """Tálcaikon: kijelző, fél-fényes/fél-sötét képernyővel (szögletes), bekapcsolt állapotban narancs jelzéssel."""
    from PIL import Image, ImageDraw
    s = size / 64
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    box = lambda x0, y0, x1, y1: [round(x0 * s), round(y0 * s), round(x1 * s) - 1, round(y1 * s) - 1]
    d.rectangle(box(4, 8, 60, 46), fill=(229, 231, 235, 255))
    d.rectangle(box(8, 12, 56, 42), fill=(30, 41, 59, 255))
    d.rectangle(box(8, 12, 32, 42), fill=(245, 197, 66, 255))
    d.rectangle(box(26, 46, 38, 54), fill=(229, 231, 235, 255))
    d.rectangle(box(16, 54, 48, 59), fill=(229, 231, 235, 255))
    if active:
        d.rectangle(box(44, 2, 62, 20), fill=(249, 115, 22, 255), outline=(255, 255, 255, 255), width=max(1, round(2 * s)))
    return im


# ---------------------------------------------------------------- felület

def run_app(start_hidden):
    import customtkinter as ctk
    from tkinter import colorchooser, filedialog, messagebox
    import pystray

    already, show_ev = single_instance()
    if already:
        kernel32.SetEvent(show_ev)
        return

    q = queue.Queue()
    auto_backup()                                   # még azelőtt, hogy az indulás bármit újraírna
    eng = Engine(notify=lambda: q.put(("refresh",)))
    eng.toast_cb = lambda text, mid: q.put(("toast", text, mid))
    first_run = not eng.set.get("migrated")
    if first_run:
        kill_old_watcher()
        eng.set["migrated"] = True
        eng.save_settings()
    eng.save_config()

    def log_exception(where, et, ev, tb):
        write_log(f"Kezeletlen hiba ({where}):\n" + "".join(traceback.format_exception(et, ev, tb)))

    sys.excepthook = lambda et, ev, tb: log_exception("főszál", et, ev, tb)
    threading.excepthook = lambda a: log_exception(f"szál: {a.thread.name if a.thread else '?'}", a.exc_type, a.exc_value,
                                                   a.exc_traceback)
    eng.say(f"Indul: {APP_NAME} {VERSION}")
    hk = Hotkeys(lambda action: q.put(("hk", action)))
    hk.start()
    sysev = SystemEvents(eng.system_event)         # ébredés / kijelzőváltás után a kép visszaállítása
    sysev.start()

    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    root.report_callback_exception = lambda et, ev, tb: log_exception("felület", et, ev, tb)
    root.title(APP_NAME)
    root.geometry("620x920")
    root.minsize(580, 760)
    ico = RES_DIR / "assets" / "icon.ico"
    if ico.is_file():
        root.after(300, lambda: root.iconbitmap(str(ico)))
    MUTED = ("gray40", "gray60")
    GREY = dict(fg_color=("gray75", "gray30"), hover_color=("gray65", "gray40"), text_color=("gray10", "gray90"))
    ui, cur = {}, {"mid": None, "name": None, "variant": None, "loading": False, "job": None}
    plans = power_plans()
    PLAN_NONE = "Nem változtat"
    RGB_MODES = {"Nem változtat": "none", "Kikapcsolva": "off", "Szín": "color", "Mentett állapot": "snapshot",
                 "OpenRGB-profil": "profile"}

    # ---- kis összetett vezérlők
    class HotkeyEntry(ctk.CTkFrame):
        def __init__(self, parent, on_change=None):
            super().__init__(parent, fg_color="transparent")
            self.on_change, self.value = on_change, ""
            self.entry = ctk.CTkEntry(self, width=200, placeholder_text="kattints ide, és nyomd meg a gombokat")
            self.entry.pack(side="left")
            self.entry.bind("<KeyPress>", self._key)
            ctk.CTkButton(self, text="Törlés", width=64, command=lambda: self.set("", True), **GREY).pack(
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

        def _key(self, ev):
            ks = ev.keysym
            if ks in ("Control_L", "Control_R", "Alt_L", "Alt_R", "Shift_L", "Shift_R", "Win_L", "Win_R", "Caps_Lock"):
                return "break"
            if ks == "BackSpace":
                self.set("", True)
                return "break"
            names = {"Escape": "Esc", "space": "Space", "Insert": "Insert", "Delete": "Delete", "Home": "Home",
                     "End": "End", "Prior": "PageUp", "Next": "PageDown", "Up": "Up", "Down": "Down", "Left": "Left",
                     "Right": "Right", "Pause": "Pause"}
            if ks in names:
                key = names[ks]
            elif re.fullmatch(r"F\d{1,2}", ks):
                key = ks
            elif re.fullmatch(r"KP_\d", ks):
                key = "Num" + ks[-1]
            elif len(ks) == 1 and ks.isalnum():
                key = ks.upper()
            else:
                return "break"
            mods = (["Ctrl"] if ev.state & 0x4 else []) + (["Alt"] if ev.state & 0x20000 else []) + \
                   (["Shift"] if ev.state & 0x1 else [])
            text = "+".join(mods + [key])
            if parse_hotkey(text):
                self.set(text, True)
            else:
                self.entry.delete(0, "end")
                self.entry.insert(0, "legalább egy Ctrl/Alt/Shift kell")
            return "break"

    class RgbPicker(ctk.CTkFrame):
        def __init__(self, parent, on_change=None):
            super().__init__(parent, fg_color="transparent")
            self.on_change, self.color, self.snap = on_change, "#ff8800", None
            self.menu = ctk.CTkOptionMenu(self, values=list(RGB_MODES), width=150, command=self._mode)
            self.menu.pack(side="left")
            self.swatch = ctk.CTkButton(self, text="", width=60, command=self._pick, fg_color=self.color,
                                        hover_color=self.color)
            self.name = ctk.CTkEntry(self, width=150, placeholder_text="profil neve")
            self.name.bind("<KeyRelease>", lambda e: self._changed())
            self._mode(self.menu.get(), notify=False)

        def _mode(self, label, notify=True):
            mode = RGB_MODES[label]
            self.swatch.pack_forget()
            self.name.pack_forget()
            if mode == "color":
                self.swatch.pack(side="left", padx=(8, 0))
            elif mode == "profile":
                self.name.pack(side="left", padx=(8, 0))
            if notify:
                self._changed()

        def _pick(self):
            c = colorchooser.askcolor(color=self.color, title="RGB-szín", parent=self.winfo_toplevel())
            if c and c[1]:
                self.color = c[1]
                self.swatch.configure(fg_color=self.color, hover_color=self.color)
                self._changed()

        def _changed(self):
            if self.on_change:
                self.on_change(self.get())

        def get(self):
            mode = RGB_MODES[self.menu.get()]
            value = {"color": self.color, "profile": self.name.get().strip(), "snapshot": self.snap}.get(mode, "")
            return {"mode": mode, "value": value}

        def set(self, spec):
            mode = (spec or {}).get("mode", "none")
            label = next(k for k, v in RGB_MODES.items() if v == mode) if mode in RGB_MODES.values() else "Nem változtat"
            self.menu.set(label)
            value = (spec or {}).get("value", "")
            if mode == "snapshot":
                self.snap = value or None
            if mode == "color" and re.fullmatch(r"#[0-9a-fA-F]{6}", value or ""):
                self.color = value
                self.swatch.configure(fg_color=value, hover_color=value)
            self.name.delete(0, "end")
            if mode == "profile" and value:
                self.name.insert(0, value)
            self._mode(label, notify=False)

    # ---- váz: felső sáv (monitor, preset, kapcsoló), fülek, alsó sáv
    page = ctk.CTkFrame(root, fg_color="transparent")
    page.pack(fill="both", expand=True, padx=18, pady=14)
    top = ctk.CTkFrame(page, corner_radius=12)
    top.pack(fill="x")
    ui["mon"] = ctk.CTkSegmentedButton(top, values=[m["name"] for m in eng.cfg["monitors"]], command=lambda v: pick_monitor(v, ask=True))
    ui["mon"].pack(fill="x", padx=14, pady=(12, 8))
    pr_ = ctk.CTkFrame(top, fg_color="transparent")               # "Alkalmazás:" felirat + választó, középen
    pr_.pack(pady=(6, 0))
    ctk.CTkLabel(pr_, text="Alkalmazás:").pack(side="left")
    ui["preset"] = ctk.CTkOptionMenu(pr_, values=["Alap"], width=260, anchor="center", command=lambda v: pick_preset(v))
    ui["preset"].pack(side="left", padx=(8, 0))
    r = ctk.CTkFrame(top, fg_color="transparent")                 # alatta a gombok egy sorban, középen
    r.pack(pady=(12, 0))
    ctk.CTkButton(r, text="Új…", width=76, command=lambda: new_preset_dialog(), **GREY).pack(side="left")
    ctk.CTkButton(r, text="Másolás…", width=90, command=lambda: copy_preset_dialog(), **GREY).pack(side="left", padx=(8, 0))
    ui["ren"] = ctk.CTkButton(r, text="Átnevezés…", width=100, command=lambda: rename_preset_dialog(), **GREY)
    ui["ren"].pack(side="left", padx=(8, 0))
    ui["del"] = ctk.CTkButton(r, text="Törlés", width=76, command=lambda: delete_preset(), **GREY)
    ui["del"].pack(side="left", padx=(8, 0))
    ui["on"] = ctk.CTkSwitch(top, text="Be van kapcsolva", command=lambda: toggle_on())              # a gombok alatt
    ui["on"].pack(pady=(16, 16))

    tabs = ctk.CTkTabview(page, corner_radius=12)
    tabs.pack(fill="both", expand=True, pady=(10, 0))
    for t in ("Kép", "Színek", "Játék és profil", "Éjszakai mód", "Program"):
        tabs.add(t)

    class ValueBox(ctk.CTkEntry):
        """A csúszka értéke: mutatja, és beírható (Enter / mezőelhagyás véglegesíti). configure(text=) mint a címkénél."""

        def __init__(self, parent, commit):
            super().__init__(parent, width=68, height=26, justify="right")
            self._commit = commit
            self.bind("<Return>", lambda e: self._done(True))
            self.bind("<FocusOut>", lambda e: self._done(False))

        def configure(self, **kw):
            if "text" in kw:
                t = kw.pop("text")
                if self.focus_get() is not self._entry:           # gépelés közben ne írjuk felül
                    self.delete(0, "end")
                    self.insert(0, t)
            if kw:
                super().configure(**kw)

        def _done(self, enter):
            self._commit(self.get())
            if enter:
                self.winfo_toplevel().focus_set()

    def slider(parent, caption, lo, hi, steps, fmt, default=None):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(16, 0))
        ctk.CTkLabel(row, text=caption).pack(side="left")
        sl = ctk.CTkSlider(parent, from_=lo, to=hi, number_of_steps=steps, command=lambda v: on_slider())

        def fire(v):
            sl.set(v)
            cmd = sl.cget("command")
            (cmd or (lambda x: on_slider()))(v)

        def typed(text):
            try:
                v = float(text.replace("%", "").replace(",", ".").strip())
            except ValueError:
                val.configure(text=fmt(sl.get()))                  # érvénytelen: marad a régi
                return
            fire(max(lo, min(hi, v)))

        val = ValueBox(row, typed)
        val.pack(side="right")
        sl.pack(fill="x", pady=(5, 0))
        if default is not None:
            sl.bind("<Double-Button-1>", lambda e: fire(default))     # dupla kattintás: alapérték
        return sl, val, fmt

    # -- Kép
    t1 = tabs.tab("Kép")
    vr = ctk.CTkFrame(t1, fg_color="transparent")                 # változatok: a kiválasztott preset (alkalmazás) alatt
    vr.pack(fill="x", pady=(8, 0))
    vs_ = ctk.CTkFrame(vr, fg_color="transparent")                # a változat-választó középen
    vs_.pack()
    ctk.CTkLabel(vs_, text="Változat:").pack(side="left")
    ui["var"] = ctk.CTkOptionMenu(vs_, values=["–"], width=260, anchor="center", command=lambda v: pick_variant(v))
    ui["var"].pack(side="left", padx=(8, 0))
    vb = ctk.CTkFrame(vr, fg_color="transparent")                 # alatta a 3 gomb, szintén középen
    vb.pack(pady=(12, 0))
    ctk.CTkButton(vb, text="Új…", width=70, command=lambda: new_variant_dialog(), **GREY).pack(side="left")
    ui["vren"] = ctk.CTkButton(vb, text="Átnevezés…", width=96, command=lambda: rename_variant_dialog(), **GREY)
    ui["vren"].pack(side="left", padx=(8, 0))
    ui["vdel"] = ctk.CTkButton(vb, text="Törlés", width=70, command=lambda: delete_variant(), **GREY)
    ui["vdel"].pack(side="left", padx=(8, 0))
    vh = ctk.CTkFrame(t1, fg_color="transparent")
    vh.pack(fill="x", pady=(22, 0))
    ctk.CTkLabel(vh, text="Gyorsgomb (erre a változatra):", width=190, anchor="w").pack(side="left")
    ui["vhk"] = HotkeyEntry(vh)
    ui["vhk"].pack(side="left", padx=(8, 0))
    vc = ctk.CTkFrame(t1, fg_color="transparent")
    vc.pack(fill="x", pady=(12, 0))
    ctk.CTkLabel(vc, text="Léptető gyorsgomb (köröz):", width=190, anchor="w").pack(side="left")
    ui["chk"] = HotkeyEntry(vc)
    ui["chk"].pack(side="left", padx=(8, 0))
    ctk.CTkFrame(t1, height=1, fg_color=("gray78", "gray28")).pack(fill="x", pady=(20, 4))      # elválasztó a csúszkák előtt
    pct = lambda v: f"{v:.0f}%"
    ui["b"] = slider(t1, "Fényerő", 0, 100, 100, pct, default=50)
    ui["c"] = slider(t1, "Kontraszt", 0, 100, 100, pct, default=50)
    ui["g"] = slider(t1, "Gamma", 0.30, 2.80, 250, lambda v: f"{v:.2f}", default=1.0)   # mint az NVIDIA panelben: 0,30-2,80, alap 1,00
    ui["v"] = slider(t1, "Digital vibrance (NVIDIA)", 0, 100, 100, pct, default=50)
    br = ctk.CTkFrame(t1, fg_color="transparent")
    br.pack(fill="x", pady=(28, 0))
    ui["def"] = ctk.CTkButton(br, text="Preset alapértéke", width=140, command=lambda: preset_default(), **GREY)
    ui["def"].pack(side="left")
    ctk.CTkButton(br, text="Semleges kép", width=120, command=lambda: neutral_now(), **GREY).pack(side="left", padx=(8, 0))
    ui["cmp"] = ctk.CTkButton(br, text="Összehasonlítás (nyomva tartva)", width=210, **GREY)
    ui["cmp"].pack(side="left", padx=(8, 0))
    ui["cmp"].bind("<ButtonPress-1>", lambda e: compare(True), add="+")
    ui["cmp"].bind("<ButtonRelease-1>", lambda e: compare(False), add="+")
    ctk.CTkLabel(t1, text="Amíg ez az ablak nyitva van, a csúszkák élőben hatnak, de mentés nélkül bezárva a mentett "
                          "állapot tér vissza. A \"Be van kapcsolva\" kapcsoló ettől független: az marad, ami be van kapcsolva.\n"
                          "Az érték a csúszka melletti mezőbe be is írható; dupla kattintás a csúszkán az alapértékre állítja.",
                 text_color=MUTED, wraplength=520, justify="left").pack(anchor="w", pady=(20, 0))

    # -- Színek: R/G/B csatornák erősítése (100% = semleges; csökkentve az adott szín halványodik)
    t1b = tabs.tab("Színek")
    ui["cr"] = slider(t1b, "Vörös", 0, 100, 100, pct, default=100)
    ui["cg"] = slider(t1b, "Zöld", 0, 100, 100, pct, default=100)
    ui["cb"] = slider(t1b, "Kék", 0, 100, 100, pct, default=100)
    ctk.CTkButton(t1b, text="Színek visszaállítása (100%)", width=210, command=lambda: reset_colors(), **GREY).pack(
        anchor="w", pady=(28, 0))
    ctk.CTkLabel(t1b, text="Csatornánként csökkentheted az erősítést: kevesebb kékkel melegebb, kevesebb vörössel "
                           "hidegebb a kép. 100% a semleges. A beállítás a kiválasztott változaté (vagy az alkalmazásé, ha nincs "
                           "változata), és együtt mentődik a többivel; az éjszakai mód ráteszi a magáét.",
                 text_color=MUTED, wraplength=520, justify="left").pack(anchor="w", pady=(20, 0))

    # -- Játék és profil
    t2 = tabs.tab("Játék és profil")

    def section(parent, text):
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(14, 4))

    section(t2, "Automatikus bekapcsolás")
    pr = ctk.CTkFrame(t2, fg_color="transparent")
    pr.pack(fill="x")
    ui["proc"] = ctk.CTkEntry(pr, width=200, placeholder_text="a játék exe-ja, pl. bf6")
    ui["proc"].pack(side="left")
    ctk.CTkButton(pr, text="Futó programok…", width=130, command=lambda: running_dialog(), **GREY).pack(side="left", padx=(8, 0))
    ctk.CTkButton(pr, text="Tallózás…", width=90, command=lambda: browse_exe(), **GREY).pack(side="left", padx=(8, 0))
    ctk.CTkLabel(t2, text="Ha ez a program elindul, a preset magától bekapcsol; kilépéskor kikapcsol. Üresen hagyva csak kézzel.",
                 text_color=MUTED, wraplength=520, justify="left").pack(anchor="w", pady=(4, 0))
    section(t2, "Gyorsgomb (be- és kikapcsolja a presetet)")
    ui["hotkey"] = HotkeyEntry(t2)
    ui["hotkey"].pack(anchor="w")
    section(t2, "Profil: amikor a preset bekapcsol…")
    r2 = ctk.CTkFrame(t2, fg_color="transparent")
    r2.pack(fill="x")
    ctk.CTkLabel(r2, text="Energiaprofil:", width=100, anchor="w").pack(side="left")
    ui["power"] = ctk.CTkOptionMenu(r2, values=[PLAN_NONE] + [n for _, n, _ in plans], width=240)
    ui["power"].pack(side="left")
    r3 = ctk.CTkFrame(t2, fg_color="transparent")
    r3.pack(fill="x", pady=(8, 0))
    ctk.CTkLabel(r3, text="RGB:", width=100, anchor="w").pack(side="left")
    ui["rgb"] = RgbPicker(r3)
    ui["rgb"].pack(side="left")
    ctk.CTkLabel(t2, text="Kikapcsoláskor az energiaprofil visszaáll az előzőre, az RGB pedig az \"alap\" állapotra "
                          "(Program fül). A JBL EQ innen nem váltható, azt a JBL alkalmazás játékfelismerése kezeli.",
                 text_color=MUTED, wraplength=520, justify="left").pack(anchor="w", pady=(8, 0))

    # -- Éjszakai mód
    t3 = tabs.tab("Éjszakai mód")
    ui["night"] = ctk.CTkSwitch(t3, text="Éjszakai mód bekapcsolva", command=lambda: night_click())
    ui["night"].pack(anchor="w", pady=(10, 0))
    ui["ns"] = slider(t3, "Erősség (melegebb, halványabb kép)", 0, 100, 100, pct, default=60)
    section(t3, "Gyorsgomb")
    ui["nhk"] = HotkeyEntry(t3, on_change=lambda t: set_setting("night_hotkey", t))
    ui["nhk"].pack(anchor="w")
    ctk.CTkLabel(t3, text="A kapcsoló monitoronként külön működik: mindig a fent kiválasztott monitort érinti (a tálcamenüben "
                          "minden monitornál van külön, és van egy \"minden monitor\" is). A gyorsgomb az összes monitort "
                          "együtt kapcsolja: ha bárhol be van kapcsolva, mindenhol kikapcsol.\n"
                          "Csak akkor kapcsol be, ha te bekapcsolod; a program újraindításakor mindig kikapcsolt. Játék alatt "
                          "(ha annak a presetje be van kapcsolva az adott monitoron) szünetel, hogy a színek ne torzuljanak.",
                 text_color=MUTED, wraplength=520, justify="left").pack(anchor="w", pady=(14, 0))

    # -- Program
    t4 = tabs.tab("Program")
    ui["auto"] = ctk.CTkSwitch(t4, text="Indítás a Windows-szal (tálcán, ablak nélkül)", command=lambda: auto_click())
    ui["auto"].pack(anchor="w", pady=(10, 0))
    ui["toast"] = ctk.CTkSwitch(t4, text="Értesítés a képernyőn váltáskor (a játék fölött is)", command=lambda: toast_click())
    ui["toast"].pack(anchor="w", pady=(10, 0))
    tr = ctk.CTkFrame(t4, fg_color="transparent")
    tr.pack(fill="x", pady=(6, 0))
    ctk.CTkButton(tr, text="Értesítés próbája", width=140, command=lambda: show_toast("Értesítés próba", cur["mid"]),
                  **GREY).pack(side="left")
    ctk.CTkLabel(tr, text="Teljes képernyős (exkluzív) módú játék fölött nem látszik; ablak nélküli módban igen.",
                 text_color=MUTED, wraplength=360, justify="left").pack(side="left", padx=(10, 0))
    section(t4, "Gyorsgomb: semleges kép (minden kikapcsol)")
    ui["nehk"] = HotkeyEntry(t4, on_change=lambda t: set_setting("neutral_hotkey", t))
    ui["nehk"].pack(anchor="w")
    section(t4, "RGB alapállapot (ide áll vissza, ha egy profil kikapcsol)")
    ui["base"] = RgbPicker(t4, on_change=lambda s: set_setting("base_rgb", s))
    ui["base"].pack(anchor="w")
    ctk.CTkButton(t4, text="A mostani RGB-állapot mentése alapnak", width=270, command=lambda: save_base_rgb(), **GREY).pack(
        anchor="w", pady=(8, 0))
    section(t4, "Mentés és visszatöltés")
    bk = ctk.CTkFrame(t4, fg_color="transparent")
    bk.pack(fill="x")
    ctk.CTkButton(bk, text="Exportálás…", width=120, command=lambda: export_all(), **GREY).pack(side="left")
    ctk.CTkButton(bk, text="Importálás…", width=120, command=lambda: import_all(), **GREY).pack(side="left", padx=(8, 0))
    ctk.CTkLabel(t4, text=f"Az összes preset és beállítás egy fájlba. A program naponta egyszer maga is másolatot készít "
                          f"(utolsó 10 marad): {BACKUP_DIR}", text_color=MUTED, wraplength=520, justify="left").pack(
        anchor="w", pady=(6, 0))
    lg = ctk.CTkFrame(t4, fg_color="transparent")
    lg.pack(fill="x", pady=(14, 0))
    ctk.CTkButton(lg, text="Napló megnyitása", width=140, command=lambda: open_path(LOG_FILE), **GREY).pack(side="left")
    ctk.CTkButton(lg, text="Adatmappa megnyitása", width=160, command=lambda: open_path(DATA_DIR), **GREY).pack(
        side="left", padx=(8, 0))
    ui["info"] = ctk.CTkLabel(t4, text="", text_color=MUTED, wraplength=520, justify="left")
    ui["info"].pack(anchor="w", pady=(14, 0))

    # -- alsó sáv
    bot = ctk.CTkFrame(page, fg_color="transparent")
    bot.pack(side="bottom", fill="x", pady=(10, 0))                # alulra rögzítve: kis ablaknál sem csúszhat ki
    ctk.CTkButton(bot, text="Mentés a presetbe", width=160, command=lambda: save_preset()).pack(side="left")
    ui["dirty"] = ctk.CTkLabel(bot, text="", text_color=("#b45309", "#f59e0b"), width=150, anchor="w")   # mentetlen módosítás jelzése
    ui["dirty"].pack(side="left", padx=(12, 0))
    ui["status"] = ctk.CTkLabel(bot, text="", text_color=MUTED, anchor="w", wraplength=240, justify="left")
    ui["status"].pack(side="left", padx=12)
    tabs.pack_forget()                                              # a fülek az alsó sáv UTÁN kapjanak helyet
    tabs.pack(fill="both", expand=True, pady=(10, 0))

    # ---- logika
    def status(text):
        ui["status"].configure(text=text)

    def mon_by_name(name):
        return next((m for m in eng.cfg["monitors"] if m["name"] == name), eng.cfg["monitors"][0])

    # A gamma-csúszka az NVIDIA-panel skáláján megy (1,00 = semleges); a mentett/belső érték marad a régi
    # (2,2 = semleges), így a meglévő presetek nem változnak: belső = csúszka * 2,2.
    def set_slider(k, v):
        ui[k][0].set(v / 2.2 if k == "g" else v)

    def vals_now():
        return (round(round(ui["g"][0].get(), 2) * 2.2, 4), round(ui["c"][0].get()), round(ui["b"][0].get()), round(ui["v"][0].get()))

    def gains_now():
        return [round(ui[k][0].get()) for k in ("cr", "cg", "cb")]

    def set_gains(gain):
        for k, val in zip(("cr", "cg", "cb"), gain):
            ui[k][0].set(val)

    def update_labels():
        for k in ("g", "c", "b", "v", "cr", "cg", "cb"):
            sl, lbl, fmt = ui[k]
            lbl.configure(text=fmt(sl.get()))
        ui["ns"][1].configure(text=ui["ns"][2](ui["ns"][0].get()))

    def reset_colors():
        set_gains([100, 100, 100])
        on_slider()

    def on_slider():
        update_labels()
        if cur["loading"]:
            return
        if cur["job"]:
            root.after_cancel(cur["job"])
        cur["job"] = root.after(40, do_preview)

    def do_preview():
        cur["job"] = None
        ok = eng.preview(cur["mid"], vals_now(), gains_now())
        status("" if ok else "Hiba: a monitor nem található vagy nem sikerült beállítani.")

    def load_preset(name):
        mid = cur["mid"]
        p = eng.preset(mid, name)
        if p is None:
            return
        cur["name"], cur["loading"] = name, True
        cur["variant"] = eng.cur_variant(mid, name)
        ui["preset"].set(name)
        for k, val in zip("gcbv", pvals(p, cur["variant"])):
            set_slider(k, val)
        set_gains(pgain(p, cur["variant"]))
        refresh_variant_ui(p)
        ui["proc"].delete(0, "end")
        if p.get("process"):
            ui["proc"].insert(0, p["process"])
        ui["hotkey"].set(p.get("hotkey", ""))
        plan = next((n for g, n, _ in plans if g == p.get("power")), PLAN_NONE)
        ui["power"].set(plan)
        ui["rgb"].set(p.get("rgb"))
        ui["def"].configure(state="normal" if p.get("default") else "disabled")
        ui["del"].configure(state="disabled" if name == "Alap" else "normal")
        ui["ren"].configure(state="disabled" if name == "Alap" else "normal")
        cur["loading"] = False
        update_labels()
        sync_switches()
        mark_clean()

    def sync_switches():
        on = eng.active.get(cur["mid"]) == cur["name"]
        ui["on"].select() if on else ui["on"].deselect()
        ui["night"].select() if cur["mid"] in eng.night_mons else ui["night"].deselect()
        ui["night"].configure(text="Éjszakai mód ezen a monitoron: " + (eng.mon(cur["mid"]) or {}).get("name", ""))

    # -- mentetlen módosítások: az alapállapot a legutóbbi betöltés/mentés utáni felület (collect()), ehhez hasonlítunk
    def mark_clean():
        cur["base"] = collect()
        ui["dirty"].configure(text="")

    def is_dirty():
        return bool(cur.get("name")) and cur.get("base") is not None and collect() != cur["base"]

    def confirm_discard():
        return (not is_dirty()) or messagebox.askyesno(
            APP_NAME, "Mentetlen módosításaid vannak ezen a presetten.\nEldobod őket?", parent=root)

    def poll_dirty():
        try:
            if root.state() != "withdrawn":
                ui["dirty"].configure(text="● Mentetlen módosítás" if is_dirty() else "")
        except Exception:
            pass
        root.after(400, poll_dirty)

    def pick_monitor(name, ask=False):
        if ask and mon_by_name(name)["id"] != cur["mid"] and not confirm_discard():
            ui["mon"].set(mon_by_name(next((m["name"] for m in eng.cfg["monitors"] if m["id"] == cur["mid"]), name))["name"])
            return
        m = mon_by_name(name)
        cur["mid"] = m["id"]
        ui["mon"].set(m["name"])
        ui["preset"].configure(values=list(m["presets"]))
        load_preset(eng.active.get(m["id"]) or "Alap")
        do_preview()

    def pick_preset(name):
        if name != cur["name"] and not confirm_discard():
            ui["preset"].set(cur["name"])
            return
        load_preset(name)
        do_preview()

    def refresh_variant_ui(p):
        vs = p.get("variants") or {}
        names = list(vs)
        ui["var"].configure(values=names or ["–"], state="normal" if names else "disabled")
        ui["var"].set(cur["variant"] if names else "–")
        ui["vren"].configure(state="normal" if names else "disabled")
        ui["vdel"].configure(state="normal" if len(names) > 1 else "disabled")
        ui["vhk"].set((vs.get(cur["variant"]) or {}).get("hotkey", "") if names else "")
        ui["chk"].set(p.get("cycle_hotkey", "") if names else "")

    def pick_variant(vn, ask=True):
        p = eng.preset(cur["mid"], cur["name"]) or {}
        if vn not in (p.get("variants") or {}):
            return
        if ask and vn != cur["variant"] and not confirm_discard():
            ui["var"].set(cur["variant"])
            return
        cur["variant"] = vn
        eng.variant[(cur["mid"], cur["name"])] = vn       # a panel bezárása után is ez a változat marad érvényben
        cur["loading"] = True
        for k, val in zip("gcbv", pvals(p, vn)):
            set_slider(k, val)
        set_gains(pgain(p, vn))
        cur["loading"] = False
        ui["vhk"].set(p["variants"][vn].get("hotkey", ""))
        update_labels()
        do_preview()
        mark_clean()

    def ask_variant_name(text, title):
        n = ctk.CTkInputDialog(text=text, title=title).get_input()
        if not n or not n.strip():
            return None
        n = n.strip()
        if "|" in n:
            status("A névben nem lehet | jel.")
            return None
        if n in ((eng.preset(cur["mid"], cur["name"]) or {}).get("variants") or {}):
            status("Ilyen nevű változat már van.")
            return None
        return n

    def new_variant_dialog():
        mid, name = cur["mid"], cur["name"]
        p = eng.preset(mid, name)
        n = ask_variant_name("Az új változat neve (pl. a pálya):", "Új változat")
        if not p or not n:
            return
        g, c, b, v = vals_now()
        if not p.get("variants"):
            if n == "Alap":
                status("Ilyen nevű változat már van (az eddigi értékek 'Alap' néven az első változat lesznek).")
                return
            # az eddig mentett értékek lesznek az első változat; az új a mostani csúszkaállásból indul
            p["variants"] = {"Alap": {"gamma": p["gamma"], "contrast": p["contrast"], "brightness": p["brightness"],
                                      "vibrance": p.get("vibrance", 50), "gain": pgain(p)}}
        p["variants"][n] = {"gamma": g, "contrast": c, "brightness": b, "vibrance": v, "gain": gains_now()}
        eng.save_config()
        cur["variant"] = n
        eng.variant[(mid, name)] = n
        refresh_variant_ui(p)
        ui["vhk"].set("")
        mark_clean()
        status(f"Új változat: {n} (az értékei a mostani csúszkaállásból indultak)")

    def rename_variant_dialog():
        mid, name, old = cur["mid"], cur["name"], cur["variant"]
        p = eng.preset(mid, name)
        if not p or not old:
            return
        n = ask_variant_name(f"A(z) '{old}' változat új neve:", "Változat átnevezése")
        if not n:
            return
        with eng.lock:
            p["variants"] = {(n if k == old else k): v for k, v in p["variants"].items()}       # a sorrend megmarad
            if eng.variant.get((mid, name)) == old:
                eng.variant[(mid, name)] = n
        cur["variant"] = n
        eng.save_config()
        apply_hotkeys()                               # a gyorsgomb-azonosító tartalmazza a változat nevét
        refresh_variant_ui(p)
        mark_clean()
        status(f"Átnevezve: {old} → {n}")

    def delete_variant():
        mid, name, old = cur["mid"], cur["name"], cur["variant"]
        p = eng.preset(mid, name)
        if not p or len(p.get("variants") or {}) < 2 or not messagebox.askyesno(
                APP_NAME, f"Törlöd a(z) '{old}' változatot?", parent=root):
            return
        with eng.lock:
            del p["variants"][old]
            eng.variant.pop((mid, name), None)
            mirror_first(p)
        eng.save_config()
        apply_hotkeys()
        cur["variant"] = next(iter(p["variants"]))
        refresh_variant_ui(p)
        pick_variant(cur["variant"], ask=False)
        eng.sync(mid)
        status(f"Törölve: {old}")

    def collect():
        p = json.loads(json.dumps(eng.preset(cur["mid"], cur["name"]) or {}))        # mély másolat: a mentésig az eredeti nem változik
        g, c, b, v = vals_now()
        gn = gains_now()
        p.update(gamma=g, contrast=c, brightness=b, vibrance=v, gain=gn,
                 process=re.sub(r"(?i)\.exe$", "", ui["proc"].get().strip()))
        vs = p.get("variants")
        if vs and cur["variant"] in vs:
            vs[cur["variant"]].update(gamma=g, contrast=c, brightness=b, vibrance=v, gain=gn)
            vhk = ui["vhk"].get()
            if vhk:
                vs[cur["variant"]]["hotkey"] = vhk
            else:
                vs[cur["variant"]].pop("hotkey", None)
            mirror_first(p)
            if ui["chk"].get():
                p["cycle_hotkey"] = ui["chk"].get()
            else:
                p.pop("cycle_hotkey", None)
        for key, val in (("hotkey", ui["hotkey"].get()),
                         ("power", next((g_ for g_, n, _ in plans if n == ui["power"].get()), "")),
                         ("rgb", ui["rgb"].get())):
            if val and not (key == "rgb" and val.get("mode") == "none"):
                p[key] = val
            else:
                p.pop(key, None)
        return p

    def save_preset():
        mid, name = cur["mid"], cur["name"]
        p = collect()
        eng.mon(mid)["presets"][name] = p
        if cur.get("variant") in (p.get("variants") or {}):
            eng.variant[(mid, name)] = cur["variant"]         # a mentett változat lesz az érvényes
        eng.save_config()
        apply_hotkeys()
        was_on = eng.active.get(mid) == name
        if was_on:
            eng.sync(mid)
        else:
            eng.set_active(mid, name, True)   # mentéskor a preset be is kapcsol: ami a képernyőn van, az marad bezárás után is
        do_preview()                  # amíg a panel nyitva van, a kép a csúszkákat kövesse (a sync az éjszakaira ugrasztana)
        sync_switches()
        refresh_tray()
        mark_clean()
        status(f"Mentve: {name}" + ("" if was_on else " – bekapcsolva") +
               (f" – a gyorsgomb ({p['hotkey']}) foglalt, másikat válassz" if
                p.get("hotkey") and f"p|{mid}|{name}" in hk.failed else ""))

    def ask_name(text, title):
        """Új preset-nevet kér; None, ha mégse, üres vagy már foglalt."""
        n = ctk.CTkInputDialog(text=text, title=title).get_input()
        if not n or not n.strip():
            return None
        n = n.strip()
        if "|" in n:
            status("A névben nem lehet | jel.")
            return None
        if n in eng.mon(cur["mid"])["presets"]:
            status("Ilyen nevű preset már van.")
            return None
        return n

    def add_preset(n, p, msg):
        eng.mon(cur["mid"])["presets"][n] = p
        eng.save_config()
        ui["preset"].configure(values=list(eng.mon(cur["mid"])["presets"]))
        load_preset(n)
        status(msg)
        refresh_tray()

    def new_preset_dialog():
        n = ask_name("Az új preset neve:", "Új preset")
        if not n:
            return
        g, c, b, v = vals_now()
        p = new_preset((g, c, b, v), re.sub(r"(?i)\.exe$", "", ui["proc"].get().strip()))
        p["gain"] = gains_now()
        p["default"] = {"gamma": g, "contrast": c, "brightness": b, "vibrance": v, "gain": gains_now()}
        add_preset(n, p, f"Létrehozva: {n}")

    def copy_preset_dialog():
        src = cur["name"]
        n = ask_name(f"A(z) '{src}' másolatának neve:", "Preset másolása")
        if not n:
            return
        p = json.loads(json.dumps(collect()))         # mély másolat: a mostani csúszkaállással, energia/RGB profillal
        p.pop("hotkey", None)                         # gyorsgomb és játék-exe nem másolódik: ütköznének az eredetivel
        p["process"] = ""
        p.pop("cycle_hotkey", None)
        for v_ in (p.get("variants") or {}).values():
            v_.pop("hotkey", None)
        g, c, b, v = vals_now()
        p["default"] = {"gamma": g, "contrast": c, "brightness": b, "vibrance": v, "gain": gains_now()}
        add_preset(n, p, f"Másolva: {src} → {n} (gyorsgomb és játék nélkül)")

    def rename_preset_dialog():
        mid, old = cur["mid"], cur["name"]
        if old == "Alap":
            return
        n = ask_name(f"A(z) '{old}' új neve:", "Preset átnevezése")
        if not n:
            return
        with eng.lock:
            mon = eng.mon(mid)
            mon["presets"] = {(n if k == old else k): v for k, v in mon["presets"].items()}    # a sorrend megmarad
            if eng.active.get(mid) == old:
                eng.active[mid] = n
            for s in (eng.auto, eng.manual_off):
                if (mid, old) in s:
                    s.discard((mid, old))
                    s.add((mid, n))
            if (mid, old) in eng.variant:
                eng.variant[(mid, n)] = eng.variant.pop((mid, old))
        cur["name"] = n
        eng.save_config()
        apply_hotkeys()                               # a gyorsgomb-azonosító tartalmazza a preset nevét
        ui["preset"].configure(values=list(eng.mon(mid)["presets"]))
        ui["preset"].set(n)
        refresh_tray()
        status(f"Átnevezve: {old} → {n}")

    def export_all():
        f = filedialog.asksaveasfilename(title="Presetek exportálása", defaultextension=".json",
                                         initialfile=f"kepprofil-mentes-{time.strftime('%Y-%m-%d')}.json",
                                         filetypes=[("Képprofil mentés", "*.json")])
        if not f:
            return
        data = {"kepprofil_backup": 1, "exported": time.strftime("%Y-%m-%d %H:%M:%S"), "config": eng.cfg,
                "settings": {k: eng.set.get(k) for k in SETTINGS_KEYS}}
        try:
            Path(f).write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
            status(f"Exportálva: {f}")
        except OSError as e:
            status(f"Nem sikerült exportálni: {e.__class__.__name__}")

    def import_all():
        f = filedialog.askopenfilename(title="Presetek importálása", filetypes=[("Képprofil mentés", "*.json")])
        if not f:
            return
        data = _read_json(Path(f), None)
        cfg = data.get("config") if isinstance(data, dict) and "config" in data else data
        if not valid_config(cfg):
            status("Ez a fájl nem Képprofil-mentés (vagy sérült), nem importáltam.")
            return
        if not messagebox.askyesno(APP_NAME, "Az importálás felülírja az összes mostani presetet, gyorsgombot és az "
                                   "éjszakai mód beállításait.\nA mostani állapotról előbb biztonsági mentés készül "
                                   "(backup mappa). Folytatod?", parent=root):
            return
        _write_json(BACKUP_DIR / f"presets-{time.strftime('%Y-%m-%d_%H%M%S')}-import-elott.json", eng.cfg)
        saved = data.get("settings") if isinstance(data, dict) else None
        with eng.lock:
            eng.active.clear()
            eng.auto.clear()
            eng.manual_off.clear()
            eng.cfg = normalize_config(cfg)
            if isinstance(saved, dict):
                for k in SETTINGS_KEYS:
                    if saved.get(k) is not None:
                        eng.set[k] = saved[k]
            eng.save_config()
            eng.save_settings()
        ui["mon"].configure(values=[m["name"] for m in eng.cfg["monitors"]])
        ui["ns"][0].set(eng.set["night_strength"])
        eng.set_night_strength(eng.set["night_strength"])
        ui["nhk"].set(eng.set.get("night_hotkey", ""))
        ui["nehk"].set(eng.set.get("neutral_hotkey", ""))
        ui["base"].set(eng.set.get("base_rgb"))
        ui["toast"].select() if eng.set.get("toast", True) else ui["toast"].deselect()
        apply_hotkeys()
        eng.sync()
        pick_monitor(eng.cfg["monitors"][0]["name"])
        refresh_tray()
        status("Importálva: a presetek és beállítások betöltve.")

    def delete_preset():
        mid, name = cur["mid"], cur["name"]
        if name == "Alap" or not messagebox.askyesno(APP_NAME, f"Törlöd a(z) '{name}' presetet?", parent=root):
            return
        eng.set_active(mid, name, False)
        del eng.mon(mid)["presets"][name]
        eng.save_config()
        apply_hotkeys()
        pick_monitor(eng.mon(mid)["name"])
        status(f"Törölve: {name}")
        refresh_tray()

    def toggle_on():
        eng.set_active(cur["mid"], cur["name"], bool(ui["on"].get()))

    def preset_default():
        d = (eng.preset(cur["mid"], cur["name"]) or {}).get("default")
        if not d:
            return
        cur["loading"] = True
        for k, key in (("g", "gamma"), ("c", "contrast"), ("b", "brightness"), ("v", "vibrance")):
            set_slider(k, d.get(key, 2.2 if k == "g" else 50))
        set_gains(d.get("gain") or [100, 100, 100])
        cur["loading"] = False
        update_labels()
        do_preview()
        status("A preset alapértékei betöltve (a mentéshez nyomd meg a Mentés gombot).")

    def neutral_now():
        cur["loading"] = True
        for k, v in zip("gcbv", NEUTRAL):
            set_slider(k, v)
        set_gains([100, 100, 100])
        cur["loading"] = False
        update_labels()
        eng.show_neutral(cur["mid"])
        status("Semleges kép (gamma 1,00, vibrance 50, színek 100%), a presetek nem változtak.")

    def compare(down):
        eng.hold = down
        if down:
            eng.show_neutral(cur["mid"])
        else:
            do_preview()

    def running_dialog():
        top_ = ctk.CTkToplevel(root)
        top_.title("Futó programok")
        top_.geometry("460x460")
        top_.transient(root)
        top_.after(150, top_.grab_set)
        ctk.CTkLabel(top_, text="Indítsd el a játékot, majd válaszd ki a listából:").pack(anchor="w", padx=16, pady=(14, 6))
        lst = ctk.CTkScrollableFrame(top_)
        lst.pack(fill="both", expand=True, padx=16)
        choice = ctk.StringVar(value="")
        for name, title in visible_programs().items():
            ctk.CTkRadioButton(lst, text=f"{name}   —   {title[:48]}", variable=choice, value=name).pack(anchor="w", pady=3)

        def ok():
            if choice.get():
                ui["proc"].delete(0, "end")
                ui["proc"].insert(0, choice.get())
            top_.destroy()

        foot = ctk.CTkFrame(top_, fg_color="transparent")
        foot.pack(fill="x", padx=16, pady=12)
        ctk.CTkButton(foot, text="Kiválaszt", width=100, command=ok).pack(side="right")
        ctk.CTkButton(foot, text="Mégse", width=90, command=top_.destroy, **GREY).pack(side="right", padx=8)

    def browse_exe():
        f = filedialog.askopenfilename(title="Válaszd ki a játék .exe fájlját", filetypes=[("Programok", "*.exe")])
        if f:
            ui["proc"].delete(0, "end")
            ui["proc"].insert(0, Path(f).stem)

    def night_click():
        if bool(ui["night"].get()) != (cur["mid"] in eng.night_mons):
            eng.toggle_night(cur["mid"])

    def set_setting(key, value):
        eng.set[key] = value
        eng.save_settings()
        if key.endswith("hotkey"):
            apply_hotkeys()

    def open_path(p):
        try:
            if not p.exists() and p.suffix:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.touch()
            os.startfile(str(p))
        except OSError as e:
            status(f"Nem sikerült megnyitni: {e.__class__.__name__}")

    def auto_click():
        set_autostart(bool(ui["auto"].get()))

    def toast_click():
        set_setting("toast", bool(ui["toast"].get()))

    toast_state = {"win": None, "job": None}

    def show_toast(text, mid=None):
        """Kattintható-átlátszó, fókuszt nem lopó, mindig felül lévő felirat a monitor tetején (a játék fölött is)."""
        import tkinter as tk
        if toast_state["job"]:
            root.after_cancel(toast_state["job"])
        if toast_state["win"] is not None:
            try:
                toast_state["win"].destroy()
            except Exception:
                pass
        bg = "#14161a"
        w = tk.Toplevel(root)
        toast_state["win"] = w
        w.withdraw()
        w.overrideredirect(True)
        w.configure(bg=bg)
        w.attributes("-topmost", True)
        w.attributes("-alpha", 0.0)
        tk.Label(w, text="KÉPPROFIL", fg="#7fb2ff", bg=bg, font=("Segoe UI", 9, "bold")).pack(padx=28, pady=(12, 0))
        tk.Label(w, text=text, fg="#ffffff", bg=bg, font=("Segoe UI", 20, "bold")).pack(padx=28, pady=(0, 14))
        w.update_idletasks()
        ww, wh = w.winfo_reqwidth(), w.winfo_reqheight()
        l, t, r, b = monitor_rect(mid) or (0, 0, w.winfo_screenwidth(), w.winfo_screenheight())
        w.geometry(f"{ww}x{wh}+{l + (r - l - ww) // 2}+{t + int((b - t) * 0.06)}")
        w.deiconify()
        w.update_idletasks()
        try:                                                  # átkattintható, nem aktiválódik, nincs tálcagomb
            hwnd = user32.GetParent(w.winfo_id()) or w.winfo_id()
            ex = user32.GetWindowLongW(hwnd, -20)
            user32.SetWindowLongW(hwnd, -20, ex | 0x00080000 | 0x00000020 | 0x08000000 | 0x00000080)
            user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0040)   # TOPMOST, aktiválás nélkül
        except Exception:
            pass

        def fade(step):
            if toast_state["win"] is not w:
                return
            a = min(0.92, step * 0.23) if step < 5 else (0.92 if step < 5 + 18 else max(0.0, 0.92 - (step - 23) * 0.15))
            try:
                w.attributes("-alpha", a)
            except Exception:
                return
            if step > 23 and a <= 0.0:
                w.destroy()
                toast_state["win"] = None
                return
            toast_state["job"] = root.after(100 if 5 <= step < 23 else 40, lambda: fade(step + 1))

        fade(1)

    def save_base_rgb():
        status("Mentés…")

        def work():
            try:
                q.put(("base_saved", "", eng.rgb.snapshot()))
            except Exception as e:
                q.put(("base_saved", f"Nem sikerült: {e.__class__.__name__}. Fut az OpenRGB szolgáltatás?", None))

        threading.Thread(target=work, daemon=True).start()

    def apply_hotkeys():
        hk.set(eng.hotkey_map())

    # ---- tálca
    state = {"icon": None}

    def refresh_tray():
        ic = state["icon"]
        if ic is None:
            return
        try:
            ic.icon = make_icon(bool(eng.active) or bool(eng.night_mons))
            ic.update_menu()
        except Exception:
            pass

    def tray_menu():
        def toggler(mid, name):
            return lambda icon, item: q.put(("toggle", mid, name))

        def checker(mid, name):
            return lambda item: eng.active.get(mid) == name

        items = [pystray.MenuItem("Panel megnyitása", lambda icon, item: q.put(("panel",)), default=True),
                 pystray.Menu.SEPARATOR]
        for m in eng.cfg["monitors"]:
            if not find_dev(m["id"]):
                continue
            items.append(pystray.MenuItem(m["name"], lambda icon, item: None, enabled=False))
            for name, p in m["presets"].items():
                items.append(pystray.MenuItem(name + (f"   ({p['hotkey']})" if p.get("hotkey") else ""),
                                              toggler(m["id"], name), checked=checker(m["id"], name)))
            items.append(pystray.MenuItem("Éjszakai mód", (lambda mid_: lambda icon, item: q.put(("night", mid_)))(m["id"]),
                                          checked=(lambda mid_: lambda item: mid_ in eng.night_mons)(m["id"])))
        items += [pystray.Menu.SEPARATOR,
                  pystray.MenuItem("Éjszakai mód (minden monitor)", lambda icon, item: q.put(("night",)),
                                   checked=lambda item: bool(eng.night_mons)),
                  pystray.MenuItem("Semleges kép (minden kikapcsol)", lambda icon, item: q.put(("neutral",))),
                  pystray.Menu.SEPARATOR,
                  pystray.MenuItem("Kilépés", lambda icon, item: q.put(("quit",)))]
        return items

    state["icon"] = pystray.Icon("kepprofil",make_icon(False), APP_NAME, pystray.Menu(tray_menu))
    state["icon"].run_detached()

    # ---- ablak megjelenítése / elrejtése
    def show_panel():
        eng.panel_open = True
        root.deiconify()
        root.lift()
        root.focus_force()
        sync_info()

    def hide_panel():
        eng.panel_open = False
        eng.hold = False
        root.withdraw()
        eng.sync()                    # a mentetlen előnézet helyére a bekapcsolt állapot kerül

    def request_close():
        """Bezárás: ha vannak mentetlen módosítások, rákérdez (mentés / eldobás / maradás)."""
        if is_dirty():
            ans = messagebox.askyesnocancel(APP_NAME, "Mentetlen módosításaid vannak.\nMented őket a presetbe?\n\n"
                                            "Igen: mentés és bezárás • Nem: eldobás és bezárás • Mégse: marad az ablak",
                                            parent=root)
            if ans is None:
                return
            if ans:
                save_preset()
            else:
                load_preset(cur["name"])                      # a mentetlen állapot helyére a mentett kerül
        hide_panel()

    root.protocol("WM_DELETE_WINDOW", request_close)

    def sync_info():
        nv = "NVIDIA vibrance elérhető" if eng.nv.ok else "NVIDIA vibrance nem elérhető (nincs NVIDIA driver)"
        failed = [a for a in hk.failed]
        ui["info"].configure(text=f"{APP_NAME} {VERSION}. {nv}. Adatok: {DATA_DIR}" + (
            f"\nFoglalt gyorsgomb(ok): {', '.join(failed)}" if failed else ""))
        ui["auto"].select() if autostart_enabled() else ui["auto"].deselect()

    def pump():
        try:
            while True:
                m = q.get_nowait()
                k = m[0]
                if k == "panel":
                    show_panel()
                elif k == "toast":
                    show_toast(m[1], m[2])
                elif k == "toggle":
                    eng.toggle_preset(m[1], m[2])
                elif k == "night":
                    eng.toggle_night(m[1] if len(m) > 1 else None)
                elif k == "neutral":
                    eng.neutral_all()
                elif k == "hk":
                    eng.run_action(m[1])
                elif k == "refresh":
                    refresh_tray()
                    if root.state() != "withdrawn":
                        sync_switches()
                        if eng.log:
                            status(f"{eng.log[-1][0]}  {eng.log[-1][1]}")
                elif k == "base_saved":
                    if not m[1]:
                        spec = {"mode": "snapshot", "value": m[2]}
                        ui["base"].set(spec)
                        set_setting("base_rgb", spec)
                        eng.rgb_applied = dict(spec)       # a mostani állapot az alap: nincs mit visszaállítani
                    status(m[1] or f"Elmentve: a mostani RGB-állapot lett az alap ({len(m[2])} eszköz).")
                elif k == "quit":
                    quit_app()
                    return
        except queue.Empty:
            pass
        root.after(100, pump)

    def quit_app():
        eng.shutdown()
        try:
            state["icon"].stop()
        except Exception:
            pass
        root.destroy()

    # ---- indítás
    ui["ns"][0].set(eng.set["night_strength"])
    ui["ns"][0].configure(command=lambda v: (update_labels(), eng.set_night_strength(v), eng.save_settings()))
    ui["nhk"].set(eng.set.get("night_hotkey", ""))
    ui["nehk"].set(eng.set.get("neutral_hotkey", ""))
    ui["base"].set(eng.set.get("base_rgb"))
    ui["toast"].select() if eng.set.get("toast", True) else ui["toast"].deselect()
    pick_monitor(eng.cfg["monitors"][0]["name"] if eng.cfg["monitors"] else "")
    poll_dirty()
    eng.sync()                         # induláskor ismert (semleges) állapot
    threading.Thread(target=eng.fx_loop, daemon=True).start()

    def watch():
        while not eng.stop:
            try:
                eng.watch_tick()
            except Exception as e:
                eng.say(f"Figyelő hiba: {e}")
            time.sleep(2)

    threading.Thread(target=watch, daemon=True).start()

    def wait_show():
        while not eng.stop:
            if kernel32.WaitForSingleObject(show_ev, 1000) == 0:      # a második indítás jelzett
                q.put(("panel",))

    threading.Thread(target=wait_show, daemon=True).start()
    apply_hotkeys()
    pump()
    HOOK.update(ui=ui, cur=cur, root=root, eng=eng, tabs=tabs, save=save_preset, is_dirty=is_dirty, on_slider=on_slider,
                collect=collect)                   # csak az automatikus tesztek használják
    if start_hidden:
        root.withdraw()
    else:
        show_panel()
    root.mainloop()
