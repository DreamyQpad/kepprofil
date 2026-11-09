"""Windows-megvalósítás (a system.py ezt tölti be Windowson). Rendszer-segédek: futó programok listája, automatikus indítás, egy példány, régi figyelő leállítása."""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
from pathlib import Path

from consts import APP_NAME, CREATE_NO_WINDOW, FROZEN, HERE, STARTUP_DIR
from hw import kernel32, user32


def visible_programs():
    """A látható ablakkal rendelkező futó programok: {programnév: ablakcím}."""
    import psutil
    skip = {"explorer", "applicationframehost", "textinputhost", "systemsettings", "shellexperiencehost",
            "searchhost", "startmenuexperiencehost", "powershell", "pwsh", "conhost", "windowsterminal",
            "kijelzo", "kijelző", "python", "pythonw", "lockapp", "widgets"}
    res = {}
    proto = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                pid = wt.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                try:
                    name = psutil.Process(pid.value).name()
                except psutil.Error:
                    return True
                name = name[:-4] if name.lower().endswith(".exe") else name
                if name.lower() not in skip:
                    res.setdefault(name, buf.value)
        return True

    user32.EnumWindows(proto(cb), 0)
    return dict(sorted(res.items(), key=lambda kv: kv[0].lower()))


def kill_old_watcher():
    """Az előző (PowerShell-es) változat figyelője és indítója: leállítjuk, hogy ne dolgozzanak egymás ellen.
    Csak akkor nyúlunk hozzá, ha a régi automatikus indítás (Startup-parancsikon) ténylegesen megvan."""
    old = STARTUP_DIR / "Kijelző játék-figyelő.lnk"
    if not old.exists():
        return
    try:
        import psutil
        for p in psutil.process_iter(["name", "cmdline"]):
            cmd = " ".join(p.info.get("cmdline") or [])
            if "GameWatcher.ps1" in cmd:
                p.kill()
    except Exception:
        pass
    try:
        old.unlink()
    except OSError:
        pass


def autostart_link():
    return STARTUP_DIR / f"{APP_NAME}.lnk"


def autostart_enabled():
    return autostart_link().exists()


def set_autostart(on):
    lnk = autostart_link()
    if not on:
        try:
            lnk.unlink()
        except OSError:
            pass
        return
    target = sys.executable if FROZEN else str(Path(sys.executable).with_name("pythonw.exe"))
    args = "--tray" if FROZEN else f'"{HERE / "kijelzo.py"}" --tray'
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');$s.TargetPath='%s';$s.Arguments='%s';"
          "$s.WorkingDirectory='%s';$s.Save()" % (lnk, target, args.replace("'", "''"), HERE))
    STARTUP_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, creationflags=CREATE_NO_WINDOW)


def single_instance():
    """-> (már_fut, jelző-esemény). A második indítás a már futó példányban megnyitja a panelt."""
    kernel32.CreateMutexW(None, False, "Local\\KepprofilProgram")
    already = ctypes.get_last_error() == 183
    ev = kernel32.CreateEventW(None, False, False, "Local\\KepprofilPanelMutat")
    return already, ev


def signal_running(ev):
    """A már futó példánynak jelzés: mutassa a panelt."""
    kernel32.SetEvent(ev)


def show_signaled(ev, ms):
    """Igaz, ha a második indítás jelzett a várakozás alatt."""
    return kernel32.WaitForSingleObject(ev, ms) == 0


def open_native(p):
    """Fájl/mappa megnyitása az alapértelmezett programmal."""
    os.startfile(str(p))
