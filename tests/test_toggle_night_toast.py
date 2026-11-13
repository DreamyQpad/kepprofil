"""Az éjszakai mód toastja: monitoronkénti kapcsolásnál az adott monitort kapja, "mind"-nél nem."""
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import engine  # noqa: E402


def fake_engine():
    toasts = []
    e = SimpleNamespace(
        lock=threading.RLock(), night_mons=set(),
        cfg={"monitors": [{"id": "A", "name": "Bal"}, {"id": "B", "name": "Jobb"}]},
        sync=lambda *a: None, say=lambda t: None, toast=lambda text, mid=None: toasts.append((text, mid)),
    )
    e.mon = lambda mid: next((m for m in e.cfg["monitors"] if m["id"] == mid), None)
    e.mons = lambda: e.cfg["monitors"]
    return e, toasts


class ToggleNightToastTest(unittest.TestCase):
    def test_monitoronkenti_kapcsolas_a_monitorra_toastol(self):
        e, toasts = fake_engine()
        engine.Engine.toggle_night(e, "A")
        self.assertEqual(toasts, [("Éjszakai mód: Bal – be", "A")])

    def test_mind_nem_ad_monitort(self):
        e, toasts = fake_engine()
        engine.Engine.toggle_night(e, None)
        self.assertEqual(toasts, [("Éjszakai mód: minden monitor – be", None)])


if __name__ == "__main__":
    unittest.main()
