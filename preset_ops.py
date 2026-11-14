"""A presetek és a változatok módosítása a felülettől függetlenül: névellenőrzés, létrehozás, átnevezés, törlés, másolat,
export és import. A függvények a motor (`Engine`) állapotát és a konfigurációs fájlt módosítják; a párbeszédeket, az
állapotsort és a felület frissítését a hívó (`gui.py`) végzi."""
import json
import time

from config import (SETTINGS_KEYS, _write_json, mirror_first, new_preset, normalize_config, pgain, valid_config)

FIRST_VARIANT_NAME = "Alap"


def clean_name(raw, taken_names, kind):
    """A bekért névből `(név, None)`-t ad, ha használható. Üres bevitelnél (mégse) `(None, None)`, egyébként
    `(None, hibaüzenet)`. `kind`: "preset" vagy "változat" (a foglalt-névre szóló üzenethez)."""
    name = (raw or "").strip()
    if not name:
        return None, None
    if "|" in name:
        return None, "A névben nem lehet | jel."
    if name in taken_names:
        return None, f"Ilyen nevű {kind} már van."
    return name, None


def values_dict(gamma, contrast, brightness, vibrance, gain):
    """A kép egy változatának értékei, ahogy a konfigurációban tárolódnak."""
    return {"gamma": gamma, "contrast": contrast, "brightness": brightness, "vibrance": vibrance, "gain": gain}


def add_variant(eng, mid, preset_name, variant_name, values):
    """Új változatot vesz fel a presetbe `values` értékekkel. Ha a presetnek még nincs változata, az eddigi értékei
    `FIRST_VARIANT_NAME` néven az első változat lesznek. Hibaüzenetet ad vissza, ha nem lehetett; sikernél `None`."""
    preset = eng.preset(mid, preset_name)
    if not preset.get("variants"):
        if variant_name == FIRST_VARIANT_NAME:
            return (f"Ilyen nevű változat már van (az eddigi értékek '{FIRST_VARIANT_NAME}' néven az első változat "
                    "lesznek).")
        preset["variants"] = {FIRST_VARIANT_NAME: values_dict(
            preset["gamma"], preset["contrast"], preset["brightness"], preset.get("vibrance", 50), pgain(preset))}
    preset["variants"][variant_name] = values
    eng.save_config()
    eng.variant[(mid, preset_name)] = variant_name
    return None


def rename_variant(eng, mid, preset_name, old_name, new_name):
    preset = eng.preset(mid, preset_name)
    with eng.lock:
        preset["variants"] = {(new_name if name == old_name else name): values
                              for name, values in preset["variants"].items()}       # a sorrend megmarad
        if eng.variant.get((mid, preset_name)) == old_name:
            eng.variant[(mid, preset_name)] = new_name
    eng.save_config()


def delete_variant(eng, mid, preset_name, variant_name):
    """Törli a változatot, és visszaadja az utána érvényes (első) változat nevét."""
    preset = eng.preset(mid, preset_name)
    with eng.lock:
        del preset["variants"][variant_name]
        eng.variant.pop((mid, preset_name), None)
        mirror_first(preset)
    eng.save_config()
    return next(iter(preset["variants"]))


def blank_preset(values, process):
    """Új preset a megadott (gamma, kontraszt, fényerő, vibrance) értékekből és színerősítésekből: ezek az alapértékei is."""
    gamma, contrast, brightness, vibrance, gain = values
    preset = new_preset((gamma, contrast, brightness, vibrance), process)
    preset["gain"] = gain
    preset["default"] = values_dict(gamma, contrast, brightness, vibrance, gain)
    return preset


def copy_of_preset(collected, values):
    """A preset másolata: a gyorsgomb és a játék-exe nem másolódik (ütköznének az eredetivel), az alapértékek a mostaniak."""
    copy = json.loads(json.dumps(collected))
    copy.pop("hotkey", None)
    copy["process"] = ""
    for variant in (copy.get("variants") or {}).values():
        variant.pop("hotkey", None)
    copy["default"] = values_dict(*values)
    return copy


def rename_preset(eng, mid, old_name, new_name):
    with eng.lock:
        monitor = eng.mon(mid)
        monitor["presets"] = {(new_name if name == old_name else name): preset
                              for name, preset in monitor["presets"].items()}    # a sorrend megmarad
        if eng.active.get(mid) == old_name:
            eng.active[mid] = new_name
        for marked in (eng.auto, eng.manual_off):
            if (mid, old_name) in marked:
                marked.discard((mid, old_name))
                marked.add((mid, new_name))
        if (mid, old_name) in eng.variant:
            eng.variant[(mid, new_name)] = eng.variant.pop((mid, old_name))
    eng.save_config()


def delete_preset(eng, mid, preset_name):
    eng.set_active(mid, preset_name, False)
    del eng.mon(mid)["presets"][preset_name]
    eng.save_config()


def export_data(eng):
    return {"kepprofil_backup": 1, "exported": time.strftime("%Y-%m-%d %H:%M:%S"), "config": eng.cfg,
            "settings": {key: eng.set.get(key) for key in SETTINGS_KEYS}}


def importable_config(data):
    """A beolvasott fájlból az importálható konfigurációt adja, vagy `None`-t, ha az nem Képprofil-mentés / sérült."""
    config = data.get("config") if isinstance(data, dict) and "config" in data else data
    return config if valid_config(config) else None


def import_config(eng, data, config, backup_file):
    """Lecseréli a motor konfigurációját és beállításait. A mostani állapotot előbb `backup_file`-ba menti."""
    _write_json(backup_file, eng.cfg)
    saved_settings = data.get("settings") if isinstance(data, dict) else None
    with eng.lock:
        eng.active.clear()
        eng.auto.clear()
        eng.manual_off.clear()
        eng.cfg = normalize_config(config)
        if isinstance(saved_settings, dict):
            for key in SETTINGS_KEYS:
                if saved_settings.get(key) is not None:
                    eng.set[key] = saved_settings[key]
        eng.migrate_cycle_hotkey()
        eng.save_config()
        eng.save_settings()
