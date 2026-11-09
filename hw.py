"""Platformválasztó: Windowson a hw_windows, máshol a hw_linux modul neveit adja tovább."""
import sys

if sys.platform == "win32":
    from hw_windows import *  # noqa: F401,F403
else:
    from hw_linux import *  # noqa: F401,F403
