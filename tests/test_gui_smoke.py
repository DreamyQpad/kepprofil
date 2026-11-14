"""Füstpróba a valódi `gui.run_app`-ra: a felület felépül, és a preset-/változat-/import-export műveletek, a toast és a
tálcamenü a stubolt motoron (hardver és tálcaikon nélkül) a várt eredményt adják. Nincs Tk-képernyő: a tesztet kihagyja."""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.stubs import make_engine

try:
    import customtkinter as ctk
    import tkinter
    import gui
    from tkinter import filedialog, messagebox
except ImportError:                                     # pragma: no cover - a környezetben nincs GUI-csomag
    ctk = None


class FakeHotkeys:
    failed = []

    def __init__(self, cb=None):
        self.map = {}

    def start(self):
        pass

    def set(self, m):
        self.map = dict(m)


class FakeSystemEvents:
    def __init__(self, cb=None):
        pass

    def start(self):
        pass


def walk(w):
    for c in w.winfo_children():
        yield c
        yield from walk(c)


def buttons(root, text):
    return [w for w in walk(root) if isinstance(w, ctk.CTkButton) and w.cget("text") == text]


@unittest.skipIf(ctk is None, "nincs customtkinter")
class GuiSmokeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.eng, display = make_engine(self, settings={"migrated": True})
        display.vibrance_state = lambda dev: (True, "")
        eng = self.eng

        def factory(notify=lambda: None):
            eng.notify = notify
            eng.fx_loop = lambda: None
            eng.watch_loop = lambda *a, **k: None
            return eng

        self.answers = []

        class FakeDialog:
            def __init__(s, text="", title=""):
                pass

            def get_input(s):
                return self_answers.pop(0)

        self_answers = self.answers
        self.confirm = True
        for obj, name, value in [
                (gui, "Engine", factory), (gui, "single_instance", lambda: (False, None)),
                (gui, "ensure_launcher", lambda: None), (gui, "auto_backup", lambda: None),
                (gui, "kill_old_watcher", lambda: None), (gui, "Hotkeys", FakeHotkeys),
                (gui, "SystemEvents", FakeSystemEvents), (gui, "power_plans", lambda: [("g1", "Nagy teljesítmény", "x")]),
                (gui, "find_dev", lambda mid: "DEV_" + mid), (gui, "monitor_rect", lambda mid: None),
                (gui, "foreground_monitor_id", lambda: None), (gui, "start_tray", lambda icon: None),
                (gui, "show_signaled", lambda *a: time.sleep(0.05)), (gui, "BACKUP_DIR", self.tmp),
                (ctk, "CTkInputDialog", FakeDialog),
                (messagebox, "askyesno", lambda *a, **k: self.confirm)]:
            mock.patch.object(obj, name, value).start()
        mock.patch("pystray.Icon").start()
        self.exc_hooks = (sys.excepthook, threading.excepthook)
        self.addCleanup(lambda: (setattr(sys, "excepthook", self.exc_hooks[0]),
                                 setattr(threading, "excepthook", self.exc_hooks[1])))

    def run_scenario(self, scenario):
        """A valódi run_app-ot indítja; a főciklus helyett a `scenario(root, H)` fut (H: gui.HOOK)."""
        error = []

        def fake_mainloop(root):
            try:
                root.update()
                scenario(root, gui.HOOK)
            except BaseException as e:                  # a főciklus helyett futunk: a kivételt a teszt dobja újra
                error.append(e)
            finally:
                self.eng.stop = True
                for job in root.tk.call("after", "info"):          # a függő időzítők ne fussanak a lebontott ablakra
                    root.after_cancel(job)
                root.destroy()

        with mock.patch.object(ctk.CTk, "mainloop", fake_mainloop):
            try:
                gui.run_app(True)
            except tkinter.TclError as e:               # nincs képernyő
                self.skipTest(f"nincs Tk-képernyő: {e}")
        if error:
            raise error[0]

    def presets(self):
        return list(self.eng.mon("MON1")["presets"])

    def status(self, H):
        return H["ui"]["status"].cget("text")

    def test_indulas_a_bekapcsolt_presetet_tolti(self):
        def sc(root, H):
            self.assertEqual(H["cur"]["mid"], "MON1")
            self.assertEqual(H["cur"]["name"], "Játék")
            self.assertEqual(H["ui"]["preset"].get(), "Játék")
            self.assertEqual(H["ui"]["proc"].get(), "game")
            self.assertEqual(H["ui"]["hotkey"].get(), "ctrl+alt+1")
            self.assertFalse(H["is_dirty"]())
        self.run_scenario(sc)

    def test_preset_uj_masolas_atnevezes_torles(self):
        eng = self.eng

        def sc(root, H):
            ui = H["ui"]
            self.answers[:] = ["Új1"]
            buttons(root, "Új…")[0].invoke()
            self.assertEqual(self.presets(), ["Alap", "Játék", "Új1"])
            self.assertEqual(H["cur"]["name"], "Új1")
            self.assertEqual(ui["preset"].get(), "Új1")
            self.assertEqual(eng.preset("MON1", "Új1")["process"], "game")
            self.assertIn("default", eng.preset("MON1", "Új1"))

            self.answers[:] = ["Új1 másolat"]
            H["pick_preset"]("Játék")
            buttons(root, "Másolás…")[0].invoke()
            cp = eng.preset("MON1", "Új1 másolat")
            self.assertEqual(cp["process"], "")
            self.assertNotIn("hotkey", cp)
            self.assertEqual(H["cur"]["name"], "Új1 másolat")

            eng.auto.add(("MON1", "Játék"))
            eng.variant[("MON1", "Játék")] = "x"
            H["pick_preset"]("Játék")
            self.answers[:] = ["Játék2"]
            ui["ren"].invoke()
            self.assertEqual(self.presets(), ["Alap", "Játék2", "Új1", "Új1 másolat"])
            self.assertEqual(eng.active["MON1"], "Játék2")
            self.assertIn(("MON1", "Játék2"), eng.auto)
            self.assertNotIn(("MON1", "Játék"), eng.auto)
            self.assertEqual(eng.variant[("MON1", "Játék2")], "x")
            self.assertEqual(H["cur"]["name"], "Játék2")
            self.assertEqual(ui["preset"].get(), "Játék2")
            self.assertIn("p|MON1|Játék2", H["hk"].map)

            H["pick_preset"]("Új1 másolat")
            ui["del"].invoke()
            self.assertEqual(self.presets(), ["Alap", "Játék2", "Új1"])
            self.assertEqual(H["cur"]["name"], "Játék2")                  # a bekapcsolt preset töltődik be
            self.assertEqual(self.status(H), "Törölve: Új1 másolat")

            self.confirm = False                                          # a törlés megerősítése nélkül marad
            H["pick_preset"]("Új1")
            ui["del"].invoke()
            self.assertIn("Új1", self.presets())
        self.run_scenario(sc)

    def test_nev_ellenorzes(self):
        def sc(root, H):
            for answer, text in (("a|b", "A névben nem lehet | jel."), ("Alap", "Ilyen nevű preset már van.")):
                self.answers[:] = [answer]
                buttons(root, "Új…")[0].invoke()
                self.assertEqual(self.status(H), text)
            self.answers[:] = ["   "]
            buttons(root, "Új…")[0].invoke()
            self.assertEqual(self.presets(), ["Alap", "Játék"])
        self.run_scenario(sc)

    def test_valtozat_uj_atnevezes_torles(self):
        eng = self.eng

        def sc(root, H):
            ui = H["ui"]
            H["pick_preset"]("Alap")
            self.answers[:] = ["Alap"]                                    # az első változat neve foglalt
            buttons(root, "Új…")[1].invoke()
            self.assertFalse(eng.preset("MON1", "Alap").get("variants"))
            self.answers[:] = ["Pálya1"]
            buttons(root, "Új…")[1].invoke()
            self.assertEqual(list(eng.preset("MON1", "Alap")["variants"]), ["Alap", "Pálya1"])
            self.assertEqual(H["cur"]["variant"], "Pálya1")
            self.assertEqual(ui["var"].get(), "Pálya1")

            self.answers[:] = ["Pálya2"]
            ui["vren"].invoke()
            self.assertEqual(list(eng.preset("MON1", "Alap")["variants"]), ["Alap", "Pálya2"])
            self.assertEqual(H["cur"]["variant"], "Pálya2")
            self.assertEqual(eng.variant[("MON1", "Alap")], "Pálya2")

            ui["vdel"].invoke()
            self.assertEqual(list(eng.preset("MON1", "Alap")["variants"]), ["Alap"])
            self.assertEqual(H["cur"]["variant"], "Alap")
            self.assertEqual(eng.variant[("MON1", "Alap")], "Alap")      # a megmaradt változat az érvényes
            self.assertEqual(self.status(H), "Törölve: Pálya2")
        self.run_scenario(sc)

    def test_mentes_a_csuszkak_ertekevel(self):
        eng = self.eng

        def sc(root, H):
            H["pick_preset"]("Alap")
            H["ui"]["b"][0].set(70)
            H["on_slider"]()
            self.assertTrue(H["is_dirty"]())
            H["save"]()
            self.assertEqual(eng.preset("MON1", "Alap")["brightness"], 70)
            self.assertFalse(H["is_dirty"]())
            self.assertEqual(eng.active["MON1"], "Alap")                  # mentéskor a preset be is kapcsol
            self.assertTrue(self.status(H).startswith("Mentve: Alap"))
        self.run_scenario(sc)

    def test_export_import(self):
        eng = self.eng
        path = self.tmp / "mentes.json"

        def sc(root, H):
            with mock.patch.object(filedialog, "asksaveasfilename", lambda **k: str(path)):
                buttons(root, "Exportálás…")[0].invoke()
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["kepprofil_backup"], 1)
            self.assertEqual(list(data["config"]["monitors"][0]["presets"]), ["Alap", "Játék"])
            self.assertTrue(self.status(H).startswith("Exportálva"))

            H["ui"]["del"].invoke()                                       # a bekapcsolt "Játék" törlése
            self.assertEqual(self.presets(), ["Alap"])
            with mock.patch.object(filedialog, "askopenfilename", lambda **k: str(path)):
                buttons(root, "Importálás…")[0].invoke()
            self.assertEqual(self.presets(), ["Alap", "Játék"])
            self.assertEqual(eng.active, {})
            self.assertEqual(H["cur"]["name"], "Alap")
            self.assertEqual(self.status(H), "Importálva: a presetek és beállítások betöltve.")
            self.assertTrue(any(f.name.endswith("-import-elott.json") for f in self.tmp.iterdir()))

            bad = self.tmp / "rossz.json"
            bad.write_text("[1, 2]", encoding="utf-8")
            with mock.patch.object(filedialog, "askopenfilename", lambda **k: str(bad)):
                buttons(root, "Importálás…")[0].invoke()
            self.assertEqual(self.status(H), "Ez a fájl nem Képprofil-mentés (vagy sérült), nem importáltam.")
            self.assertEqual(self.presets(), ["Alap", "Játék"])
        self.run_scenario(sc)

    def test_toast_es_talcamenu(self):
        import pystray

        def sc(root, H):
            before = {id(w) for w in walk(root) if isinstance(w, tkinter.Toplevel)}
            H["show_toast"]("Próba", "MON1")
            after = [w for w in walk(root) if isinstance(w, tkinter.Toplevel) and id(w) not in before]
            self.assertEqual(len(after), 1)
            H["show_toast"]("Második", "MON1")                            # az előző megszűnik, nem halmozódnak
            now = [w for w in walk(root) if isinstance(w, tkinter.Toplevel) and id(w) not in before]
            self.assertEqual(len(now), 1)

            menu = pystray.Icon.call_args[0][3]
            texts = [str(i.text) for i in menu.items if str(i.text)]
            self.assertIn("Panel megnyitása", texts)
            self.assertIn("Monitor 1", texts)
            self.assertIn("Alap", texts)
            self.assertIn("Játék   (ctrl+alt+1)", texts)
            self.assertIn("Éjszakai mód (minden monitor)", texts)
            self.assertEqual(texts[-1], "Kilépés")
        self.run_scenario(sc)


if __name__ == "__main__":
    unittest.main()
