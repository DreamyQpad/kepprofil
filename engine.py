"""A motor: melyik monitoron melyik preset aktív, játékfigyelő, kijelző-visszaállítás, energiaprofil és RGB."""
import sys
import threading
import time

from config import _write_json, add_new_monitors, load_config, load_settings, mirror_first, night_mult, pgain, pvals, write_log
from consts import CONFIG_FILE, NEUTRAL, SETTINGS_FILE
from hw import Display, Rgb, find_dev, list_monitors, power_active, power_set


def norm_proc(name):
    """A folyamatnév összehasonlítható alakja: kisbetűs, `.exe` nélkül; üres/None -> üres."""
    normalized = (name or "").lower()
    return normalized.removesuffix(".exe")


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
        self.toast_cb = lambda text, monitor_id: None      # a GUI állítja be: képernyő-értesítés
        self.monitors_cb = lambda: None             # a GUI állítja be: a csatlakoztatott monitorok köre változott
        self.connected = set()      # a most csatlakoztatott monitorok azonosítója (kisbetűvel); üres: a detektálás nem ment
        self.monitors_t = 0.0
        self.night_mons = set()     # azok a monitorok (azonosító), ahol az éjszakai mód be van kapcsolva
        self.panel_open = False
        self.hold = False           # összehasonlítás: nyomva tartva a semleges kép látszik
        self.proc_counts = {}       # normalizált név -> futó példányok száma (esemény- és lekérdezéses módban is ez a forrás)
        self.running = set()        # a proc_counts pozitív kulcsai
        self.running_t = 0.0
        self.events = None          # a folyamat-eseményforrás (van `stop()`-ja), vagy None
        self.event_mode = False     # igaz: a folyamat-eseményfigyelő él, a gyorsítótár nem avul el (nincs 6 mp-es újraolvasás)
        self.watch_wake = threading.Event()     # figyelt nevű folyamat indult/kilépett: a figyelő azonnal fusson
        self.run_lock = threading.Lock()
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
        for monitor in self.cfg["monitors"]:
            for preset in monitor["presets"].values():
                found = found or preset.get("cycle_hotkey", "")
                preset.pop("cycle_hotkey", None)
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

    def mon(self, monitor_id):
        return next((monitor for monitor in self.cfg["monitors"] if monitor["id"] == monitor_id), None)

    def mons(self):
        """A most csatlakoztatott monitorok (a cfg-beli bejegyzések). A lecsatlakoztatott monitor presetjei a cfg-ben
        megmaradnak, de sehol nem jelennek meg és nem működnek. Ha a detektálás nem adott eredményt, az összes."""
        if not self.connected:
            return list(self.cfg["monitors"])
        return [monitor for monitor in self.cfg["monitors"] if monitor["id"].lower() in self.connected]

    def refresh_monitors(self, initial=False):
        """Újraolvassa, mely monitorok vannak csatlakoztatva: az újakat felveszi (Alap presettel), a lecsatlakoztatottak
        bekapcsolt állapotát eldobja. Igaz, ha változott a csatlakoztatott monitorok köre."""
        self.monitors_t = time.time()
        found = list_monitors()
        if not found:                                           # átmeneti üres lista: ne ürítsük ki a felületet
            return False
        ids = {monitor["id"].lower() for monitor in found}
        with self.lock:
            changed = ids != self.connected
            if add_new_monitors(self.cfg, found) and not initial:
                self.save_config()
            gone = self.connected - ids
            self.connected = ids
            for monitor_id in [stored_id for stored_id in self.active if stored_id.lower() in gone]:
                name = self.active.pop(monitor_id)
                self.auto.discard((monitor_id, name))
                self.prev.pop(monitor_id, None)
            self.night_mons -={stored_id for stored_id in self.night_mons if stored_id.lower() in gone}
        if changed and not initial:
            names = ", ".join(monitor["name"] for monitor in self.mons())
            self.say(f"Monitorok változtak: {names}")
            self.monitors_cb()
        return changed

    def preset(self, monitor_id, name):
        monitor = self.mon(monitor_id)
        return monitor["presets"].get(name) if monitor else None

    def refresh_running(self):
        import psutil
        self.set_running(process.info.get("name") for process in psutil.process_iter(["name"]))

    def set_running(self, raw_names):
        """A névszámlálót a nyers folyamatnevekből újraépíti (teljes pillanatkép)."""
        counts = {}
        for raw in raw_names:
            normalized = norm_proc(raw)
            if normalized:
                counts[normalized] = counts.get(normalized, 0) + 1
        with self.run_lock:
            self.proc_counts = counts
            self.running = set(counts)
            self.running_t = time.time()

    def proc_event(self, started, name):
        """Egy folyamat indulása/kilépése: a névszámlálót +1/-1 módosítja (nulla alá nem megy). Ha a név figyelt
        (valamelyik preset folyamata), felébreszti a figyelőt. A példányszám azért kell, mert több azonos nevű
        folyamat is futhat, és az egyik kilépése nem jelenti a játék végét."""
        normalized = norm_proc(name)
        if not normalized:
            return
        with self.run_lock:
            count = self.proc_counts.get(normalized, 0) + (1 if started else -1)
            if count > 0:
                self.proc_counts[normalized] = count
            else:
                self.proc_counts.pop(normalized, None)
            self.running = set(self.proc_counts)
        names = self.watched_names(blocking=False)
        if names is None or normalized in names:                         # ha a konfig épp zárolt, inkább felesleges ébresztés, mint várakozás
            self.watch_wake.set()

    def watched_names(self, blocking=True):
        """Az összes monitor összes presetjének normalizált folyamatneve (üres nélkül). Nem blokkoló hívásnál None, ha a
        `lock`-ot épp más tartja (hardver-szinkron közben): az eseményszál nem várakozhat rá."""
        if not self.lock.acquire(blocking):
            return None
        try:
            return {norm_proc(preset.get("process")) for monitor in self.cfg["monitors"] for preset in monitor["presets"].values()} - {""}
        finally:
            self.lock.release()

    def proc_running(self, proc):
        if not proc:
            return False
        if not self.event_mode and time.time() - self.running_t > 6:
            self.refresh_running()
        return norm_proc(proc) in self.running

    # -- mit kell látni
    def target(self, monitor_id):
        """((gamma, kontraszt, fényerő, vibrance), RGB-szorzó) a monitor jelenlegi állapotához."""
        name = self.active.get(monitor_id)
        preset = self.preset(monitor_id, name) if name else None
        values = pvals(preset, self.cur_variant(monitor_id, name)) if preset else NEUTRAL
        gain = [percent / 100.0 for percent in pgain(preset, self.cur_variant(monitor_id, name))] if preset else [1.0, 1.0, 1.0]
        return values, tuple(night_gain * preset_gain for night_gain, preset_gain in zip(self.night_factor(monitor_id), gain))    # éjszakai mód × a preset színcsatorna-erősítése

    def night_factor(self, monitor_id):
        """A monitor éjszakai szorzója: csak ha ezen a monitoron be van kapcsolva, és nem fut a bekapcsolt preset játéka."""
        name = self.active.get(monitor_id)
        preset = self.preset(monitor_id, name) if name else None
        game = bool(preset and preset.get("process") and self.proc_running(preset["process"]))
        return night_mult(self.set["night_strength"]) if (monitor_id in self.night_mons and not game) else (1.0, 1.0, 1.0)

    def apply_display(self, monitor_id, values, mult=(1.0, 1.0, 1.0)):
        device = find_dev(monitor_id)
        if not device:
            return False
        with self.lock:
            return self.display.apply(device, values, mult)

    def sync(self, monitor_id=None):
        """A kijelzőt az aktuális állapotra (bekapcsolt preset + éjszakai mód) állítja."""
        all_applied = True
        for monitor in self.mons():
            if monitor_id is None or monitor["id"] == monitor_id:
                all_applied = self.apply_display(monitor["id"], *self.target(monitor["id"])) and all_applied
        self.fx_wake.set()
        self.notify()
        return all_applied

    def preview(self, monitor_id, values, gain=(100, 100, 100)):
        """Panel: élő előnézet mentés nélkül; a gain az R/G/B erősítés százalékban. Az éjszakai mód rajta marad,
        ha az adott monitoron be van kapcsolva (különben a csúszka mozdítása kikapcsolni látszana)."""
        return self.apply_display(monitor_id, values, tuple(night_gain * percent / 100.0 for night_gain, percent in zip(self.night_factor(monitor_id), gain)))

    def show_neutral(self, monitor_id):
        return self.apply_display(monitor_id, NEUTRAL)

    # -- kapcsolók
    def set_active(self, monitor_id, name, enabled):
        with self.lock:
            preset = self.preset(monitor_id, name)
            if preset is None:
                return
            running = bool(preset.get("process") and self.proc_running(preset["process"]))
            changed = True
            if enabled:
                self.active[monitor_id] = name
                self.prev.pop(monitor_id, None)                       # kézi választás: a kilépés már nem ír felül
                self.manual_off.discard((monitor_id, name))
                # ha a játék épp fut, a játék kilépése kikapcsolja; ha nem fut, a preset kézi marad
                (self.auto.add if running else self.auto.discard)((monitor_id, name))
            elif self.active.get(monitor_id) == name:
                self.active.pop(monitor_id)
                self.auto.discard((monitor_id, name))
                if running:
                    self.manual_off.add((monitor_id, name))           # a játék fut: a figyelő ne kapcsolja vissza
            else:
                changed = False
            self.sync(monitor_id)
            if changed:
                self.toast(self.label(monitor_id, name) + ("" if enabled else " – kikapcsolva"), monitor_id)

    def toggle_preset(self, monitor_id, name):
        self.set_active(monitor_id, name, self.active.get(monitor_id) != name)

    # -- képernyő-értesítés (a GUI jeleníti meg, a játék fölött is)
    def toast(self, text, monitor_id=None):
        if self.set.get("toast", True) and not self.panel_open:
            self.toast_cb(text, monitor_id)

    def label(self, monitor_id, name):
        variant_name = self.cur_variant(monitor_id, name)
        return name + (f" – {variant_name}" if variant_name else "")

    # -- változatok: egy presetnek (alkalmazásnak) több csúszkaállása lehet, pl. pályánként
    def cur_variant(self, monitor_id, name):
        """A preset éppen érvényes változata (None, ha a presetnek nincsenek változatai)."""
        names = list((self.preset(monitor_id, name) or {}).get("variants") or {})
        variant_name = self.variant.get((monitor_id, name))
        return variant_name if variant_name in names else (names[0] if names else None)

    def select_variant(self, monitor_id, name, vname):
        """Gyorsgomb: a változat kiválasztása; ha a preset nem volt bekapcsolva, be is kapcsol."""
        with self.lock:
            if vname not in ((self.preset(monitor_id, name) or {}).get("variants") or {}):
                return
            self.variant[(monitor_id, name)] = vname
            if self.active.get(monitor_id) != name:
                self.set_active(monitor_id, name, True)               # ez maga is jelez
            else:
                self.sync(monitor_id)
                self.toast(self.label(monitor_id, name), monitor_id)
        self.say(f"{(self.mon(monitor_id) or {}).get('name', monitor_id)}: '{name}' – {vname}")

    def cycle_variant(self, monitor_id, name):
        """Egy gomb a preset változatai között: a következőre lép; ha a preset ki volt kapcsolva, a mostanival bekapcsol."""
        with self.lock:
            names = list((self.preset(monitor_id, name) or {}).get("variants") or {})
            if not names:
                return
            if self.active.get(monitor_id) != name:
                self.set_active(monitor_id, name, True)
            else:
                self.variant[(monitor_id, name)] = names[(names.index(self.cur_variant(monitor_id, name)) + 1) % len(names)]
                self.sync(monitor_id)
                self.toast(self.label(monitor_id, name), monitor_id)
        self.say(f"{(self.mon(monitor_id) or {}).get('name', monitor_id)}: '{name}' – {self.cur_variant(monitor_id, name)}")

    def cycle_active(self):
        """A globális léptető gomb: minden monitoron a most aktív preset következő változatára lép
        (csak azon, amelyiknek vannak változatai); ha nincs ilyen, jelzi."""
        with self.lock:
            targets = [(monitor["id"], self.active[monitor["id"]]) for monitor in self.mons()
                       if monitor["id"] in self.active and (self.preset(monitor["id"], self.active[monitor["id"]]) or {}).get("variants")]
        if not targets:
            self.toast("Nincs aktív preset változatokkal")
            return
        for monitor_id, name in targets:
            self.cycle_variant(monitor_id, name)

    # -- játék-overlay: az aktuális játék profiljának szerkesztése a játék fölött
    def overlay_target(self, fg_mid=None):
        """(monitor, preset), amit az overlay szerkeszt: az előtérben lévő ablak monitorja, ha ott van aktív preset;
        különben az első monitor, amelyiken van. None, ha sehol nincs aktív preset."""
        with self.lock:
            if fg_mid in self.active and self.preset(fg_mid, self.active[fg_mid]) is not None:
                return fg_mid, self.active[fg_mid]
            return next(((monitor["id"], self.active[monitor["id"]]) for monitor in self.mons()
                         if monitor["id"] in self.active and self.preset(monitor["id"], self.active[monitor["id"]]) is not None), None)

    @staticmethod
    def _values(values, gain):
        gamma, contrast, brightness, vibrance = values
        return {"gamma": gamma, "contrast": contrast, "brightness": brightness, "vibrance": vibrance, "gain": [int(channel) for channel in gain]}

    def save_values(self, monitor_id, name, values, gain):
        """Az érvényes változatba (változat nélküli presetnél a felső szintre) menti a képértékeket; vals = (gamma
        belső skálán, kontraszt, fényerő, vibrance), gain = R/G/B százalék. A preset többi mezőjéhez nem nyúl."""
        with self.lock:
            preset = self.preset(monitor_id, name)
            if preset is None:
                return
            target = preset["variants"][self.cur_variant(monitor_id, name)] if preset.get("variants") else preset
            target.update(self._values(values, gain))
            mirror_first(preset)
            self.save_config()

    def add_variant(self, monitor_id, name, values, gain):
        """Új változat a megadott értékekből, automatikus névvel („Változat N", N ≥ 2); a visszaadott név lesz az érvényes.
        Ha a presetnek még nem volt változata, az eddigi értékek „Alap" néven az első változattá válnak."""
        with self.lock:
            preset = self.preset(monitor_id, name)
            if not preset.get("variants"):
                preset["variants"] = {"Alap": {"gamma": preset["gamma"], "contrast": preset["contrast"], "brightness": preset["brightness"],
                                          "vibrance": preset.get("vibrance", 50), "gain": pgain(preset)}}
            new_name = next(f"Változat {number}" for number in range(2, len(preset["variants"]) + 3) if f"Változat {number}" not in preset["variants"])
            preset["variants"][new_name] = self._values(values, gain)
            self.variant[(monitor_id, name)] = new_name
            self.save_config()
            return new_name

    def toggle_night(self, monitor_id=None):
        """Éjszakai mód: mid megadva -> csak az a monitor; nélküle (gyorsgomb/tálca "mind") -> ha bárhol be van
        kapcsolva, mindenhol ki, különben minden jelenlegi monitoron be."""
        with self.lock:
            if monitor_id is not None:
                targets, turned_on = [monitor_id], monitor_id not in self.night_mons
                label = (self.mon(monitor_id) or {}).get("name", monitor_id)
            else:
                targets = [monitor["id"] for monitor in self.mons()]
                turned_on, label = not self.night_mons, "minden monitor"
            for target_id in targets:
                (self.night_mons.add if turned_on else self.night_mons.discard)(target_id)
            if not turned_on and monitor_id is None:
                self.night_mons.clear()
            self.sync()
        text = f"Éjszakai mód: {label} – " + ("be" if turned_on else "ki")
        self.toast(text, monitor_id)
        self.say(text)

    def set_night_strength(self, strength):
        self.set["night_strength"] = int(strength)
        if self.night_mons:
            self.sync()

    def neutral_all(self):
        with self.lock:
            for monitor_id, name in list(self.active.items()):
                preset = self.preset(monitor_id, name)
                if preset and preset.get("process") and self.proc_running(preset["process"]):
                    self.manual_off.add((monitor_id, name))
            self.active.clear()
            self.auto.clear()
            self.prev.clear()
            self.night_mons.clear()
            self.sync()
        self.toast("Semleges kép")
        self.say("Semleges kép")

    def hotkey_map(self):
        hotkeys = {}
        for monitor in self.mons():
            for name, preset in monitor["presets"].items():
                if preset.get("hotkey"):
                    hotkeys[f"p|{monitor['id']}|{name}"] = preset["hotkey"]
                for variant_name, variant in (preset.get("variants") or {}).items():
                    if variant.get("hotkey"):
                        hotkeys[f"v|{monitor['id']}|{name}|{variant_name}"] = variant["hotkey"]
        if self.set.get("cycle_hotkey"):
            hotkeys["cycle"] = self.set["cycle_hotkey"]
        if self.set.get("overlay_hotkey"):
            hotkeys["overlay"] = self.set["overlay_hotkey"]
        if self.set.get("menu_hotkey"):
            hotkeys["menu"] = self.set["menu_hotkey"]
        if self.set.get("map_hotkey"):
            hotkeys["map"] = self.set["map_hotkey"]
        if self.set.get("map_interact_hotkey"):
            hotkeys["map_interact"] = self.set["map_interact_hotkey"]
        if self.set.get("night_hotkey"):
            hotkeys["night"] = self.set["night_hotkey"]
        if self.set.get("neutral_hotkey"):
            hotkeys["neutral"] = self.set["neutral_hotkey"]
        return hotkeys

    def run_action(self, action):
        if action == "night":
            self.toggle_night()
        elif action == "neutral":
            self.neutral_all()
        elif action.startswith("v|"):
            _, monitor_id, name, vname = action.split("|", 3)
            self.select_variant(monitor_id, name, vname)
        elif action == "cycle":
            self.cycle_active()
        elif action.startswith("p|"):
            _, monitor_id, name = action.split("|", 2)
            self.toggle_preset(monitor_id, name)

    # -- játékfigyelő
    POLL_SECONDS = 1.0 if sys.platform == "win32" else 2.0     # lekérdezéses módban ennyi másodpercenként fut a figyelő
    RESYNC_SECONDS = 5.0                                       # eseménymódban legfeljebb ennyi másodpercenként olvassa újra az összes futó programot
    START_DELAYS = (1.5, 4.0)                                  # a játék indulása utáni ellenőrzések késleltetése: a játék ekkor nullázhatja a görbét

    def watch_interval(self):
        """A figyelő-ciklus várakozása mindkét módban `POLL_SECONDS`: eseménymódban is ennyi időnként fut az `enforce`
        és derül ki egy csendesen elromlott eseményforrás. A teljes pillanatkép ritkább, a `running_t` időbélyeg
        alapján a `watch_tick` kapuzza (`RESYNC_SECONDS`)."""
        return self.POLL_SECONDS

    def watch_loop(self, start_events=None):
        """A figyelő-szál törzse. A `start_events(on_event, on_lost)` eseményforrást ad (van `stop()`-ja) vagy None-t;
        az indítás is ebben a szálban fut, hogy ne tartsa fel a felületet."""
        if start_events:
            why = "nincs emelt jog vagy az eseményforrás nem elérhető"
            try:
                self.events = start_events(self.proc_event, self._events_lost)
                if self.events:
                    self.refresh_running()                     # induló pillanatkép, ehhez adnak hozzá az események
                    self.event_mode = True
                    self.say("Játékfigyelő: események")
            except Exception as error:                             # a forrás hibája nem ölheti meg a figyelőt: marad a lekérdezés
                why = f"az eseményforrás hibázott: {error.__class__.__name__}: {error}"
                if self.events:
                    try:
                        self.events.stop()
                    except Exception:
                        pass
                    self.events = None
            if not self.event_mode:
                self.say(f"Játékfigyelő: lekérdezés ({why})")
        while not self.stop:
            try:
                self.watch_tick()
            except Exception as error:
                self.say(f"Figyelő hiba: {error}")
            self.watch_wake.wait(self.watch_interval())
            self.watch_wake.clear()

    def _events_lost(self):
        """Az eseményfolyam megszakadt: vissza a lekérdezésre, a következő tick újraolvassa a futó programokat."""
        self.event_mode = False
        self.running_t = 0.0
        self.watch_wake.set()
        self.say("Játékfigyelő: az eseményfolyam megszakadt, lekérdezés")

    def after_game_start(self):
        """A játék a képernyőmódja felvételekor gyakran nullázza a görbét: késleltetve újra ellenőrzünk."""
        for delay in self.START_DELAYS:
            timer = threading.Timer(delay, self.reapply, args=("start",))
            timer.daemon = True
            timer.start()

    def watch_tick(self):
        """A figyelő egy köre: friss futó-program lista, monitor-ellenőrzés, majd monitoronként a játék-automatika."""
        if not self.event_mode or time.time() - self.running_t > self.RESYNC_SECONDS:
            self.refresh_running()
        if time.time() - self.monitors_t > self.MONITOR_POLL:
            self.refresh_monitors()
        for monitor in self.mons():
            self._watch_monitor(monitor)

    def _watch_monitor(self, monitor):
        monitor_id = monitor["id"]
        self._forget_finished_manual_off(monitor_id)
        hit = next(((preset_name, preset) for preset_name, preset in monitor["presets"].items()
                    if preset.get("process") and self.proc_running(preset["process"]) and (monitor_id, preset_name) not in self.manual_off), None)
        current_name = self.active.get(monitor_id)
        if hit and current_name != hit[0]:
            self._game_started(monitor, hit[0], current_name)
        elif current_name and (monitor_id, current_name) in self.auto:
            self._game_maybe_ended(monitor, current_name)
        if not (self.panel_open or self.hold):
            self.enforce(monitor_id)

    def _forget_finished_manual_off(self, monitor_id):
        for key in [marked for marked in self.manual_off if marked[0] == monitor_id]:
            preset = self.preset(*key)
            if not (preset and self.proc_running(preset.get("process"))):
                self.manual_off.discard(key)                   # a játék kilépett: újra automatikus

    def _game_started(self, monitor, name, current_name):
        monitor_id = monitor["id"]
        with self.lock:
            if not (current_name and (monitor_id, current_name) in self.auto):          # másik játék átvételekor a korábbi alap marad
                if current_name:
                    self.prev[monitor_id] = current_name
                else:
                    self.prev.pop(monitor_id, None)
            self.active[monitor_id] = name
            self.variant.pop((monitor_id, name), None)                # a játék indulásakor az első változat
            self.auto.add((monitor_id, name))
            synced = self.sync(monitor_id)
        self.toast(self.label(monitor_id, name), monitor_id)
        self.say(f"{monitor['name']}: '{name}' bekapcsolt (játék elindult){'' if synced else ' – nem sikerült'}")
        self.after_game_start()

    def _game_maybe_ended(self, monitor, current_name):
        monitor_id = monitor["id"]
        preset = self.preset(monitor_id, current_name)
        if preset and preset.get("process") and self.proc_running(preset["process"]):
            return
        with self.lock:
            self.active.pop(monitor_id, None)
            self.auto.discard((monitor_id, current_name))
            back = self.prev.pop(monitor_id, None)
            if back and self.preset(monitor_id, back) is not None:
                self.active[monitor_id] = back                        # a játék előtti alap, nem a semleges kép
            self.sync(monitor_id)
        self.say(f"{monitor['name']}: '{current_name}' kikapcsolt (a játék kilépett)"
                 + (f", vissza: '{back}'" if self.active.get(monitor_id) == back and back else ""))

    def enforce(self, monitor_id, why="felülírta a játék/driver"):
        """A játék vagy a driver nullázhatja a görbét: ha eltér a kívánttól, visszaállítjuk."""
        values, mult = self.target(monitor_id)
        if values == NEUTRAL and mult == (1.0, 1.0, 1.0):
            return                                             # semleges állapotban nem nyúlunk bele
        device = find_dev(monitor_id)
        if not device:
            return
        if self.display.drifted(device, values, mult):
            self.apply_display(monitor_id, values, mult)
            self.say(f"{self.mon(monitor_id)['name']}: a beállítást visszaállítottam ({why})")
            return True
        return False

    # -- rendszeresemények: ébredés, kijelzőváltás, feloldás (hw.SystemEvents hívja)
    MONITOR_POLL = 6.0                                         # ennyi másodpercenként ellenőrzi a figyelő a csatlakoztatott monitorokat
    EVENT_DELAYS = {"resume": (2.0, 6.0, 15.0), "display": (1.0, 4.0), "unlock": (1.5, 5.0)}
    EVENT_TEXT = {"resume": "ébredés után", "display": "kijelzőváltás után", "unlock": "a munkamenet feloldása után",
                  "start": "a játék indulása után"}

    def system_event(self, kind):
        """A driver ilyenkor gyakran nullázza a gamma-görbét vagy a vibrance-t, de a monitor még nem biztos, hogy kész:
        ezért néhány késleltetéssel újra ellenőrzünk (ami rendben van, ahhoz nem nyúlunk, így nincs villanás)."""
        for delay in self.EVENT_DELAYS.get(kind, (2.0,)):
            timer = threading.Timer(delay, self._after_event, args=(kind,))
            timer.daemon = True
            timer.start()

    def _after_event(self, kind):
        if self.stop:
            return
        try:
            self.refresh_monitors()                              # monitor ki-/becsatlakoztatása is kijelzőváltás
        except Exception as error:
            self.say(f"Monitor-detektálás hiba ({error.__class__.__name__})")
        self.reapply(kind)

    def reapply(self, kind):
        if self.stop or self.hold or self.panel_open:         # a panel előnézete / az összehasonlítás nem bántható
            return
        with self.lock:
            if time.time() - self.reapplied_t < 0.4:          # a közeli események egyszeri ellenőrzést kapnak
                return
            self.reapplied_t = time.time()
            for monitor in self.mons():
                try:
                    self.enforce(monitor["id"], self.EVENT_TEXT.get(kind, kind))
                except Exception as error:
                    self.say(f"Visszaállítás hiba ({error.__class__.__name__})")

    # -- mellékhatások: energiaprofil, RGB (külön szálban, mert lassú lehet)
    def desired_fx(self):
        power, rgb = None, None
        for monitor in self.mons():
            preset = self.preset(monitor["id"], self.active.get(monitor["id"])) if monitor["id"] in self.active else None
            if preset:
                power = power or preset.get("power") or None
                if not rgb and preset.get("rgb", {}).get("mode", "none") != "none":
                    rgb = preset["rgb"]
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
                except Exception as error:
                    self.rgb_applied = dict(rgb)               # ne próbálkozzon végtelenül
                    self.say(f"RGB: nem sikerült ({error.__class__.__name__}). Fut az OpenRGB szolgáltatás?")
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
            except Exception as error:
                self.say(f"Profil: hiba ({error})")

    def shutdown(self):
        self.stop = True
        self.watch_wake.set()
        if self.events:
            try:
                self.events.stop()
            except Exception:
                pass
        with self.lock:
            self.active.clear()
            self.night_mons.clear()
            for monitor in self.mons():
                self.apply_display(monitor["id"], NEUTRAL)
        try:
            self.fx_once()
        except Exception:
            pass
        self.fx_wake.set()
