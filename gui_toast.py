"""Képernyőn megjelenő értesítés (toast): kattintható-átlátszó, fókuszt nem lopó, mindig felül lévő felirat a monitor tetején,
a játék fölött is. Egyszerre egy látszik: az újabb leváltja az előzőt."""
import tkinter as tk

from hw import overlay_style

BACKGROUND = "#14161a"
TITLE_COLOR = "#7fb2ff"
TEXT_COLOR = "#ffffff"
MAX_ALPHA = 0.92
FADE_IN_STEPS = 5                  # ennyi lépés alatt tűnik elő
HOLD_END_STEP = 23                 # eddig a lépésig teljesen látszik, utána halványodik
FADE_IN_PER_STEP = 0.23
FADE_OUT_PER_STEP = 0.15
HOLD_FRAME_MS = 100                # a látszó szakasz lépéseinek ideje
FADE_FRAME_MS = 40                 # az elő- és eltűnés lépéseinek ideje
TOP_MARGIN_RATIO = 0.06            # a monitor tetejétől: a magasság hányadrésze


def alpha_at(step):
    """Az ablak áttetszősége az animáció `step`. lépésében (1-től számolva)."""
    if step < FADE_IN_STEPS:
        return min(MAX_ALPHA, step * FADE_IN_PER_STEP)
    if step < HOLD_END_STEP:
        return MAX_ALPHA
    return max(0.0, MAX_ALPHA - (step - HOLD_END_STEP) * FADE_OUT_PER_STEP)


def frame_delay_ms(step):
    return HOLD_FRAME_MS if FADE_IN_STEPS <= step < HOLD_END_STEP else FADE_FRAME_MS


class Toast:
    def __init__(self, root, rect_for):
        """`rect_for(monitor_id)`: a monitor (bal, felső, jobb, alsó) téglalapja, vagy None, ha nem ismert."""
        self.root = root
        self.rect_for = rect_for
        self.window = None
        self.job = None

    def show(self, text, monitor_id=None):
        """Kiírja a `text`-et a megadott monitor tetején (ismeretlen monitornál az elsődleges képernyőn)."""
        self._dismiss_previous()
        window = self._build_window(text)
        self.window = window
        self._place(window, monitor_id)
        window.deiconify()
        window.update_idletasks()
        try:                                                  # átkattintható, nem aktiválódik, nincs tálcagomb
            overlay_style(window)
        except Exception:
            pass
        self._fade(window, 1)

    def _dismiss_previous(self):
        if self.job:
            self.root.after_cancel(self.job)
        if self.window is not None:
            try:
                self.window.destroy()
            except Exception:
                pass

    def _build_window(self, text):
        window = tk.Toplevel(self.root)
        window.withdraw()
        window.overrideredirect(True)
        window.configure(bg=BACKGROUND)
        window.attributes("-topmost", True)
        window.attributes("-alpha", 0.0)
        tk.Label(window, text="KÉPPROFIL", fg=TITLE_COLOR, bg=BACKGROUND, font=("Segoe UI", 9, "bold")).pack(
            padx=28, pady=(12, 0))
        tk.Label(window, text=text, fg=TEXT_COLOR, bg=BACKGROUND, font=("Segoe UI", 20, "bold")).pack(
            padx=28, pady=(0, 14))
        window.update_idletasks()
        return window

    def _place(self, window, monitor_id):
        width, height = window.winfo_reqwidth(), window.winfo_reqheight()
        left, top, right, bottom = (self.rect_for(monitor_id)
                                    or (0, 0, window.winfo_screenwidth(), window.winfo_screenheight()))
        x = left + (right - left - width) // 2
        y = top + int((bottom - top) * TOP_MARGIN_RATIO)
        window.geometry(f"{width}x{height}+{x}+{y}")

    def _fade(self, window, step):
        if self.window is not window:                         # közben újabb toast jött
            return
        alpha = alpha_at(step)
        try:
            window.attributes("-alpha", alpha)
        except Exception:
            return
        if step > HOLD_END_STEP and alpha <= 0.0:
            window.destroy()
            self.window = None
            return
        self.job = self.root.after(frame_delay_ms(step), lambda: self._fade(window, step + 1))
