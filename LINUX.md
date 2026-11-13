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

## Telepítés a kész csomagból (ajánlott)
A Windowsos fejlesztői gépen épül a csomag ugyanabból a forrásból (`build_linux.py`, lásd a README-t); a Windows-réteg
(`hw_windows`, `system_windows`) nincs benne. Linuxon:
```
tar xzf Kepprofil-linux-<verzió>.tar.gz && cd kepprofil-<verzió>
./install.sh --deps        # a hiányzó rendszercsomagokat (tk, python-gobject, libayatana-appindicator, libkscreen, qt6-tools) is felrakja
kepprofil                  # vagy: kepprofil --tray
```
Az `install.sh` a `~/.local/share/kepprofil/` alá másol (program + virtuális környezet `--system-site-packages`-szel),
és létrehozza a `~/.local/bin/kepprofil` parancsot. Újrafuttatva frissít; a beállításokhoz (`~/.config/kepprofil/`) nem nyúl.
Eltávolítás: `./uninstall.sh` (`--purge`: a beállításokat is törli). A Linuxos rész ezzel a csomaggal még **nem lett kipróbálva
valódi gépen**; a szkriptek logikáját hamis parancsokkal ellenőriztük.

## Indítás (forrásból)
```
python -m venv --system-site-packages .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python kijelzo.py          # --tray: ablak nélkül a tálcára
```
Kell hozzá: `kscreen-doctor` (KDE), `qdbus6` (a `qt6-tools` csomagból; az értesítés az aktív képernyőre kerül, nélküle a teljes asztal közepére), tkinter (`python-tk` / `tk` csomag), a tálcához StatusNotifier (KDE-n alap) és `python-gobject` + `libayatana-appindicator` (a menühöz, lásd 11.).
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
5. **Globális gyorsgomb**: Waylanden nincs szabványos, ezért a futó példány a Unix-socketen fogad parancsot
   (`kijelzo.py --action night|neutral|cycle|preset:<monitor>:<név>|variant:<monitor>:<név>:<változat>`;
   kilépési kód: 0 elküldve, 1 nem fut, 2 ismeretlen akció). A billentyűt a KDE köti hozzá (Rendszerbeállítások →
   Gyorsbillentyűk → Parancs); a tálcamenü „Gyorsbillentyűk (KDE)…" pontja kész, másolható parancsokat ad. A GUI saját
   gyorsgomb-mezői Linuxon nem hatnak (a `Hotkeys` osztály üres). Élesben ellenőrizve: akciók, ICC-váltás, vágólap.
6. **Képernyő-értesítés** (toast): Waylanden a tk-ablak nem átkattintható/legfelső → helyette `notify-send` / KDE-értesítés.
7. **Játékfelismerés**: a Linuxos folyamatnév 15 karakterre csonkol (`/proc/<pid>/comm`); Proton-játékoknál a
   `process` mezőt a cmdline alapján is egyeztetni kell (`Engine.refresh_running`).
8. `drifted()` Linuxon mindig `None` (nincs kiolvasás) – az ébredés/kijelzőváltás utáni újraalkalmazás ezért itt nem hat;
   ha kell, ébredéskor feltétel nélkül újra `apply`.
9. Telepítő / csomag Linuxra (PKGBUILD vagy AppImage) – később.
10. A `Unix-socketes egypéldányosság` Windowson nem tesztelhető volt (nincs AF_UNIX) – Linuxon próbáld ki: két indítás.
11. **Tálcaikon Plasma Waylanden**: a pystray `appindicator` backendjét kell használni (StatusNotifierItem + dbusmenu), mert
    a `xorg` (XEMBED) backendnek nincs menüje (`HAS_MENU = False`), és az `xembedsniproxy` a kattintást sem adta át neki
    (se bal, se jobb gomb nem érkezett meg) → jobb klikkre nem jött fel semmi. Az `appindicator` két feltétele:
    - a venvben legyen `gi` (Arch: `python-gobject`, `libayatana-appindicator`): a venv `--system-site-packages`-szel
      készüljön (`include-system-site-packages = true` a `.venv/pyvenv.cfg`-ben); `gi` nélkül a pystray csendben az
      `xorg`-ra esik vissza (ekkor `run_app` legalább az 1x1-es ablakot 32x32-re állítja, hogy az ikon látszódjon);
    - a `run_detached()` nem indít GLib-főciklust, a mi főciklusunk a Tk → `start_tray` külön szálon futtat egyet.
      Enélkül az ikon létre sem jön (ez volt a régebbi „nem jelentkezett be a StatusNotifierWatcherhez").
    Mérve: az ikon az `org.kde.StatusNotifierWatcher`nél bejelentkezik, és a dbusmenu kiadja a menüelemeket.

## Tesztek
`python3 -m unittest discover -s tests` a repó gyökeréből (hardver és KDE nélkül fut, a külső parancsokat helyettesíti):
- `tests/test_monitor_rect.py`: az értesítés helye (aktív képernyő, leválasztott monitor, `qdbus6`/`qdbus` hibaágak).
- `tests/test_toggle_night_toast.py`: az éjszakai mód értesítése a megfelelő monitort kapja.

A tiszta Linux-részek (ICC-fejléc/címkék, EDID-azonosító, `powerprofilesctl`-kimenet, nvibrant-leképezés, kscreen-JSON)
tesztjei a Claude scratchpadjében voltak (Windowson 16/16-ra lefutottak), a repóban nincsenek.
