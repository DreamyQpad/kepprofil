# Képprofil – Linux (KDE Plasma Wayland)

Átadó jegyzet: a Linux-rész **Windows-gépen íródott, Linuxon még soha nem futott**. Cél: ugyanazt tudja, mint a Windowsos
változat, egyetlen kódbázisból (`main` ág, nincs külön linux ág).

## Felépítés
- `kijelzo.py` – belépési pont. `hw.py` / `system.py` – platformválasztók (win32 → `*_windows`, különben `*_linux`).
- `hw_common.py` – közös: OpenRGB (`Rgb`), gyorsgomb-szöveg (`parse_hotkey`).
- `hw_linux.py` – monitorok (kscreen-doctor + EDID), ICC-profil, nvibrant, powerprofilesctl, ébredés (logind), `Display`.
- `system_linux.py` – futó programok, autostart (`~/.config/autostart`), egypéldányosság (Unix-socket), xdg-open.
- `engine.py`, `config.py`, `gui.py` – platformfüggetlen; csak a `hw` / `system` felületét használják.
- Adatok Linuxon: `~/.config/kepprofil/` (presets.json, settings.json, log.txt). A `presets.json` a Windowsról átmásolható:
  a monitor-azonosító (pl. `SAM777F`) mindkét rendszeren az EDID-ből jön.

## Indítás (forrásból)
```
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python kijelzo.py          # --tray: ablak nélkül a tálcára
```
Kell hozzá: `kscreen-doctor` (KDE), tkinter (`python-tk` / `tk` csomag), a tálcához StatusNotifier (KDE-n alap).
NVIDIA-nál vibrance-hoz: `nvibrant` (AUR/pip), a kimenet–index párosítás a `~/.config/kepprofil/vibrance_index.json`-ban
(`{"HDMI-A-1": 0, "HDMI-A-2": 3}`; ez a régi asztali gépé, a laptopon mást kell megadni). Nem NVIDIA-s gépen a vibrance
nem érhető el (`vibrance_ok` = hamis), a gamma/kontraszt/fényerő attól még megy.

## Hogyan működik (a régi `gamma-panel`-ből, az volt bevált)
- Gamma + kontraszt + fényerő (+ az R/G/B erősítés és az éjszakai mód) = saját ICC-profil, `~/.local/share/color/icc/kepprofil-<kimenet>-….icc`,
  beállítás: `kscreen-doctor output.<név>.iccprofile.<út> output.<név>.colorProfileSource.ICC`; semleges kép: `colorProfileSource.sRGB`.
- Vibrance: `nvibrant <8 érték>`; nyers érték −1024…1023, 50 % = 0.
- A régi program: `G:\gamma-panel\gamma-panel` (a BACKUP pendrive-on).

## Ami még NINCS kész / ellenőrizni kell (sorrendben)
1. Fusson el egyáltalán: `python kijelzo.py --tray`, majd panel. Várható első hibák: tk-betűtípus, pystray backend, importok.
2. `kscreen-doctor -j` kimenete: a `pos` / `size` kulcsok (monitor_rect) és az `enabled` mező ténylegesen így vannak-e.
3. Az ICC átvétele: látszik-e a kép változása, és a **preset-csúszkák előnézete** (a GUI szálban hívja az `apply`-t, a
   kscreen-doctor ~100–300 ms → szaggathat; a régi program `LatestJob`-bal összevonta a hívásokat – kell egy ilyen).
4. Az éjszakai mód/R-G-B erősítés a profil csatornánkénti görbéjével (`mult`) – nézd meg szemmel.
5. **Globális gyorsgomb**: Waylanden nincs szabványos. Terv: a futó példány Unix-socketen fogad parancsot
   (`kijelzo.py --action night|neutral|preset:<monitor>:<név>`), és ezeket a KDE Rendszerbeállítások → Gyorsbillentyűk
   alá lehet kötni. A `Hotkeys` osztály (`hw_linux.py`) most üres.
6. **Képernyő-értesítés** (toast): Waylanden a tk-ablak nem átkattintható/legfelső → helyette `notify-send` / KDE-értesítés.
7. **Játékfelismerés**: a Linuxos folyamatnév 15 karakterre csonkol (`/proc/<pid>/comm`); Proton-játékoknál a
   `process` mezőt a cmdline alapján is egyeztetni kell (`Engine.refresh_running`).
8. `drifted()` Linuxon mindig `None` (nincs kiolvasás) – az ébredés/kijelzőváltás utáni újraalkalmazás ezért itt nem hat;
   ha kell, ébredéskor feltétel nélkül újra `apply`.
9. Telepítő / csomag Linuxra (PKGBUILD vagy AppImage) – később.
10. A `Unix-socketes egypéldányosság` Windowson nem tesztelhető volt (nincs AF_UNIX) – Linuxon próbáld ki: két indítás.

## Tesztek
A Windowson írt tesztek a Claude scratchpadben voltak (nem a repóban). A tiszta Linux-részek (ICC-fejléc/címkék,
EDID-azonosító, `powerprofilesctl`-kimenet, nvibrant-leképezés, kscreen-JSON) Windowson 16/16-ra lefutottak.
