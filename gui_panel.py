"""A főablak (panel) viselkedése: a kiválasztott monitor és preset betöltése, a csúszkák élő előnézete, a mentetlen módosítások
követése, mentés, kapcsolók és beállítások. Az elrendezést a `gui_layout`, a preset- és változatműveleteket a
`gui_preset_dialogs` adja; a motort, a gyorsgombokat, a tálcát és az üzenetsort az `app` (gui.App) adja."""
import json
import re
import threading
from contextlib import contextmanager
from pathlib import Path
from tkinter import filedialog, messagebox
from types import SimpleNamespace

import customtkinter as ctk

from config import mirror_first, pgain, pvals
from consts import APP_NAME, BASE_PRESET_NAME, DATA_DIR, NEUTRAL, VERSION
from gui_dialogs import choose_running_program
from gui_layout import NO_POWER_PLAN, build_main_window
from gui_preset_dialogs import PresetActions
from hw import find_dev
from system import autostart_enabled, open_native, set_autostart

IMAGE_SLIDERS = ("gamma", "contrast", "brightness", "vibrance")      # a preset értékeinek sorrendje
GAIN_SLIDERS = ("red_gain", "green_gain", "blue_gain")
LABELLED_SLIDERS = IMAGE_SLIDERS + GAIN_SLIDERS + ("night_strength",)
GAMMA_SCALE = 2.2                  # a gamma-csúszka az NVIDIA-panel skáláján megy (1,00 = semleges); a mentett érték a régi
                                   # (2,2 = semleges), így a meglévő presetek nem változnak: belső érték = csúszka * 2,2
NEUTRAL_GAINS = [100, 100, 100]
PREVIEW_DELAY_MS = 40              # a csúszka mozgatása után ennyivel megy ki az előnézet (egy mozgás = egy küldés)
DIRTY_POLL_MS = 400


def set_switch(switch, on):
    switch.select() if on else switch.deselect()


def without_exe_suffix(text):
    """A játék exe-neve kiterjesztés nélkül (a figyelő a program nevét így hasonlítja)."""
    return re.sub(r"(?i)\.exe$", "", text.strip())


class Panel:
    """A főablak tartalma. `app` adja: `root`, `eng`, `hotkeys`, `overlay`, `toast`, `post(üzenet)`, `apply_hotkeys()`,
    `refresh_tray()`."""

    def __init__(self, app, power_plans):
        self.app = app
        self.root = app.root
        self.eng = app.eng
        self.power_plans = power_plans                         # (azonosító, név, ...) sorok
        self.widgets = SimpleNamespace()
        self.monitor_id = None
        self.preset_name = None
        self.variant_name = None
        self.loading = False                                   # igaz, amíg a csúszkákat töltjük: nincs előnézet
        self.preview_job = None
        self.clean_snapshot = None                             # a legutóbbi betöltés/mentés utáni felület (collect_preset)
        self.preset_actions = PresetActions(self)
        page = ctk.CTkFrame(self.root, fg_color="transparent")
        page.pack(fill="both", expand=True, padx=18, pady=14)
        build_main_window(page, self)
        self.root.protocol("WM_DELETE_WINDOW", self.request_close)

    def start(self):
        """Az ablak feltöltése a mentett beállításokkal; az első monitor és preset betöltése."""
        self.show_settings()
        self.widgets.night_strength.slider.configure(command=self.on_night_strength)
        self.pick_monitor(self.eng.mons()[0]["name"] if self.eng.mons() else "")
        self.poll_dirty()

    # ---- állapotsor, apró segédek

    def set_status(self, text):
        self.widgets.status_label.configure(text=text)

    def monitor_named(self, name):
        monitors = self.eng.mons()
        return next((monitor for monitor in monitors if monitor["name"] == name), monitors[0])

    @contextmanager
    def loading_values(self):
        """A csúszkák programból való beállítása közben nem megy ki előnézet."""
        self.loading = True
        try:
            yield
        finally:
            self.loading = False

    # ---- csúszkák

    def set_image_slider(self, name, value):
        slider = getattr(self.widgets, name).slider
        slider.set(value / GAMMA_SCALE if name == "gamma" else value)

    def set_image_values(self, values):
        """`values`: (gamma, kontraszt, fényerő, vibrance) a mentett skálán."""
        for name, value in zip(IMAGE_SLIDERS, values):
            self.set_image_slider(name, value)

    def image_values(self):
        """A csúszkák állása: (gamma a mentett skálán, kontraszt, fényerő, vibrance)."""
        widgets = self.widgets
        gamma = round(round(widgets.gamma.slider.get(), 2) * GAMMA_SCALE, 4)
        return (gamma, round(widgets.contrast.slider.get()), round(widgets.brightness.slider.get()),
                round(widgets.vibrance.slider.get()))

    def color_gains(self):
        return [round(getattr(self.widgets, name).slider.get()) for name in GAIN_SLIDERS]

    def set_color_gains(self, gains):
        for name, gain in zip(GAIN_SLIDERS, gains):
            getattr(self.widgets, name).slider.set(gain)

    def refresh_value_labels(self):
        for name in LABELLED_SLIDERS:
            row = getattr(self.widgets, name)
            row.value_box.configure(text=row.format_value(row.slider.get()))

    def reset_colors(self):
        self.set_color_gains(NEUTRAL_GAINS)
        self.on_slider()

    def on_slider(self):
        self.refresh_value_labels()
        if self.loading:
            return
        if self.preview_job:
            self.root.after_cancel(self.preview_job)
        self.preview_job = self.root.after(PREVIEW_DELAY_MS, self.send_preview)

    def send_preview(self):
        self.preview_job = None
        shown = self.eng.preview(self.monitor_id, self.image_values(), self.color_gains())
        self.set_status("" if shown else "Hiba: a monitor nem található vagy nem sikerült beállítani.")

    def on_night_strength(self, value):
        self.refresh_value_labels()
        self.eng.set_night_strength(value)
        self.eng.save_settings()

    def update_vibrance_state(self):
        """A vibrance-csúszka csak ott aktív, ahol hat; máshol szürke, az okkal."""
        widgets = self.widgets
        usable, hint = self.eng.display.vibrance_state(find_dev(self.monitor_id))
        for part in (widgets.vibrance.slider, widgets.vibrance.value_box):
            part.configure(state="normal" if usable else "disabled")
        if usable:
            widgets.vibrance_hint.pack_forget()
        else:
            widgets.vibrance_hint.configure(text=hint)
            widgets.vibrance_hint.pack(fill="x", pady=(6, 0), before=widgets.image_buttons_row)

    # ---- monitor, preset és változat kiválasztása

    def pick_monitor(self, name, ask=False):
        widgets = self.widgets
        if ask and self.monitor_named(name)["id"] != self.monitor_id and not self.confirm_discard():
            current_name = next((monitor["name"] for monitor in self.eng.cfg["monitors"]
                                 if monitor["id"] == self.monitor_id), name)
            widgets.monitor_selector.set(self.monitor_named(current_name)["name"])
            return
        monitor = self.monitor_named(name)
        self.monitor_id = monitor["id"]
        widgets.monitor_selector.set(monitor["name"])
        widgets.preset_menu.configure(values=list(monitor["presets"]))
        self.load_preset(self.eng.active.get(monitor["id"]) or BASE_PRESET_NAME)
        self.update_vibrance_state()
        self.send_preview()

    def pick_preset(self, name):
        if name != self.preset_name and not self.confirm_discard():
            self.widgets.preset_menu.set(self.preset_name)
            return
        self.load_preset(name)
        self.send_preview()

    def load_preset(self, name):
        """A felület feltöltése a preset (és az érvényes változata) értékeivel."""
        widgets = self.widgets
        preset = self.eng.preset(self.monitor_id, name)
        if preset is None:
            return
        self.preset_name = name
        self.variant_name = self.eng.cur_variant(self.monitor_id, name)
        with self.loading_values():
            widgets.preset_menu.set(name)
            self.set_image_values(pvals(preset, self.variant_name))
            self.set_color_gains(pgain(preset, self.variant_name))
            self.refresh_variant_controls(preset)
            self._show_profile_fields(preset)
            widgets.defaults_button.configure(state="normal" if preset.get("default") else "disabled")
            protected_state = "disabled" if name == BASE_PRESET_NAME else "normal"
            widgets.delete_preset_button.configure(state=protected_state)
            widgets.rename_preset_button.configure(state=protected_state)
        self.refresh_value_labels()
        self.sync_switches()
        self.mark_clean()

    def _show_profile_fields(self, preset):
        """A játék exe-je, a gyorsgomb, az energiaprofil és az RGB mezői."""
        widgets = self.widgets
        widgets.process_entry.delete(0, "end")
        if preset.get("process"):
            widgets.process_entry.insert(0, preset["process"])
        widgets.preset_hotkey.set(preset.get("hotkey", ""))
        plan_name = next((name for plan_id, name, _ in self.power_plans if plan_id == preset.get("power")), NO_POWER_PLAN)
        widgets.power_plan_menu.set(plan_name)
        widgets.rgb_picker.set(preset.get("rgb"))

    def refresh_variant_controls(self, preset):
        widgets = self.widgets
        variants = preset.get("variants") or {}
        names = list(variants)
        widgets.variant_menu.configure(values=names or ["–"], state="normal" if names else "disabled")
        widgets.variant_menu.set(self.variant_name if names else "–")
        widgets.rename_variant_button.configure(state="normal" if names else "disabled")
        widgets.delete_variant_button.configure(state="normal" if len(names) > 1 else "disabled")
        variant_hotkey = (variants.get(self.variant_name) or {}).get("hotkey", "") if names else ""
        widgets.variant_hotkey.set(variant_hotkey)

    def pick_variant(self, variant_name, ask=True):
        preset = self.eng.preset(self.monitor_id, self.preset_name) or {}
        if variant_name not in (preset.get("variants") or {}):
            return
        if ask and variant_name != self.variant_name and not self.confirm_discard():
            self.widgets.variant_menu.set(self.variant_name)
            return
        self.variant_name = variant_name
        self.eng.variant[(self.monitor_id, self.preset_name)] = variant_name   # a panel bezárása után is ez marad érvényben
        with self.loading_values():
            self.set_image_values(pvals(preset, variant_name))
            self.set_color_gains(pgain(preset, variant_name))
        self.widgets.variant_hotkey.set(preset["variants"][variant_name].get("hotkey", ""))
        self.refresh_value_labels()
        self.send_preview()
        self.mark_clean()

    def sync_switches(self):
        """A bekapcsolva- és az éjszakai kapcsoló a motor mostani állapotát mutatja."""
        widgets = self.widgets
        set_switch(widgets.enabled_switch, self.eng.active.get(self.monitor_id) == self.preset_name)
        set_switch(widgets.night_switch, self.monitor_id in self.eng.night_mons)
        monitor_name = (self.eng.mon(self.monitor_id) or {}).get("name", "")
        widgets.night_switch.configure(text="Éjszakai mód ezen a monitoron: " + monitor_name)

    # ---- mentetlen módosítások

    def mark_clean(self):
        self.clean_snapshot = self.collect_preset()
        self.widgets.dirty_label.configure(text="")

    def is_dirty(self):
        return (bool(self.preset_name) and self.clean_snapshot is not None
                and self.collect_preset() != self.clean_snapshot)

    def confirm_discard(self):
        return (not self.is_dirty()) or messagebox.askyesno(
            APP_NAME, "Mentetlen módosításaid vannak ezen a presetten.\nEldobod őket?", parent=self.root)

    def poll_dirty(self):
        try:
            if self.root.state() != "withdrawn":
                self.widgets.dirty_label.configure(text="● Mentetlen módosítás" if self.is_dirty() else "")
        except Exception:
            pass
        self.root.after(DIRTY_POLL_MS, self.poll_dirty)

    # ---- összegyűjtés és mentés

    def collect_preset(self):
        """A felület mostani állapota preset-szótárként (a motor szótárát nem módosítja)."""
        widgets = self.widgets
        preset = json.loads(json.dumps(self.eng.preset(self.monitor_id, self.preset_name) or {}))   # mély másolat
        gamma, contrast, brightness, vibrance = self.image_values()
        gains = self.color_gains()
        preset.update(gamma=gamma, contrast=contrast, brightness=brightness, vibrance=vibrance, gain=gains,
                      process=self.entered_process())
        variants = preset.get("variants")
        if variants and self.variant_name in variants:
            variant = variants[self.variant_name]
            variant.update(gamma=gamma, contrast=contrast, brightness=brightness, vibrance=vibrance, gain=gains)
            self._set_or_drop(variant, "hotkey", widgets.variant_hotkey.get())
            mirror_first(preset)
        plan_id = next((plan_id for plan_id, name, _ in self.power_plans if name == widgets.power_plan_menu.get()), "")
        rgb = widgets.rgb_picker.get()
        self._set_or_drop(preset, "hotkey", widgets.preset_hotkey.get())
        self._set_or_drop(preset, "power", plan_id)
        self._set_or_drop(preset, "rgb", None if rgb.get("mode") == "none" else rgb)
        return preset

    def entered_process(self):
        """A játék exe-neve a mezőből, kiterjesztés nélkül."""
        return without_exe_suffix(self.widgets.process_entry.get())

    @staticmethod
    def _set_or_drop(target, key, value):
        """Az érték bekerül a szótárba; üres érték esetén a kulcs kikerül belőle."""
        if value:
            target[key] = value
        else:
            target.pop(key, None)

    def save_preset(self):
        monitor_id, name = self.monitor_id, self.preset_name
        preset = self.collect_preset()
        self.eng.mon(monitor_id)["presets"][name] = preset
        if self.variant_name in (preset.get("variants") or {}):
            self.eng.variant[(monitor_id, name)] = self.variant_name         # a mentett változat lesz az érvényes
        self.eng.save_config()
        self.app.apply_hotkeys()
        was_on = self.eng.active.get(monitor_id) == name
        if was_on:
            self.eng.sync(monitor_id)
        else:
            self.eng.set_active(monitor_id, name, True)   # mentéskor a preset be is kapcsol: ami a képernyőn van, az marad
        self.send_preview()                   # amíg a panel nyitva van, a kép a csúszkákat kövesse (a sync az éjszakaira ugrasztana)
        self.sync_switches()
        self.app.refresh_tray()
        self.mark_clean()
        message = f"Mentve: {name}" + ("" if was_on else " – bekapcsolva")
        if preset.get("hotkey") and f"p|{monitor_id}|{name}" in self.app.hotkeys.failed:
            message += f" – a gyorsgomb ({preset['hotkey']}) foglalt, másikat válassz"
        self.set_status(message)

    # ---- gombok

    def toggle_enabled(self):
        self.eng.set_active(self.monitor_id, self.preset_name, bool(self.widgets.enabled_switch.get()))

    def toggle_night(self):
        if bool(self.widgets.night_switch.get()) != (self.monitor_id in self.eng.night_mons):
            self.eng.toggle_night(self.monitor_id)

    def load_preset_defaults(self):
        defaults = (self.eng.preset(self.monitor_id, self.preset_name) or {}).get("default")
        if not defaults:
            return
        with self.loading_values():
            self.set_image_values((defaults.get("gamma", GAMMA_SCALE), defaults.get("contrast", 50),
                                   defaults.get("brightness", 50), defaults.get("vibrance", 50)))
            self.set_color_gains(defaults.get("gain") or NEUTRAL_GAINS)
        self.refresh_value_labels()
        self.send_preview()
        self.set_status("A preset alapértékei betöltve (a mentéshez nyomd meg a Mentés gombot).")

    def show_neutral(self):
        with self.loading_values():
            self.set_image_values(NEUTRAL)
            self.set_color_gains(NEUTRAL_GAINS)
        self.refresh_value_labels()
        self.eng.show_neutral(self.monitor_id)
        self.set_status("Semleges kép (gamma 1,00, vibrance 50, színek 100%), a presetek nem változtak.")

    def compare_with_neutral(self, held):
        """Az „Összehasonlítás" gomb: nyomva tartva a semleges kép látszik, felengedve a csúszkák képe."""
        self.eng.hold = held
        if held:
            self.eng.show_neutral(self.monitor_id)
        else:
            self.send_preview()

    def choose_running_program(self):
        choose_running_program(self.root, self._set_process)

    def browse_executable(self):
        file_name = filedialog.askopenfilename(title="Válaszd ki a játék .exe fájlját", filetypes=[("Programok", "*.exe")])
        if file_name:
            self._set_process(Path(file_name).stem)

    def _set_process(self, program):
        self.widgets.process_entry.delete(0, "end")
        self.widgets.process_entry.insert(0, program)

    def show_test_toast(self):
        self.app.toast.show("Értesítés próba", self.monitor_id)

    def open_in_system(self, path):
        try:
            if not path.exists() and path.suffix:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            open_native(path)
        except OSError as error:
            self.set_status(f"Nem sikerült megnyitni: {error.__class__.__name__}")

    # ---- beállítások

    def set_setting(self, key, value):
        self.eng.set[key] = value
        self.eng.save_settings()
        if key.endswith("hotkey"):
            self.app.apply_hotkeys()

    def toggle_autostart(self):
        set_autostart(bool(self.widgets.autostart_switch.get()))

    def toggle_toast_setting(self):
        self.set_setting("toast", bool(self.widgets.toast_switch.get()))

    def show_settings(self):
        """A mentett beállítások (éjszakai erősség, gyorsgombok, RGB alap, értesítés) a megfelelő mezőkbe."""
        widgets, settings = self.widgets, self.eng.set
        widgets.night_strength.slider.set(settings["night_strength"])
        widgets.night_hotkey.set(settings.get("night_hotkey", ""))
        widgets.neutral_hotkey.set(settings.get("neutral_hotkey", ""))
        widgets.cycle_hotkey.set(settings.get("cycle_hotkey", ""))
        widgets.overlay_hotkey.set(settings.get("overlay_hotkey", ""))
        widgets.base_rgb_picker.set(settings.get("base_rgb"))
        set_switch(widgets.toast_switch, settings.get("toast", True))

    def reload_after_import(self):
        """Importálás után: minden mező és a gyorsgombok a betöltött adatokból."""
        self.widgets.monitor_selector.configure(values=[monitor["name"] for monitor in self.eng.mons()])
        self.show_settings()
        self.eng.set_night_strength(self.eng.set["night_strength"])
        self.app.apply_hotkeys()
        self.eng.sync()
        self.pick_monitor(self.eng.mons()[0]["name"])
        self.app.refresh_tray()

    def save_current_rgb_as_base(self):
        """A mostani RGB-állapot elmentése alapállapotnak (a lekérdezés lassú: külön szálon fut)."""
        self.set_status("Mentés…")

        def work():
            try:
                self.app.post(("base_saved", "", self.eng.rgb.snapshot()))
            except Exception as error:
                self.app.post(("base_saved",
                               f"Nem sikerült: {error.__class__.__name__}. Fut az OpenRGB szolgáltatás?", None))

        threading.Thread(target=work, daemon=True).start()

    def on_base_saved(self, error, snapshot):
        if not error:
            spec = {"mode": "snapshot", "value": snapshot}
            self.widgets.base_rgb_picker.set(spec)
            self.set_setting("base_rgb", spec)
            self.eng.rgb_applied = dict(spec)       # a mostani állapot az alap: nincs mit visszaállítani
        self.set_status(error or f"Elmentve: a mostani RGB-állapot lett az alap ({len(snapshot)} eszköz).")

    # ---- megjelenítés, bezárás, a motor jelzései

    def show(self):
        self.app.overlay.close()                  # a főablak és az overlay nem szerkeszthet egyszerre
        self.eng.panel_open = True
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.refresh_info()

    def hide(self):
        self.eng.panel_open = False
        self.eng.hold = False
        self.root.withdraw()
        self.eng.sync()                           # a mentetlen előnézet helyére a bekapcsolt állapot kerül

    def request_close(self):
        """Bezárás: ha vannak mentetlen módosítások, rákérdez (mentés / eldobás / maradás)."""
        if self.is_dirty():
            answer = messagebox.askyesnocancel(
                APP_NAME, "Mentetlen módosításaid vannak.\nMented őket a presetbe?\n\n"
                "Igen: mentés és bezárás • Nem: eldobás és bezárás • Mégse: marad az ablak", parent=self.root)
            if answer is None:
                return
            if answer:
                self.save_preset()
            else:
                self.load_preset(self.preset_name)    # a mentetlen állapot helyére a mentett kerül
        self.hide()

    def refresh_info(self):
        widgets = self.widgets
        vibrance_text = ("NVIDIA vibrance elérhető" if self.eng.display.vibrance_ok
                         else "NVIDIA vibrance nem elérhető (nincs NVIDIA driver)")
        failed = list(self.app.hotkeys.failed)
        failed_text = f"\nFoglalt gyorsgomb(ok): {', '.join(failed)}" if failed else ""
        widgets.info_label.configure(text=f"{APP_NAME} {VERSION}. {vibrance_text}. Adatok: {DATA_DIR}{failed_text}")
        set_switch(widgets.autostart_switch, autostart_enabled())

    def on_engine_refresh(self):
        """A motor állapota változott: a kapcsolók és az állapotsor követi (rejtett ablaknál nincs mit frissíteni)."""
        if self.root.state() != "withdrawn":
            self.sync_switches()
            if self.eng.log:
                self.set_status(f"{self.eng.log[-1][0]}  {self.eng.log[-1][1]}")

    def on_monitors_changed(self):
        """Monitor került a gépre / lekerült róla: a választó, a gyorsgombok és a tálcamenü is csak a csatlakoztatottakat mutatja."""
        monitors = self.eng.mons()
        self.widgets.monitor_selector.configure(values=[monitor["name"] for monitor in monitors])
        shown = next((monitor for monitor in monitors if monitor["id"] == self.monitor_id), None)
        if shown:
            self.widgets.monitor_selector.set(shown["name"])        # a values átírása a kijelölést elveszi
        elif monitors:
            self.pick_monitor(monitors[0]["name"])                  # az épp szerkesztett monitor lekerült: a mentetlen módosítás elvész
        self.app.apply_hotkeys()
        self.app.refresh_tray()
        self.set_status(f"Monitorok: {', '.join(monitor['name'] for monitor in monitors)}")
