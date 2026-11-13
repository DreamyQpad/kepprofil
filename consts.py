"""Közös állandók és elérési utak (más modult nem importál)."""
import os
import shutil
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
APP_NAME = "Képprofil"
VERSION = "2.9"                      # a build.ps1 innen veszi a telepítő verzióját
OLD_APP_NAME = "Kijelző"             # az előző név: adatmappa és parancsikon átvétele
HERE = Path(sys.executable).parent if FROZEN else Path(__file__).resolve().parent
RES_DIR = Path(getattr(sys, "_MEIPASS", HERE))
USE_APPDATA = FROZEN or "--appdata" in sys.argv                       # --appdata: forrásból futtatva is a telepített adatok (teszt-ikon)
if sys.platform == "win32":
    DATA_DIR = (Path(os.environ.get("APPDATA", str(HERE))) / APP_NAME) if USE_APPDATA else HERE
else:                                                                 # Linux: XDG-konfigmappa
    DATA_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "kepprofil"
if sys.platform == "win32" and FROZEN and not DATA_DIR.exists():                                  # első indítás az új név alatt
    _old_data = DATA_DIR.parent / OLD_APP_NAME
    if _old_data.is_dir():
        try:
            shutil.copytree(_old_data, DATA_DIR)
        except OSError:
            pass
CONFIG_FILE = DATA_DIR / "presets.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
LOG_FILE = DATA_DIR / "log.txt"
OLD_DIR = Path.home() / "Tools" / "display-presets"          # az előző (PowerShell-es) változat helye
STARTUP_DIR = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
CREATE_NO_WINDOW = 0x08000000
NEUTRAL = (2.2, 50, 50, 50)          # gamma, kontraszt, fényerő, vibrance
