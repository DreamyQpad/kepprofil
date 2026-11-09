"""Linux-megvalósítás (a hw.py ezt tölti be Linuxon; KDE Plasma Wayland-re készült, a régi `gamma-panel` portja).

- Gamma / kontraszt / fényerő / R-G-B erősítés: ICC-profil, amit `kscreen-doctor` állít a kimenetre.
- Vibrance: `nvibrant` (csak NVIDIA); a kimenet-indexek a DATA_DIR/vibrance_index.json-ban állíthatók.
- Energiaprofil: `powerprofilesctl`.
- Ébredés: a logind PrepareForSleep jelzése (`gdbus monitor`).
- A globális gyorsgomb Waylanden még nincs megoldva (lásd LINUX.md).

FIGYELEM: Windows-gépen íródott, ott nem futtatható; csak a tiszta részek (ICC, EDID, parancs-kimenetek
értelmezése) vannak ott letesztelve.
"""
import glob
import json
import re
import shutil
import struct
import subprocess
import threading
from pathlib import Path

from consts import DATA_DIR
from hw_common import Rgb, parse_hotkey  # noqa: F401  (a hw.py innen is továbbadja)

ICC_DIR = Path.home() / ".local/share/color/icc"
PREFIX = "kepprofil"
NEUTRAL_GAMMA = 2.2
VIBRANCE_MIN, VIBRANCE_MAX, VIBRANCE_PCT_DEFAULT = -1024, 1023, 50
VIBRANCE_INDEX_FILE = DATA_DIR / "vibrance_index.json"          # {"HDMI-A-1": 0, "HDMI-A-2": 3}: a kimenet nvibrant-indexe


def run(*cmd, timeout=15):
    try:
        return subprocess.run(list(cmd), capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None


# ---------------------------------------------------------------- monitorok

def edid_id(edid):
    """EDID-bájtokból a Windowsos hardver-azonosítóval megegyező id: 3 betűs gyártó + 4 jegyű hex terméktípus (pl. SAM777F)."""
    if len(edid) < 12:
        return None
    code = (edid[8] << 8) | edid[9]
    maker = "".join(chr(((code >> s) & 31) + 64) for s in (10, 5, 0))
    return f"{maker}{edid[10] | (edid[11] << 8):04X}"


def read_edid(output):
    for path in glob.glob(f"/sys/class/drm/card*-{output}/edid"):
        try:
            data = Path(path).read_bytes()
        except OSError:
            continue
        if len(data) >= 128:
            return data
    return None


def kscreen_outputs():
    r = run("kscreen-doctor", "-j")
    try:
        return [o for o in json.loads(r.stdout)["outputs"] if o.get("enabled")] if r else []
    except (ValueError, KeyError, TypeError):
        return []


def list_monitors():
    """[{"id": "SAM777F", "dev": "HDMI-A-1"}]: az id az EDID-ből (mint Windowson), a dev a KDE kimenet neve."""
    out = []
    for o in kscreen_outputs():
        edid = read_edid(o["name"])
        out.append({"id": (edid_id(edid) if edid else None) or o["name"], "dev": o["name"]})
    return out


def find_dev(mid):
    for m in list_monitors():
        if m["id"].lower() == mid.lower():
            return m["dev"]
    return None


def monitor_rect(mid):
    dev = find_dev(mid) if mid else None
    for o in kscreen_outputs():
        if o["name"] == dev:
            pos, size = o.get("pos") or {}, o.get("size") or {}
            if size.get("width"):
                x, y = pos.get("x", 0), pos.get("y", 0)
                return (x, y, x + size["width"], y + size["height"])
    return None


# ---------------------------------------------------------------- ICC-profil

def _s15(x):
    return struct.pack(">i", round(x * 65536))


def _xyz(x, y, z):
    return b"XYZ \0\0\0\0" + _s15(x) + _s15(y) + _s15(z)


def _text_tag(s):
    return b"text\0\0\0\0" + s.encode() + b"\0"


def _desc_tag(s):
    b = s.encode() + b"\0"
    return b"desc\0\0\0\0" + struct.pack(">I", len(b)) + b + b"\0" * 8 + b"\0\0" + b"\0" * 67


def build_icc(gamma, name, contrast=50, brightness=50, mult=(1.0, 1.0, 1.0)):
    """ICC v2 monitorprofil. Semleges kontraszt/fényerő/erősítésnél egyetlen gamma-érték, különben 1024 pontos görbe
    csatornánként: f(d) = u(d)^gamma, u = a közép körül nyújtott és eltolt d (0..1-re vágva); a mult az R/G/B szorzó."""
    if contrast == 50 and brightness == 50 and tuple(mult) == (1.0, 1.0, 1.0):
        curves = [b"curv\0\0\0\0" + struct.pack(">I", 1) + struct.pack(">H", round(gamma * 256))] * 3
    else:
        k, b, n = 2 ** ((contrast - 50) / 50), (brightness - 50) / 50 * 0.25, 1024
        curves = []
        for m in mult:
            points = [round(min(1, max(0, (i / (n - 1) - 0.5 - b) / k + 0.5)) ** gamma * m * 65535) for i in range(n)]
            curves.append(b"curv\0\0\0\0" + struct.pack(">I", n) + struct.pack(f">{n}H", *points))
    tags = {
        b"desc": _desc_tag(name), b"cprt": _text_tag("Public domain"), b"wtpt": _xyz(0.9642, 1.0, 0.8249),
        b"rXYZ": _xyz(0.4360747, 0.2225045, 0.0139322), b"gXYZ": _xyz(0.3850649, 0.7168786, 0.0971045),
        b"bXYZ": _xyz(0.1430804, 0.0606169, 0.7141733), b"rTRC": curves[0], b"gTRC": curves[1], b"bTRC": curves[2],
    }
    offset = 128 + 4 + 12 * len(tags)
    table, body = b"", b""
    for sig, data in tags.items():
        table += sig + struct.pack(">II", offset + len(body), len(data))
        body += data + b"\0" * (-len(data) % 4)
    header = struct.pack(">I4sI4s4s4s", offset + len(body), b"\0" * 4, 0x02200000, b"mntr", b"RGB ", b"XYZ ")
    header += struct.pack(">HHHHHH", 2026, 1, 1, 0, 0, 0) + b"acsp" + b"\0" * 24
    header += _s15(0.9642) + _s15(1.0) + _s15(0.8249)
    return header.ljust(128, b"\0") + struct.pack(">I", len(tags)) + table + body


def _clean_icc(output, keep=None):
    for old in ICC_DIR.glob(f"{PREFIX}-{output}-*.icc"):
        if old != keep:
            old.unlink(missing_ok=True)


def apply_icc(output, gamma, contrast, brightness, mult):
    ICC_DIR.mkdir(parents=True, exist_ok=True)
    tag = "-".join(f"{int(round(m * 1000))}" for m in mult)
    path = ICC_DIR / f"{PREFIX}-{output}-g{gamma:.2f}-c{int(contrast)}-b{int(brightness)}-m{tag}.icc"
    path.write_bytes(build_icc(gamma, f"Képprofil: gamma {gamma:.2f}, kontraszt {contrast}%, fényerő {brightness}%",
                               contrast, brightness, mult))
    r = run("kscreen-doctor", f"output.{output}.iccprofile.{path}", f"output.{output}.colorProfileSource.ICC")
    _clean_icc(output, keep=path)
    return bool(r and r.returncode == 0)


def reset_icc(output):
    r = run("kscreen-doctor", f"output.{output}.colorProfileSource.sRGB")
    _clean_icc(output)
    return bool(r and r.returncode == 0)


# ---------------------------------------------------------------- vibrance (nvibrant)

def pct_to_raw(pct):
    span = VIBRANCE_MAX if pct >= VIBRANCE_PCT_DEFAULT else -VIBRANCE_MIN
    return round((pct - VIBRANCE_PCT_DEFAULT) / VIBRANCE_PCT_DEFAULT * span)


def vibrance_index():
    try:
        return {k: int(v) for k, v in json.loads(VIBRANCE_INDEX_FILE.read_text(encoding="utf-8")).items()}
    except (OSError, ValueError, TypeError):
        return {"HDMI-A-1": 0, "HDMI-A-2": 3}          # a régi gép beállítása; máshol a vibrance_index.json-t kell megadni


class Display:
    """Képbeállítás monitoronként: ICC-profil (kscreen-doctor) + vibrance (nvibrant)."""

    def __init__(self):
        self.vib = {}                                   # kimenet -> nyers érték (az nvibrant mindig az összeset állítja)
        self.has_nvibrant = shutil.which("nvibrant") is not None

    @property
    def vibrance_ok(self):
        return self.has_nvibrant

    def apply(self, dev, vals, mult=(1.0, 1.0, 1.0)):
        gamma, contrast, brightness, vib = vals
        neutral = (abs(gamma - NEUTRAL_GAMMA) < 0.005 and contrast == 50 and brightness == 50
                   and tuple(mult) == (1.0, 1.0, 1.0))
        ok = reset_icc(dev) if neutral else apply_icc(dev, gamma, contrast, brightness, mult)
        if self.has_nvibrant:
            self.vib[dev] = pct_to_raw(vib)
            idx = vibrance_index()
            if dev in idx:
                raw = [0] * 8
                for out, v in self.vib.items():
                    if out in idx and 0 <= idx[out] < 8:
                        raw[idx[out]] = v
                r = run("nvibrant", *map(str, raw))
                ok = ok and bool(r and r.returncode == 0)
        return ok

    def drifted(self, dev, vals, mult=(1.0, 1.0, 1.0)):
        return None             # a KWin megtartja az ICC-profilt; a kscreen-doctor 2 másodpercenkénti hívása túl nehéz lenne


def overlay_style(w):
    """Waylanden a tk-ablak nem lehet átkattintható/legfelső; amit lehet, megtesszük."""
    w.attributes("-topmost", True)


# ---------------------------------------------------------------- energiaprofil (power-profiles-daemon)

def parse_power_profiles(text):
    """A `powerprofilesctl list` kimenetéből [(név, név, aktív)]."""
    res = []
    for line in text.splitlines():
        m = re.match(r"^([* ]) ([A-Za-z][\w-]*):\s*$", line)
        if m:
            res.append((m.group(2), m.group(2), m.group(1) == "*"))
    return res


def power_plans():
    r = run("powerprofilesctl", "list")
    return parse_power_profiles(r.stdout) if r and r.returncode == 0 else []


def power_active():
    r = run("powerprofilesctl", "get")
    return r.stdout.strip() if r and r.returncode == 0 and r.stdout.strip() else None


def power_set(name):
    r = run("powerprofilesctl", "set", name)
    return bool(r and r.returncode == 0)


# ---------------------------------------------------------------- gyorsgombok, rendszeresemények

class Hotkeys(threading.Thread):
    """Egyelőre nem csinál semmit: Waylanden nincs szabványos globális gyorsgomb (lásd LINUX.md)."""

    def __init__(self, callback):
        super().__init__(daemon=True)
        self.cb, self.failed = callback, set()

    def run(self):
        pass

    def set(self, mapping):
        self.failed = set()


class SystemEvents(threading.Thread):
    """Ébredés: a logind PrepareForSleep(false) jelzése. Kijelzőváltás-jelzés még nincs."""

    def __init__(self, callback):
        super().__init__(daemon=True)
        self.cb, self.ready, self.error, self.hwnd = callback, threading.Event(), None, None

    def run(self):
        self.ready.set()
        if not shutil.which("gdbus"):
            self.error = "nincs gdbus"
            return
        try:
            p = subprocess.Popen(["gdbus", "monitor", "--system", "--dest", "org.freedesktop.login1"],
                                 stdout=subprocess.PIPE, text=True)
            for line in p.stdout:
                if "PrepareForSleep" in line and "false" in line:
                    self.cb("resume")
        except Exception as e:                           # noqa: BLE001
            self.error = e
