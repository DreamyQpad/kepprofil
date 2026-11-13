"""A toast helye monitor nélkül: az aktív képernyő, nem a teljes (több monitoros) asztal."""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import hw_linux  # noqa: E402

OUTPUTS = [
    {"name": "eDP-2", "enabled": True, "pos": {"x": 0, "y": 0}, "size": {"width": 1920, "height": 1080}},
    {"name": "HDMI-A-1", "enabled": True, "pos": {"x": 1920, "y": 0}, "size": {"width": 1920, "height": 1080}},
]


def fake_run(qdbus6=None, qdbus=None, timeout_on=()):
    """A hw_linux.run helyettese: kscreen-doctor JSON-t, qdbus6/qdbus választ ad. A válasz (rc, stdout) vagy None
    (nincs ilyen eszköz); a timeout_on-ban felsorolt eszköz időtúllépést (None) ad."""
    calls = []

    def run(*cmd, timeout=15):
        calls.append(cmd[0])
        if cmd[0] == "kscreen-doctor":
            return SimpleNamespace(returncode=0, stdout=json.dumps({"outputs": OUTPUTS}))
        if cmd[0] in timeout_on:
            return None
        rc_out = {"qdbus6": qdbus6, "qdbus": qdbus}[cmd[0]]
        return SimpleNamespace(returncode=rc_out[0], stdout=rc_out[1]) if rc_out else None

    run.calls = calls
    return run


class MonitorRectTest(unittest.TestCase):
    def rect(self, mid, run, installed=("qdbus6", "qdbus")):
        with mock.patch.object(hw_linux, "run", run), \
             mock.patch.object(hw_linux.shutil, "which", lambda t: t if t in installed else None), \
             mock.patch.object(hw_linux, "list_monitors", return_value=[{"id": "SAM777F", "dev": "HDMI-A-1"}]):
            return hw_linux.monitor_rect(mid)

    def test_monitor_nelkul_az_aktiv_kepernyo_sorveggel(self):
        self.assertEqual(self.rect(None, fake_run(qdbus6=(0, "HDMI-A-1\n"))), (1920, 0, 3840, 1080))
        self.assertEqual(self.rect(None, fake_run(qdbus6=(0, "eDP-2\n"))), (0, 0, 1920, 1080))

    def test_qdbus6_hiba_utan_qdbus(self):
        self.assertEqual(self.rect(None, fake_run(qdbus6=(2, ""), qdbus=(0, "eDP-2\n"))), (0, 0, 1920, 1080))

    def test_hianyzo_qdbus6_utan_qdbus(self):
        run = fake_run(qdbus=(0, "eDP-2\n"))
        self.assertEqual(self.rect(None, run, installed=("qdbus",)), (0, 0, 1920, 1080))
        self.assertNotIn("qdbus6", run.calls)

    def test_nincs_eszkoz_vagy_ismeretlen_kimenet_none(self):
        self.assertIsNone(self.rect(None, fake_run(), installed=()))
        self.assertIsNone(self.rect(None, fake_run(qdbus6=(0, "DP-9\n"))))

    def test_idotullepes_utan_nem_probalja_a_masodik_eszkozt(self):
        run = fake_run(qdbus6=(0, "x"), qdbus=(0, "eDP-2\n"), timeout_on=("qdbus6",))
        self.assertIsNone(self.rect(None, run))
        self.assertNotIn("qdbus", run.calls)

    def test_leválasztott_monitor_az_aktiv_kepernyore_esik(self):
        self.assertEqual(self.rect("NINCS123", fake_run(qdbus6=(0, "eDP-2\n"))), (0, 0, 1920, 1080))

    def test_megadott_monitor_marad(self):
        self.assertEqual(self.rect("SAM777F", fake_run(qdbus6=(0, "eDP-2\n"))), (1920, 0, 3840, 1080))


if __name__ == "__main__":
    unittest.main()
