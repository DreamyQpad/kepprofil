"""Képprofil: játékonkénti kijelző-presetek (gamma / kontraszt / fényerő / vibrance) tálcás programként.

Belépési pont. A modulok: consts (útvonalak), hw (Windows/hardver), config (presetek), engine (motor),
system (rendszer-segédek), gui (felület).

- tálcaikon: kattintható presetek, éjszakai mód, semleges kép
- globális gyorsgombok (presetenként, éjszakai módhoz, semleges képhez)
- játékfigyelő: ha elindul egy preset "process" mezőjében megadott program, bekapcsol; kilépéskor kikapcsol
- profil: a preset bekapcsolásakor energiaprofil és RGB-szín (OpenRGB) is váltható
- panel: csúszkák, összehasonlítás (nyomva tartva a semleges kép látszik), éjszakai mód, beállítások
- ébredés / kijelzőváltás után azonnal visszaállítja a képet (SystemEvents)
- `--action <akció>`: parancs a már futó példánynak (Linuxon így köthető a KDE-gyorsbillentyűkhöz);
  akció: night | neutral | cycle | preset:<monitor>:<név> | variant:<monitor>:<név>:<változat>
"""
import sys


def send_action_cli(text):
    """`--action` kezelése: kilépési kód 0 = elküldve, 1 = nem fut a program, 2 = ismeretlen akció."""
    from hw_common import parse_action
    from system import send_action
    action = parse_action(text)
    if action is None:
        print(f"Ismeretlen akció: {text!r}", file=sys.stderr)
        return 2
    if not send_action(action):
        print("A Képprofil nem fut (vagy nem ezen a platformon érhető el az --action).", file=sys.stderr)
        return 1
    return 0


def main():
    if "--action" in sys.argv:
        i = sys.argv.index("--action")
        sys.exit(send_action_cli(sys.argv[i + 1] if i + 1 < len(sys.argv) else ""))
    from gui import run_app
    run_app("--tray" in sys.argv)


if __name__ == "__main__":
    main()
