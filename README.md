# Képprofil

Tálcás program, ami **játékonként más kijelzőbeállítást** kapcsol: gamma, kontraszt, fényerő, színcsatornák és
NVIDIA digital vibrance – monitoronként. Ha elindul egy beállított játék, a hozzá tartozó preset magától bekapcsol,
kilépéskor visszaáll az alaphelyzet. Kézzel is váltható tálcamenüből vagy gyorsgombbal.

Eredetileg két, kézzel összerakott szkriptből (Linuxos KDE-panel, majd PowerShell-es változat) nőtt egy közös programmá.

**Állapot (v2.27):** Windows 11-en és Linuxon (KDE Plasma Wayland) is használatra kész; a Linuxos változat valódi gépen
tesztelve, működik – lásd [LINUX.md](LINUX.md).

## Mit tud

- **Presetek monitoronként**: gamma (0,30–2,80 az NVIDIA-skálán), kontraszt, fényerő, vibrance, R/G/B erősítés (Színek fül).
- **Változatok**: egy presetnek több csúszkaállása lehet (pl. pályánként), külön gyorsgombbal vagy egy globális léptető gombbal (a következő változatra lép).
- **Játékfigyelő**: a preset „process" mezője alapján automatikusan be-/kikapcsol; kézi felülbírálás játék közben is. Emelt jogú futásnál (Windows) a játék indulását/kilépését eseményből ismeri fel, nem emelt jognál 1 mp-es lekérdezéssel; a napló jelzi, melyik mód aktív.
- **Tálcamenü és globális gyorsgombok**: presetek, éjszakai mód, semleges kép.
- **Játék-overlay** (Program fül → „Gyorsgomb: játék-overlay"): egy gombbal a játék fölé kerül az aktuális játék profilja
  (fényerő, kontraszt, gamma, vibrance, R/G/B), és a játék elvesztése nélkül, billentyűzettel szerkeszthető: ↑↓ sor,
  ←→ állít (Shift: ×5), Del alapérték, Enter mentés, N új változat a mostani állásból, Esc elvet. Nyitva tartás alatt ezek
  a gombok nem jutnak el a játékhoz; ha a játék kilép vagy a preset vált, a panel magától bezárul.
- **Térkép-overlay (Escape from Tarkov, csak Windows)**: a Tarkov logjából (`Logs\log_*\*application_000.log`) felismeri a pályát
  (betöltéskor előkészíti, a raid indulásakor megnyitja, a raid végén bezárja), és a tarkov.dev interaktív térképét mutatja
  a játék fölött. Három mód (Program fül, két gyorsgomb): **pillantás** (áttetsző, átkattintható, a játék megtartja a fókuszt),
  **billentyűzet** (←↑↓→ mozgat, numpad + és − nagyít, PageUp/PageDown az átlátszóságot állítja, Esc kilép; ekkor ezek a gombok nem jutnak el a játékhoz), **egér**
  (az ablak fókuszt kap, mozgatható, kattintható; az Esc elrejti a térképet; kilépéskor a játék visszakapja a fókuszt, a hely megmarad). Ha a program nem tudja, melyik pályán vagy, a gyorsgomb egér módban nyitja a legutóbb választott (vagy az első) térképet, és a térkép tetején lévő
  **pályaválasztóval** kézzel választhatsz; a program megtanulja a raidben látott ismeretlen pályanevet (a `map_learned` beállításba menti), így legközelebb magától felismeri; az ismeretlen pályánál a régi raid térképét nem mutatja. A megtanult neveket a Program fülön listázza, és egy gombbal törölhetők. Az átlátszóság
  és az automatikus megnyitás állítható. A térkép külön folyamat (`--map`, pywebview + WebView2), nem injektál a játékba.
- **Főmenü és böngésző (csak Windows)**: egy gyorsgombbal (alapból **Shift+Tab**, a Program fülön átállítható) a játék fölé
  jön a menü: **Térkép**, **Böngésző**, **Képbeállítások** (a profil-overlay). Kattintható, és ↑↓ / Enter / Esc is működik; a
  játék megtartja a fókuszt. A böngésző minimális (külön folyamat, Google kezdőoldal, Vissza / Előre / Bezár gomb, nincs címsor);
  csak a használata alatt fut, és a térkép fölé kerül, ha az is látszik. A tetején **könyvjelzősáv** van: a ☆ az éppen nyitott oldalt menti, a könyvjelzőre kattintva odalép, a × törli. A sáv **játékonként külön** van (az aktív játék presetjének neve alapján; ha nincs aktív játék, a közös „Általános” sáv látszik); legfeljebb 30 könyvjelző fér egy sávba. A Képprofil futása alatt a Shift+Tab a menüt nyitja.
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
| Gamma / kontraszt / fényerő | `SetDeviceGammaRamp` | ICC-profil + `kscreen-doctor` |
| Vibrance | NVAPI | `nvibrant` – csak NVIDIA |
| Globális gyorsgomb | `RegisterHotKey` | `kijelzo.py --action …` + KDE-gyorsbillentyű (tálcamenü: „Gyorsbillentyűk (KDE)…"); a játék-overlay Linuxon nem érhető el |
| Ébredés-észlelés | `WM_POWERBROADCAST` | logind `PrepareForSleep` |
| Energiaprofil | `powercfg` | `powerprofilesctl` |

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
| `hotkey_layers.py` | az overlay, a menü és a térkép gyorsgomb-rétegei: az alap fölé kerülnek, egymást nem írják felül |
| `hw_common.py` | közös: OpenRGB, gyorsgomb-szöveg értelmezése |
| `config.py` | presetek, beállítások, mentés, napló |
| `engine.py` | motor: aktív presetek, játékfigyelő, visszaállítás, mellékhatások |
| `tarkov_log.py` | a Tarkov logjának feldolgozása: pályaesemények (preload / raid / end), pálya-táblázat, naplókövetés |
| `map_overlay.py` | a térkép-overlay szülő oldali vezérlője (módok, gyorsgombok, folyamatkezelés) és a logfigyelő összekötése |
| `menu_overlay.py` | a főmenü: modell (léptetés), nem aktiválódó tk-nézet, vezérlő (nyitás, billentyűfoglalás, akciók) |
| `bookmarks.py` | a böngésző könyvjelzői játékonként: hozzáadás, törlés, ellenőrzés (csak http/https) |
| `web_bar.py` | a böngészőablak sávja (Vissza, Előre, ☆, könyvjelzők, Bezár) és a könyvjelző-sorok |
| `browser_overlay.py` | a böngészőfolyamat (`--web`) szülő oldali vezérlője |
| `map_window.py` | a térképfolyamat (`--map`): pywebview-ablak, parancshurok (stdin), ablak-módok |
| `overlay.py` | játék-overlay: modell (értékek, mentés), nem aktiválódó megjelenítő, vezérlő (nyitás, billentyűk) |
| `gui.py` | a felület belépője: a motor, a gyorsgombok, a tálca, az ablak és a főszál üzenetsorának összekötése |
| `gui_layout.py` | a főablak elrendezése (fülek, elemek létrehozása), viselkedés nélkül |
| `gui_panel.py` | a főablak viselkedése: kiválasztott monitor/preset/változat, csúszkák, mentés, állapotsor |
| `gui_preset_dialogs.py` | a preset- és változatműveletek párbeszédei (név bekérése, megerősítés, fájlválasztás), a művelet a `preset_ops`-szal |
| `gui_dialogs.py` | önálló párbeszédek: futó programok listája (játék kiválasztásához), gyorsbillentyű-súgó (Linux) |
| `gui_tray.py` | tálcaikon: rajza, indítása, menüje |
| `gui_toast.py` | képernyő-értesítés (kattintható-átlátszó, halványuló felirat a monitor tetején) |
| `gui_widgets.py` | önálló felületi elemek: gyorsgomb-mező, RGB-választó, csúszka-sor |
| `preset_ops.py` | preset- és változatműveletek (névellenőrzés, átnevezés, törlés, másolat, export/import), felület nélkül tesztelhetően |
| `build.ps1`, `build_linux.py`, `linux/` | Windowsos telepítő építése; Linux-csomag építése és a benne lévő `install.sh` / `uninstall.sh` |

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

## Linux-csomag építése

Ugyanabból a forrásból, a Windowsos gépen (nincs külön Linux-ág):

```
.venv\Scripts\python build_linux.py
```

Eredmény: `out\Kepprofil-linux-<verzió>.tar.gz` (és másolat a Dokumentumok\telepitok mappába): a program a Windows-réteg nélkül,
`install.sh` / `uninstall.sh` szkriptekkel. Az építő ellenőrzi, hogy minden modul lefordul, és nem hivatkozik hiányzó modulra.
Telepítés Linuxon: [LINUX.md](LINUX.md).

## Terv

**Windows**
- Frissítés-ellenőrzés a programból (verzió megjelenítése már van; telepítő-mappából vagy GitHub Releases-ből).
- Hibák jelzése a tálcaikonon (pl. nem elérhető NVAPI / OpenRGB), nem csak a naplóban.
- Időzített éjszakai mód (napnyugta vagy fix időpont).
- Színhőmérséklet-csúszka (Kelvin) az R/G/B erősítés mellé.

**Linux** (részletesen: [LINUX.md](LINUX.md))
- Globális gyorsgomb: futó példány parancsot fogad, a KDE gyorsbillentyűkhöz kötve.
- KDE-értesítés a tk-ablak helyett, a csúszkák előnézetének összevonása (kscreen-doctor lassú).
- Játékfelismerés Proton alatt (a folyamatnév 15 karakterre csonkul).
- Csomagolás (PKGBUILD vagy AppImage).

## Tudott korlátok

- Exkluzív teljes képernyős játék fölött a képernyő-értesítés nem látszik.
- Valódi altatás utáni visszaállítás és hosszú játékmenet alatti működés nem lett teljesen végigtesztelve.

## Licenc

Még nincs megadva.
