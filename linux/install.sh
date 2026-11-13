#!/usr/bin/env bash
# Képprofil telepítése Linuxra (KDE Plasma Wayland; Arch-alapú rendszeren: CachyOS, Garuda, Arch).
#
#   ./install.sh            telepítés / frissítés (a beállításokhoz, presetekhez nem nyúl)
#   ./install.sh --deps     a hiányzó rendszercsomagokat is felrakja (sudo pacman -S --needed)
#
# Hova kerül: ~/.local/share/kepprofil/{app,venv}, indító parancs: ~/.local/bin/kepprofil.
# Az alkalmazásmenü-bejegyzést és az ikont a program az első indításkor maga hozza létre.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="${XDG_DATA_HOME:-$HOME/.local/share}/kepprofil"
APP="$BASE/app"
VENV="$BASE/venv"
BIN="$HOME/.local/bin"
WANT_DEPS=0
[ "${1:-}" = "--deps" ] && WANT_DEPS=1

say() { printf '\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\033[31mHIBA: %s\033[0m\n' "$*" >&2; exit 1; }

command -v python3 >/dev/null || die "Nincs python3."

# ---- rendszerfüggőségek ------------------------------------------------------------------
# tk: ablakok · python-gobject + libayatana-appindicator: tálcaikon Plasma Waylanden
# libkscreen: kscreen-doctor (képbeállítás) · qt6-tools: qdbus6 (értesítés az aktív képernyőn)
need=()
python3 -c 'import tkinter' 2>/dev/null || need+=(tk)
python3 -c 'import gi' 2>/dev/null || need+=(python-gobject)
if command -v pacman >/dev/null; then
    pacman -Qq libayatana-appindicator >/dev/null 2>&1 || need+=(libayatana-appindicator)
fi
command -v kscreen-doctor >/dev/null || need+=(libkscreen)
command -v qdbus6 >/dev/null || need+=(qt6-tools)

if [ "${#need[@]}" -gt 0 ]; then
    if [ "$WANT_DEPS" = 1 ] && command -v pacman >/dev/null; then
        say "Hiányzó csomagok telepítése: ${need[*]}"
        sudo pacman -S --needed --noconfirm "${need[@]}"
    else
        printf 'Hiányzó rendszercsomagok: %s\n' "${need[*]}" >&2
        command -v pacman >/dev/null && printf 'Felrakásuk: sudo pacman -S --needed %s\n   vagy futtasd újra: ./install.sh --deps\n' "${need[*]}" >&2
        die "Előbb a függőségeket kell felrakni."
    fi
fi

# ---- program + virtuális környezet ---------------------------------------------------------
say "Program másolása: $APP"
mkdir -p "$BASE" "$BIN"
rm -rf "$APP"
mkdir -p "$APP"
cp -r "$SRC"/. "$APP"/
rm -f "$APP/install.sh" "$APP/uninstall.sh"

# --system-site-packages: a tálcaikonhoz kell a rendszer python-gobject (gi) csomagja
if [ ! -x "$VENV/bin/python" ]; then
    say "Virtuális környezet: $VENV"
    python3 -m venv --system-site-packages "$VENV"
fi
say "Python-csomagok (pip)"
"$VENV/bin/pip" install --quiet --upgrade -r "$APP/requirements.txt"

# ---- indító parancs --------------------------------------------------------------------------
cat > "$BIN/kepprofil" <<EOF
#!/usr/bin/env bash
exec "$VENV/bin/python" "$APP/kijelzo.py" "\$@"
EOF
chmod +x "$BIN/kepprofil"

# ---- ellenőrzés: a modulok betöltődnek-e (ablak nélkül) ------------------------------------
say "Ellenőrzés"
(cd "$APP" && "$VENV/bin/python" -c 'import tkinter, customtkinter, psutil, PIL, openrgb, config, engine, hw, system, overlay') \
    || die "A program moduljai nem töltődnek be (lásd fent)."

VERSION="$(sed -n 's/^VERSION = "\(.*\)".*/\1/p' "$APP/consts.py" | head -1)"
say "Kész: Képprofil ${VERSION:-?}"
cat <<EOF

Indítás:        kepprofil            (ablakkal)
                kepprofil --tray     (csak a tálcára)
Alkalmazásmenü: az első indítás után a „Képprofil" bejegyzés is megjelenik.
Automatikus indítás: a program Program fülén, a kapcsolóval.
Gyorsgombok:    Waylanden nincs globális gyorsgomb; a tálcamenü „Gyorsbillentyűk (KDE)…" pontja kész parancsokat ad.
Eltávolítás:    ./uninstall.sh (a csomagban)
EOF
case ":$PATH:" in *":$BIN:"*) ;; *) printf '\nFIGYELEM: a %s nincs a PATH-ban, a parancs teljes útvonallal indítható: %s/kepprofil\n' "$BIN" "$BIN" ;; esac
