"""Windows-megvalósítás (a hw.py ezt tölti be Windowson). Hardver- és Windows-réteg: monitorok, gamma-görbe, NVAPI-vibrance, energiaprofil, OpenRGB, gyorsgombok."""
import ctypes
import ctypes.wintypes as wt
import re
import subprocess
import threading

from consts import APP_NAME, CREATE_NO_WINDOW
from hw_common import Rgb, parse_hotkey  # noqa: F401  (a hw.py innen is tovabbadja)

# ---------------------------------------------------------------- Windows API

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
gdi32.CreateDCW.restype = ctypes.c_void_p
gdi32.CreateDCW.argtypes = [wt.LPCWSTR, wt.LPCWSTR, wt.LPCWSTR, ctypes.c_void_p]
gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
gdi32.SetDeviceGammaRamp.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.GetDeviceGammaRamp.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
kernel32.CreateMutexW.restype = ctypes.c_void_p
kernel32.CreateEventW.restype = ctypes.c_void_p
kernel32.SetEvent.argtypes = [ctypes.c_void_p]
kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, wt.DWORD]


class DISPLAY_DEVICE(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("DeviceName", wt.WCHAR * 32), ("DeviceString", wt.WCHAR * 128),
                ("StateFlags", wt.DWORD), ("DeviceID", wt.WCHAR * 128), ("DeviceKey", wt.WCHAR * 128)]


def list_monitors():
    """A csatlakoztatott monitorok: [{"id": "SAM777F", "dev": r"\\\\.\\DISPLAY2"}]."""
    out, i = [], 0
    while True:
        a = DISPLAY_DEVICE()
        a.cb = ctypes.sizeof(a)
        if not user32.EnumDisplayDevicesW(None, i, ctypes.byref(a), 0):
            break
        i += 1
        if not (a.StateFlags & 1):                     # nincs az asztalhoz csatolva
            continue
        m = DISPLAY_DEVICE()
        m.cb = ctypes.sizeof(m)
        if user32.EnumDisplayDevicesW(a.DeviceName, 0, ctypes.byref(m), 0):
            parts = m.DeviceID.split("\\")
            out.append({"id": parts[1] if len(parts) > 1 else m.DeviceID, "dev": a.DeviceName})
    return out


def find_dev(mid):
    for m in list_monitors():
        if m["id"].lower() == mid.lower():
            return m["dev"]
    return None


class _MONITORINFOEX(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD),
                ("szDevice", wt.WCHAR * 32)]


_MONENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(wt.RECT), ctypes.c_void_p)
user32.GetParent.restype, user32.GetParent.argtypes = ctypes.c_void_p, [ctypes.c_void_p]
user32.GetWindowLongW.restype, user32.GetWindowLongW.argtypes = ctypes.c_long, [ctypes.c_void_p, ctypes.c_int]
user32.SetWindowLongW.restype, user32.SetWindowLongW.argtypes = ctypes.c_long, [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.EnumDisplayMonitors.argtypes = [ctypes.c_void_p, ctypes.c_void_p, _MONENUMPROC, ctypes.c_void_p]


def monitor_rect(mid):
    """(bal, felső, jobb, alsó) az asztal-koordinátákban a monitor-azonosítóhoz; None, ha nem található."""
    dev = find_dev(mid) if mid else None
    found = []

    def cb(hm, hdc, rect, data):
        mi = _MONITORINFOEX()
        mi.cbSize = ctypes.sizeof(mi)
        if user32.GetMonitorInfoW(hm, ctypes.byref(mi)) and dev and mi.szDevice.lower() == dev.lower():
            r = mi.rcMonitor
            found.append((r.left, r.top, r.right, r.bottom))
        return 1

    proc = _MONENUMPROC(cb)                                  # a hívás idejére életben kell tartani
    user32.EnumDisplayMonitors(None, None, proc, 0)
    return found[0] if found else None


user32.GetForegroundWindow.restype = ctypes.c_void_p
user32.MonitorFromWindow.restype, user32.MonitorFromWindow.argtypes = ctypes.c_void_p, [ctypes.c_void_p, wt.DWORD]


def foreground_monitor_id():
    """Az előtérben lévő ablak monitorjának azonosítója (mint a list_monitors()-é); None, ha nem megállapítható."""
    hwnd = user32.GetForegroundWindow()
    hmon = user32.MonitorFromWindow(hwnd, 2) if hwnd else None          # 2 = a legközelebbi monitor
    if not hmon:
        return None
    mi = _MONITORINFOEX()
    mi.cbSize = ctypes.sizeof(mi)
    if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
        return None
    return next((m["id"] for m in list_monitors() if m["dev"].lower() == mi.szDevice.lower()), None)


def _clamp(v):
    return 0.0 if v < 0 else (1.0 if v > 1 else v)


def build_ramp(gamma, contrast, brightness, mult=(1.0, 1.0, 1.0)):
    """d(be) = clip((be^(2,2/gamma) - 0,5) * k + 0,5 + b), k = 2^((kontraszt-50)/50), b = (fényerő-50)/50*0,25.
    A mult az R/G/B csatorna szorzója (éjszakai mód). A Windows nem fogad el a lineárishoz képest túl
    távoli görbét, ezért az értékeket +-32000-re szorítjuk."""
    k, b, e = 2 ** ((contrast - 50) / 50), (brightness - 50) / 50 * 0.25, 2.2 / gamma
    arr = (ctypes.c_ushort * 768)()
    for ch in range(3):
        for i in range(256):
            d = _clamp((((i / 255.0) ** e) - 0.5) * k + 0.5 + b) * mult[ch]
            ident = i * 257
            arr[ch * 256 + i] = int(max(0, min(65535, max(ident - 32000, min(ident + 32000, round(d * 65535))))))
    return arr


def set_ramp(dev, ramp):
    dc = gdi32.CreateDCW(None, dev, None, None)
    if not dc:
        return False
    try:
        return bool(gdi32.SetDeviceGammaRamp(dc, ctypes.byref(ramp)))
    finally:
        gdi32.DeleteDC(dc)


def get_ramp(dev):
    dc = gdi32.CreateDCW(None, dev, None, None)
    if not dc:
        return None
    try:
        arr = (ctypes.c_ushort * 768)()
        return arr if gdi32.GetDeviceGammaRamp(dc, ctypes.byref(arr)) else None
    finally:
        gdi32.DeleteDC(dc)


class _DVC(ctypes.Structure):
    _fields_ = [("version", ctypes.c_uint32), ("cur", ctypes.c_int32), ("min", ctypes.c_int32),
                ("max", ctypes.c_int32), ("default", ctypes.c_int32)]


class Nv:
    """NVIDIA digital vibrance (0..100, alap 50) az NVAPI-n át, ugyanúgy, mint az NVIDIA Vezérlőpult."""

    def __init__(self):
        self.ok = False
        try:
            q = ctypes.WinDLL("nvapi64.dll").nvapi_QueryInterface
            q.restype, q.argtypes = ctypes.c_void_p, [ctypes.c_uint]
            self._q = q
            init = self._fn(0x0150E828, ctypes.c_int)
            self.ok = bool(init) and init() == 0
            if self.ok:
                self._enum = self._fn(0x9ABDD40D, ctypes.c_int, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))
                self._name = self._fn(0x22A78B05, ctypes.c_int, ctypes.c_void_p, ctypes.c_char_p)
                self._oid = self._fn(0xD995937E, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32))
                self._get = self._fn(0x0E45002D, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(_DVC))
                self._set = self._fn(0x4A82C2B1, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(_DVC))
                self.ok = all((self._enum, self._name, self._oid, self._get, self._set))
        except OSError:
            self.ok = False

    def _fn(self, fid, restype, *argtypes):
        p = self._q(fid)
        return ctypes.CFUNCTYPE(restype, *argtypes)(p) if p else None

    def _locate(self, dev):
        for i in range(16):
            h = ctypes.c_void_p()
            if self._enum(i, ctypes.byref(h)) != 0:
                break
            buf = ctypes.create_string_buffer(64)
            self._name(h, buf)
            if buf.value.decode("ascii", "ignore").lower() == dev.lower():
                oid = ctypes.c_uint32()
                return (h, oid.value) if self._oid(h, ctypes.byref(oid)) == 0 else None
        return None

    def _info(self):
        d = _DVC()
        d.version = ctypes.sizeof(_DVC) | (1 << 16)
        return d

    def get(self, dev):
        if not self.ok:
            return -1
        loc = self._locate(dev)
        if not loc:
            return -1
        d = self._info()
        return d.cur if self._get(loc[0], loc[1], ctypes.byref(d)) == 0 else -1

    def set(self, dev, level):
        if not self.ok:
            return True            # nincs NVIDIA: nincs mit beállítani
        loc = self._locate(dev)
        if not loc:
            return False
        d = self._info()
        d.cur, d.min, d.max, d.default = max(0, min(100, int(level))), 0, 100, 50
        return self._set(loc[0], loc[1], ctypes.byref(d)) == 0


# ---------------------------------------------------------------- energiaprofil, RGB

def power_plans():
    """[(guid, név, aktív)] a powercfg kimenetéből."""
    try:
        r = subprocess.run(["powercfg", "/list"], capture_output=True, text=True, encoding="oem", errors="replace",
                           creationflags=CREATE_NO_WINDOW, timeout=15)
    except Exception:
        return []
    plans = []
    for line in r.stdout.splitlines():
        m = re.search(r"([0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})\s+\((.+?)\)\s*(\*)?", line)
        if m:
            plans.append((m.group(1).lower(), m.group(2), bool(m.group(3))))
    return plans


def power_active():
    return next((g for g, _, a in power_plans() if a), None)


def power_set(guid):
    try:
        return subprocess.run(["powercfg", "/setactive", guid], capture_output=True,
                              creationflags=CREATE_NO_WINDOW, timeout=15).returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------- gyorsgombok

WM_HOTKEY, WM_RELOAD = 0x0312, 0x8001


class Hotkeys(threading.Thread):
    """Globális gyorsgombok: a RegisterHotKey és az üzenethurok ugyanabban a szálban kell, hogy legyen.
    A térkép értéke szöveg ("Ctrl+Alt+1") vagy nyers (módosítók, vk, ismétlődhet) hármas; ez utóbbi lehet módosító nélküli is."""

    def __init__(self, callback):
        super().__init__(daemon=True)
        self.cb, self.tid, self.wanted, self.failed = callback, None, {}, set()
        self.ready, self.lock = threading.Event(), threading.Lock()
        self.applied = threading.Event()                      # a legutóbbi set() lefoglalásai megtörténtek (failed érvényes)

    def run(self):
        self.tid = kernel32.GetCurrentThreadId()
        msg = wt.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)          # üzenetsor létrehozása
        self.ready.set()
        ids = {}
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_RELOAD:
                for i in ids:
                    user32.UnregisterHotKey(None, i)
                ids.clear()
                with self.lock:
                    wanted = dict(self.wanted)
                failed = set()
                for n, (action, spec) in enumerate(wanted.items(), 1):
                    if isinstance(spec, tuple):
                        hk = spec
                    else:
                        parsed = parse_hotkey(spec)
                        hk = (parsed[0], parsed[1], False) if parsed else None
                    # MOD_NOREPEAT (0x4000): a nyomva tartott gomb csak egyszer hat, kivéve ahol az ismétlés a cél (csúszka)
                    if hk and user32.RegisterHotKey(None, n, hk[0] | (0 if hk[2] else 0x4000), hk[1]):
                        ids[n] = action
                    else:
                        failed.add(action)
                self.failed = failed
                self.applied.set()
            elif msg.message == WM_HOTKEY and msg.wParam in ids:
                self.cb(ids[msg.wParam])

    def set(self, mapping):
        with self.lock:
            self.wanted = dict(mapping)
        self.applied.clear()
        self.ready.wait(5)
        if self.tid:
            user32.PostThreadMessageW(self.tid, WM_RELOAD, 0, 0)
            self.applied.wait(3)



# ---------------------------------------------------------------- rendszeresemények (ébredés, kijelzőváltás)

WM_DISPLAYCHANGE, WM_POWERBROADCAST, WM_WTSSESSION_CHANGE = 0x007E, 0x0218, 0x02B1
PBT_RESUMESUSPEND, PBT_RESUMEAUTOMATIC = 0x0007, 0x0012
WTS_CONSOLE_CONNECT, WTS_REMOTE_CONNECT, WTS_SESSION_UNLOCK = 0x1, 0x3, 0x8
_LRESULT = ctypes.c_ssize_t
_WNDPROC = ctypes.WINFUNCTYPE(_LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class _WNDCLASS(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", _WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wt.HINSTANCE), ("hIcon", wt.HANDLE), ("hCursor", wt.HANDLE), ("hbrBackground", wt.HANDLE),
                ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]


user32.DefWindowProcW.restype, user32.DefWindowProcW.argtypes = _LRESULT, [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.CreateWindowExW.restype = wt.HWND
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, wt.HWND, wt.HANDLE, wt.HINSTANCE, ctypes.c_void_p]
user32.RegisterClassW.argtypes = [ctypes.POINTER(_WNDCLASS)]
kernel32.GetModuleHandleW.restype, kernel32.GetModuleHandleW.argtypes = wt.HMODULE, [wt.LPCWSTR]


class SystemEvents(threading.Thread):
    """Rejtett ablak, ami megkapja a Windows üzeneteit: ébredés (\"resume\"), kijelzőváltás (\"display\": felbontás,
    monitor ki/be, játék képmódja) és a munkamenet feloldása/visszacsatlakozása (\"unlock\"). Ilyenkor a driver
    gyakran nullázza a gamma-görbét. A callback(kind) az üzenethurok szálában fut, ezért legyen gyors."""

    def __init__(self, callback):
        super().__init__(daemon=True)
        self.cb, self.hwnd, self.ready, self.error = callback, None, threading.Event(), None

    def _proc(self, hwnd, msg, wparam, lparam):
        kind = None
        if msg == WM_DISPLAYCHANGE:
            kind = "display"
        elif msg == WM_POWERBROADCAST and wparam in (PBT_RESUMEAUTOMATIC, PBT_RESUMESUSPEND):
            kind = "resume"
        elif msg == WM_WTSSESSION_CHANGE and wparam in (WTS_SESSION_UNLOCK, WTS_CONSOLE_CONNECT, WTS_REMOTE_CONNECT):
            kind = "unlock"
        if kind:
            try:
                self.cb(kind)
            except Exception:
                pass
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def run(self):
        try:
            self._wndproc = _WNDPROC(self._proc)                # életben kell tartani
            cls = _WNDCLASS()
            cls.lpfnWndProc, cls.lpszClassName = self._wndproc, f"{APP_NAME}Events"
            cls.hInstance = kernel32.GetModuleHandleW(None)
            user32.RegisterClassW(ctypes.byref(cls))
            # nem üzenet-ablak (HWND_MESSAGE): az nem kapja meg a szétküldött WM_DISPLAYCHANGE / WM_POWERBROADCAST üzenetet
            self.hwnd = user32.CreateWindowExW(0, cls.lpszClassName, cls.lpszClassName, 0, 0, 0, 0, 0, None, None,
                                               cls.hInstance, None)
            if not self.hwnd:
                raise OSError(f"CreateWindowEx: {ctypes.get_last_error()}")
            try:
                wts = ctypes.WinDLL("wtsapi32")
                wts.WTSRegisterSessionNotification.argtypes = [wt.HWND, wt.DWORD]
                wts.WTSRegisterSessionNotification(self.hwnd, 0)                  # csak ebben a munkamenetben
            except OSError:
                pass
        except Exception as e:
            self.error = e
            self.ready.set()
            return
        self.ready.set()
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))


# ---------------------------------------------------------------- platform-felület (a motor és a felület csak ezt használja)

class Display:
    """Képbeállítás monitoronként: gamma-görbe (SetDeviceGammaRamp) + NVIDIA vibrance (NVAPI)."""

    def __init__(self):
        self.nv = Nv()

    @property
    def vibrance_ok(self):
        return self.nv.ok

    def vibrance_state(self, dev):
        """(elérhető, indok): Windowson az NVAPI minden NVIDIA-s kijelzőre elérhető."""
        return (True, "") if self.nv.ok else (False, "Nincs NVIDIA driver.")

    def apply(self, dev, vals, mult=(1.0, 1.0, 1.0)):
        """vals = (gamma, kontraszt, fényerő, vibrance); mult = R/G/B szorzó. Igaz, ha sikerült."""
        g, c, b, v = vals
        return set_ramp(dev, build_ramp(g, c, b, mult)) and self.nv.set(dev, v)

    def drifted(self, dev, vals, mult=(1.0, 1.0, 1.0)):
        """Igaz, ha a kijelző állapota eltér a kívánttól (a játék/driver felülírta); None, ha nem olvasható."""
        now = get_ramp(dev)
        if not now:
            return None
        want = build_ramp(vals[0], vals[1], vals[2], mult)
        bad = any(abs(now[ch * 256 + i] - want[ch * 256 + i]) > 8 for ch in range(3) for i in (64, 128, 192))
        if not bad and self.nv.ok:
            bad = self.nv.get(dev) not in (-1, int(vals[3]))
        return bad


def overlay_style(w):
    """Átkattintható, nem aktiválódó, tálcagomb nélküli, legfelső ablak (a képernyő-értesítéshez); w: tk ablak."""
    hwnd = user32.GetParent(w.winfo_id()) or w.winfo_id()
    ex = user32.GetWindowLongW(hwnd, -20)
    user32.SetWindowLongW(hwnd, -20, ex | 0x00080000 | 0x00000020 | 0x08000000 | 0x00000080)
    user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0040)   # TOPMOST, aktiválás nélkül
