"""Platformfüggetlen hardver-segédek: OpenRGB-vezérlés és gyorsgomb-szöveg értelmezése."""
import re

from consts import APP_NAME


class Rgb:
    """Az OpenRGB SDK-szerveren (alapból 127.0.0.1:6742) át állítja a világítást."""

    def __init__(self):
        self.client = None

    def _conn(self):
        if self.client is None:
            from openrgb import OpenRGBClient
            self.client = OpenRGBClient(address="127.0.0.1", port=6742, name=APP_NAME)
        return self.client

    def snapshot(self):
        """Az összes eszköz jelenlegi módja és színei (a szolgáltatásként futó OpenRGB nem ment profilt SDK-n át)."""
        try:
            snap = []
            for device in self._conn().devices:
                mode = device.modes[device.active_mode]
                snap.append({"name": device.name, "mode": device.active_mode,
                             "colors": [[color.red, color.green, color.blue] for color in device.colors],          # LED-ek (Direct módban)
                             "mode_colors": [[color.red, color.green, color.blue] for color in (mode.colors or [])],
                             "brightness": mode.brightness, "speed": mode.speed, "direction": mode.direction})
            return snap
        except Exception:
            self.client = None
            raise

    def apply(self, spec):
        """spec: {"mode": "none|off|color|profile|snapshot", "value": "#rrggbb" | profilnév | pillanatkép}.
        Hibánál kivételt dob."""
        mode, value = spec.get("mode", "none"), spec.get("value", "")
        if mode == "none":
            return
        try:
            connection = self._conn()
            if mode == "off":
                connection.clear()
            elif mode == "snapshot" and value:
                from openrgb.utils import RGBColor
                from openrgb.utils import ModeColors
                for device, state in zip(connection.devices, value):
                    if device.name != state["name"] or state["mode"] >= len(device.modes):
                        continue
                    device_mode = device.modes[state["mode"]]
                    if state.get("mode_colors"):
                        device_mode.colors = [RGBColor(*rgb) for rgb in state["mode_colors"]]
                    for attr in ("brightness", "speed", "direction"):
                        if state.get(attr) is not None and getattr(device_mode, attr) is not None:
                            setattr(device_mode, attr, state[attr])
                    device.set_mode(device_mode)
                    if device_mode.color_mode == ModeColors.PER_LED:
                        device.set_colors([RGBColor(*rgb) for rgb in state["colors"]])
            elif mode == "profile" and value:
                connection.load_profile(value)
            elif mode == "color":
                from openrgb.utils import RGBColor
                col = RGBColor(int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))
                for device in connection.devices:
                    mode_names = {device_mode.name.lower(): device_mode.name for device_mode in device.modes}
                    for want in ("direct", "static", "custom"):
                        if want in mode_names:
                            device.set_mode(mode_names[want])
                            break
                    device.set_color(col)
        except Exception:
            self.client = None
            raise


# Az overlay gombjai: művelet -> (módosítók, virtuális billentyűkód, ismétlődhet-e a nyomva tartott gomb). Csak a panel
# nyitva tartása alatt vannak lefoglalva; módosító nélküliek is lehetnek, ezért nem a parse_hotkey-n mennek át.
OVERLAY_KEYS = {"ov|up": (0, 0x26, True), "ov|down": (0, 0x28, True),
                "ov|left": (0, 0x25, True), "ov|right": (0, 0x27, True),
                "ov|sleft": (0x4, 0x25, True), "ov|sright": (0x4, 0x27, True),
                "ov|reset": (0, 0x2E, False), "ov|save": (0, 0x0D, False),
                "ov|new": (0, 0x4E, False), "ov|close": (0, 0x1B, False)}

MODS = {"ctrl": 0x2, "alt": 0x1, "shift": 0x4}
NAMED_KEYS = {"esc": 0x1B, "space": 0x20, "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
              "pageup": 0x21, "pagedown": 0x22, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
              "pause": 0x13}


def parse_hotkey(text):
    """'Ctrl+Alt+1' -> (módosítók, vk) vagy None, ha hibás."""
    parts = [part.strip().lower() for part in (text or "").split("+") if part.strip()]
    if not parts:
        return None
    key, mods = parts[-1], 0
    for part in parts[:-1]:
        if part not in MODS:
            return None
        mods |= MODS[part]
    if re.fullmatch(r"[a-z0-9]", key):
        virtual_key = ord(key.upper())
    elif re.fullmatch(r"f(\d{1,2})", key) and 1 <= int(key[1:]) <= 24:
        virtual_key = 0x6F + int(key[1:])
    elif re.fullmatch(r"num[0-9]", key):
        virtual_key = 0x60 + int(key[3])
    elif key in NAMED_KEYS:
        virtual_key = NAMED_KEYS[key]
    else:
        return None
    if not mods and not (0x70 <= virtual_key <= 0x87):          # módosító nélkül csak F-billentyű
        return None
    return mods, virtual_key




def parse_action(text):
    """Parancssori akció -> a motor belső akció-azonosítója (`Engine.run_action`), vagy None, ha hibás.

    night | neutral | cycle | preset:<monitor>:<név> | variant:<monitor>:<név>:<változat>; a cycle az aktív játék(ok)
    következő változatára lép. A belső alak (`p|…`, `v|…`) is elfogadott. A név ne tartalmazzon kettőspontot."""
    text = (text or "").strip()
    if text in ("night", "neutral", "cycle"):
        return text
    if text[:2] in ("p|", "v|"):
        need = {"p": 3, "v": 4}[text[0]]
        return text if len(text.split("|")) == need and all(text.split("|")) else None
    kind, _, rest = text.partition(":")
    parts = rest.split(":")
    need = {"preset": 2, "variant": 3}.get(kind)
    if need is None or len(parts) != need or not all(parts):
        return None
    return "|".join([{"preset": "p", "variant": "v"}[kind], *parts])


def build_action(kind, *parts):
    """A `parse_action` ellentettje: preset | variant + részek -> parancssori akció (None, ha a nevek nem férnek bele)."""
    if any(not part or "|" in part for part in parts):
        return None
    if any(":" in part for part in parts):                                 # a kettőspontos nevekhez a belső alak való
        return "|".join([{"preset": "p", "variant": "v"}[kind], *parts])
    return ":".join([kind, *parts])
