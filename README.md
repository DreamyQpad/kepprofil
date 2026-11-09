# Képprofil

Tálcás program, ami **játékonként más kijelzőbeállítást** kapcsol: gamma, kontraszt, fényerő, színcsatornák és
NVIDIA digital vibrance – monitoronként. Ha elindul egy beállított játék, a hozzá tartozó preset magától bekapcsol,
kilépéskor visszaáll az alaphelyzet. Kézzel is váltható tálcamenüből vagy gyorsgombbal.

Eredetileg két, kézzel összerakott szkriptből (Linuxos KDE-panel, majd PowerShell-es változat) nőtt egy közös programmá.

**Állapot (v2.5):** Windows 11-en használatra kész. Linux (KDE Plasma Wayland) a kódban megvan, de még **soha nem futott
Linuxon** – lásd [LINUX.md](LINUX.md).

## Mit tud

- **Presetek monitoronként**: gamma (0,30–2,80 az NVIDIA-skálán), kontraszt, fényerő, vibrance, R/G/B erősítés (Színek fül).
- **Változatok**: egy presetnek több csúszkaállása lehet (pl. pályánként), külön gyorsgombbal vagy egy körző gombbal.
- **Játékfigyelő**: a preset „process" mezője alapján automatikusan be-/kikapcsol; kézi felülbírálás játék közben is.
- **Tálcamenü és globális gyorsgombok**: presetek, éjszakai mód, semleges kép.
- **Összehasonlítás**: gombnyomásig a semleges kép látszik.
- **Éjszakai mód**: monitoronként kapcsolható, állítható erősséggel; játék-preset alatt szünetel.
- **Profil presetenként**: energiaprofil és RGB (OpenRGB SDK: szín / ki / mentett állapot) is váltható.
- **Képernyő-értesítés** váltáskor (átkattintható, a játék fölött is látszik – exkluzív fullscreen alatt nem).
- **Ébredés és kijelzőváltás után automatikus visszaállítás**: ha a driver nullázta a görbét, a program 1–15 mp-en belül
  visszaállítja (ép kép mellett nem nyúl semmihez, így nincs villanás).
- **Mentés**: export/import, napi automatikus másolat (utolsó 10), mentetlen-jelzés váltáskor, fájlnapló (`log.txt`).
- Telepítő (Inno Setup), automatikus indítás a Windows-szal, egy példány.

## Platformok

| | Windows 11 | Linux (KDE Plasma Wayland) |
|---|---|---|
| Gamma / kontraszt / fényerő | `SetDeviceGammaRamp` | ICC-profil + `kscreen-doctor` *(nem tesztelt)* |
| Vibrance | NVAPI | `nvibrant` – csak NVIDIA *(nem tesztelt)* |
| Globális gyorsgomb | `RegisterHotKey` | még nincs (terv: parancs + KDE-gyorsbillentyű) |
| Ébredés-észlelés | `WM_POWERBROADCAST` | logind `PrepareForSleep` *(nem tesztelt)* |
| Energiaprofil | `powercfg` | `powerprofilesctl` *(nem tesztelt)* |

Egyetlen kódbázis, a platformfüggő részek külön modulban (`hw_windows.py` / `hw_linux.py`, `system_windows.py` /
`system_linux.py`); a `hw.py` és a `system.py` választja ki a megfelelőt.

## Felépítés

| Fájl | Szerep |
|---|---|
| `kijelzo.py` | belépési pont |
| `consts.py` | verzió, útvonalak, állandók |
| `hw.py`, `system.py` | platformválasztó |
| `hw_windows.py`, `hw_linux.py` | monitorok, kép beállítása (`Display`), energiaprofil, gyorsgomb, rendszeresemények |
| `system_windows.py`, `system_linux.py` | futó programok, autostart, egy példány, megnyitás |
| `hw_common.py` | közös: OpenRGB, gyorsgomb-szöveg értelmezése |
| `config.py` | presetek, beállítások, mentés, napló |
| `engine.py` | motor: aktív presetek, játékfigyelő, visszaállítás, mellékhatások |
| `gui.py` | felület (CustomTkinter), tálcaikon, értesítés |

## Futtatás forrásból

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt      # Linuxon: .venv/bin/pip
.venv\Scripts\python kijelzo.py                    # --tray: ablak nélkül a tálcára
```

Adatok: Windowson `%APPDATA%\Képprofil\` (telepítve; forrásból a projektmappa, vagy `--appdata`-val a telepített adatok),
Linuxon `~/.config/kepprofil/`. A `presets.json` a két rendszer között átvihető: a monitor-azonosító (pl. `SAM777F`)
mindkét helyen az EDID-ből jön.

## Telepítő építése (Windows)

Kell hozzá: `pyinstaller` a venvben és [Inno Setup 6](https://jrsoftware.org/isinfo.php).

```
powershell -ExecutionPolicy Bypass -File build.ps1
```

Eredmény: `out\Kepprofil-telepito.exe` (és másolat a Dokumentumok\telepitok mappába). A verziót a `consts.py` `VERSION`
értékéből veszi.

## Terv

**Windows**
- Frissítés-ellenőrzés a programból (verzió megjelenítése már van; telepítő-mappából vagy GitHub Releases-ből).
- Gyorsabb játékfelismerés folyamatindítás-eseményekkel (most 2 mp-es lekérdezés).
- Hibák jelzése a tálcaikonon (pl. nem elérhető NVAPI / OpenRGB), nem csak a naplóban.
- Időzített éjszakai mód (napnyugta vagy fix időpont).
- Színhőmérséklet-csúszka (Kelvin) az R/G/B erősítés mellé.
- A `gui.py` további bontása (a `run_app` még egyetlen nagy függvény).

**Linux** (részletesen: [LINUX.md](LINUX.md))
- Első futtatás és hibajavítás valódi KDE Wayland alatt.
- Globális gyorsgomb: futó példány parancsot fogad, a KDE gyorsbillentyűkhöz kötve.
- KDE-értesítés a tk-ablak helyett, a csúszkák előnézetének összevonása (kscreen-doctor lassú).
- Játékfelismerés Proton alatt (a folyamatnév 15 karakterre csonkul).
- Csomagolás (PKGBUILD vagy AppImage).

## Tudott korlátok

- Exkluzív teljes képernyős játék fölött a képernyő-értesítés nem látszik.
- Valódi altatás utáni visszaállítás és hosszú játékmenet alatti működés nem lett teljesen végigtesztelve.

## Licenc

Még nincs megadva.
