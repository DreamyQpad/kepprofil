# Játék-overlay megvalósítási terv

> **Végrehajtóknak:** a lépések `- [ ]` jelölésűek; a feladatokat sorrendben kell végigvinni (superpowers:executing-plans).

**Cél:** egy gyorsgombbal nyíló, billentyűzettel vezérelt, fókuszt nem lopó panel a játék monitorján: csúszkák élő
állítása, mentés a mostani változatba, új változat felvétele.

**Felépítés:** a logika (modell, vezérlő) az új `overlay.py`-ban, a megjelenítő (tk ablak) szintén ott; a motor
(`engine.py`) kapja a mentés/új változat műveleteket; a `Hotkeys` megtanul módosító nélküli, nyers (mods, vk, ismétlés)
gombokat; a `gui.py` csak összeköti. Tesztek: stdlib `unittest` (a `.venv`-ben nincs pytest), stubolt kijelzővel.

**Technológia:** Python 3.13, tkinter, ctypes (`RegisterHotKey`), `unittest`.

**Terv (spec):** `docs/superpowers/specs/2026-11-13-jatek-overlay-design.md`

## Globális megkötések
- Windows-only működés; Linuxon a modulok importálhatók maradnak (`hw_linux.foreground_monitor_id` -> `None`).
- Gamma a panelen az NVIDIA-skálán (0,30–2,80, lépés 0,01, alap 1,00); a mentett érték belső gamma = megjelenített × 2,2.
- Tartományok/alapértékek mint a főablakban: fényerő, kontraszt, vibrance 0–100 (alap 50); R/G/B 0–100 (alap 100).
- A játék nem kap fókuszt/aktiválást; zárás után egyetlen lefoglalt overlay-gomb sem marad.
- A kódban/kommentben nincs fejlesztési-folyamat nyom; a kommentek magyarul, jelen időben, a „miért"-et írják.
- Commit csak kérésre (a munkafában korábbi, nem commitolt v2.6-os módosítások vannak, azokhoz nem nyúlunk).
- Tesztek nem írhatják a valódi `presets.json`/`settings.json`-t (a motor `save_config`/`save_settings` metódusát
  stubolni kell).

## Review Focus (nem triviális esetek, mindegyikhez van teszt a megjelölt feladatban)
1. Gamma-átváltás: 1,00 megjelenített = 2,2 belső; lépéskor nincs lebegőpontos elcsúszás (0,30-tól 0,01-es lépésekkel) — 2. feladat.
2. Új változat névütközés: van „Változat 2" -> „Változat 3"; változat nélküli preset -> „Alap" + „Változat 2" — 1. feladat.
3. N után az Esc csak az N utáni, mentetlen módosítást dobja el; az új változat megmarad — 2. feladat.
4. Nincs aktív preset: nem nyílik, jelzés; ugyanaz a gomb másodszor zár; zárás után érkező billentyű figyelmen kívül marad — 5. feladat.
5. Játék kilép / preset vált nyitva tartás alatt: a panel automatikusan zár, a kép a mentett állapotra áll, a gombok felszabadulnak — 5. feladat.

## Fájlok
- Módosít: `config.py` (beállítás), `engine.py` (`overlay_target`, `save_values`, `add_variant`, `hotkey_map`),
  `hw_common.py` (`OVERLAY_KEYS`), `hw_windows.py` (`Hotkeys` nyers gombok, `foreground_monitor_id`), `hw_linux.py`
  (`foreground_monitor_id`), `gui.py` (összekötés, beállítás a Program fülön), `consts.py` (VERSION 2.7), `README.md`.
- Új: `overlay.py` (`OverlayModel`, `OverlayView`, `OverlayController`), `tests/__init__.py`, `tests/stubs.py`
  (stubolt motor), `tests/test_engine_overlay.py`, `tests/test_overlay_model.py`, `tests/test_hotkeys.py`,
  `tests/test_overlay_view.py`, `tests/test_overlay_controller.py`.
- Tesztek futtatása: `.venv\Scripts\python.exe -m unittest discover -s tests -v` (a projektmappából).

---

### 1. feladat: Motor — beállítás, cél, mentés, új változat

**Fájlok:** `config.py`, `engine.py`, `tests/__init__.py`, `tests/stubs.py`, `tests/test_engine_overlay.py`

**Interfaces — előállítja:**
- `config.DEFAULT_SETTINGS["overlay_hotkey"] = ""`; `"overlay_hotkey"` a `SETTINGS_KEYS`-ben.
- `Engine.overlay_target(self, fg_mid: str | None = None) -> tuple[str, str] | None` — `(mid, preset)`: az `fg_mid` monitor,
  ha van rajta aktív preset; különben a `cfg["monitors"]` első monitora, amelyiken van aktív preset; különben `None`.
- `Engine.save_values(self, mid: str, name: str, vals: tuple, gain: list) -> None` — `vals = (gamma_belső, kontraszt,
  fényerő, vibrance)`; az érvényes változatba ír (a `cur_variant`), változat nélkül a preset felső szintjére; változatnál
  `mirror_first`; utána `save_config()`. Csak ezt az 5 mezőt módosítja (gyorsgomb, process, rgb marad).
- `Engine.add_variant(self, mid, name, vals, gain) -> str` — új változat az átadott értékekből; ha nem volt változat, az
  eddigi felső szintű értékek „Alap" néven az első változat; név: első szabad „Változat N" (N ≥ 2); beállítja
  `self.variant[(mid, name)]`-t; `save_config()`; visszaadja a nevet.
- `hotkey_map()` kiegészül: `m["overlay"] = self.set["overlay_hotkey"]`, ha be van állítva.
- `tests/stubs.py`: `make_engine(cfg=None, settings=None) -> (Engine, StubDisplay)` — a `engine.load_config`,
  `engine.load_settings`, `engine.Display`, `engine.Rgb`, `engine.find_dev` patch-elésével és `Engine.refresh_running`
  no-op-pal építi a motort; `eng.save_config`/`eng.save_settings` no-op számlálók; `StubDisplay.apply(dev, vals, mult)`
  rögzíti a hívásokat (`.calls`) és `True`-t ad; alap cfg: egy monitor `"MON1"` az `"Alap"` és `"Játék"` presettel.

- [ ] **1. lépés: hibázó tesztek** a `tests/test_engine_overlay.py`-ban (`unittest.TestCase`):
  `test_overlay_target_prefers_foreground_monitor`, `test_overlay_target_falls_back_to_first_active`,
  `test_overlay_target_none_without_active`, `test_save_values_without_variants_writes_top_level`,
  `test_save_values_writes_current_variant_and_mirrors_first`, `test_save_values_keeps_hotkey_and_process`,
  `test_add_variant_first_time_creates_alap_and_valtozat_2` (assert: `list(p["variants"]) == ["Alap", "Változat 2"]`,
  `eng.variant[("MON1","Játék")] == "Változat 2"`), `test_add_variant_name_collision_gives_next_free`
  (van „Változat 2" és „Változat 4" -> új: „Változat 3"), `test_hotkey_map_has_overlay_when_set`.
- [ ] **2. lépés:** futtasd, várt: mind elbukik (hiányzó metódus/beállítás).
- [ ] **3. lépés:** valósítsd meg a fenti interfészeket a `config.py`-ban és az `engine.py`-ban (a változat-/mirror
  logika a `gui.py` `new_variant_dialog`/`collect` mintáját követi; a motor lock-ja alatt).
- [ ] **4. lépés:** futtasd a teszteket, várt: zöld.

### 2. feladat: Modell — sorok, léptetés, mentés, új változat, elvetés

**Fájlok:** `overlay.py` (új), `tests/test_overlay_model.py`

**Interfaces — fogyaszt:** 1. feladat (`save_values`, `add_variant`), `config.pvals/pgain`, `Engine.preview(mid, vals, gain)`,
`Engine.sync(mid)`, `Engine.cur_variant`.
**Előállítja:**
- `overlay.ROWS: tuple[Row, ...]` — `Row(key, caption, lo, hi, step, default)` ebben a sorrendben: `b` Fényerő, `c` Kontraszt,
  `g` Gamma (0.30, 2.80, 0.01, 1.0), `v` Vibrance, `cr` Vörös, `cg` Zöld, `cb` Kék.
- `class OverlayModel(eng, mid: str, name: str)` — attribútumok: `values: dict[str, float]`, `sel: int`, `mid`, `name`;
  `variant: str | None`.
  - `title() -> str` (`"Játék · Változat 2"` vagy csak a preset neve), `move(d: int)` (körbeforog), `adjust(steps: int)`
    (a kijelölt sor `step × steps`, a tartományra szorítva, `round(…, 2)`), `reset_row()`.
  - `vals() -> tuple` (belső gamma = `round(g × 2.2, 4)`), `gain() -> list[int]`, `dirty() -> bool` (a betöltés/mentés/új
    változat óta eltér-e), `preview() -> bool` (`eng.preview`), `save()` (`eng.save_values`, utána nem dirty),
    `new_variant() -> str` (`eng.add_variant` a mostani értékekből, `variant` frissül, nem dirty),
    `discard()` (`eng.sync(mid)`; a `values` visszaáll a legutóbb mentett/betöltött állapotra).

- [ ] **1. lépés: hibázó tesztek:** `test_loads_values_of_current_variant_with_gamma_display_scale` (belső 2,2 -> 1,00),
  `test_adjust_clamps_at_both_ends`, `test_gamma_steps_do_not_drift` (0,30 + 250×0,01 == 2,80 pontosan),
  `test_move_wraps_around`, `test_reset_row_uses_row_default`, `test_vals_converts_gamma_back_to_internal`,
  `test_save_persists_into_current_variant`, `test_new_variant_keeps_values_and_switches_title`,
  `test_discard_after_new_variant_only_drops_later_changes` (módosít, N, módosít, Esc: az új változat megmarad az N-kori
  értékkel, a legutóbbi módosítás elveszik), `test_preview_calls_engine_preview_with_values_and_gain`.
- [ ] **2. lépés:** futtasd, várt: mind elbukik (az `overlay` modul még nincs).
- [ ] **3. lépés:** valósítsd meg a `Row`-t, a `ROWS`-t és az `OverlayModel`-t (csak a motor interfészére épül, tk-t nem importál).
- [ ] **4. lépés:** futtasd, várt: zöld (az 1. feladat tesztjeivel együtt).

### 3. feladat: Gyorsgomb-réteg — nyers gombok, előtér-monitor

**Fájlok:** `hw_common.py`, `hw_windows.py`, `hw_linux.py`, `tests/test_hotkeys.py`

**Interfaces — előállítja:**
- `hw_common.OVERLAY_KEYS: dict[str, tuple[int, int, bool]]` — művelet -> `(módosítók, vk, ismétlődik)`: `ov|up` (0,0x26,True),
  `ov|down` (0,0x28,True), `ov|left` (0,0x25,True), `ov|right` (0,0x27,True), `ov|sleft` (Shift=0x4,0x25,True), `ov|sright`
  (0x4,0x27,True), `ov|reset` (0,0x2E,False), `ov|save` (0,0x0D,False), `ov|new` (0,0x4E,False), `ov|close` (0,0x1B,False).
- `hw_windows.Hotkeys`: a `wanted` értéke szöveg **vagy** `(mods, vk, repeat)` hármas; hármasnál nincs `parse_hotkey`, és
  a `MOD_NOREPEAT` (0x4000) csak `repeat=False`-nál kerül rá (a szövegesek változatlanul NOREPEAT-tel mennek).
- `hw_windows.foreground_monitor_id() -> str | None` (az előtérben lévő ablak monitorának azonosítója a `list_monitors()`
  azonosítói közül); `hw_linux.foreground_monitor_id() -> None`.

- [ ] **1. lépés: hibázó tesztek** (`@unittest.skipUnless(sys.platform == "win32", …)`):
  `test_raw_keys_register_and_release` (`Hotkeys.set({"ov|up": (0,0x26,True)})`, megvárja a regisztrációt, ellenőrzi,
  hogy ugyanazt a gombot a teszt-szálból `RegisterHotKey`-jel nem lehet felvenni; `set({})` után fel lehet venni, majd
  `UnregisterHotKey`), `test_text_hotkeys_still_work` (`"ctrl+alt+9"`), `test_failed_set_reports_action` (a gombot előbb a
  teszt veszi fel -> `hk.failed` tartalmazza az akciót), `test_foreground_monitor_id_is_known_monitor` (az eredmény `None`
  vagy elem a `list_monitors()` azonosítói közül).
- [ ] **2. lépés:** futtasd, várt: elbukik (nincs nyers gomb támogatás / függvény).
- [ ] **3. lépés:** valósítsd meg a fenti módosításokat (`foreground_monitor_id`: `GetForegroundWindow` ->
  `MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)` -> `GetMonitorInfoW().szDevice` -> egyezés a `list_monitors()` `dev` mezőjével).
- [ ] **4. lépés:** futtasd, várt: zöld.

### 4. feladat: Megjelenítő — nem aktiválódó tk-ablak

**Fájlok:** `overlay.py`, `tests/test_overlay_view.py`

**Interfaces — fogyaszt:** `hw.overlay_style(w)`, `hw.monitor_rect(mid)`, `overlay.ROWS`.
**Előállítja:** `class OverlayView(root)` — `show(rect: tuple, model: OverlayModel, warning: str = "")` (felépíti/megjeleníti a
panelt a monitor jobb szélén, függőlegesen középen, ~340 px, alpha 0,92), `update(model, warning="")` (értékek, kijelölt sor,
címsor, súgósor, mentetlen-jelzés), `close()`, `is_open -> bool`, `hwnd -> int | None`.

- [ ] **1. lépés: hibázó tesztek** (valódi, eltűnt `tk.Tk()` gyökérrel):
  `test_show_does_not_take_foreground` (nyit egy másik tk-ablakot, `SetForegroundWindow`; `show` + `update` után
  `GetForegroundWindow` ugyanaz), `test_window_has_noactivate_topmost_toolwindow_styles` (az ablak ex-stílusában
  `WS_EX_NOACTIVATE 0x08000000`, `WS_EX_TOPMOST 0x8`, `WS_EX_TOOLWINDOW 0x80`), `test_update_shows_selected_row_and_values`
  (a megjelenített szövegek: kijelölt sor jelölője, `1.00`, `52%`), `test_close_destroys_window`.
- [ ] **2. lépés:** futtasd, várt: elbukik.
- [ ] **3. lépés:** valósítsd meg az `OverlayView`-t (mintaként a `gui.py` `show_toast` ablakkezelése; sötét háttér `#14161a`,
  kijelölt sor kiemelve, csúszka-sáv `tk.Canvas`-szal, súgósor: `↑↓ sor · ←→ állít · Shift ×5 · Del alap · N új változat ·
  Enter mentés · Esc elvet`, a mentetlen jelzés és a figyelmeztetés külön sor).
- [ ] **4. lépés:** futtasd, várt: zöld. A fókusz-teszt mellé készíts egy képernyőképet a panelről (`PIL.ImageGrab`) a
  scratchpadbe, és nézd meg szemmel is (kijelölés, olvashatóság).

### 5. feladat: Vezérlő — nyitás/zárás, billentyűk, automatikus zárás

**Fájlok:** `overlay.py`, `tests/test_overlay_controller.py`

**Interfaces — fogyaszt:** 1–4. feladat.
**Előállítja:** `class OverlayController(eng, root, set_hotkeys, foreground_mid, rect_for, hotkey_failed, main_visible)` ahol
`set_hotkeys(mapping: dict)` a `Hotkeys.set`, `foreground_mid() -> str | None`, `rect_for(mid) -> tuple | None`,
`hotkey_failed() -> set` (a `hk.failed`), `main_visible() -> bool` (a főablak látszik-e).
- `is_open -> bool`
- `toggle()` — zárva: ha `main_visible()` vagy nincs `overlay_target`: `eng.toast("Nincs aktív preset")` / semmi, és nem nyit;
  különben `eng.panel_open = True`, modell + nézet létrejön, `set_hotkeys({**eng.hotkey_map(), **OVERLAY_KEYS})`, majd 300 ms múlva
  a `hotkey_failed()` alapján a nem működő `ov|…` gombok figyelmeztetésként a nézetbe. Nyitva: `close(save=False)`.
- `key(action: str)` — `ov|up/down` -> `move(∓1)`; `ov|left/right` -> `adjust(∓1)`; `ov|sleft/sright` -> `adjust(∓5)`; `ov|reset`;
  `ov|save` -> `save()` + `close()` + `eng.toast("Mentve: …")`; `ov|new` -> `new_variant()` (nyitva marad, a címsor frissül);
  `ov|close` -> `close()`. Zárva figyelmen kívül hagy mindent. Minden változtatás után nézet-frissítés és 40 ms-os
  késleltetett előnézet (`model.preview()`).
- `close()` — nézet bezár, `discard()` (ha nem mentés történt), `eng.panel_open = False`, `set_hotkeys(eng.hotkey_map())`.
- `check()` — 500 ms-onként (`root.after`) hívandó: ha nyitva van és (`eng.active.get(mid) != name` vagy `main_visible()`),
  zár.

- [ ] **1. lépés: hibázó tesztek** (stubolt motor, valódi eltűnt tk-gyökér, `set_hotkeys` rögzít):
  `test_toggle_opens_for_active_game_and_registers_keys`, `test_toggle_without_active_preset_does_not_open_and_toasts`,
  `test_second_toggle_closes_and_restores_hotkeys` (utolsó `set_hotkeys` hívás == `eng.hotkey_map()`),
  `test_keys_adjust_and_preview_hits_display` (a `StubDisplay.calls` változik a ←-re), `test_enter_saves_and_closes`,
  `test_escape_restores_saved_image` (a legutóbbi `calls` a mentett értékekhez tartozik), `test_n_creates_variant_and_stays_open`,
  `test_key_after_close_is_ignored`, `test_auto_close_when_active_preset_changes` (`eng.active.pop(mid)` + `check()`),
  `test_does_not_open_while_main_panel_visible`, `test_warns_about_failed_overlay_keys`.
- [ ] **2. lépés:** futtasd, várt: elbukik.
- [ ] **3. lépés:** valósítsd meg a vezérlőt (a tk-hívások a főszálban; nincs külön szál).
- [ ] **4. lépés:** futtasd az összes tesztet, várt: zöld.

### 6. feladat: Összekötés a programmal, beállítás, kiadás

**Fájlok:** `gui.py`, `consts.py`, `README.md`

- [ ] **1. lépés (`gui.py`):** a `run_app`-ban `overlay = OverlayController(eng, root, hk.set, foreground_monitor_id, monitor_rect,
  lambda: hk.failed, lambda: root.state() != "withdrawn")`; a `pump` `"hk"` ágában: `"overlay"` -> `overlay.toggle()`, `ov|…` ->
  `overlay.key(action)`, más -> `eng.run_action`; a `show_panel()` elején `overlay.close()` ha nyitva; `root.after(500, …)` a
  `overlay.check()`-hez; a `quit_app`-ban zárás.
- [ ] **2. lépés (`gui.py`):** Program fülön új gyorsgomb-mező („Gyorsgomb: játék-overlay (a mostani játék profilja)", `ui["ovhk"]`,
  `set_setting("overlay_hotkey", …)`, induláskor betöltve), a magyarázó szöveggel (billentyűk, exkluzív fullscreen korlát).
- [ ] **3. lépés:** `consts.VERSION = "2.7"`; `README.md`-be rövid szakasz az overlayról (használat, billentyűk, korlátok).
- [ ] **4. lépés (teljes ellenőrzés):** a teljes tesztcsomag zöld; `python -m pyflakes *.py` tiszta; a program forrásból indítva
  (`--appdata` NÉLKÜL, hogy a user adatait ne írja; teszt-adatmappával) betölt, az overlay gombbal megnyitható és zárható
  egy stubolt presettel; a `GetForegroundWindow` egy másik ablakkal nem változik (3–4. feladat tesztjei ezt már fedik, itt
  kézi/scriptelt füstpróba a valódi `run_app`-pal).
- [ ] **5. lépés:** telepítő újraépítése (`powershell -ExecutionPolicy Bypass -File build.ps1`), a másolat a
  `Dokumentumok\telepitok` mappába kerül (a build maga másolja). A telepítést nem futtatjuk (a user játéka közben).
- [ ] **6. lépés:** jelentés: mi készült, mi nem tesztelt (valódi játék alatti működés, élő billentyűleütés játékban,
  exkluzív fullscreen), review-kérdés a user szabálya szerint (nem indítom magamtól).
