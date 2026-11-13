"""Beállítások és preset-konfiguráció: betöltés, mentés, ellenőrzés, segédek."""
import json
import shutil
import threading
import time

from consts import CONFIG_FILE, DATA_DIR, LOG_FILE, NEUTRAL, OLD_DIR, SETTINGS_FILE
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
            with LOG_FILE.open("a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S  ") + str(text).rstrip() + "\n")
    except OSError:
        pass


DEFAULT_SETTINGS = {"night_strength": 60, "night_hotkey": "", "neutral_hotkey": "", "cycle_hotkey": "", "overlay_hotkey": "",
                    "toast": True, "base_rgb": {"mode": "none", "value": ""}, "migrated": False}


def load_settings():
    s = json.loads(json.dumps(DEFAULT_SETTINGS))
    s.update(_read_json(SETTINGS_FILE, {}))
    return s


def new_preset(vals=NEUTRAL, process=""):
    g, c, b, v = vals
    return {"gamma": g, "contrast": c, "brightness": b, "vibrance": v, "process": process}


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
        for f in sorted(BACKUP_DIR.glob("presets-*.json"))[:-10]:
            f.unlink()
    except OSError:
        pass


def valid_config(cfg):
    """Igaz, ha a cfg olyan, mint egy presets.json: monitorok listája, bennük érvényes presetek."""
    if not (isinstance(cfg, dict) and isinstance(cfg.get("monitors"), list)):
        return False
    num = (int, float)
    for m in cfg["monitors"]:
        if not (isinstance(m, dict) and isinstance(m.get("id"), str) and isinstance(m.get("presets", {}), dict)):
            return False
        for p in m.get("presets", {}).values():
            if not (isinstance(p, dict) and all(isinstance(p.get(k), num) and not isinstance(p.get(k), bool)
                                                for k in ("gamma", "contrast", "brightness"))):
                return False
            vs = p.get("variants")
            if vs is not None and not (isinstance(vs, dict) and all(
                    isinstance(v, dict) and all(isinstance(v.get(k), num) and not isinstance(v.get(k), bool)
                                                for k in ("gamma", "contrast", "brightness")) for v in vs.values())):
                return False
            for item in [p] + list((vs or {}).values()):
                gn = item.get("gain")
                if gn is not None and not (isinstance(gn, list) and len(gn) == 3 and all(
                        isinstance(x, num) and not isinstance(x, bool) and 0 <= x <= 100 for x in gn)):
                    return False
    return True


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
        mon["presets"].setdefault("Alap", new_preset())
        # a régi változat PowerShell-objektumként mentett mezői is egyszerű dict-ek
    known = {m["id"].lower() for m in cfg["monitors"]}
    for m in list_monitors():                                        # újonnan csatlakoztatott monitor
        if m["id"].lower() not in known:
            cfg["monitors"].append({"id": m["id"], "name": f"Monitor {m['id']}", "presets": {"Alap": new_preset()}})
    return cfg


def pvals(p, vname=None):
    """(gamma, kontraszt, fényerő, vibrance) a presetből; ha van változata, annak az értékei."""
    v = (p.get("variants") or {}).get(vname) or p
    return (v["gamma"], v["contrast"], v["brightness"], v.get("vibrance", 50))


def pgain(p, vname=None):
    """Színcsatorna-erősítés százalékban [R, G, B]; 100 = semleges (a régi presetekben nincs: 100)."""
    v = (p.get("variants") or {}).get(vname) or p
    g = v.get("gain")
    return [int(x) for x in g] if isinstance(g, (list, tuple)) and len(g) == 3 else [100, 100, 100]


def mirror_first(p):
    """Ha a presetnek vannak változatai, a felső szintű értékek az első változatot tükrözik (régi/idegen olvasóknak)."""
    vs = p.get("variants")
    if vs:
        f = next(iter(vs.values()))
        p.update(gamma=f["gamma"], contrast=f["contrast"], brightness=f["brightness"], vibrance=f.get("vibrance", 50))
        if f.get("gain") is not None:
            p["gain"] = f["gain"]
        else:
            p.pop("gain", None)


def night_mult(strength):
    s = max(0, min(100, strength)) / 100.0
    return (1 - 0.08 * s, 1 - 0.25 * s, 1 - 0.45 * s)

