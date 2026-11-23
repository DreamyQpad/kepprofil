"""A böngésző könyvjelzői, játékonként külön: `{játék: [{"title", "url"}]}`. A játék azonosítója az aktív preset neve; az
üres azonosító (GENERAL) a közös sáv, ha nincs aktív játék. Tiszta adatréteg: a hívó adja a szótárt (a beállítások `bookmarks`
kulcsa), és ő menti."""
from urllib.parse import urlparse

GENERAL = ""
MAX_ITEMS = 30
TITLE_MAX = 40
URL_MAX = 2000


def valid_url(url):
    """Csak http/https cím fogadható el (a `javascript:`, `file:`, `data:` stb. nem)."""
    if not isinstance(url, str) or not url or len(url) > URL_MAX:
        return False
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _clean(entries):
    """A sérült elemeket (nem szótár, rossz típus, érvénytelen URL) eldobja."""
    if not isinstance(entries, list):
        return []
    result = []
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("title"), str) and valid_url(entry.get("url")):
            result.append({"title": entry["title"], "url": entry["url"]})
    return result


def items(data, game):
    """A játék könyvjelzői (másolat, a sérült elemek nélkül)."""
    return _clean(data.get(game))


def add(data, game, title, url):
    """Hozzáad; False, ha az URL érvénytelen, már szerepel, vagy a lista tele van. Üres cím helyett a hoszt neve kerül be."""
    if not valid_url(url):
        return False
    current = items(data, game)
    if len(current) >= MAX_ITEMS or any(item["url"] == url for item in current):
        return False
    text = (title if isinstance(title, str) else "").strip()[:TITLE_MAX] or urlparse(url).netloc[:TITLE_MAX]
    current.append({"title": text, "url": url})
    data[game] = current
    return True


def remove(data, game, index):
    """Törli az adott sorszámú elemet; False, ha nincs ilyen."""
    current = items(data, game)
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(current):
        return False
    del current[index]
    data[game] = current
    return True


def payload(data, game):
    """A böngészőfolyamatnak küldött sáv: a játék neve és a könyvjelzői."""
    return {"game": game, "items": items(data, game)}
