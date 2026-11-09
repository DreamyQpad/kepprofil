"""Képprofil: játékonkénti kijelző-presetek (gamma / kontraszt / fényerő / vibrance) tálcás programként.

Belépési pont. A modulok: consts (útvonalak), hw (Windows/hardver), config (presetek), engine (motor),
system (rendszer-segédek), gui (felület).

- tálcaikon: kattintható presetek, éjszakai mód, semleges kép
- globális gyorsgombok (presetenként, éjszakai módhoz, semleges képhez)
- játékfigyelő: ha elindul egy preset "process" mezőjében megadott program, bekapcsol; kilépéskor kikapcsol
- profil: a preset bekapcsolásakor energiaprofil és RGB-szín (OpenRGB) is váltható
- panel: csúszkák, összehasonlítás (nyomva tartva a semleges kép látszik), éjszakai mód, beállítások
- ébredés / kijelzőváltás után azonnal visszaállítja a képet (SystemEvents)
"""
import sys


def main():
    from gui import run_app
    run_app("--tray" in sys.argv)


if __name__ == "__main__":
    main()
