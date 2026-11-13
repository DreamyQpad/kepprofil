"""Tesztsegédek: stubolt kijelzővel és tárolással épített motor (a valódi presets.json/log.txt-hez nem nyúl)."""
import copy
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import engine as engine_mod                     # noqa: E402
from config import DEFAULT_SETTINGS             # noqa: E402


def default_cfg():
    return {"monitors": [{"id": "MON1", "name": "Monitor 1", "presets": {
        "Alap": {"gamma": 2.2, "contrast": 50, "brightness": 50, "vibrance": 50, "process": ""},
        "Játék": {"gamma": 2.2, "contrast": 55, "brightness": 45, "vibrance": 60, "process": "game",
                  "hotkey": "ctrl+alt+1"}}}]}


class StubDisplay:
    """A Display felülete; rögzíti, mit állítottak be."""
    vibrance_ok = True

    def __init__(self):
        self.calls = []

    def apply(self, dev, vals, mult=(1.0, 1.0, 1.0)):
        self.calls.append((dev, tuple(vals), tuple(mult)))
        return True

    def drifted(self, dev, vals, mult=(1.0, 1.0, 1.0)):
        return False


def make_engine(test, cfg=None, settings=None, active=("MON1", "Játék"), plugged=None):
    """(Engine, StubDisplay). A patch-ek a teszt végén (addCleanup) megszűnnek. `active`: induláskor bekapcsolt (monitor, preset).
    `plugged`: a csatlakoztatott monitorok azonosítói (módosítható lista, a teszt ki-/becsatlakoztathat); alapból a cfg összes monitora."""
    cfg = copy.deepcopy(cfg or default_cfg())
    test.plugged = [m["id"] for m in cfg["monitors"]] if plugged is None else plugged
    sett = copy.deepcopy(DEFAULT_SETTINGS)
    sett.update(settings or {})
    display = StubDisplay()
    for target, repl in (("load_config", lambda: cfg), ("load_settings", lambda: sett), ("Display", lambda: display),
                         ("Rgb", lambda: object()), ("find_dev", lambda mid: "DEV_" + mid),
                         ("list_monitors", lambda: [{"id": i, "dev": "DEV_" + i} for i in test.plugged]), ("write_log", lambda text: None)):
        mock.patch.object(engine_mod, target, repl).start()
    mock.patch.object(engine_mod.Engine, "refresh_running", lambda self: None).start()
    test.addCleanup(mock.patch.stopall)
    eng = engine_mod.Engine()
    eng.saves = {"config": 0, "settings": 0}
    eng.save_config = lambda: eng.saves.__setitem__("config", eng.saves["config"] + 1)
    eng.save_settings = lambda: eng.saves.__setitem__("settings", eng.saves["settings"] + 1)
    eng.toasts = []
    eng.toast_cb = lambda text, mid: eng.toasts.append(text)
    if active:
        eng.active[active[0]] = active[1]
    return eng, display
