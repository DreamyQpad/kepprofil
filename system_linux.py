"""Linux-megvalósítás (a system.py ezt tölti be Linuxon): futó programok, autostart, egy példány, megnyitás.

FIGYELEM: Windows-gépen íródott, Linuxon még nem próbáltuk; a Unix-socketes egypéldányosság Windowson is tesztelhető volt.
"""
import os
import socket
import subprocess
import sys
from pathlib import Path

from consts import APP_NAME, FROZEN, HERE

AUTOSTART_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart"
SOCKET_PATH = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "kepprofil.sock"


def visible_programs():
    """{programnév: cím}. Waylanden nincs ablaklista, ezért a saját felhasználó futó programjait adjuk (a rendszer-
    folyamatok nélkül); a cím a futtatható fájl útvonala."""
    import psutil
    skip = {"systemd", "(sd-pam)", "dbus-daemon", "dbus-broker", "dbus-broker-lau", "pipewire", "pipewire-pulse", "wireplumber",
            "kwin_wayland", "plasmashell", "kded6", "kglobalaccel", "ksmserver", "konsole", "fish", "bash", "zsh", "sh", "python",
            "python3", "xdg-desktop-por", "xdg-document-po", "xdg-permission-", "Xwayland", "kepprofil", "gamma-panel"}
    res = {}
    uid = os.getuid()
    for p in psutil.process_iter(["name", "uids", "exe"]):
        try:
            if p.info["uids"] and p.info["uids"].real == uid and p.info["name"] and p.info["name"] not in skip:
                name = p.info["name"][:-4] if p.info["name"].lower().endswith(".exe") else p.info["name"]
                res.setdefault(name, p.info.get("exe") or "")
        except psutil.Error:
            continue
    return dict(sorted(res.items(), key=lambda kv: kv[0].lower()))


def kill_old_watcher():
    """Linuxon nincs régi figyelő, amit le kellene állítani."""


def _autostart_file():
    return AUTOSTART_DIR / "kepprofil.desktop"


def autostart_enabled():
    return _autostart_file().exists()


def set_autostart(on):
    f = _autostart_file()
    if not on:
        f.unlink(missing_ok=True)
        return
    cmd = f'"{sys.executable}" --tray' if FROZEN else f'"{sys.executable}" "{HERE / "kijelzo.py"}" --tray'
    AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
    f.write_text(f"[Desktop Entry]\nType=Application\nName={APP_NAME}\nExec={cmd}\nX-KDE-autostart-after=panel\n", encoding="utf-8")


def single_instance():
    """-> (már_fut, jelző-kezelő). Az első példány egy Unix-socketen hallgat; a második ide küld "show"-t."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.connect(str(SOCKET_PATH))
        s.close()
        return True, None
    except OSError:
        s.close()
    SOCKET_PATH.unlink(missing_ok=True)                    # elárvult socket-fájl
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(SOCKET_PATH))
    srv.listen(4)
    return False, srv


def signal_running(_ev=None):
    """A már futó példánynak jelzés: mutassa a panelt."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.connect(str(SOCKET_PATH))
        s.sendall(b"show\n")
    except OSError:
        pass
    finally:
        s.close()


def show_signaled(srv, ms):
    """Igaz, ha a második indítás jelzett a várakozás alatt."""
    srv.settimeout(ms / 1000.0)
    try:
        conn, _ = srv.accept()
    except (socket.timeout, OSError):
        return False
    try:
        conn.settimeout(1)
        return conn.recv(16).startswith(b"show")
    except OSError:
        return False
    finally:
        conn.close()


def open_native(p):
    """Fájl/mappa megnyitása az alapértelmezett programmal."""
    subprocess.Popen(["xdg-open", str(p)])
