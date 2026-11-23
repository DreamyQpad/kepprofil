# Főmenü-overlay és böngésző — terv (2. fázis)

Állapot: **jóváhagyva** (a felhasználó döntései: Shift+Tab, Google, a térkép marad és a böngésző kerül fölé). Az 1. fázis (térkép-overlay, v2.12) kész: `2026-11-23-terkep-overlay-design.md`.

## Cél
Egy gyorsgombbal előhívható, Steam-szerű főmenü a játék fölött, ahonnan három dolog érhető el:
**Térkép**, **Böngésző**, **Képbeállítások** (a meglévő F10 profil-overlay). Az F10 közvetlen gyorsgomb marad.
A böngésző azért kell, hogy játék közben (második monitor nélkül) lehessen keresni: wiki, tárgyak, útmutatók.

## Nem cél
- Teljes értékű böngésző (nincs címsor, könyvjelző, fülek, letöltés-kezelés).
- Játékba injektálás vagy a játék memóriájának olvasása: marad a külön ablak + logfigyelés.
- Linux-támogatás (az 1. fázishoz hasonlóan csak Windows).

## Döntések (a saját hívásaim, a felhasználó javíthatja)
1. **Menü kinézete és vezérlése.** Kis, középre igazított tk-ablak (mint a profil-overlay), nem aktiválódó (`WS_EX_NOACTIVATE`),
   így a játék megtartja a fókuszt. Kattintható **és** billentyűzettel is vezérelhető: a menü ideje alatt a ↑/↓, Enter,
   Esc globális gyorsgombként foglalt (ugyanaz a technika, mint az `OVERLAY_KEYS` / `MAP_KEYS`), és onnan szabadul fel,
   hogy a menü bezárul.
2. **Gyorsgomb.** Új beállítás: `menu_hotkey`, alapértéke **Shift+Tab** (a felhasználó döntése: a Steam-overlay le van szedve a játékról;
   a Tarkovban a Shift a sprint, a Tab a hátizsák, ezt a menü a Képprofil futása alatt elveszi). Ugyanaz a gomb nyitja
   és zárja. A meglévő `map_hotkey`, `map_interact_hotkey`, `overlay_hotkey` változatlanul működik.
3. **Menüpontok.** Térkép → a térkép elő-/eltüntetése (`MapController.toggle`); Böngésző → a böngészőablak megnyitása;
   Képbeállítások → `OverlayController` megnyitása (a főablak-elrejtés logika már megvan). Minden pont után a menü bezárul.
4. **Böngésző = külön folyamat**, mint a térkép, de **másik példány**: `kijelzo.py --web`. Oka: a térkép egy raid alatt
   végig fut, a böngészőt csak keresés idejére akarjuk (a térkép folyamata ~890 MB, ezt nem akarjuk tartósan duplázni).
   A böngésző folyamat bezáráskor kilép.
5. **Közös kód.** A `map_window.run` általánosítása: egy `run_window(url, title, ...)` alap, amit a térkép és a böngésző is
   használ (stdin-parancsok, EOF-kilépés, `WindowModes`, `nav_buttons_script`). A parancs-szótár bővül: `web` mód alapból
   **egér mód** (fókusszal, mert gépelni kell), nincs billentyűzetes/pillantás mód.
6. **Kezdőoldal.** Keresőoldal (Google), nincs címsor. A „← Vissza / Előre →" gombok megvannak (már megépültek), mellé
   „✕ Bezár" gomb. A bezárás a játéknak visszaadja a fókuszt (a `WindowModes` már így működik).
7. **Külön WebView2-profil** a böngészőnek (`DATA_DIR/webview-browser`), hogy a térkép sütijei és a böngésző belépései ne
   keveredjenek, és két példány ne vitatkozzon egy profilmappán.
8. **Kilépés a böngészőből:** a menü gombja újra, vagy a „✕ Bezár" gomb. Az Esc-et nem foglaljuk le (az oldalaknak kell).

## Megvalósítási felosztás (becslés: a térkép-overlay kb. fele)
- `menu_overlay.py` — a menü ablaka és a billentyűkezelése (tk, tesztelhető nézet/modell szétválasztással, mint az `overlay.py`).
- `map_window.py` → közös `run_window`, új `web_window.py` vagy `--web` ág a `kijelzo.py`-ban.
- `map_overlay.py`-hoz hasonló `BrowserController` (indítás, leállítás, élet-ellenőrzés).
- `gui.py` bekötés, Program fül mező (`menu_hotkey`), README, telepítő.

## Eldöntött kérdések
- Gyorsgomb: Shift+Tab (alap, átállítható). Keresőmotor: Google.
- Ha a térkép is látszik, **a térkép marad**, a böngésző fölé kerül (mindkettő legfelső ablak; az aktiválás a böngészőt emeli).

## Kockázatok
- A fókuszvesztés hatása a Tarkovra egér módban még **nem tesztelt** valódi raidben (az 1. fázisból öröklött nyitott pont). A böngésző ezt még gyakrabban használja.
- Memória: két WebView2-folyamat egyszerre ~1,7 GB lehet. A böngészőt ezért csak igény szerint indítjuk.
- A „Képbeállítások" menüpont a főablak-elrejtésre épít (kész), de a menü és a profil-overlay billentyűfoglalása nem fedhet át: a menü zárásakor szabadulnak fel, utána nyílik az overlay.
