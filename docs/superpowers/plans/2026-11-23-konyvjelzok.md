# Böngésző: játékfüggő könyvjelzősáv — terv

**Kérés:** a böngészőben könyvjelzősáv legyen, a könyvjelzők menthetők, és a mentett sáv **játékonként külön** legyen.

## Döntések
- **Játék-azonosító:** az aktív preset neve (`Engine.overlay_target`); „Alap" vagy nincs aktív preset → közös („Általános") sáv.
- **Tárolás:** `settings.json` → `bookmarks: {játék: [{title, url}]}` (a meglévő export/import is viszi). Legfeljebb 30 könyvjelző játékonként, cím legfeljebb 40 karakter.
- **Megjelenítés:** teljes szélességű sáv az oldal tetején (Vissza, Előre, ☆ mentés, a könyvjelzők, jobbra Bezár); a sáv alatt az oldal lejjebb tolódik.
- **Adatáramlás:** a szülő (BrowserController) a tulajdonos: megnyitáskor `bookmarks <json>` parancsot küld a böngészőfolyamatnak; a folyamat a ☆ / ✕ gombra `bookmark add <json>` / `bookmark remove <index>` sort ír ki; a szülő menti és visszaküldi a frissített sávot.
- **Biztonság:** csak http/https URL (a szülő és a folyamat is ellenőrzi), a cím `textContent`-tel kerül az oldalba, a JSON-t `json.dumps` szolgáltatja.

## Taskok
1. `bookmarks.py` tiszta tárolóréteg (add/remove/items/payload, validálás) + tesztek.
2. `map_window.py`: `bookmarks` parancs, új sáv-script, `WebApi.add_bookmark/remove_bookmark`, kimeneti sorok + tesztek.
3. `BrowserController`: játék-lekérdezés, `bookmarks` küldése, `bookmark add/remove` feldolgozása + tesztek.
4. `gui.py` bekötés (`game_key` az aktív presetből), `config` (`bookmarks` alapérték és SETTINGS_KEYS), README, build, csomagolt ellenőrzés.
