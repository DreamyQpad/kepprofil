# Gyorsabb játékfelismerés folyamat-eseményekkel – megvalósítási terv

> **Végrehajtóknak:** KÖTELEZŐ al-skill: `superpowers:subagent-driven-development` (ajánlott) vagy `superpowers:executing-plans`. A lépések `- [ ]` jelölésűek.

**Cél:** Windowson, emelt jogú futásnál a játék indulása/kilépése eseményből, azonnal látszik; a 3 mp-es vakvárakozás megszűnik; emelés nélkül (és Linuxon) a régi lekérdezéses működés marad.

**Felépítés:** Az `Engine` a futó programokat névszámlálóban (`proc_counts`) tartja, amit a Windows-eseményforrás (`proc_events_windows.py`, PowerShell gyerekfolyamat `Win32_ProcessStartTrace`/`StopTrace` WMI-figyelővel) inkrementálisan frissít, a teljes `psutil`-lekérdezés pedig 5 mp-enként újraépít (tartalék/önjavítás). A figyelő-ciklus az `Engine.watch_loop`-ba kerül, és eseményre azonnal fut.

**Tech stack:** Python 3 (`unittest`, `psutil`, `ctypes`, `subprocess`), meglévő `engine.py` / `system_*.py` / `gui.py`. Új pip-függőség nincs.

**Terv (spec):** `docs/superpowers/specs/2026-11-14-jatekfelismeres-esemenyek-design.md`

## Globális megkötések

- Új pip-függőség nincs. Az eseményforrás: PowerShell gyerekfolyamat (`powershell -NoProfile -NonInteractive`, `CREATE_NO_WINDOW` a `consts`-ból).
- Emelés nélkül, Linuxon és eseményforrás-hiba esetén a mostani működés áll (lekérdezés); semmi nem törhet el.
- Lekérdezési ritmus lekérdezéses módban: `Engine.POLL_SECONDS` = **1.0** Windowson, **2.0** máshol (a Linuxos `kscreen-doctor` lassú, ott nem sűrítünk). Eseménymódban a tartalék-újraszinkron: `Engine.RESYNC_SECONDS = 5.0`.
- A bekapcsolás utáni utánellenőrzés késleltetései: `Engine.START_DELAYS = (1.5, 4.0)` mp (kiindulóérték, a valódi játékos mérés után hangolható).
- Nyelv: kommentek, docstringek, üzenetek, doksik magyarul; kódazonosítók a meglévő stílusban. A kódba nem kerül változás-narratíva, jegyszám, `fájl:sor` hivatkozás; a „miért így" marad.
- Tesztek: `unittest`, funkcionális szint. Futtatás: `.venv/Scripts/python.exe -m unittest discover -s tests -t .` (alapállapot: 89 teszt, OK).
- Commit csak akkor, ha a user kéri (ágra: `dev`); a lépések „Commit-pont"-jai javaslatok. Review-t magadtól nem indítasz: a végén egy soros kérdés („Kérsz review-t erre a diffre?").

## Review Focus

Az alábbiak a spec által sejtetett, de a feladatok fő tesztjei által nem kimondottan fedett esetek; mindegyikhez van pontosan egy rögzítő teszt/ellenőrzés a megjelölt feladatban:

1. Két azonos nevű folyamat (pl. launcher + játék) egyike kilép – a játék „fut" marad (Task 1).
2. Az eseményfolyam menet közben megszakad (a PowerShell meghal) – a motor visszaáll lekérdezésre, a profil nem ragad be (Task 2).
3. A rendszerben tömegesen indulnak irreleváns folyamatok – nem fut `watch_tick` minden eseményre (Task 1).
4. A játék indulás után lenullázza a görbét – az utánellenőrzés visszaállítja (Task 2).
5. A programot `taskkill /F` lövi le (a telepítő ezt teszi) – a PowerShell gyerek nem marad árván (Task 3, kézi).

---

### Task 1: Név-számláló és eseménybelépési pont az `Engine`-ben

**Files:**
- Modify: `engine.py` (`__init__`, `refresh_running`, `proc_running`, új `norm_proc`, `set_running`, `proc_event`, `watched_names`)
- Create: `tests/test_proc_events.py`

**Interfaces:**
- Produces (a többi task erre épít):
  - `engine.norm_proc(name: str) -> str` – kisbetűs, `.exe` nélküli név; üres/`None` → `""`.
  - `Engine.proc_counts: dict[str, int]`, `Engine.running: set[str]` (a számláló pozitív kulcsai; a meglévő tesztek ezt közvetlenül is felülírják), `Engine.event_mode: bool = False`, `Engine.watch_wake: threading.Event`, `Engine.run_lock: threading.Lock`.
  - `Engine.set_running(raw_names: Iterable[str]) -> None` – a számlálót a nyers nevekből újraépíti (`run_lock` alatt), beállítja `running`-ot és `running_t = time.time()`-ot.
  - `Engine.proc_event(started: bool, name: str) -> None` – számláló +1/−1 (nulla alá nem megy), `running` frissül; ha a normalizált név benne van a `watched_names()`-ben, `watch_wake.set()`.
  - `Engine.watched_names() -> set[str]` – az összes monitor összes presetjének normalizált `process` mezője (üres nélkül).

- [x] **Step 1: Írd meg a bukó teszteket** a `tests/test_proc_events.py`-ban (`make_engine` a `tests.stubs`-ból; az alap konfigban a „Játék" preset `process` = `"game"`):
  - `test_norm_proc`: `norm_proc("Game.EXE") == "game"`, `norm_proc("game") == "game"`, `norm_proc("") == ""`, `norm_proc(None) == ""`.
  - `test_ket_pelda_egyik_kilep_a_jatek_fut_marad` *(Review Focus 1)*: kétszer `proc_event(True, "game.exe")`, egyszer `proc_event(False, "game.exe")` → `eng.proc_running("game")` igaz; a második stop után hamis.
  - `test_stop_nem_megy_nulla_ala`: ismeretlen névre `proc_event(False, "x.exe")` → `eng.proc_counts.get("x", 0) == 0`, majd `proc_event(True, "x.exe")` → `proc_running("x")` igaz (nem ragad −1-en).
  - `test_set_running_ujraepiti_a_szamlalot`: `set_running(["Game.exe", "game.exe", "x.exe"])` → `proc_counts == {"game": 2, "x": 1}`, `running == {"game", "x"}`; egy újabb `set_running(["x.exe"])` után `proc_running("game")` hamis.
  - `test_csak_figyelt_nevre_ebreszt` *(Review Focus 3)*: `eng.watch_wake.clear()`; `proc_event(True, "conhost.exe")` → `watch_wake.is_set()` hamis; `proc_event(True, "GAME.exe")` → igaz.
  - `test_esemenymodban_nincs_gyorsitotar_frissites`: `eng.event_mode = True`, `eng.running_t = 0.0`, `eng.refresh_running = mock.Mock()` → `eng.proc_running("game")` nem hívja a `refresh_running`-ot. Lekérdezéses módban (`event_mode = False`, `running_t = 0.0`) hívja.

- [x] **Step 2: Futtasd, győződj meg, hogy bukik** – `.venv/Scripts/python.exe -m unittest tests.test_proc_events -v` → hiányzó `norm_proc`/`proc_event` miatt hibák.

- [x] **Step 3: Implementáld** az `engine.py`-ben a fenti felületet:
  - A `refresh_running` a `psutil.process_iter(["name"])` nyers neveit adja a `set_running`-nak (a név-normalizálás a `norm_proc`-ba kerül, a régi inline logika helyett).
  - A `proc_running(proc)`: a névvel `norm_proc`-ot hív; a 6 mp-es gyorsítótár-frissítés **csak** `not self.event_mode` esetén fut; az ellenőrzés `norm_proc(proc) in self.running`.
  - A számláló és a `running` módosítása `run_lock` alatt; az `Engine.__init__` az új mezőket a `refresh_running()` hívás előtt inicializálja.
  - Egyetlen `norm_proc` van; a `watched_names()` is azt használja.

- [x] **Step 4: Futtasd** `tests.test_proc_events` és a teljes csomag → mind zöld (a meglévő 89 teszt változatlanul, mert a `running`/`running_t` közvetlen felülírása továbbra is érvényes).

- [x] **Step 5: Commit-pont** – `engine.py`, `tests/test_proc_events.py`.

---

### Task 2: Figyelő-ciklus az `Engine`-ben, azonnali bekapcsolás, utánellenőrzés

**Files:**
- Modify: `engine.py` (`watch_tick`, új `watch_loop`, `watch_interval`, `after_game_start`, `shutdown`; osztály-konstansok), `tests/stubs.py` (`make_engine`: `eng.START_DELAYS = ()`), `gui.py` (a `watch` belső függvény)
- Create: `tests/test_game_start_fast.py`

**Interfaces:**
- Consumes (Task 1): `Engine.event_mode`, `watch_wake`, `proc_event`, `set_running`, `refresh_running`.
- Consumes (Task 3/4, injektálva): `start_events(on_event, on_lost) -> source | None`, ahol `source.stop()` létezik; `on_event(started: bool, name: str)`, `on_lost()`.
- Produces:
  - Osztály-konstansok: `POLL_SECONDS` (1.0 Windowson / 2.0 máshol, `sys.platform` alapján), `RESYNC_SECONDS = 5.0`, `START_DELAYS = (1.5, 4.0)`; a `EVENT_TEXT` kapja a `"start": "a játék indulása után"` kulcsot.
  - `Engine.watch_interval() -> float` – `RESYNC_SECONDS` eseménymódban, különben `POLL_SECONDS`.
  - `Engine.watch_loop(start_events=None) -> None` – a figyelő-szál törzse (lásd Step 3).
  - `Engine.after_game_start() -> None` – a `START_DELAYS` minden elemére daemon `threading.Timer`, ami `self.reapply("start")`-ot hív.
  - `Engine.events` (az eseményforrás vagy `None`).

- [x] **Step 1: Írd meg a bukó teszteket** a `tests/test_game_start_fast.py`-ban (segéd: a `test_game_exit_restore.py` `tick`/`last_vals` mintájára, de a `time.sleep` patch-et **ne** vedd át, hanem ellenőrizd):
  - `test_inditaskor_nincs_vakvarakozas`: `mock.patch("engine.time.sleep")` mellett `eng.running = {"game"}`, `running_t = 1e18`, `monitors_t = 1e18`, `watch_tick()` → a mock nem hívódott, és az utolsó beállított érték vibrance-a 60 (a Játék preset).
  - `test_inditas_utan_utanellenorzes_idozitve`: `eng.START_DELAYS = (1.5, 4.0)`, `mock.patch("engine.threading.Timer")` → egy `watch_tick` után a `Timer` pontosan kétszer hívódott, a késleltetések 1.5 és 4.0, a callback `eng.reapply`, argumentum `("start",)`; mindkét Timer `daemon = True` és `start()`-olt.
  - `test_utanellenorzes_visszaallitja_a_nullazott_gorbet` *(Review Focus 4)*: indítás után `display.calls.clear()`; `display.drifted = lambda *a, **k: True`; `eng.reapply("start")` → új `display.calls` bejegyzés vibrance 60-nal. Ha a görbe ép (`drifted` hamis), nincs új hívás.
  - `test_esemenymodban_a_tick_csak_resyncre_kerdezi_le_a_programokat`: `eng.event_mode = True`, `eng.refresh_running = mock.Mock()`; `running_t = time.time()` → `watch_tick()` után nem hívódott; `running_t = time.time() - 10` → pontosan egyszer hívódott. (`monitors_t = 1e18`.) `event_mode = False` mellett mindig hívódik.
  - `test_watch_interval`: `event_mode False` → `Engine.POLL_SECONDS`; `True` → `Engine.RESYNC_SECONDS`.
  - `test_watch_loop_esemenyre_azonnal_fut`: `eng.POLL_SECONDS = 60`, `eng.watch_tick = mock.Mock()`; a `watch_loop()` szálon indul, megvárod az első tick-et, `eng.watch_wake.set()` → a második tick 0,5 mp-en belül megérkezik; végül `eng.stop = True`, `watch_wake.set()`, `join` (a szál leáll).
  - `test_forras_sikeres_inditasa_esemenymodba_visz`: hamis `start_events(on_event, on_lost)`, amely elmenti a callbackeket és egy `.stop()`-pal rendelkező objektumot ad → `watch_loop(start_events=...)` után `eng.event_mode` igaz; `on_event(True, "game.exe")` után `proc_running("game")` igaz; a napló (`eng.log`, vagy a `say` patch-elt változata) tartalmazza: `Játékfigyelő: események`.
  - `test_forras_hiba_eseten_lekerdezes_marad`: `start_events` `None`-t ad → `event_mode` hamis, a napló tartalmazza: `Játékfigyelő: lekérdezés` (és az okot: nincs emelt jog / nem elérhető).
  - `test_eseményfolyam_megszakadasa_visszaall_lekerdezesre` *(Review Focus 2)*: sikeres indítás után `on_lost()` → `event_mode` hamis, `running_t == 0.0` (a következő tick újra lekérdez), `watch_wake` be van állítva, a napló jelzi a visszaállást.
  - `test_shutdown_leallitja_a_forrast`: a hamis forrás `.stop()`-ját hívja a `shutdown()`.

- [x] **Step 2: Futtasd, győződj meg, hogy bukik** – `.venv/Scripts/python.exe -m unittest tests.test_game_start_fast -v`.

- [x] **Step 3: Implementáld**:
  - `watch_tick`: a `refresh_running()` az elején csak akkor fut, ha `not self.event_mode or time.time() - self.running_t > self.RESYNC_SECONDS`. A `time.sleep(3)` és a mögötte lévő megjegyzés törlődik; a profil a hit észlelésekor azonnal kapcsol be, a bekapcsolás (a `toast`/`say` után) a `self.after_game_start()`-ot hívja.
  - `after_game_start`: a `system_event` Timer-mintájára, de csak a `reapply("start")`-ot ütemezi (nem a monitor-újraellenőrzést).
  - `watch_loop(start_events=None)`: elején, ha `start_events` adott, `self.events = start_events(self.proc_event, self._events_lost)`; ha `None` → `say("Játékfigyelő: lekérdezés (nincs emelt jog vagy az eseményforrás nem elérhető)")`; ha van forrás → `refresh_running()` (induló pillanatkép), `self.event_mode = True`, `say("Játékfigyelő: események")`. Ezután: `while not self.stop:` a `watch_tick` hívása `try/except`-ben (hibára `say(f"Figyelő hiba: {e}")`, mint a mostani `gui.watch`), majd `self.watch_wake.wait(self.watch_interval())` és `self.watch_wake.clear()`. A forrás indítása és a ciklus ugyanabban a (watch) szálban fut, hogy az indítás ne tartsa fel a GUI-t.
  - `_events_lost()`: `event_mode = False`, `running_t = 0.0`, `watch_wake.set()`, `say` a visszaállásról.
  - `shutdown()`: ha `self.events`, `try: self.events.stop()` (hibát elnyel), a meglévő logika előtt.
  - `gui.py`: a `watch()` belső függvény helyét és a szál indítását `threading.Thread(target=lambda: eng.watch_loop(start_process_events), daemon=True).start()` váltja; a `start_process_events` a `system` modulból jön (Task 3/4 hozza létre – a Task 2 idejére a GUI-ban még `None`-t adj át, a bekötés a Task 4-ben történik).
  - `tests/stubs.py` `make_engine`: `eng.START_DELAYS = ()` (a tesztek ne indítsanak Timert; a Timer-tesztek felülírják).

- [x] **Step 4: Futtasd** `tests.test_game_start_fast`, majd a teljes csomag → zöld (a `test_game_exit_restore` és `test_monitor_detection` `time.sleep` patch-e ártalmatlan marad).

- [x] **Step 5: Commit-pont** – `engine.py`, `gui.py`, `tests/stubs.py`, `tests/test_game_start_fast.py`.

---

### Task 3: Windows eseményforrás (`proc_events_windows.py`)

**Files:**
- Create: `proc_events_windows.py`, `tests/test_proc_events_source.py`

**Interfaces:**
- Consumes: `consts.CREATE_NO_WINDOW`.
- Produces:
  - `parse_line(line: str) -> tuple[bool, str] | None` – `"start|Game.exe"` → `(True, "Game.exe")`, `"stop|Game.exe"` → `(False, "Game.exe")`; a `ready`, üres, hibás vagy ismeretlen sor → `None`; CR/LF levágva.
  - `is_admin() -> bool` – `ctypes.windll.shell32.IsUserAnAdmin()`, hibára `False`.
  - `class ProcessEventSource(on_event, on_lost, popen=subprocess.Popen, ready_timeout=8.0)` – `start() -> bool`, `stop() -> None`.
  - `start_process_events(on_event, on_lost) -> ProcessEventSource | None` – `None`, ha nincs emelt jog vagy a `start()` hamis.

**Soros protokoll** (a PowerShell gyerek stdout-ja, soronként): először `ready`, utána `start|<ProcessName>` / `stop|<ProcessName>`. A hiba (pl. hozzáférés megtagadva) a `ready` előtti kilépést jelent.

- [x] **Step 1: Írd meg a bukó teszteket** (`popen`-ként hamis folyamat: iterálható `stdout`, `poll()`, `kill()`, `wait()`):
  - `test_parse_line`: a fenti esetek, plusz `"stop|x y.exe"` → `(False, "x y.exe")` (a név szóközt tartalmazhat), `"start|"` → `None`.
  - `test_ready_utan_az_esemenyek_megerkeznek_es_eof_on_lost`: stdout `["ready\n", "start|A.exe\n", "garbage\n", "stop|A.exe\n"]` → `start()` igaz; az `on_event` hívásai `[(True, "A.exe"), (False, "A.exe")]`; az EOF után `on_lost` pontosan egyszer hívódott (várakozás: legfeljebb 2 mp, `threading.Event`-tel).
  - `test_eof_ready_elott_start_hamis`: stdout üres → `start()` hamis, a hamis folyamat `kill()`-je hívódott, `on_lost` **nem** hívódott.
  - `test_ready_idotullepes`: a stdout nem ad sort (blokkoló hamis olvasó, `ready_timeout=0.2`) → `start()` hamis, `kill()` hívódott.
  - `test_stop_leallitja_es_nem_hiv_on_lost`: sikeres indítás után `stop()` → `kill()` hívódott; az olvasó szál leállása után `on_lost` nem hívódott.

- [x] **Step 2: Futtasd, győződj meg, hogy bukik** – `.venv/Scripts/python.exe -m unittest tests.test_proc_events_source -v`.

- [x] **Step 3: Implementáld**:
  - `ProcessEventSource.start()`: a gyereket `popen([...powershell, "-NoProfile", "-NonInteractive", "-Command", SCRIPT], stdout=PIPE, stderr=DEVNULL, text=True, encoding="utf-8", creationflags=CREATE_NO_WINDOW)`-val indítja; olvasó daemon szál olvassa a sorokat; az első `ready` jelzi a készenlétet (`threading.Event`), a `start()` ezt várja `ready_timeout`-ig; sikertelen indításnál `kill()`. A `ready` után a sorok a `parse_line`-on át az `on_event`-be mennek; EOF-nál, ha nem `stop()` okozta, `on_lost()`.
  - A `SCRIPT` (PowerShell, a `os.getpid()`-et a Python illeszti be): `Register-WmiEvent` kétszer (`SELECT * FROM Win32_ProcessStartTrace` / `Win32_ProcessStopTrace`, külön `-SourceIdentifier`), siker után `[Console]::Out.WriteLine('ready')`; ciklus: `Wait-Event -Timeout 3`, a `SourceEventArgs.NewEvent.ProcessName`-ből `start|<név>` / `stop|<név>` sor a `[Console]::Out.WriteLine`-nal, majd `Remove-Event`; **minden iterációban** ellenőrzi, él-e a szülő (`Get-Process -Id <pid> -ErrorAction SilentlyContinue`), és ha nem, `exit`. Ez teszi, hogy a gyerek akkor is leáll, ha a programot `taskkill /F` lövi le (Review Focus 5). `$ErrorActionPreference = 'Stop'`, hogy a jog hiánya a `ready` előtti kilépést okozza.
  - `stop()`: jelzi a leállást, `kill()`, nem hív `on_lost`-ot.

- [x] **Step 4: Futtasd** `tests.test_proc_events_source` és a teljes csomag → zöld.

- [x] **Step 5: Kézi ellenőrzés (nem automatizálható; emelt jogú PowerShellben):** egy Python-egysoros hívja a `start_process_events`-et, kiírja az eseményeket; indíts el és zárj be egy `notepad.exe`-t → látni kell `(True, "notepad.exe")`, `(False, "notepad.exe")`, az esemény < 1 mp. Ugyanez **nem emelt** shellben → `None`. Majd a hívó Python-folyamatot `taskkill /F`-fel lődd le, és Feladatkezelőben/`Get-Process powershell`-lel ellenőrizd: a PowerShell gyerek ~3 mp-en belül eltűnik. Az eredményt (idő, igen/nem) írd a jelentésbe; ami nem futott, az `not-run` + ok.

- [x] **Step 6: Commit-pont** – `proc_events_windows.py`, `tests/test_proc_events_source.py`.

---

### Task 4: Bekötés, dokumentáció, végső ellenőrzés

**Files:**
- Modify: `system_windows.py`, `system_linux.py`, `gui.py`, `README.md`

**Interfaces:**
- Consumes: Task 3 `start_process_events`, Task 2 `Engine.watch_loop(start_events)`.
- Produces: `system.start_process_events(on_event, on_lost)` mindkét platformon.

- [x] **Step 1: `system_windows.py`**: `start_process_events(on_event, on_lost)` – a `proc_events_windows.start_process_events`-t hívja (az import a függvényben, hogy a modul betöltése ne függjön tőle); kivételt (import- vagy indítási hiba) elnyel és `None`-t ad.
- [x] **Step 2: `system_linux.py`**: `start_process_events(on_event, on_lost)` mindig `None` (Linuxon marad a lekérdezés); egy soros docstring: miért.
- [x] **Step 3: `gui.py`**: a Task 2-ben átmenetileg `None`-nal hívott `eng.watch_loop(...)` a `system` modul `start_process_events`-ét kapja (a `gui.py` már importál a `system`-ből – a meglévő import-stílust kövesd).
- [x] **Step 4: Automatikus ellenőrzés** – a teljes csomag: `.venv/Scripts/python.exe -m unittest discover -s tests -t .` → minden zöld; `Grep` bizonyítja, hogy a `gui.py`-ban nincs már `time.sleep(2)` a figyelőben és az `engine.py`-ban nincs `time.sleep(3)`.
- [x] **Step 5: README**: a „Terv / Windows" listából a „Gyorsabb játékfelismerés…" pont törlődik; a funkciók közé (Játékfigyelő pont) egy mondat kerül: emelt jogú futásnál a játék indulását/kilépését eseményből ismeri fel (nem emelt jognál 1 mp-es lekérdezés); a napló/tálca jelzi, melyik mód aktív.
- [x] **Step 6: Kézi, valódi próba (a user futtatja, mert játék és emelt jog kell):** emelt jogú indítás, egy valódi játék preset-tel: (a) a profil a játék indulása után ~1–2 mp-en belül bekapcsol, (b) nincs tartós nullázott görbe/villanás, (c) kilépéskor az előző profil gyorsan visszaáll, (d) nem emelt indításnál a napló a lekérdezéses módot jelzi és minden a régi módon működik. Az eredményt kérd el; amíg nincs meg, a jelentés verdiktje `partial` (nem `verified`), az (a)–(d) pontok `not-run` + ok.
- [x] **Step 7: Commit-pont** – `system_windows.py`, `system_linux.py`, `gui.py`, `README.md`. A végén egy soros kérdés a usernek: „Kérsz review-t erre a diffre?"

---

## Önellenőrzés (spec lefedettség)

- Esemény + lekérdezés tartalék, emelés nélkül régi működés: Task 1–4. A spec „1. nyilvántartás": Task 1; „2. eseményforrás": Task 3; „3. ritmus": Task 2; „4. várakozás javítása": Task 2; „5. visszajelzés": Task 2 (napló) – a tálcaikon-hibajelzés a spec szerint külön pont.
- Anti-célok: villanás (Task 2 utánellenőrzés + Task 4 kézi), hamis „kilépett" (Task 1 számláló, Task 2 resync/on_lost), árva segédfolyamat (Task 3 szülőellenőrzés + kézi).
- Nyitott, mérendő (a 3 mp oka): Task 4 Step 6; a `START_DELAYS` ott hangolható.
- Ismert, elfogadott korlát: a tartalék-újraszinkron és egy egyidejű esemény ritkán duplán számolhat egy példányt; ez legfeljebb 5 mp-ig (a következő újraszinkronig) tarthat, utána kijavul.
