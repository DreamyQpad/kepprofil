# Térkép-overlay (Escape from Tarkov) – terv

Méret: projekt (új külső függőség, külön folyamat, logfigyelő, két új gyorsgomb, telepítő-módosítás, tesztek).
Csak Windowson; Linuxon a funkció nem jelenik meg (ahogy a játék-overlay sem érhető el ott).

## Cél és ok

Escape from Tarkov raid közben a játékos az interaktív térképet (nagyítás, húzás, szűrők) a játék fölött akarja látni,
és azt a térképet, amelyiken éppen játszik, magától megnyitva. Ma ehhez alt-tab vagy második monitor kell.
A Képprofil már ismeri a játékot (játékfigyelő) és van játék fölé nyíló, fókuszlopás nélküli overlayje,
ezért ez a funkció ide kerül, nem külön programba.

## Célok

- Gyorsgombbal elő-/eltüntethető, mindig felül lévő térképablak, ami a tarkov.dev interaktív térképét mutatja.
- A pályát a Tarkov saját logjából ismeri fel (betöltéskor), és a megfelelő térképet nyitja meg, kézi választás nélkül.
- Három használati mód:
  - **Pillantás**: áttetsző, átkattintható, a játék megtartja a fókuszt és az egeret.
  - **Billentyűzetes vezérlés**: nyilak = húzás, +/− = nagyítás, a gombok nem jutnak el a játékhoz amíg nyitva van
    (mint a mostani szerkesztő-overlaynél), a fókusz nem változik.
  - **Egeres mód**: külön gyorsgombra az ablak átveszi a fókuszt, kattintható/görgethető; ugyanazzal a gombbal vissza.
- Az ablak helye, mérete és átlátszósága állítható és megmarad.

## Nem-célok

- Injektálás a játékba, a játék memóriájának vagy hálózati forgalmának olvasása.
- Offline, saját térképoldal (a tarkov.dev élő oldala a forrás; internet kell hozzá).
- Linuxos változat.
- Bármi, ami a játékot vezérli vagy a játékfájlokat módosítja (a log csak olvasható).
- A Steam overlay böngészőjére építés (`steam://openurl`): megfontolva, lásd a megközelítéseket.

## Anti-célok (akkor is hiba, ha technikailag működik)

- Fókuszlopás pillantás- és billentyűzetes módban: a játék nem veszítheti el a bemenetet.
- Raid közbeni akadás vagy FPS-esés a térkép miatt.
- A log tartalmának kiszivárgása: a Tarkov logja profilazonosítót és IP-címet is tartalmaz. A figyelő csak a pálya
  nevét veszi ki; mást nem tárol, nem naplóz, nem ír ki sehova.
- Visszamaradó segédfolyamat: a térképfolyamat a Képprofil kilépésekor (vagy összeomlásakor) is megszűnik.
- Hamis térkép: ismeretlen pályanévnél nem nyit találgatott térképet.

## Megközelítések (a megbeszélésből)

- **A. (választott)** Külön folyamat, `pywebview` (Windowson WebView2) a tarkov.dev élő térképével. A Képprofil
  `--map <pálya>` kapcsolóval indítja, a tk főszál érintetlen marad. Ára: új függőség (pywebview + pythonnet) a
  onedir csomagban, internet kell. Azért ez, mert a tkinter nem tud weboldalt megjeleníteni, a pywebview pedig saját
  főszálat igényel, ezért nem futhat a tk-val egy folyamatban.
- **B.** Offline, saját térképoldal: független az oldaltól, de a térképet és az adatokat nekünk kellene karbantartani
  (nagyságrenddel több munka).
- **C.** Steam overlay böngészője `steam://openurl`-lel: nincs új függőség és a Steam kezeli az egeret, de csak
  Steamből indított Tarkovnál megy, nincs billentyűzetes vezérlés, és nem ismert, hogy a parancs az overlay böngészőben
  nyílik-e. A prototípus-lépés tartaléka marad, ha az A elakad.
- **D.** Böngészőablak második monitoron: nem overlay, ezért elvetve.

## Felépítés

- **Logfigyelő** (tisztán szöveg-feldolgozó rész, felület nélkül tesztelhető): a Tarkov telepítési mappájából
  (beállítás: `tarkov_path`; alapból a Windows-eltávolítási nyilvántartás `InstallLocation`) a legfrissebb
  `Logs\log_*` mappa `*application_000.log` fájlját követi (új mappa = új játékindítás). A `scene preset path:maps/<név>_preset`
  és a `Location: <név>` sorokból pályát olvas. Betöltéskor a log egy másodperces olvasással, megosztott olvasással
  nyílik (a játék közben írja).
- **Pálya-táblázat**: játék-belső név → tarkov.dev térkép-azonosító. A betöltési név és a `Location:` név eltérhet
  (mérve: `city` és `TarkovStreets`; `woods` és `Woods`), a táblázat mindkét alakot kezeli. Ismeretlen név: a Képprofil
  naplózza a nevet (csak azt), és nem nyit térképet.
- **Térképfolyamat**: `kijelzo.py --map <azonosító>` indítja a pywebview-ablakot; egyetlen példány, új pályánál
  a meglévő ablak új címre vált, nem új ablak nyílik.
- **Ablakkezelés**: a három mód közti váltás Win32-stílusokkal az ablak HWND-jén (átkattintható/aktiválás nélküli ↔
  kattintható/aktiválható, TOPMOST), a meglévő `overlay_style` mintájára.
- **Gyorsgombok**: két új beállítás: `map_hotkey` elő-/eltüntet (előtűnéskor pillantás mód), `map_interact_hotkey` a módok
  körbeléptetése (pillantás → billentyűzetes → egeres → pillantás; rejtett ablaknál előhozza), ugyanazon az úton, mint
  az `overlay_hotkey` (`DEFAULT_SETTINGS`, `SETTINGS_KEYS`, a Program fül mezője, `hotkey_map`, `_run_hotkey_action`).
- **Beállítások**: automatikus megnyitás betöltéskor (be/ki), átlátszóság, pozíció/méret, `tarkov_path`.
- **Csomagolás**: `requirements.txt` + `build.ps1` (`--collect-all webview`, pythonnet DLL-ek); a WebView2-futtatókörnyezet
  hiánya esetén érthető hibaüzenet (Windows 11-en alapból van).

## Amit a prototípusnak (eldobható) előbb el kell döntenie

1. A tarkov.dev betölt-e a WebView2-ben, és a `https://tarkov.dev/map/<azonosító>` forma működik-e.
2. A pywebview-ablak HWND-jén kívülről (a Képprofil folyamatából) átváltható-e az átkattintható ↔ kattintható állapot.
3. A billentyűzetes vezérlés megoldható-e (nyíl/+/− eljut-e az oldal térképéhez fókuszváltás nélkül, vagy JavaScripttel).
4. A Tarkov hogyan reagál az egeres mód fókuszvesztésére (nem éles raidben, biztonságos pillanatban).
Ha az 1–3 pont akad, a C megközelítés a tartalék.

## Mért: a log jelzősorai (2026-11-23, 7 raid, Woods és Streets)

Az `application_000.log` sorai, ugyanabban a fájlban:

- **Pálya előkészítése**: `scene preset path:maps/<név>_preset.bundle` – a párosítás (matching) elején jelenik meg,
  kb. 30 mp-cel a raid kezdete előtt. Megszakított párosításnál ez téves lehet.
- **Pálya megerősítve / raid indul**: `TRACE-NetworkGameCreate ... Location: <név>` – a betöltés végén, 10–30 mp-cel
  a preset-sor után. Ebből a sorból csak a `Location:` utáni nevet szabad kivenni (a sor profilazonosítót és IP-t is tartalmaz).
- **Raid vége**: `BEClient exit` (majd `BEClient exit successfully`) – mindkét mért raid végén megjelent
  (16:41 és 16:56), és a következő párosítás előtt van. Két minta, nem több.
- Másodlagos vég-jelző (másik fájl, `network-connection`): `Enter to the 'Disconnected' state`, és
  a `SessionEndUIScene` betöltése az output logban. Ezeket nem használjuk, csak tartaléknak jegyezzük.

A terv ebből: előtöltés a preset-sorra, megjelenítés a `Location:` sorra, elrejtés a `BEClient exit` sorra.
A `BEClient exit` játékból való kilépéskor is megjelenhet; ilyenkor az ablak úgyis bezárul a folyamat megszűnésével.

## Nem ismert / ellenőrizendő

- A `BEClient exit` mint raid-vége jelző csak két raidből ismert; a prototípus alatt újabb raidekkel ellenőrizni.
- A többi pálya (Customs, Shoreline, Interchange, Reserve, Lighthouse, Factory, Labs, Ground Zero) log-neve és
  tarkov.dev-azonosítója: eddig csak Woods és Streets látott a logban. A táblázatot a naplózott ismeretlen nevekből és
  a tarkov.dev oldalról kell kiegészíteni.
- A memóriahasználat és a hatás az FPS-re: nincs mérve; a prototípus után mérendő, mielőtt bármit állítanánk róla.
- BattlEye és külső ablak/logolvasás: a külső ablak nem injektál, a logolvasás elterjedt (pl. TarkovMonitor), de
  garancia nincs.

## Kész, ha

- A logfigyelő és a pálya-táblázat egységtesztekkel (valós logsorokból vett mintákkal) zöld.
- A gyorsgomb-bekötés, a beállítások és a térképfolyamat indítása/leállítása tesztelve (a meglévő stubolási technikával).
- A telepítő újraépítve, a másolat a `Dokumentumok\telepitok` mappában.
- A valódi raid alatti működést (pálya-felismerés, módváltás, fókusz) a felhasználó nézi meg; amíg ez nem történt meg,
  ezt nem jelentjük késznek.

## Prototípus eredménye (2026-11-23, eldobható, Windows 11, Python 3.13.17, pywebview 6.2.1, pythonnet 3.2.1)

A prototípus a valódi útvonalat mérte: a szülő a projekt `hw_windows.Hotkeys` osztályával regisztrált gyorsgombot és `Popen`-nel
indította a térképfolyamatot; a „játék" egy tk-ablak volt a térkép alatt. A gyorsgomb szintetikus billentyűleütéssel
(`keybd_event`) lett kiváltva, nem fizikai gombnyomással.

1. **A tarkov.dev betölt a WebView2-ben**, az URL-forma `https://tarkov.dev/map/<azonosító>` (a Woods működött). A térképmotor
   Leaflet (`.leaflet-container`, `window.L`, `.leaflet-control-zoom` gombok). Az oldal sütibanner-t mutat; az elfogadás
   a WebView2-profilban marad (a profilmappa a kapott `storage_path`, `%APPDATA%\KepprofilSpike\EBWebView` jött létre).
2. **Az ablak stílusát a gyerekfolyamat a saját HWND-jén váltja, és működik:**
   - pillantás: rétegezett + átkattintható + nem aktiválódó + tálcagomb nélküli; a tartalom 0,6-os átlátszóságnál is látszik
     (a szórás 61 → 37, az átlag a „játék" színével keveredik, nem üres); a `WindowFromPoint` és egy valódi kattintás is a
     mögötte lévő ablakra ment, az előtér nem változott;
   - egeres mód: az átkattintható és a nem aktiválódó jelző törölve, az ablak kattintható, a valódi kattintás az ablakon marad;
   - a keret (`WS_CAPTION | WS_THICKFRAME`) futás közben ki-be kapcsolható `SWP_FRAMECHANGED`-del (bekapcsolva a kliensterület
     984×661-ről 968×622-re csökken), tehát a mozgatás/átméretezés egeres módban megoldható.
3. **Előtér-zár (a legfontosabb lelet).** A gyerekfolyamat `SetForegroundWindow` hívása a háttérből **elbukik**
   (a térkép nem kapja meg a fókuszt), ha a szülő nem engedélyezi. Ha a szülő a gyorsgomb-üzenetnél `AllowSetForegroundWindow`-t hív
   a `mode mouse` elküldése előtt, a fókusz átkerül. Fejlesztői (venv) futásnál a `Popen` pid-je az indító stub, nem az
   értelmező, ezért a szülő `ASFW_ANY` (-1) értéket használjon. Módból kilépéskor a korábbi előtérablakot vissza kell állítani
   (nincs még kipróbálva).
4. **Billentyűzetes vezérlés oldalszinten megoldható, OS-fókusz nélkül:** a Leaflet-tartály fókuszálható (`tabIndex=0`);
   `container.focus()` + `dispatchEvent(new KeyboardEvent('keydown', {key:'ArrowLeft', keyCode:37, which:37, bubbles:true}))`
   eltolta a térképet (a pane transzformációja 0 → 80 px); a nagyítás a `.leaflet-control-zoom-in` / `-out` elem `.click()` hívása
   (az overlay szélessége 1044 → 2088 px). A mechanizmus tehát JavaScript (`evaluate_js`), nem OS-szintű billentyű.
5. **Folyamatkezelés:** ha a szülő bezárja a gyerek stdin-jét, a gyerek ~2,2 mp alatt kilép (EOF = a szülő meghalt, nincs árva
   folyamat). Fordított irányban a hurok `quit` parancsra is kilép.
6. **Nem kiderített instabilitás:** a hat próbaindításból kettőn a gyerekben a WebView2 inicializálása kivétellel elbukott
   (`InitCoreWebView2Async`), a `loaded` esemény nem jött. Egy korábbi, kilőtt futás árva böngészőfolyamata a profilmappát
   foghatta, de ez nincs megerősítve. A vezérlőnek tűrnie kell, hogy a gyerek sosem jelez `loaded`-et (időkorlát, naplózás,
   egyszeri újraindítás).
7. **Kapu: az 1–3. pont (a spec prototípus-listájában) teljesült, a C megközelítésre (Steam `openurl`) nincs szükség.**
   A 4. pont (a Tarkov fókuszvesztésre adott reakciója egeres módban) még nincs kipróbálva; játékos próbát igényel.
