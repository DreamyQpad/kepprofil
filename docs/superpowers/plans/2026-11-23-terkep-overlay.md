# Térkép-overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Képprofil a Tarkov logjából felismeri a pályát, és gyorsgombbal/automatikusan egy felül lévő, interaktív tarkov.dev térképablakot mutat.

**Architecture:** Tisztán szöveg-feldolgozó logfigyelő (`tarkov_log.py`) → `MapController` (szülő, a tk főszálon) → külön folyamat (`kijelzo.py --map`, pywebview/WebView2), amelyet soronkénti szöveges parancsokkal (stdin) vezérlünk. Az ablak Win32-stílusát a gyerekfolyamat maga váltja (övé a HWND).

**Tech Stack:** Python 3.13, tkinter/customtkinter (főszál), pywebview + WebView2 (gyerekfolyamat), unittest, PyInstaller onedir, Inno Setup.

**Spec:** `docs/superpowers/specs/2026-11-23-terkep-overlay-design.md`

## Global Constraints

- Csak Windows: Linuxon a funkció nem jelenik meg; `tarkov_log`, `map_overlay` importja Linuxon nem hibázhat (`winreg`, `webview` csak függvényen belüli, lusta import).
- Nincs injektálás, nincs memória-/hálózatolvasás; a Tarkov logja csak olvasható, megosztott olvasással.
- A logból csak a pálya neve (és az esemény fajtája) jöhet ki; profilazonosító és IP nem kerül eseménybe, naplóba, kivételüzenetbe.
- Ismeretlen pályanévnél nem nyit térképet; csak a nevet naplózza (egyszer).
- Térképforrás: `https://tarkov.dev/map/<azonosító>`.
- Verzió: `consts.VERSION` emelése; a telepítőt minden kódváltozás végén újra kell építeni (`build.ps1`), másolat: `Dokumentumok\telepitok`.
- Tesztek: `E:\Development\kijelzo\.venv\Scripts\python.exe -m unittest discover -s tests` (pytest nincs).
- Commit csak ha a felhasználó kéri, `Co-Authored-By` nélkül.
- Kommentek: jelen idejű „miért így"; nincs jegyszám, nincs változás-narratíva, nincs `fájl:sor`.

## Review Focus

- A Képprofil már folyamatban lévő raid alatt indul: nincs új log-esemény, a térkép mégis a jó pályára álljon (`LogTail.state()`).
- A Tarkov nincs telepítve / még nincs log, vagy a játék újraindul (új `log_*` mappa): a figyelő nem dob kivételt, átvált az újra.
- Ismeretlen pályanév: nincs térkép, nincs összeomlás, a név egyszer naplózva.
- A térképfolyamat meghal vagy kilövik, illetve a Képprofil kilép: nem marad árva folyamat, a következő gyorsgomb újraindítja.
- A billentyűzetes mód nyers gyorsgombjai (nyilak, numpad +/−, Esc) a módból kilépéskor, a folyamat halálakor és `stop()`-nál mindig felszabadulnak (különben a játék nem kapná meg ezeket a gombokat).

---

### Task 0: Eldobható prototípus (kapu)

**Files:**
- Create (nem kerül verziókezelésbe): `prototypes/map_spike.py`; `prototypes/` kerüljön a `.gitignore`-ba.
- Modify: a spec „Prototípus eredménye" szakasza (új, a spec végén).

**Interfaces:** Produces: írásos döntés a spec-ben, amelyből a 3–4. task az egyes kérdésekre épít.

- [ ] **Step 1:** `.venv\Scripts\pip install pywebview` (csak a venv-be; a `requirements.txt` a 6. taskban változik).
- [ ] **Step 2:** `map_spike.py`: pywebview-ablak `https://tarkov.dev/map/woods`-ra, frameless, topmost; a futás közben a konzolról (stdin-sorok) vezérelhető: `glance`, `mouse`, `keys-test`, `quit`.
- [ ] **Step 3:** Ellenőrizd és jegyezd a spec-be, külön-külön OK/NEM OK + ok: (1) betölt-e a tarkov.dev a WebView2-ben, működik-e a nagyítás/szűrő; (2) a gyerekfolyamat a saját HWND-jén (`webview` ablak natív handle vagy `FindWindowW` cím alapján) át tudja-e váltani az átkattintható ↔ kattintható állapotot, és a keret (`WS_CAPTION|WS_THICKFRAME`) ki/be kapcsolását `SWP_FRAMECHANGED`-del; (3) a nyíl/+/− mozgatja-e a térképet fókuszváltás nélkül, és melyik mechanizmus működik: szintetikus `KeyboardEvent` az oldalnak, vagy a térkép API-ja (`evaluate_js`); (4) a Tarkov egeres módnál (a felhasználó kipróbálja, biztonságos pillanatban) elviseli-e a fókuszvesztést.
- [ ] **Step 4 (kapu):** Ha az 1–3 közül bármelyik NEM OK: állj meg, és kérdezd meg a felhasználót, hogy a Steames `steam://openurl` megközelítésre (spec C) térjünk-e. Ne építs tovább a 3–6. taskokon.

### Task 1: Logfigyelő és pálya-táblázat

**Files:**
- Create: `tarkov_log.py`
- Test: `tests/test_tarkov_log.py`

**Interfaces:**
- Produces:
  - `class MapEvent(NamedTuple): kind: str; name: str` — `kind` ∈ `"preload" | "raid" | "end"`, `name` az eredeti pályanév (`""` a `"end"`-nél).
  - `MAP_SLUGS: dict[str, str]` — kisbetűs játék-belső név → tarkov.dev azonosító. Kezdőtartalom (csak mért): `woods→woods`, `city→streets-of-tarkov`, `tarkovstreets→streets-of-tarkov`. Újabb sor csak mért logból vagy a tarkov.dev oldalon igazolt névvel kerül be.
  - `parse_line(line: str) -> MapEvent | None`
  - `map_slug(name: str) -> str | None` (kis/nagybetű-független)
  - `tarkov_install_dir(setting: str = "") -> Path | None` — a beállítás elsőbbséget élvez; különben a Windows-eltávolítási nyilvántartás („Escape from Tarkov" `InstallLocation`); hiányában `None`.
  - `class LogTail: __init__(self, install_dir: Path)`; `poll(self) -> list[MapEvent]` (csak az új, teljes sorok); `state(self) -> MapEvent | None` (az utolsó `"raid"` esemény, ha utána nem jött `"end"`; különben `None`).

- [ ] **Step 1: Failing tesztek** (`tests/test_tarkov_log.py`), valós sorminták azonosítók nélkül:
  - `test_preload_sor`: `…|Info|application|scene preset path:maps/woods_preset.bundle rcid:woods.scenespreset.asset` → `MapEvent("preload","woods")`.
  - `test_raid_sor_csak_a_nevet_veszi_ki`: egy `TRACE-NetworkGameCreate profileStatus: 'Profileid: 000000000000000000000000, Status: Busy, RaidMode: Online, Ip: 10.0.0.1, Port: 17010, Location: TarkovStreets, Sid: x'` sor → `MapEvent("raid","TarkovStreets")`, és `"Profileid" not in repr(event)`, `"10.0.0.1" not in repr(event)`.
  - `test_end_sor`: `…|Info|application|BEClient exit` → `MapEvent("end","")`; a `BEClient exit successfully` sor → `None`; `Location:` egy nem `TRACE-NetworkGameCreate` sorban → `None`.
  - `test_map_slug`: `city`, `TarkovStreets` → `"streets-of-tarkov"`; `Woods` → `"woods"`; `"ismeretlen"` → `None`.
  - `test_logtail_csak_uj_sorokat_ad`: ideiglenes `Logs\log_A\2026… application_000.log`; első `poll()` után hozzáfűzött sorokból csak az újak jönnek.
  - `test_logtail_state_folyamatban_levo_raid`: a fájl `preload`, `raid` sorokkal már megvan a csatlakozáskor → `state() == MapEvent("raid", <név>)`; egy `BEClient exit` hozzáfűzése + `poll()` után `state() is None`.
  - `test_logtail_uj_log_mappa`: új, későbbi nevű `log_B` mappa → a következő `poll()` onnan olvas.
  - `test_logtail_hianyzo_mappa`: nem létező `install_dir` → `poll() == []`, nincs kivétel.
- [ ] **Step 2:** Futtasd: `…python.exe -m unittest tests.test_tarkov_log -v` — Expected: FAIL (modul nincs).
- [ ] **Step 3:** Implementáld a fenti szignatúrákat. `LogTail`: a legutolsó név szerint rendezett `Logs\log_*` mappa `*application_000.log` fájlja; csatlakozáskor egyszer végigolvassa a `state()` számításához (eseményt nem ad vissza), utána a bájt-offsettől olvas; kisebb fájl vagy új mappa → offset nullázás és újraszámolt `state()`; `OSError` → üres lista; dekódolás `errors="replace"`; csak teljes (újsor-záró) sorokat dolgoz fel.
- [ ] **Step 4:** Futtasd újra — Expected: PASS.
- [ ] **Step 5:** Commit (kérésre): `git add tarkov_log.py tests/test_tarkov_log.py`.

### Task 2: Beállítások és gyorsgombok a motorban

**Files:**
- Modify: `config.py` (`DEFAULT_SETTINGS`, `SETTINGS_KEYS`), `engine.py` (`hotkey_map`)
- Test: `tests/test_engine_map.py`

**Interfaces:**
- Produces: új beállítás-kulcsok és alapértékek: `map_hotkey: ""`, `map_interact_hotkey: ""`, `map_auto: True`, `map_alpha: 0.85`, `map_rect: None` (`[x, y, w, h]` vagy `None`), `tarkov_path: ""`. `Engine.hotkey_map()` új akciói: `"map"` (a `map_hotkey`-ból), `"map_interact"` (a `map_interact_hotkey`-ból).

- [ ] **Step 1: Failing tesztek** (a `tests/stubs.make_engine` mintájára, mint `test_engine_overlay.py`): `test_hotkey_map_tartalmazza_a_terkep_gombokat` (beállított két gomb → `hotkey_map()["map"]` és `["map_interact"]` megvan); `test_ures_gomb_nem_kerul_be` (üres → a kulcsok hiányoznak); `test_alapertekek` (`load_settings()` alapértéke `map_auto is True`, `map_alpha == 0.85`, `map_rect is None`); `test_settings_keys_exportja_tartalmazza_az_ujakat`.
- [ ] **Step 2:** Futtasd: `…unittest tests.test_engine_map -v` — Expected: FAIL.
- [ ] **Step 3:** Vedd fel a kulcsokat a `DEFAULT_SETTINGS`-be és a `SETTINGS_KEYS`-be; a `hotkey_map()` az `overlay_hotkey` mintájára adja az akciókat.
- [ ] **Step 4:** Futtasd — Expected: PASS; majd a teljes suite (`discover`) zöld marad.
- [ ] **Step 5:** Commit (kérésre).

### Task 3: A térképfolyamat (gyerek) és az ablak-módok

**Files:**
- Create: `map_window.py`
- Modify: `kijelzo.py` (`--map <azonosító>` ág a `main()`-ben, a `--action` mintájára), `hw_windows.py` (új: `map_window_style`)
- Test: `tests/test_map_window.py`

**Interfaces:**
- Produces:
  - `tarkov_url(slug: str) -> str` → `f"https://tarkov.dev/map/{slug}"`.
  - `parse_command(line: str) -> tuple | None` — érvényes parancsok: `("map", slug)`, `("show",)`, `("hide",)`, `("mode", "glance"|"keys"|"mouse")`, `("pan", "up"|"down"|"left"|"right")`, `("zoom", "in"|"out")`, `("alpha", float 0.2–1.0)`, `("rect", x, y, w, h)` (egész számok), `("quit",)`; minden más (ismeretlen szó, rossz argumentum, tartományon kívüli alpha) → `None`.
  - `run(slug: str, alpha: float, rect: list | None) -> None` — pywebview-ablak (lusta `import webview`), rejtve indul; stdin-olvasó szál a parancsokhoz; a `mouse` módból kilépéskor stdout-ra egy sort ír: `rect x y w h`.
  - `hw_windows.map_window_style(hwnd: int, mode: str) -> None` — `glance` és `keys`: átkattintható, nem aktiválódó, tálcagomb nélküli, legfelső, keret nélküli; `mouse`: kattintható, aktiválható, legfelső, kerettel (mozgatható/átméretezhető). A kerettel kapcsolatos stílusváltás a Task 0 eredménye szerint.
  - `kijelzo.main()`: `--map <azonosító>` esetén `map_window.run(...)`-t hív (a beállításokból alpha/rect), nem indít GUI-t.

- [ ] **Step 1: Failing tesztek:** `test_parse_command_ervenyes` (`"map woods"` → `("map","woods")`; `"mode keys"`; `"pan left"`; `"zoom out"`; `"alpha 0.5"` → `("alpha", 0.5)`; `"rect 10 20 800 600"` → `("rect",10,20,800,600)`; `"quit"`); `test_parse_command_ervenytelen` (`""`, `"mode xyz"`, `"alpha 5"`, `"rect a b c d"`, `"pan"` → `None`); `test_tarkov_url`.
- [ ] **Step 2:** Futtasd — Expected: FAIL.
- [ ] **Step 3:** Implementáld a `parse_command`-ot és a `tarkov_url`-t (a tesztelhető, ablak nélküli rész), majd a `run`-t és a `map_window_style`-t. A billentyűzetes mozgatás mechanizmusa a Task 0 (3) eredménye szerint. A `kijelzo.py` `--map` ága a `--action` mintáját követi.
- [ ] **Step 4:** Futtasd a tesztet — Expected: PASS. Kézi ellenőrzés: `.venv\Scripts\python.exe kijelzo.py --map woods`, majd az stdin-ről beírt `show`, `mode mouse`, `mode glance`, `quit` a várt módon viselkedik (a Task 0 szerinti ablakállapotok).
- [ ] **Step 5:** Commit (kérésre).

### Task 4: A szülő oldali vezérlő (MapController)

**Files:**
- Create: `map_overlay.py`
- Modify: `hw_common.py` (új `MAP_KEYS`)
- Test: `tests/test_map_controller.py`

**Interfaces:**
- Consumes: `MapEvent`, `map_slug` (Task 1); parancs-szókincs (Task 3); az `OverlayController` minta (`set_hotkeys`, `hotkey_failed`, `FakeRoot`).
- Produces:
  - `MAP_KEYS: dict[str, tuple]` — `"mp|up"`, `"mp|down"`, `"mp|left"`, `"mp|right"` (nyilak, ismétlődhet), `"mp|zin"`/`"mp|zout"` (numpad `+`/`−`, ismétlődhet; a billentyűzetkiosztástól független), `"mp|exit"` (Esc, nem ismétlődik); formátum azonos az `OVERLAY_KEYS`-szel: `(módosító, vk, ismétlődhet)`.
  - `map_argv(slug: str) -> list[str]` — csomagolt futásnál `[sys.executable, "--map", slug]`, forrásból `[sys.executable, <kijelzo.py útvonal>, "--map", slug]`.
  - `class MapController: __init__(self, eng, root, set_hotkeys, spawn=subprocess.Popen, argv_for=map_argv, say=None)`; metódusok: `on_event(event: MapEvent)`, `toggle()`, `cycle_mode()`, `key(action: str)`, `check()`, `stop()`; csak olvasható `mode` ∈ `"hidden" | "glance" | "keys" | "mouse"`.
  - Viselkedés: `preload` → ismert pályánál a folyamat rejtve indul (ismeretlennél: a név egyszeri naplózása, semmi más); `raid` → ha `map_auto`, a térkép megjelenik `glance` módban (más azonosítónál `map <slug>` parancs); `end` → elrejt és `stop()`; `toggle()` → `hidden↔glance` (ismert pálya hiányában értesítés, nem indít); `cycle_mode()` → `glance→keys→mouse→glance` (rejtettből előhoz); `keys` módban a `set_hotkeys` a normál térkép + `MAP_KEYS`, minden más módban a normál térkép; `check()` észleli a kilőtt folyamatot (`poll() is not None`), `hidden` állapotba tér, a gombokat visszaállítja; a `rect x y w h` sor (a gyerek stdout-járól) a `map_rect` beállításba mentődik.

- [ ] **Step 1: Failing tesztek** (`FakeProc` a `stdin.write`-ok rögzítésével, `FakeRoot`, `make_engine`): `test_preload_ismert_palyara_elinditja_rejtve`; `test_preload_ismeretlen_nevet_naploz_es_nem_indit` (a napló pontosan egyszer tartalmazza a nevet, azonosítót nem); `test_raid_auto_megjelenit` és `test_raid_auto_kikapcsolva_nem_jelenit_meg`; `test_raid_mas_palya_parancsot_kuld` (`map streets-of-tarkov` megy a stdin-re); `test_end_leallitja`; `test_toggle_ciklus`; `test_cycle_mode_sorrend`; `test_keys_modban_a_nyers_gombok_regisztralva_vannak_es_kilepeskor_felszabadulnak` (`set_hotkeys` utolsó hívása `MAP_KEYS` nélküli); `test_halott_folyamat_visszaallitja_a_gombokat` (`check()` után `mode == "hidden"` és nincs `mp|` kulcs); `test_stop_felszabadit_es_nem_hagy_arva_folyamatot`; `test_toggle_ujraindit_halott_folyamat_utan`; `test_rect_sor_mentodik`.
- [ ] **Step 2:** Futtasd — Expected: FAIL.
- [ ] **Step 3:** Implementáld a fenti szignatúrákat; a stdout-olvasás háttérszálon fut, a főszálnak a `root.after`-en át (vagy az `App.post` visszahívásán) üzen.
- [ ] **Step 4:** Futtasd — Expected: PASS; teljes suite zöld.
- [ ] **Step 5:** Commit (kérésre).

### Task 5: Bekötés a GUI-ba és a beállítások felülete

**Files:**
- Modify: `gui.py` (`App.__init__`, `_run_hotkey_action`, `quit`, új `map_tick`, a `HOOK`), `gui_layout.py` (új szakasz), `gui_panel.py` (`show_settings`), `README.md`
- Test: `tests/test_gui_smoke.py` (kiegészítés), `tests/test_map_wiring.py`

**Interfaces:**
- Consumes: `LogTail`, `tarkov_install_dir` (Task 1); beállítás-kulcsok (Task 2); `MapController` (Task 4).
- Produces: `App.map` (`MapController | None` — Linuxon `None`); `App.map_tick()` — 1000 ms-onként `LogTail.poll()` → `map.on_event(...)`, `map.check()`; kivétel esetén `eng.say(...)` (a kivétel szövege nem tartalmazhat logsort). `_run_hotkey_action`: `"map"` → `map.toggle()`, `"map_interact"` → `map.cycle_mode()`, `mp|…` → `map.key(action)`. `quit()` → `map.stop()`.

- [ ] **Step 1: Failing tesztek:** `test_map_akciok_a_vezerlore_kotve` (`_run_hotkey_action("map")` → `toggle`, `"map_interact"` → `cycle_mode`, `"mp|up"` → `key`); `test_map_tick_a_logbol_esemenyt_ad_tovabb` (stubolt `LogTail` + `FakeController`); `test_map_tick_kivetel_nem_szivarogtat` (a kivétel szövegében nincs logsor); a smoke teszt: a Program fül három új mezője megvan (`map_hotkey`, `map_interact_hotkey`, `map_auto`).
- [ ] **Step 2:** Futtasd — Expected: FAIL.
- [ ] **Step 3:** Implementáld. A Program fül új szakasza „Térkép-overlay (Escape from Tarkov)": két `HotkeyEntry` (`map_hotkey`, `map_interact_hotkey`, `on_change=lambda t: panel.set_setting(...)`), kapcsoló a `map_auto`-hoz, és egy rövid súgósor a három módról; `set_setting` a `…hotkey` végződésű kulcsokra magától újraköti a gombokat. Az átlátszóság állítása a Program fülön egy csúszkával (`map_alpha`, a meglévő csúszka-elem mintájára). Linuxon a szakasz és a `MapController` nem jön létre.
- [ ] **Step 4:** Futtasd — Expected: PASS; teljes suite zöld.
- [ ] **Step 5:** Commit (kérésre).

### Task 6: Csomagolás, mérés, telepítő, kézi próba

**Files:**
- Modify: `requirements.txt` (`pywebview>=5`), `build.ps1` (`--collect-all webview`, pythonnet-DLL-ek a Task 0 szerint), `consts.py` (verzió), `README.md`, `docs/…` ha kell

- [ ] **Step 1:** Építsd újra: `powershell -ExecutionPolicy Bypass -File E:\Development\kijelzo\build.ps1`; Expected: `out\Kepprofil-telepito.exe` létrejön; a telepítő mérete, és a korábbi méret különbsége feljegyezve.
- [ ] **Step 2:** A csomagolt `Kepprofil.exe --map woods` kézzel elindítva megnyílik és nem hibázik (WebView2 hiánya esetén érthető üzenet a naplóban).
- [ ] **Step 3 (mérés):** A térképfolyamat memóriája és CPU-ja nyitott térképpel (`psutil` egy rövid szkriptből): a két érték feljegyezve a specbe. FPS-hatás: mérőeszköz nincs a gépen, ezért nem mért; a felhasználó szubjektív visszajelzése a kézi próbából.
- [ ] **Step 4:** Másolat a `Dokumentumok\telepitok` mappába; a telepítő útvonalának közlése.
- [ ] **Step 5 (kézi próba, a felhasználó végzi):** raid betöltés → a jó térkép jön elő (Woods, Streets); `BEClient exit` → eltűnik; három mód; egeres mód a Tarkovban (fókuszvesztés); a nyilak/numpad gombok a keys módból kilépve ismét a játékhoz mennek. A kézi próba előtt nem jelentjük késznek.
- [ ] **Step 6:** Vedd fel az újonnan látott pályaneveket (a naplóban szereplő ismeretlenek) a `MAP_SLUGS`-ba, ha igazolhatók.
