# Főmenü-overlay és böngésző — végrehajtási terv

**Spec:** `docs/superpowers/specs/2026-11-23-fomenu-bongeszo-design.md`. Végrehajtás: Native, TDD, commit csak kérésre, review csak kérésre.

## Global Constraints
- Python 3.13 venv; tesztek: `.\.venv\Scripts\python.exe -m unittest discover -s tests` (pytest nincs).
- Csak Windows; a Linux-ágon semmi nem törhet (`sys.platform` őrök, lusta importok).
- Magyar kommentek/docblockok; a fejlesztési folyamat nyoma nem kerül a kódba.
- Gyorsgomb-értékek: szöveges spec (`parse_hotkey`) vagy nyers `(mods, vk, repeat)` tuple.
- A térkép-overlay (1. fázis) viselkedése nem változhat.

## Review Focus
- Shift+Tab lefoglalása nem törheti a Program fül gyorsgomb-mezőjét (Tab keysym).
- A menü zárásakor minden foglalt billentyű felszabadul (halott folyamat, kivétel, kilépés esetén is).
- Menü nyitása közben a térkép billentyűzetes módja és a profil-overlay nem foglalhat át ugyanazokat a gombokat.
- A böngésző folyamat nem marad árván (EOF, kilépés, összeomlás).
- Böngésző megnyitásakor a térkép nem tűnik el és nem veszít állapotot.

### Task 1: Gyorsgomb-alap (Tab, menu_hotkey)
Files: `hw_common.py` (`NAMED_KEYS["tab"]=0x09`, `MENU_KEYS`), `gui_widgets.py` (KEY_NAMES: `Tab`, `ISO_Left_Tab` → "Tab"), `config.py` (`menu_hotkey` alap "Shift+Tab", SETTINGS_KEYS), `engine.py` (`hotkey_map` → `"menu"`).
Interfaces — Produces: `MENU_KEYS = {"mn|up":(0,0x26,True),"mn|down":(0,0x28,True),"mn|ok":(0,0x0D,False),"mn|close":(0,0x1B,False)}`; `parse_hotkey("Shift+Tab") == (4, 9)`.
Tests: parse_hotkey Tab; HotkeyEntry Tab+Shift → "Shift+Tab"; hotkey_map tartalmazza a "menu"-t; régi settings.json (kulcs nélkül) is megkapja az alapot.

### Task 2: Közös ablakfolyamat + böngésző (`--web`)
Files: `map_window.py` (`run` → `run_window(url, title, storage, alpha, rect, web=False)`, `run_web()`), `kijelzo.py` (`--web` ág), `tests/test_map_window.py`.
Produces: `web_url()`, `close_button_script`/`nav_buttons_script(visible, closable)`; `--web` indul egér módban `show` után; kimenet: `loaded`, `closed` (a Bezár gombra), `rect …` (egér módból kilépéskor).
Tests: parancsok a web módban (nincs `mode keys`), `nav_buttons_script` Bezár gombbal, `--web` belépési pont.

### Task 3: BrowserController (`browser_overlay.py`)
Produces: `BrowserController(eng, spawn, argv_for, allow_foreground)` — `toggle()`, `open()`, `close()`, `check()`, `stop()`, `handle_output(line)` (`closed` → stop), `is_open`.
Tests: indítás + `allow_foreground` a `show` előtt, `closed` lezár, halott folyamat, EOF-stop, spawn OSError.

### Task 4: Menü (`menu_overlay.py`)
Produces: `MenuModel(items)` (`move`, `selected`), `MenuView(root)` (kattintható, nem aktiválódó tk-ablak, `hw_windows.menu_style`), `MenuController(eng, root, set_hotkeys, actions, rect_for, foreground_mid, view=None)` — `toggle()`, `key(action)`, `close()`, `check()`, `is_open`. Menüpontok: Térkép, Böngésző, Képbeállítások; kiválasztáskor előbb bezár, utána hívja az akciót.
Tests (hamis view-val): nyit/zár + MENU_KEYS foglalás/felszabadítás, ↑/↓ léptetés körbe, Enter az akciót hívja bezárás után, Esc zár, kattintás-akció, a megnyitás előtt `leave_keys` hívás.

### Task 5: Bekötés, felület, csomagolás
`gui.py` (`App.menu`, `App.browser`, `_run_hotkey_action` "menu"/"mn|…", `map_tick` → `browser.check()`, `quit` → `browser.stop()`), `gui_layout.py` + `gui_panel.show_settings` (`menu_hotkey` mező), `tests/test_gui_smoke.py`, README, `consts.VERSION` 2.13, build + csomagolt exe `--web` ellenőrzés, telepítő másolás.
