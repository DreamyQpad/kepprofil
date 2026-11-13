# Játék-overlay (billentyűzetvezérelt, fókuszt nem lopó) — rövid terv

Dátum: 2026-11-13 · Állapot: jóváhagyásra vár · Méret: kisebb munka (egy új modul + néhány motorfüggvény)

## Cél és miért
Játék közben, a játékból kilépés és a főablak megnyitása nélkül szeretné a user az aktuális játék profilját
finomhangolni: csúszkák állítása, és a mostani állásból új változat felvétele. A játék nem veszítheti el a fókuszt
(az előző, teljes panel-overlayt a user nem kérte; ez egy kicsi, szűkített változat).

## Célok
- Egy globális gyorsgombbal nyíló kis panel a játék monitorján, **csak az aktuális játék profiljával**.
- Sorok: Fényerő, Kontraszt, Gamma, Vibrance, Vörös, Zöld, Kék (ugyanazok a tartományok és lépcsők, mint a főablakban).
- A csúszkák élőben hatnak (előnézet), mentés csak kérésre.
- **Új változat** felvétele a mostani csúszkaállásból, ugyanahhoz a játékhoz (preset), automatikus névvel.
- A játék sem a fókuszt, sem a kurzort nem veszíti el.

## Nem célok / anti-célok
- Nincs egér- és gépelés-támogatás (ez lehet egy későbbi „C" bővítés). Nincs új preset létrehozása, nincs átnevezés vagy
  törlés (ezek a főablakban maradnak).
- Nem szabad fókuszt vagy aktiválást okoznia (ez az elfogadási kritérium, lásd Ellenőrzés).
- Bezárás után nem maradhat lefoglalva egyetlen billentyű sem.
- Linux nem része (a `hw_linux` gyorsgomb-réteg még nincs megírva).

## Megközelítések (a user az A-t választotta)
- **A) Billentyűzetvezérlés** `RegisterHotKey`-jel, a panel nyitva tartása alatt ideiglenesen lefoglalt gombokkal. ✔ választva
- B) Kattintható panel egérrel: játékfüggő (a kurzor sok játékban el van fogva), gépelni így sem lehet. Elvetve.
- C) A + B: a legtöbb munka; később az A-ra építhető.

## Működés
- **Nyitás/zárás:** új beállítás, `settings["overlay_hotkey"]` (Program fül, mint a `cycle_hotkey`), alapból üres. Ugyanaz
  a gomb zár is.
- **Melyik játék:** az a monitor + aktív preset, amelyiken az előtérben lévő ablak van (ha ott van aktív preset); ha nincs,
  az első monitor, amelyiken van aktív preset. Ha egyik sincs: toast „Nincs aktív preset", a panel nem nyílik.
- **Változat:** a preset éppen érvényes változatát szerkeszti (`Engine.cur_variant`). Ha a presetnek nincsenek változatai,
  a preset alapértékeit, ugyanúgy, mint a főablak.
- **Billentyűk nyitva tartás alatt** (a játék nem kapja meg őket): ↑/↓ sor váltása · ←/→ állít (1 egység, gammánál 0,01) ·
  Shift+←/→ ×5 · Delete a sor alapértékére · **Enter** mentés a mostani változatba és bezárás · **N** új változat a mostani
  állásból · **Esc** elvet és bezár.
- **Új változat (N):** neve „Változat N" (az első szabad szám, 2-től). Ha a presetnek eddig nem volt változata, a főablak
  logikáját követi: a mentett értékek „Alap" néven az első változat lesznek, az új a mostani állásból indul. Azonnal
  mentődik, a panel nyitva marad, és az új változatra vált (a címsor frissül). Átnevezni a főablakban lehet.
- **Előnézet:** `eng.panel_open = True` mellett `Engine.preview(...)`, így a figyelő és a toast nem zavar közbe.
  Zárásnál `panel_open = False` és `eng.sync(mid)`. Esc-nél a mentett állapot áll vissza.
- **Automatikus zárás:** ha az aktív preset megváltozik, a játék kilép, vagy a főablak megnyílik.
- **Megjelenés:** `overlay_style`-os (nem aktiválódó, átkattintható, legfelső) tk-ablak a játék monitorjának jobb szélén,
  függőlegesen középen (kb. 340 px, alpha ~0,92). Címsor: játék · változat, sorok csúszka-sávval és értékkel, alul
  a billentyűk súgója. A kijelölt sor kiemelve. Exkluzív fullscreen fölött nem látszik (mint a toast), ablak nélküli
  módban igen.

## Felépítés (az építő kiosztása)
- Új modul `overlay.py`: modell (sorok, lépés, mentés, új változat, elvetés), a megjelenítéstől függetlenül
  tesztelhető; vékony tk-megjelenítő a `gui.py`-ban.
- A változat-létrehozás és a mentés a motorba kerül (`Engine`-függvény), hogy a modell ne a `run_app` closure-jaira
  támaszkodjon. A főablak meglévő dialógusait nem írjuk át.
- Gyorsgomb-térkép: nyitáskor a `hotkey_map()` kiegészül `ov|up/down/left/right/…` műveletekkel (a `Hotkeys.set` a teljes
  térképet cseréli), zárásnál az eredeti áll vissza (`apply_hotkeys()`).

## Az építőre hagyva (az én döntéseim, itt át lehet írni)
- A panel pozíciója és mérete, színek, a súgósor szövege.
- Lépésközök: a főablak csúszkáinak lépcsőihez igazodnak.
- A `Hotkeys` jelenleg támogat-e módosító nélküli gombokat (nyíl, Enter, Esc, N); ha nem, ezt az építő bővíti.
- Ha egy nyitáskor lefoglalni kívánt gombot más program már használ (a `hk.failed` jelzi), a panel nyitva marad és kiírja,
  mely gomb nem működik.

## Ellenőrzés
- Motor/modell szinten (stubolt kijelzővel): lépés, határok, Shift-lépés, alapérték, mentés, Esc visszaállít, új változat
  névgenerálás (van/nincs eddigi változat), zárás a preset váltásakor.
- Fókusz: egy másik ablakkal (Jegyzettömb) előtérben megnyitjuk a panelt és megnyomjuk a billentyűket; az előtérben lévő
  ablak (`GetForegroundWindow`) nem változhat, az overlay ablak stílusában ott kell lennie a NOACTIVATE/TOPMOST jelzőnek.
- Zárás után a lefoglalt gombok felszabadulnak (a térkép visszaáll az eredetire).
- **Nem tesztelhető itt:** valódi játék alatti viselkedés (a user nézi meg); élő billentyűleütés játékban.
- Az építés végén a telepítő újraépítése (`build.ps1`) és másolat a Dokumentumok\telepitok mappába.
