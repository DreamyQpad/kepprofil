"""assets\\icon.ico előállítása (a tálcaikonnal azonos rajz, szögletes). Futtatás: python make_icon.py"""
from pathlib import Path

from gui_tray import make_icon

out = Path(__file__).parent / "assets" / "icon.ico"
out.parent.mkdir(exist_ok=True)
make_icon(False, 256).save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("mentve:", out)
