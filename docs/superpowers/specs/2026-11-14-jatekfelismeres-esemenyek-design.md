# Gyorsabb játékfelismerés folyamat-eseményekkel – terv

Méret: közepes (egy motor-módosítás, egy új, Windows-specifikus eseményforrás, tesztek). Az emelt jogú indítás
beállítása (ütemezett feladat, telepítő) **nem** része – lásd a nem-célokat.

## Cél és ok

Ha elindul egy játék, a hozzá rendelt profil ma kb. 4–5 mp múlva kapcsol be:
legfeljebb 2 mp a lekérdezésig (`gui.py` `watch` szál, 2 mp), utána a `watch_tick` fix `time.sleep(3)`-ja
(„a játék vegye fel a képernyőmódját"). Kilépéskor a visszaállás ugyanígy lekérdezéses.
A cél: a profil a játék indulása után észrevehetően hamarabb kapcsoljon be, és kilépéskor is gyorsabban álljon vissza.

A lekérdezés maga olcsó (mérve: ~1 ms / `process_iter` hívás, 99 folyamatnál), ezért a gépterhelés **nem** cél.

## Célok

- Windowson, emelt jogú futásnál a folyamat indulását/kilépését eseményből ismeri fel a motor, azonnal.
- Emelt jog nélkül (és Linuxon) a működés megegyezik a mostanival, legfeljebb gyorsabb lekérdezéssel – semmi nem törik el.
- A fix 3 mp-es vakvárakozás megszűnik; helyette azonnali bekapcsolás és rövid, késleltetett utánellenőrzés.

## Nem-célok

- Az emelt jogú indítás megoldása (ütemezett feladat bejelentkezéskor, `Startup`-parancsikon lecserélése, telepítő-módosítás):
  külön munka. Addig rendszergazdaként kézzel indítva próbálható.
- Új külső (pip) függőség.
- Linuxos eseményfigyelés.
- A `gui.py` bontása (külön pontja a tervnek).

## Anti-célok (akkor is hiba, ha technikailag működik)

- Villanás: a profil bekapcsolása után a játék képmódváltása nem hagyhatja tartósan nullázott görbén a képet.
- Hamis „kilépett" jelzés: ha az esemény hibás vagy elmarad, a lekérdezés tartaléka javítsa ki, ne ragadjon be a profil.
- Visszamaradó segédfolyamat: az eseményforrás nem maradhat futva a program kilépése után.

## Megközelítések (a megbeszélésből)

- **A.** Csak lekérdezés, javított várakozással: nincs emelt jog, de nem esemény.
- **B.** Csak esemény: emelés nélkül nem működik.
- **C. (választott)** Esemény + lekérdezés tartalékként, mellé a várakozás javítása. Emelés nélkül a mostani viselkedés,
  emeléssel gyors. Ára: tartalék-logika. Azért ez, mert a késés nagy része a 3 mp-es várakozás, és mert semmit nem
  kényszerít ki.

## Terv

### 1. A futó programok nyilvántartása eseménybarát
Az `Engine.running` ma név-halmaz, 6 mp-es gyorsítótárral (`refresh_running`, `proc_running`). Új: számláló (név → példányszám),
hogy két azonos nevű folyamat egyikének kilépése ne töröljön. Új belépési pont: `proc_event(name, started)`, ami a számlálót frissíti
és felébreszti a figyelőt. A `refresh_running` (teljes lekérdezés) a számlálót **újraépíti** – ez a tartalék és az önjavítás.

### 2. Eseményforrás (Windows)
Új modul (`proc_events_windows.py`), amely `Win32_ProcessStartTrace` / `Win32_ProcessStopTrace` eseményeket figyel,
és sorokat ad vissza: `start|stop <név>`. Rendszergazdai jog nélkül a hívás hibázik → a forrás „nem elérhető" állapotba kerül, és a motor
lekérdezéses módban marad. Az eseményforrás megvalósítási módja az **én döntésem**: PowerShell gyerekfolyamat (`Register-WmiEvent`),
mert nem kell hozzá új Python-függőség, és a program már használ PowerShellt (autostart-parancsikon). A gyerekfolyamat a programmal együtt
záródik (kilépéskor leállítjuk; indításkor a `kill_old_watcher` mintájára nem marad árva példány). Ha mérés szerint a PowerShell indítása/memóriája
zavaró, a megvalósító válthat `pywin32`-re vagy közvetlen COM-ra – ez csak az új modult érinti.
Linuxon a `system_linux` nem ad eseményforrást, az maradó lekérdezés.

### 3. A figyelő ritmusa
A `watch` szál `time.sleep(2)` helyett `Event.wait(timeout)`-ot használ: esemény érkezésekor azonnal fut a `watch_tick`.
A timeout: eseményforrással 5 mp (csak tartalék-újraszinkron), nélküle 1 mp. A `proc_running` 6 mp-es gyorsítótára a számláló bevezetésével
megszűnik, ahol az eseményforrás él.

### 4. A várakozás javítása (`watch_tick`, ma `time.sleep(3)`)
A profil azonnal kapcsol be a hit észlelésekor. A játék képmódváltása miatti nullázást a már meglévő
`system_event`-szerű, késleltetett utánellenőrzés fedi le: a bekapcsolás után ~1,5 mp-nél és ~4 mp-nél `enforce` fut
(csak akkor nyúl a képhez, ha eltér a kívánttól, így ép kép mellett nincs villanás). Az `enforce` a tick végén egyébként is fut.
**Nyitott, mérendő:** a 3 mp pontosan mit véd (milyen játékmód/driver nullázza a görbét és mikor). Ezt valódi játékkal kell ellenőrizni;
amíg ez nincs meg, a javítás verdiktje legfeljebb `partial`. Az utánellenőrzés késleltetései (1,5 / 4 mp) kiindulóértékek, a mérés után hangolhatók.

### 5. Visszajelzés
A tálca-/napló-üzenet jelzi, melyik módban fut a figyelő: „játékfigyelő: események" vagy „játékfigyelő: lekérdezés (nincs emelt jog)".
(A teljes hibajelzés a tálcaikonon a terv külön pontja.)

## Tesztek (funkcionális szint)

- `proc_event` számláló: két azonos nevű példány, az egyik kilép → a program „fut" marad; mindkettő kilép → nem fut.
- Esemény után a `watch_tick` a következő lekérdezés előtt kapcsolja be a profilt (ébresztés működik, a stubolt `refresh_running` mellett is).
- Esemény elmaradása: a tartalék-újraszinkron javítja a számlálót (hamis „fut"/„nem fut" kijavul).
- A sorprotokoll értelmezése hamis adatfolyammal (start/stop sorok, hibás sor, EOF).
- Emelés nélküli ág: az eseményforrás „nem elérhető" → a motor a régi működést adja (a meglévő `test_game_exit_restore`, `test_monitor_detection` zöld marad).
- Kézi, nem automatizálható: emelt jogú indítás valódi játékkal – bekapcsolási idő, villanás, kilépés.

## A megvalósítóra marad

- A modul pontos neve és a PowerShell-parancs részletei.
- Az utánellenőrzés késleltetéseinek hangolása a mérés után.
- Hogyan épül újra a számláló a tartalék-újraszinkronnál úgy, hogy közben érkező esemény ne vesszen el.
