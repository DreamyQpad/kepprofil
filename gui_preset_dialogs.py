"""A preset- és változatműveletek párbeszédei: név bekérése, megerősítés, fájlválasztás, majd a művelet a `preset_ops`-szal és
a felület frissítése a `Panel` metódusaival."""
import json
import time
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from config import BACKUP_DIR, _read_json
from consts import APP_NAME, BASE_PRESET_NAME
import preset_ops


class PresetActions:
    """A `Panel` preset- és változatgombjainak műveletei. A panel állapotát (`monitor_id`, `preset_name`, `variant_name`)
    a panelből olvassa, és a felület frissítését a panel metódusain keresztül kéri."""

    def __init__(self, panel):
        self.panel = panel

    # ---- változatok

    def new_variant(self):
        panel = self.panel
        monitor_id, preset_name = panel.monitor_id, panel.preset_name
        preset = panel.eng.preset(monitor_id, preset_name)
        variant_name = self._ask_variant_name("Az új változat neve (pl. a pálya):", "Új változat")
        if not preset or not variant_name:
            return
        values = preset_ops.values_dict(*panel.image_values(), panel.color_gains())     # a mostani csúszkaállásból indul
        error = preset_ops.add_variant(panel.eng, monitor_id, preset_name, variant_name, values)
        if error:
            panel.set_status(error)
            return
        panel.variant_name = variant_name
        panel.refresh_variant_controls(preset)
        panel.widgets.variant_hotkey.set("")
        panel.mark_clean()
        panel.set_status(f"Új változat: {variant_name} (az értékei a mostani csúszkaállásból indultak)")

    def rename_variant(self):
        panel = self.panel
        monitor_id, preset_name, old_name = panel.monitor_id, panel.preset_name, panel.variant_name
        preset = panel.eng.preset(monitor_id, preset_name)
        if not preset or not old_name:
            return
        new_name = self._ask_variant_name(f"A(z) '{old_name}' változat új neve:", "Változat átnevezése")
        if not new_name:
            return
        preset_ops.rename_variant(panel.eng, monitor_id, preset_name, old_name, new_name)
        panel.variant_name = new_name
        panel.app.apply_hotkeys()                         # a gyorsgomb-azonosító tartalmazza a változat nevét
        panel.refresh_variant_controls(preset)
        panel.mark_clean()
        panel.set_status(f"Átnevezve: {old_name} → {new_name}")

    def delete_variant(self):
        panel = self.panel
        monitor_id, preset_name, variant_name = panel.monitor_id, panel.preset_name, panel.variant_name
        preset = panel.eng.preset(monitor_id, preset_name)
        if not preset or len(preset.get("variants") or {}) < 2 or not messagebox.askyesno(
                APP_NAME, f"Törlöd a(z) '{variant_name}' változatot?", parent=panel.root):
            return
        panel.variant_name = preset_ops.delete_variant(panel.eng, monitor_id, preset_name, variant_name)
        panel.app.apply_hotkeys()
        panel.refresh_variant_controls(preset)
        panel.pick_variant(panel.variant_name, ask=False)
        panel.eng.sync(monitor_id)
        panel.set_status(f"Törölve: {variant_name}")

    # ---- presetek

    def new_preset(self):
        panel = self.panel
        name = self._ask_preset_name("Az új preset neve:", "Új preset")
        if not name:
            return
        values = (*panel.image_values(), panel.color_gains())
        self._add_preset(name, preset_ops.blank_preset(values, panel.entered_process()), f"Létrehozva: {name}")

    def copy_preset(self):
        panel = self.panel
        source_name = panel.preset_name
        name = self._ask_preset_name(f"A(z) '{source_name}' másolatának neve:", "Preset másolása")
        if not name:
            return
        values = (*panel.image_values(), panel.color_gains())
        copy = preset_ops.copy_of_preset(panel.collect_preset(), values)      # a mostani csúszkaállással, energia/RGB profillal
        self._add_preset(name, copy, f"Másolva: {source_name} → {name} (gyorsgomb és játék nélkül)")

    def rename_preset(self):
        panel = self.panel
        monitor_id, old_name = panel.monitor_id, panel.preset_name
        if old_name == BASE_PRESET_NAME:
            return
        new_name = self._ask_preset_name(f"A(z) '{old_name}' új neve:", "Preset átnevezése")
        if not new_name:
            return
        preset_ops.rename_preset(panel.eng, monitor_id, old_name, new_name)
        panel.preset_name = new_name
        panel.app.apply_hotkeys()                         # a gyorsgomb-azonosító tartalmazza a preset nevét
        panel.widgets.preset_menu.configure(values=list(panel.eng.mon(monitor_id)["presets"]))
        panel.widgets.preset_menu.set(new_name)
        panel.app.refresh_tray()
        panel.set_status(f"Átnevezve: {old_name} → {new_name}")

    def delete_preset(self):
        panel = self.panel
        monitor_id, name = panel.monitor_id, panel.preset_name
        if name == BASE_PRESET_NAME or not messagebox.askyesno(
                APP_NAME, f"Törlöd a(z) '{name}' presetet?", parent=panel.root):
            return
        preset_ops.delete_preset(panel.eng, monitor_id, name)
        panel.app.apply_hotkeys()
        panel.pick_monitor(panel.eng.mon(monitor_id)["name"])
        panel.set_status(f"Törölve: {name}")
        panel.app.refresh_tray()

    # ---- mentés és visszatöltés

    def export_all(self):
        panel = self.panel
        file_name = filedialog.asksaveasfilename(
            title="Presetek exportálása", defaultextension=".json",
            initialfile=f"kepprofil-mentes-{time.strftime('%Y-%m-%d')}.json", filetypes=[("Képprofil mentés", "*.json")])
        if not file_name:
            return
        try:
            Path(file_name).write_text(json.dumps(preset_ops.export_data(panel.eng), ensure_ascii=False, indent=4),
                                       encoding="utf-8")
            panel.set_status(f"Exportálva: {file_name}")
        except OSError as error:
            panel.set_status(f"Nem sikerült exportálni: {error.__class__.__name__}")

    def import_all(self):
        panel = self.panel
        file_name = filedialog.askopenfilename(title="Presetek importálása", filetypes=[("Képprofil mentés", "*.json")])
        if not file_name:
            return
        data = _read_json(Path(file_name), None)
        config = preset_ops.importable_config(data)
        if config is None:
            panel.set_status("Ez a fájl nem Képprofil-mentés (vagy sérült), nem importáltam.")
            return
        if not messagebox.askyesno(APP_NAME, "Az importálás felülírja az összes mostani presetet, gyorsgombot és az "
                                   "éjszakai mód beállításait.\nA mostani állapotról előbb biztonsági mentés készül "
                                   "(backup mappa). Folytatod?", parent=panel.root):
            return
        preset_ops.import_config(panel.eng, data, config,
                                 BACKUP_DIR / f"presets-{time.strftime('%Y-%m-%d_%H%M%S')}-import-elott.json")
        panel.reload_after_import()
        panel.set_status("Importálva: a presetek és beállítások betöltve.")

    # ---- segédek

    def _ask_variant_name(self, text, title):
        """Új változatnevet kér; None, ha mégse, üres vagy már foglalt (utóbbinál az okot az állapotsorba írja)."""
        panel = self.panel
        raw_name = ctk.CTkInputDialog(text=text, title=title).get_input()
        existing = (panel.eng.preset(panel.monitor_id, panel.preset_name) or {}).get("variants") or {}
        name, error = preset_ops.clean_name(raw_name, existing, "változat")
        if error:
            panel.set_status(error)
        return name

    def _ask_preset_name(self, text, title):
        """Új preset-nevet kér; None, ha mégse, üres vagy már foglalt."""
        panel = self.panel
        raw_name = ctk.CTkInputDialog(text=text, title=title).get_input()
        name, error = preset_ops.clean_name(raw_name, panel.eng.mon(panel.monitor_id)["presets"], "preset")
        if error:
            panel.set_status(error)
        return name

    def _add_preset(self, name, preset, message):
        panel = self.panel
        presets = panel.eng.mon(panel.monitor_id)["presets"]
        presets[name] = preset
        panel.eng.save_config()
        panel.widgets.preset_menu.configure(values=list(presets))
        panel.load_preset(name)
        panel.set_status(message)
        panel.app.refresh_tray()
