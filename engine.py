"""A motor: melyik monitoron melyik preset aktív, játékfigyelő, kijelző-visszaállítás, energiaprofil és RGB."""
import threading
import time

from config import _write_json, add_new_monitors, load_config, load_settings, mirror_first, night_mult, pgain, pvals, write_log
from consts import CONFIG_FILE, NEUTRAL, SETTINGS_FILE
from hw import Display, Rgb, find_dev, list_monitors, power_active, power_set


class Engine:
    def __init__(self, notify=lambda: None):
        self.lock = threading.RLock()
        self.cfg, self.set = load_config(), load_settings()
        self.notify = notify
        self.display = Display()
        self.rgb = Rgb()
        self.active = {}            # monitor-azonosító -> bekapcsolt preset neve
        self.manual_off = set()     # (monitor, preset): kézzel kikapcsolva, amíg a játék fut
        self.auto = set()           # (monitor, preset): a játék indította; a játék kilépésekor kikapcsol
        self.prev = {}              # monitor -> a játék indulása előtt kézzel bekapcsolt preset; a kilépés ezt állítja vissza
        self.variant = {}           # (monitor, preset) -> érvényes változat neve (futásidejű; hiányában az első)
        self.toast_cb = lambda text, mid: None      # a GUI állítja be: képernyő-értesítés
        self.monitors_cb = lambda: None             # a GUI állítja be: a csatlakoztatott monitorok köre változott
        self.connected = set()      # a most csatlakoztatott monitorok azonosítója (kisbetűvel); üres: a detektálás nem ment
        self.monitors_t = 0.0
        self.night_mons = set()     # azok a monitorok (azonosító), ahol az éjszakai mód be van kapcsolva
        self.panel_open = False
        self.hold = False           # összehasonlítás: nyomva tartva a semleges kép látszik
        self.running = set()
        self.running_t = 0.0
        self.log = []
        self.fx_lock = threading.Lock()
        self.fx_wake = threading.Event()
        self.power_prev = self.power_applied = None
        self.rgb_applied = dict(self.set["base_rgb"])           # induláskor feltételezzük, hogy már az alap látszik
        self.stop = False
        self.reapplied_t = 0.0
        self.migrate_cycle_hotkey()
        self.refresh_monitors(initial=True)
        self.refresh_running()

    def migrate_cycle_hotkey(self):
        """A léptető gyorsgomb globális (egy gomb minden játéknál). A régi, presetenkénti beállításból az első
        talált gomb lesz a globális (ha még nincs), a presetenkéntiek törlődnek."""
        found = ""
        for mon in self.cfg["monitors"]:
            for p in mon["presets"].values():
                found = found or p.get("cycle_hotkey", "")
                p.pop("cycle_hotkey", None)
        if found and not self.set.get("cycle_hotkey"):
            self.set["cycle_hotkey"] = found
        if found:
            self.save_config()
            self.save_settings()

    # -- segédek
    def say(self, text):
        self.log.append((time.strftime("%H:%M:%S"), text))
        del self.log[:-50]
        write_log(text)
        self.notify()

    def save_config(self):
        _write_json(CONFIG_FILE, self.cfg)

    def save_settings(self):
        _write_json(SETTINGS_FILE, self.set)

    def mon(self, mid):
        return next((m for m in self.cfg["monitors"] if m["id"] == mid), None)

    def mons(self):
        """A most csatlakoztatott monitorok (a cfg-beli bejegyzések). A lecsatlakoztatott monitor presetjei a cfg-ben
        megmaradnak, de sehol nem jelennek meg és nem működnek. Ha a detektálás nem adott eredményt, az összes."""
        if not self.connected:
            return list(self.cfg["monitors"])
        return [m for m in self.cfg["monitors"] if m["id"].lower() in self.connected]

    def refresh_monitors(self, initial=False):
        """Újraolvassa, mely monitorok vannak csatlakoztatva: az újakat felveszi (Alap presettel), a lecsatlakoztatottak
        bekapcsolt állapotát eldobja. Igaz, ha változott a csatlakoztatott monitorok köre."""
        self.monitors_t = time.time()
        found = list_monitors()
        if not found:                                           # átmeneti üres lista: ne ürítsük ki a felületet
            return False
        ids = {m["id"].lower() for m in found}
        with self.lock:
            changed = ids != self.connected
            if add_new_monitors(self.cfg, found) and not initial:
                self.save_config()
            gone = self.connected - ids
            self.connected = ids
            for mid in [k for k in self.active if k.lower() in gone]:
                name = self.active.pop(mid)
                self.auto.discard((mid, name))
                self.prev.pop(mid, None)
            self.night_mons -={k for k in self.night_mons if k.lower() in gone}
        if changed and not initial:
            names = ", ".join(m["name"] for m in self.mons())
            self.say(f"Monitorok változtak: {names}")
            self.monitors_cb()
        return changed

    def preset(self, mid, name):
        m = self.mon(mid)
        return m["presets"].get(name) if m else None

    def refresh_running(self):
        import psutil
        names = set()
        for p in psutil.process_iter(["name"]):
            n = (p.info.get("name") or "").lower()
            names.add(n[:-4] if n.endswith(".exe") else n)
        self.running, self.running_t = names, time.time()

    def proc_running(self, proc):
        if not proc:
            return False
        if time.time() - self.running_t > 6:
            self.refresh_running()
        p = proc.lower()
        return (p[:-4] if p.endswith(".exe") else p) in self.running

    # -- mit kell látni
    def target(self, mid):
        """((gamma, kontraszt, fényerő, vibrance), RGB-szorzó) a monitor jelenlegi állapotához."""
        name = self.active.get(mid)
        p = self.preset(mid, name) if name else None
        vals = pvals(p, self.cur_variant(mid, name)) if p else NEUTRAL
        gain = [x / 100.0 for x in pgain(p, self.cur_variant(mid, name))] if p else [1.0, 1.0, 1.0]
        return vals, tuple(n * g for n, g in zip(self.night_factor(mid), gain))    # éjszakai mód × a preset színcsatorna-erősítése

    def night_factor(self, mid):
        """A monitor éjszakai szorzója: csak ha ezen a monitoron be van kapcsolva, és nem fut a bekapcsolt preset játéka."""
        name = self.active.get(mid)
        p = self.preset(mid, name) if name else None
        game = bool(p and p.get("process") and self.proc_running(p["process"]))
        return night_mult(self.set["night_strength"]) if (mid in self.night_mons and not game) else (1.0, 1.0, 1.0)

    def apply_display(self, mid, vals, mult=(1.0, 1.0, 1.0)):
        dev = find_dev(mid)
        if not dev:
            return False
        with self.lock:
            return self.display.apply(dev, vals, mult)

    def sync(self, mid=None):
        """A kijelzőt az aktuális állapotra (bekapcsolt preset + éjszakai mód) állítja."""
        ok = True
        for m in self.mons():
            if mid is None or m["id"] == mid:
                ok = self.apply_display(m["id"], *self.target(m["id"])) and ok
        self.fx_wake.set()
        self.notify()
        return ok

    def preview(self, mid, vals, gain=(100, 100, 100)):
        """Panel: élő előnézet mentés nélkül; a gain az R/G/B erősítés százalékban. Az éjszakai mód rajta marad,
        ha az adott monitoron be van kapcsolva (különben a csúszka mozdítása kikapcsolni látszana)."""
        return self.apply_display(mid, vals, tuple(n * x / 100.0 for n, x in zip(self.night_factor(mid), gain)))

    def show_neutral(self, mid):
        return self.apply_display(mid, NEUTRAL)

    # -- kapcsolók
    def set_active(self, mid, name, on):
        with self.lock:
            p = self.preset(mid, name)
            if p is None:
                return
            running = bool(p.get("process") and self.proc_running(p["process"]))
            changed = True
            if on:
                self.active[mid] = name
                self.prev.pop(mid, None)                       # kézi választás: a kilépés már nem ír felül
                self.manual_off.discard((mid, name))
                # ha a játék épp fut, a játék kilépése kikapcsolja; ha nem fut, a preset kézi marad
                (self.auto.add if running else self.auto.discard)((mid, name))
            elif self.active.get(mid) == name:
                self.active.pop(mid)
                self.auto.discard((mid, name))
                if running:
                    self.manual_off.add((mid, name))           # a játék fut: a figyelő ne kapcsolja vissza
            else:
                changed = False
            self.sync(mid)
            if changed:
                self.toast(self.label(mid, name) + ("" if on else " – kikapcsolva"), mid)

    def toggle_preset(self, mid, name):
        self.set_active(mid, name, self.active.get(mid) != name)

    # -- képernyő-értesítés (a GUI jeleníti meg, a játék fölött is)
    def toast(self, text, mid=None):
        if self.set.get("toast", True) and not self.panel_open:
            self.toast_cb(text, mid)

    def label(self, mid, name):
        v = self.cur_variant(mid, name)
        return name + (f" – {v}" if v else "")

    # -- változatok: egy presetnek (alkalmazásnak) több csúszkaállása lehet, pl. pályánként
    def cur_variant(self, mid, name):
        """A preset éppen érvényes változata (None, ha a presetnek nincsenek változatai)."""
        names = list((self.preset(mid, name) or {}).get("variants") or {})
        v = self.variant.get((mid, name))
        return v if v in names else (names[0] if names else None)

    def select_variant(self, mid, name, vname):
        """Gyorsgomb: a változat kiválasztása; ha a preset nem volt bekapcsolva, be is kapcsol."""
        with self.lock:
            if vname not in ((self.preset(mid, name) or {}).get("variants") or {}):
                return
            self.variant[(mid, name)] = vname
            if self.active.get(mid) != name:
                self.set_active(mid, name, True)               # ez maga is jelez
            else:
                self.sync(mid)
                self.toast(self.label(mid, name), mid)
        self.say(f"{(self.mon(mid) or {}).get('name', mid)}: '{name}' – {vname}")

    def cycle_variant(self, mid, name):
        """Egy gomb a preset változatai között: a következőre lép; ha a preset ki volt kapcsolva, a mostanival bekapcsol."""
        with self.lock:
            names = list((self.preset(mid, name) or {}).get("variants") or {})
            if not names:
                return
            if self.active.get(mid) != name:
                self.set_active(mid, name, True)
            else:
                self.variant[(mid, name)] = names[(names.index(self.cur_variant(mid, name)) + 1) % len(names)]
                self.sync(mid)
                self.toast(self.label(mid, name), mid)
        self.say(f"{(self.mon(mid) or {}).get('name', mid)}: '{name}' – {self.cur_variant(mid, name)}")

    def cycle_active(self):
        """A globális léptető gomb: minden monitoron a most aktív preset következő változatára lép
        (csak azon, amelyiknek vannak változatai); ha nincs ilyen, jelzi."""
        with self.lock:
            targets = [(m["id"], self.active[m["id"]]) for m in self.mons()
                       if m["id"] in self.active and (self.preset(m["id"], self.active[m["id"]]) or {}).get("variants")]
        if not targets:
            self.toast("Nincs aktív preset változatokkal")
            return
        for mid, name in targets:
            self.cycle_variant(mid, name)

    # -- játék-overlay: az aktuális játék profiljának szerkesztése a játék fölött
    def overlay_target(self, fg_mid=None):
        """(monitor, preset), amit az overlay szerkeszt: az előtérben lévő ablak monitorja, ha ott van aktív preset;
        különben az első monitor, amelyiken van. None, ha sehol nincs aktív preset."""
        with self.lock:
            if fg_mid in self.active and self.preset(fg_mid, self.active[fg_mid]) is not None:
                return fg_mid, self.active[fg_mid]
            return next(((m["id"], self.active[m["id"]]) for m in self.mons()
                         if m["id"] in self.active and self.preset(m["id"], self.active[m["id"]]) is not None), None)

    @staticmethod
    def _values(vals, gain):
        g, c, b, v = vals
        return {"gamma": g, "contrast": c, "brightness": b, "vibrance": v, "gain": [int(x) for x in gain]}

    def save_values(self, mid, name, vals, gain):
        """Az érvényes változatba (változat nélküli presetnél a felső szintre) menti a képértékeket; vals = (gamma
        belső skálán, kontraszt, fényerő, vibrance), gain = R/G/B százalék. A preset többi mezőjéhez nem nyúl."""
        with self.lock:
            p = self.preset(mid, name)
            if p is None:
                return
            target = p["variants"][self.cur_variant(mid, name)] if p.get("variants") else p
            target.update(self._values(vals, gain))
            mirror_first(p)
            self.save_config()

    def add_variant(self, mid, name, vals, gain):
        """Új változat a megadott értékekből, automatikus névvel („Változat N", N ≥ 2); a visszaadott név lesz az érvényes.
        Ha a presetnek még nem volt változata, az eddigi értékek „Alap" néven az első változattá válnak."""
        with self.lock:
            p = self.preset(mid, name)
            if not p.get("variants"):
                p["variants"] = {"Alap": {"gamma": p["gamma"], "contrast": p["contrast"], "brightness": p["brightness"],
                                          "vibrance": p.get("vibrance", 50), "gain": pgain(p)}}
            n = next(f"Változat {k}" for k in range(2, len(p["variants"]) + 3) if f"Változat {k}" not in p["variants"])
            p["variants"][n] = self._values(vals, gain)
            self.variant[(mid, name)] = n
            self.save_config()
            return n

    def toggle_night(self, mid=None):
        """Éjszakai mód: mid megadva -> csak az a monitor; nélküle (gyorsgomb/tálca "mind") -> ha bárhol be van
        kapcsolva, mindenhol ki, különben minden jelenlegi monitoron be."""
        with self.lock:
            if mid is not None:
                targets, on = [mid], mid not in self.night_mons
                label = (self.mon(mid) or {}).get("name", mid)
            else:
                targets = [m["id"] for m in self.mons()]
                on, label = not self.night_mons, "minden monitor"
            for t in targets:
                (self.night_mons.add if on else self.night_mons.discard)(t)
            if not on and mid is None:
                self.night_mons.clear()
            self.sync()
        text = f"Éjszakai mód: {label} – " + ("be" if on else "ki")
        self.toast(text, mid)
        self.say(text)

    def set_night_strength(self, v):
        self.set["night_strength"] = int(v)
        if self.night_mons:
            self.sync()

    def neutral_all(self):
        with self.lock:
            for mid, name in list(self.active.items()):
                p = self.preset(mid, name)
                if p and p.get("process") and self.proc_running(p["process"]):
                    self.manual_off.add((mid, name))
            self.active.clear()
            self.auto.clear()
            self.prev.clear()
            self.night_mons.clear()
            self.sync()
        self.toast("Semleges kép")
        self.say("Semleges kép")

    def hotkey_map(self):
        m = {}
        for mon in self.mons():
            for name, p in mon["presets"].items():
                if p.get("hotkey"):
                    m[f"p|{mon['id']}|{name}"] = p["hotkey"]
                for vn, v in (p.get("variants") or {}).items():
                    if v.get("hotkey"):
                        m[f"v|{mon['id']}|{name}|{vn}"] = v["hotkey"]
        if self.set.get("cycle_hotkey"):
            m["cycle"] = self.set["cycle_hotkey"]
        if self.set.get("overlay_hotkey"):
            m["overlay"] = self.set["overlay_hotkey"]
        if self.set.get("night_hotkey"):
            m["night"] = self.set["night_hotkey"]
        if self.set.get("neutral_hotkey"):
            m["neutral"] = self.set["neutral_hotkey"]
        return m

    def run_action(self, action):
        if action == "night":
            self.toggle_night()
        elif action == "neutral":
            self.neutral_all()
        elif action.startswith("v|"):
            _, mid, name, vname = action.split("|", 3)
            self.select_variant(mid, name, vname)
        elif action == "cycle":
            self.cycle_active()
        elif action.startswith("p|"):
            _, mid, name = action.split("|", 2)
            self.toggle_preset(mid, name)

    # -- játékfigyelő
    def watch_tick(self):
        self.refresh_running()
        if time.time() - self.monitors_t > self.MONITOR_POLL:
            self.refresh_monitors()
        for mon in self.mons():
            mid = mon["id"]
            for key in [k for k in self.manual_off if k[0] == mid]:
                p = self.preset(*key)
                if not (p and self.proc_running(p.get("process"))):
                    self.manual_off.discard(key)               # a játék kilépett: újra automatikus
            hit = next(((n, p) for n, p in mon["presets"].items()
                        if p.get("process") and self.proc_running(p["process"]) and (mid, n) not in self.manual_off), None)
            cur = self.active.get(mid)
            if hit and cur != hit[0]:
                time.sleep(3)                                  # a játék vegye fel a képernyőmódját
                with self.lock:
                    if not (cur and (mid, cur) in self.auto):      # másik játék átvételekor a korábbi alap marad
                        if cur:
                            self.prev[mid] = cur
                        else:
                            self.prev.pop(mid, None)
                    self.active[mid] = hit[0]
                    self.variant.pop((mid, hit[0]), None)          # a játék indulásakor az első változat
                    self.auto.add((mid, hit[0]))
                    ok = self.sync(mid)
                self.toast(self.label(mid, hit[0]), mid)
                self.say(f"{mon['name']}: '{hit[0]}' bekapcsolt (játék elindult){'' if ok else ' – nem sikerült'}")
            elif cur and (mid, cur) in self.auto:
                p = self.preset(mid, cur)
                if not (p and p.get("process") and self.proc_running(p["process"])):
                    with self.lock:
                        self.active.pop(mid, None)
                        self.auto.discard((mid, cur))
                        back = self.prev.pop(mid, None)
                        if back and self.preset(mid, back) is not None:
                            self.active[mid] = back                # a játék előtti alap, nem a semleges kép
                        self.sync(mid)
                    self.say(f"{mon['name']}: '{cur}' kikapcsolt (a játék kilépett)"
                             + (f", vissza: '{back}'" if self.active.get(mid) == back and back else ""))
            if not (self.panel_open or self.hold):
                self.enforce(mid)

    def enforce(self, mid, why="felülírta a játék/driver"):
        """A játék vagy a driver nullázhatja a görbét: ha eltér a kívánttól, visszaállítjuk."""
        vals, mult = self.target(mid)
        if vals == NEUTRAL and mult == (1.0, 1.0, 1.0):
            return                                             # semleges állapotban nem nyúlunk bele
        dev = find_dev(mid)
        if not dev:
            return
        if self.display.drifted(dev, vals, mult):
            self.apply_display(mid, vals, mult)
            self.say(f"{self.mon(mid)['name']}: a beállítást visszaállítottam ({why})")
            return True
        return False

    # -- rendszeresemények: ébredés, kijelzőváltás, feloldás (hw.SystemEvents hívja)
    MONITOR_POLL = 6.0                                         # ennyi másodpercenként ellenőrzi a figyelő a csatlakoztatott monitorokat
    EVENT_DELAYS = {"resume": (2.0, 6.0, 15.0), "display": (1.0, 4.0), "unlock": (1.5, 5.0)}
    EVENT_TEXT = {"resume": "ébredés után", "display": "kijelzőváltás után", "unlock": "a munkamenet feloldása után"}

    def system_event(self, kind):
        """A driver ilyenkor gyakran nullázza a gamma-görbét vagy a vibrance-t, de a monitor még nem biztos, hogy kész:
        ezért néhány késleltetéssel újra ellenőrzünk (ami rendben van, ahhoz nem nyúlunk, így nincs villanás)."""
        for d in self.EVENT_DELAYS.get(kind, (2.0,)):
            t = threading.Timer(d, self._after_event, args=(kind,))
            t.daemon = True
            t.start()

    def _after_event(self, kind):
        if self.stop:
            return
        try:
            self.refresh_monitors()                              # monitor ki-/becsatlakoztatása is kijelzőváltás
        except Exception as e:
            self.say(f"Monitor-detektálás hiba ({e.__class__.__name__})")
        self.reapply(kind)

    def reapply(self, kind):
        if self.stop or self.hold or self.panel_open:         # a panel előnézete / az összehasonlítás nem bántható
            return
        with self.lock:
            if time.time() - self.reapplied_t < 0.4:          # a közeli események egyszeri ellenőrzést kapnak
                return
            self.reapplied_t = time.time()
            for mon in self.mons():
                try:
                    self.enforce(mon["id"], self.EVENT_TEXT.get(kind, kind))
                except Exception as e:
                    self.say(f"Visszaállítás hiba ({e.__class__.__name__})")

    # -- mellékhatások: energiaprofil, RGB (külön szálban, mert lassú lehet)
    def desired_fx(self):
        power, rgb = None, None
        for mon in self.mons():
            p = self.preset(mon["id"], self.active.get(mon["id"])) if mon["id"] in self.active else None
            if p:
                power = power or p.get("power") or None
                if not rgb and p.get("rgb", {}).get("mode", "none") != "none":
                    rgb = p["rgb"]
        return power, (rgb or self.set["base_rgb"])

    def fx_once(self):
        with self.fx_lock:
            power, rgb = self.desired_fx()
            if power:
                if self.power_prev is None:
                    self.power_prev = power_active()
                if power != self.power_applied:
                    self.power_applied = power if power_set(power) else self.power_applied
            elif self.power_prev:
                power_set(self.power_prev)
                self.power_prev = self.power_applied = None
            if rgb != self.rgb_applied and rgb.get("mode", "none") != "none":
                try:
                    self.rgb.apply(rgb)
                    self.rgb_applied = dict(rgb)
                except Exception as e:
                    self.rgb_applied = dict(rgb)               # ne próbálkozzon végtelenül
                    self.say(f"RGB: nem sikerült ({e.__class__.__name__}). Fut az OpenRGB szolgáltatás?")
            elif rgb.get("mode") == "none":
                self.rgb_applied = dict(rgb)

    def fx_loop(self):
        while not self.stop:
            self.fx_wake.wait()
            self.fx_wake.clear()
            if self.stop:
                break
            try:
                self.fx_once()
            except Exception as e:
                self.say(f"Profil: hiba ({e})")

    def shutdown(self):
        self.stop = True
        with self.lock:
            self.active.clear()
            self.night_mons.clear()
            for m in self.mons():
                self.apply_display(m["id"], NEUTRAL)
        try:
            self.fx_once()
        except Exception:
            pass
        self.fx_wake.set()
