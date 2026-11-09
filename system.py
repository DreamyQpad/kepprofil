"""Platformválasztó: Windowson a system_windows, máshol a system_linux modul neveit adja tovább."""
import sys

if sys.platform == "win32":
    from system_windows import *  # noqa: F401,F403
else:
    from system_linux import *  # noqa: F401,F403
