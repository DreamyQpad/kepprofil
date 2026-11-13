"""Linux-megvalósítás (a system.py ezt tölti be Linuxon): futó programok, autostart, egy példány, megnyitás.

Az egypéldányosság és a `--action` parancsok ugyanazon a Unix-socketen mennek (`$XDG_RUNTIME_DIR/kepprofil.sock`).
"""
import os
import shlex
import shutil
import socket
import subprocess
import sys
from pathlib import Path

from consts import APP_NAME, FROZEN, HERE, RES_DIR

AUTOSTART_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart"
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
LAUNCHER_FILE = DATA_HOME / "applications" / "kepprofil.desktop"
LAUNCHER_ICON = DATA_HOME / "icons/hicolor/256x256/apps/kepprofil.png"
SOCKET_PATH = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "kepprofil.sock"
SHORTCUT_HELP = True                    # a felület mutatja a gyorsbillentyű-súgót (KDE-parancsok)


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


def _exec_base():
    """A program indító parancsa a .desktop fájlok Exec= sorához."""
    return f'"{sys.executable}"' if FROZEN else f'"{sys.executable}" "{HERE / "kijelzo.py"}"'


def ensure_launcher():
    """Programindító-bejegyzés (alkalmazásmenü): a .desktop fájl és az ikon létrehozása, ha hiányzik vagy elavult.
    A bejegyzés a panelt nyitja (a már futó példányban); a jobb-klikkes menüben az éjszakai mód és a semleges kép is elérhető."""
    base = _exec_base()
    text = (f"[Desktop Entry]\nType=Application\nName={APP_NAME}\nGenericName=Kijelzőprofilok\n"
            f"Comment=Játékonkénti kijelzőbeállítás: gamma, kontraszt, fényerő, vibrance\n"
            f"Exec={base}\nIcon=kepprofil\nTerminal=false\nCategories=Utility;\nStartupNotify=false\n"
            f"Actions=Night;Neutral;\n\n"
            f"[Desktop Action Night]\nName=Éjszakai mód\nExec={base} --action night\n\n"
            f"[Desktop Action Neutral]\nName=Semleges kép\nExec={base} --action neutral\n")
    try:
        if not LAUNCHER_ICON.exists():
            from PIL import Image
            ico = RES_DIR / "assets" / "icon.ico"
            if ico.is_file():
                LAUNCHER_ICON.parent.mkdir(parents=True, exist_ok=True)
                with Image.open(ico) as im:
                    if (256, 256) in im.ico.sizes():
                        im.size = (256, 256)
                    im.convert("RGBA").save(LAUNCHER_ICON)
        if not LAUNCHER_FILE.exists() or LAUNCHER_FILE.read_text(encoding="utf-8") != text:
            LAUNCHER_FILE.parent.mkdir(parents=True, exist_ok=True)
            LAUNCHER_FILE.write_text(text, encoding="utf-8")
    except OSError:
        pass


def _autostart_file():
    return AUTOSTART_DIR / "kepprofil.desktop"


def autostart_enabled():
    return _autostart_file().exists()


def set_autostart(on):
    f = _autostart_file()
    if not on:
        f.unlink(missing_ok=True)
        return
    cmd = f"{_exec_base()} --tray"
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


def send_action(action):
    """Akció küldése a futó példánynak (`kijelzo.py --action …`). Igaz, ha volt kinek elküldeni."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.settimeout(2)
        s.connect(str(SOCKET_PATH))
        s.sendall(f"action:{action}\n".encode("utf-8"))
        return True
    except OSError:
        return False
    finally:
        s.close()


def show_signaled(srv, ms, on_action=None):
    """Igaz, ha a második indítás panelt kért a várakozás alatt; az `action:` üzenetet az on_action(akció) kapja meg."""
    srv.settimeout(ms / 1000.0)
    try:
        conn, _ = srv.accept()
    except (socket.timeout, OSError):
        return False
    try:
        conn.settimeout(1)
        msg = conn.recv(1024).decode("utf-8", "replace").strip()
    except OSError:
        return False
    finally:
        conn.close()
    if msg.startswith("action:"):
        if on_action and msg[7:]:
            on_action(msg[7:])
        return False
    return msg.startswith("show")


def action_command(action):
    """A `--action` parancssor, amit a KDE Gyorsbillentyűk alá lehet kötni."""
    base = [sys.executable] if FROZEN else [sys.executable, str(HERE / "kijelzo.py")]
    return shlex.join([*base, "--action", action])


def open_shortcut_settings():
    """A KDE Gyorsbillentyűk beállítópanelje. Igaz, ha elindult."""
    for cmd in (["systemsettings", "kcm_keys"], ["kcmshell6", "kcm_keys"]):
        if shutil.which(cmd[0]):
            subprocess.Popen(cmd)
            return True
    return False


def open_native(p):
    """Fájl/mappa megnyitása az alapértelmezett programmal."""
    subprocess.Popen(["xdg-open", str(p)])
