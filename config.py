"""Beállítások és preset-konfiguráció: betöltés, mentés, ellenőrzés, segédek."""
import json
import shutil
import threading
import time

from consts import BASE_PRESET_NAME, CONFIG_FILE, DATA_DIR, LOG_FILE, NEUTRAL, OLD_DIR, SETTINGS_FILE
from hw import list_monitors

# ---------------------------------------------------------------- beállítások, konfig

def _read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def _write_json(path, data):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
    except OSError:
        pass


_log_lock = threading.Lock()
LOG_MAX = 256 * 1024                              # ennél nagyobb naplót log.old.txt-re cseréli (így legfeljebb ~512 kB)


def write_log(text):
    """Egy sor a log.txt-be (időbélyeggel). Hiba esetén csendben eldobja: a napló sosem akaszthatja meg a programot."""
    try:
        with _log_lock:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX:
                LOG_FILE.replace(LOG_FILE.with_suffix(".old.txt"))
            with LOG_FILE.open("a", encoding="utf-8") as log_file:
                log_file.write(time.strftime("%Y-%m-%d %H:%M:%S  ") + str(text).rstrip() + "\n")
    except OSError:
        pass


DEFAULT_SETTINGS = {"night_strength": 60, "night_hotkey": "", "neutral_hotkey": "", "cycle_hotkey": "", "overlay_hotkey": "",
                    "toast": True, "base_rgb": {"mode": "none", "value": ""}, "migrated": False}


def load_settings():
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))
    settings.update(_read_json(SETTINGS_FILE, {}))
    return settings


def new_preset(values=NEUTRAL, process=""):
    gamma, contrast, brightness, vibrance = values
    return {"gamma": gamma, "contrast": contrast, "brightness": brightness, "vibrance": vibrance, "process": process}


BACKUP_DIR = DATA_DIR / "backup"
SETTINGS_KEYS = ("night_strength", "night_hotkey", "neutral_hotkey", "cycle_hotkey", "overlay_hotkey", "toast", "base_rgb")      # ami a mentésbe/exportba kerül


def auto_backup():
    """Naponta egyszer (az első indításkor) másolat a presetekről a backup mappába; az utolsó 10 marad."""
    try:
        if not isinstance(_read_json(CONFIG_FILE, None), dict):
            return
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        dst = BACKUP_DIR / f"presets-{time.strftime('%Y-%m-%d')}.json"
        if not dst.exists():
            shutil.copy2(CONFIG_FILE, dst)
        for old_backup in sorted(BACKUP_DIR.glob("presets-*.json"))[:-10]:
            old_backup.unlink()
    except OSError:
        pass


NUMBER_TYPES = (int, float)
BASE_VALUE_KEYS = ("gamma", "contrast", "brightness")


def is_number(value):
    """Szám (a bool nem az, bár az int leszármazottja)."""
    return isinstance(value, NUMBER_TYPES) and not isinstance(value, bool)


def has_base_values(entry):
    """Igaz, ha az entry (preset vagy változat) szótár, és a gamma, kontraszt és fényerő száma megvan benne."""
    return isinstance(entry, dict) and all(is_number(entry.get(key)) for key in BASE_VALUE_KEYS)


def valid_gain(gain):
    """A színcsatorna-erősítés hiányozhat; ha megvan, három százalékérték (0–100)."""
    return gain is None or (isinstance(gain, list) and len(gain) == 3
                            and all(is_number(percent) and 0 <= percent <= 100 for percent in gain))


def valid_preset(preset):
    if not has_base_values(preset):
        return False
    variants = preset.get("variants")
    if variants is not None and not (isinstance(variants, dict) and all(has_base_values(variant) for variant in variants.values())):
        return False
    return all(valid_gain(item.get("gain")) for item in [preset] + list((variants or {}).values()))


def valid_monitor(monitor):
    return (isinstance(monitor, dict) and isinstance(monitor.get("id"), str) and isinstance(monitor.get("presets", {}), dict)
            and all(valid_preset(preset) for preset in monitor.get("presets", {}).values()))


def valid_config(cfg):
    """Igaz, ha a cfg olyan, mint egy presets.json: monitorok listája, bennük érvényes presetek."""
    return (isinstance(cfg, dict) and isinstance(cfg.get("monitors"), list)
            and all(valid_monitor(monitor) for monitor in cfg["monitors"]))


def load_config():
    cfg = _read_json(CONFIG_FILE, None)
    if not (isinstance(cfg, dict) and isinstance(cfg.get("monitors"), list)):
        old = _read_json(OLD_DIR / "presets.json", None)            # átvétel az előző változatból
        cfg = old if (isinstance(old, dict) and isinstance(old.get("monitors"), list)) else {"monitors": []}
    return normalize_config(cfg)


def normalize_config(cfg):
    for mon in cfg["monitors"]:
        mon.setdefault("name", f"Monitor {mon['id']}")
        mon.setdefault("presets", {})
        mon["presets"].setdefault(BASE_PRESET_NAME, new_preset())
        # a régi változat PowerShell-objektumként mentett mezői is egyszerű dict-ek
    add_new_monitors(cfg, list_monitors())
    return cfg


def add_new_monitors(cfg, found):
    """A found (list_monitors() formátum) listában szereplő, de a cfg-ben még nem ismert monitorok felvétele
    egy „Alap" presettel. Igaz, ha bővült a cfg."""
    known = {monitor["id"].lower() for monitor in cfg["monitors"]}
    added = False
    for monitor in found:
        if monitor["id"].lower() not in known:
            cfg["monitors"].append({"id": monitor["id"], "name": f"Monitor {monitor['id']}", "presets": {BASE_PRESET_NAME: new_preset()}})
            known.add(monitor["id"].lower())
            added = True
    return added


def pvals(preset, variant_name=None):
    """(gamma, kontraszt, fényerő, vibrance) a presetből; ha van változata, annak az értékei."""
    source = (preset.get("variants") or {}).get(variant_name) or preset
    return (source["gamma"], source["contrast"], source["brightness"], source.get("vibrance", 50))


def pgain(preset, variant_name=None):
    """Színcsatorna-erősítés százalékban [R, G, B]; 100 = semleges (a régi presetekben nincs: 100)."""
    source = (preset.get("variants") or {}).get(variant_name) or preset
    gain = source.get("gain")
    return [int(percent) for percent in gain] if isinstance(gain, (list, tuple)) and len(gain) == 3 else [100, 100, 100]


def mirror_first(preset):
    """Ha a presetnek vannak változatai, a felső szintű értékek az első változatot tükrözik (régi/idegen olvasóknak)."""
    variants = preset.get("variants")
    if variants:
        first_variant = next(iter(variants.values()))
        preset.update(gamma=first_variant["gamma"], contrast=first_variant["contrast"], brightness=first_variant["brightness"], vibrance=first_variant.get("vibrance", 50))
        if first_variant.get("gain") is not None:
            preset["gain"] = first_variant["gain"]
        else:
            preset.pop("gain", None)


def night_mult(strength):
    clamped = max(0, min(100, strength)) / 100.0
    return (1 - 0.08 * clamped, 1 - 0.25 * clamped, 1 - 0.45 * clamped)

