"""Az overlay megjelenítője: nem aktiválódó, legfelső ablak, helyes tartalom."""
import sys
import time
import tkinter as tk
import unittest

from overlay import OverlayModel, OverlayView
from tests.stubs import make_engine

WIN = sys.platform == "win32"
if WIN:
    from hw_windows import user32

RECT = (0, 0, 1920, 1080)


def texts(widget):
    out = []
    try:
        t = widget.cget("text")
        if t:
            out.append(str(t))
    except tk.TclError:
        pass
    for child in widget.winfo_children():
        out.extend(texts(child))
    return out


def pump(root, seconds=0.3):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.02)


@unittest.skipUnless(WIN, "Windows-ablakstílusok")
class View(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        eng, _ = make_engine(self)
        self.model = OverlayModel(eng, "MON1", "Játék")
        self.view = OverlayView(self.root)
        self.addCleanup(self.view.close)

    def test_show_does_not_take_foreground(self):
        before = user32.GetForegroundWindow()
        self.view.show(RECT, self.model)
        pump(self.root)
        self.model.adjust(3)
        self.view.update(self.model)
        pump(self.root)
        self.assertEqual(user32.GetForegroundWindow(), before)
        self.assertNotEqual(user32.GetForegroundWindow(), self.view.hwnd)

    def test_window_has_noactivate_topmost_toolwindow_styles(self):
        self.view.show(RECT, self.model)
        pump(self.root)
        ex = user32.GetWindowLongW(self.view.hwnd, -20) & 0xFFFFFFFF
        for flag, name in ((0x08000000, "NOACTIVATE"), (0x8, "TOPMOST"), (0x80, "TOOLWINDOW"), (0x20, "TRANSPARENT")):
            self.assertTrue(ex & flag, name)

    def test_window_is_inside_rect_on_the_right_side(self):
        self.view.show(RECT, self.model)
        pump(self.root)
        w = self.view.window
        self.assertGreater(w.winfo_rootx(), RECT[2] // 2)
        self.assertLessEqual(w.winfo_rootx() + w.winfo_width(), RECT[2])
        self.assertTrue(RECT[1] <= w.winfo_rooty() and w.winfo_rooty() + w.winfo_height() <= RECT[3])

    def test_update_shows_selected_row_and_values(self):
        self.view.show(RECT, self.model)
        all_ = texts(self.view.window)
        self.assertIn("Játék", " ".join(all_))
        self.assertIn("1.00", all_)                              # gamma
        self.assertIn("55%", all_)                               # kontraszt
        self.assertEqual(all_.count("▶"), 1)
        self.model.adjust(2)
        self.model.move(1)
        self.view.update(self.model)
        all_ = texts(self.view.window)
        self.assertIn("47%", all_)                               # a fényerő a léptetés után
        self.assertEqual(all_.count("▶"), 1)

    def test_update_shows_dirty_and_warning(self):
        self.view.show(RECT, self.model)
        self.assertFalse(any("mentetlen" in t for t in texts(self.view.window)))
        self.model.adjust(1)
        self.view.update(self.model, warning="Nem működő gomb: ov|new")
        all_ = " ".join(texts(self.view.window))
        self.assertIn("mentetlen", all_)
        self.assertIn("Nem működő gomb: ov|new", all_)

    def test_hint_line_lists_the_keys(self):
        self.view.show(RECT, self.model)
        hint = " ".join(texts(self.view.window))
        for part in ("Enter", "Esc", "N", "Del"):
            self.assertIn(part, hint)

    def test_close_destroys_window(self):
        self.view.show(RECT, self.model)
        self.assertTrue(self.view.is_open)
        self.view.close()
        self.assertFalse(self.view.is_open)
        self.assertIsNone(self.view.hwnd)


if __name__ == "__main__":
    unittest.main()
