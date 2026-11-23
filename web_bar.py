"""A böngészőablak tetején álló sáv (Vissza, Előre, ☆ mentés, a játék könyvjelzői, Bezár) az oldalba beszúrt JavaScriptként,
és a folyamat és a szülő között menő könyvjelző-sorok. A sáv minden futtatáskor a régit cseréli, így a módváltás, az
oldalbetöltés és a könyvjelzők változása is ugyanezt hívja."""
import json

import bookmarks

BAR_HEIGHT = 44

# A cím mindig textContent-tel kerül az oldalba (nem HTML-ként); a könyvjelzők JSON-ként érkeznek (json.dumps).
_BAR_TEMPLATE = r"""(function(){
var data=__DATA__;var token=__TOKEN__;
var old=document.getElementById('kp-web-bar');if(old){old.remove();}
var bar=document.createElement('div');bar.id='kp-web-bar';
bar.style.cssText='position:fixed;top:0;left:0;right:0;height:__HEIGHT__px;z-index:2147483647;display:flex;align-items:center;gap:6px;padding:0 8px;background:#14161a;border-bottom:1px solid #444;box-sizing:border-box;font:14px sans-serif;overflow:hidden';
function button(text,handler,hint){var b=document.createElement('button');b.textContent=text;b.title=hint||'';b.onclick=handler;b.style.cssText='padding:5px 10px;background:#222;color:#fff;border:1px solid #888;border-radius:4px;cursor:pointer;white-space:nowrap;font:14px sans-serif';return b;}
bar.appendChild(button('← Vissza',function(){history.go(-1);}));
bar.appendChild(button('Előre →',function(){history.go(1);}));
bar.appendChild(button('☆',function(){window.pywebview.api.add_bookmark(token);},'Az oldal mentése a könyvjelzők közé'));
var label=document.createElement('span');label.textContent=(data.game||'Általános')+':';label.style.cssText='color:#7fb2ff;white-space:nowrap';bar.appendChild(label);
var list=document.createElement('div');list.style.cssText='display:flex;gap:6px;flex:1;overflow-x:auto;min-width:0';
data.items.forEach(function(item,i){var chip=document.createElement('span');chip.style.cssText='display:flex;white-space:nowrap';var open=button(item.title,function(){location.href=item.url;},item.url);open.style.maxWidth='180px';open.style.overflow='hidden';open.style.textOverflow='ellipsis';var del=button('×',function(){window.pywebview.api.remove_bookmark(i,token);},'Törlés');del.style.padding='5px 6px';chip.appendChild(open);chip.appendChild(del);list.appendChild(chip);});
bar.appendChild(list);
bar.appendChild(button('✕ Bezár',function(){window.pywebview.api.close(token);}));
(document.body||document.documentElement).appendChild(bar);
bar.style.display='__DISPLAY__';
document.documentElement.style.marginTop='__MARGIN__';
})()"""


def web_bar_script(visible, payload, token=""):
    """A sáv szkriptje; `payload`: `{"game": név, "items": [{"title", "url"}]}` (lásd `bookmarks.payload`). A `token` a folyamat
    titka: a sáv gombjai ezzel hívják a `js_api`-t, így egy megnyitott weboldal a könyvjelzőket nem tudja kezelni. A `__DATA__`
    helyőrző cseréje az utolsó, hogy a könyvjelző címében álló szöveg ne cserélődjön."""
    return (_BAR_TEMPLATE.replace("__HEIGHT__", str(BAR_HEIGHT)).replace("__DISPLAY__", "flex" if visible else "none")
            .replace("__MARGIN__", f"{BAR_HEIGHT}px" if visible else "")
            .replace("__TOKEN__", json.dumps(token)).replace("__DATA__", json.dumps(payload)))


def add_bookmark_line(title, url):
    """A folyamat kimeneti sora egy új könyvjelzőhöz (egysoros JSON, a szülő ellenőrzi és menti)."""
    return "bookmark add " + json.dumps({"title": title, "url": url})


def remove_bookmark_line(index):
    return f"bookmark remove {index}"


def parse_bookmarks_command(text):
    """A szülő `bookmarks <json>` parancsának tartalma -> ("bookmarks", tisztított sáv), vagy None, ha hibás."""
    try:
        payload = json.loads(text)
    except ValueError:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("game"), str) or not isinstance(payload.get("items"), list):
        return None
    clean = bookmarks.items({"x": payload["items"]}, "x")[:bookmarks.MAX_ITEMS]
    return ("bookmarks", {"game": payload["game"][:bookmarks.TITLE_MAX], "items": clean})
