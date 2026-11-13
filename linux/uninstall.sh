#!/usr/bin/env bash
# Képprofil eltávolítása Linuxról.
#
#   ./uninstall.sh           a program, a virtuális környezet, az indító és az automatikus indítás törlése
#   ./uninstall.sh --purge   ezen felül a beállítások és presetek (~/.config/kepprofil) is törlődnek
set -euo pipefail

DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
CONF="${XDG_CONFIG_HOME:-$HOME/.config}"

pkill -f 'kepprofil/app/kijelzo.py' 2>/dev/null || true

rm -rf "$DATA/kepprofil"
rm -f "$HOME/.local/bin/kepprofil" \
      "$DATA/applications/kepprofil.desktop" \
      "$DATA/icons/hicolor/256x256/apps/kepprofil.png" \
      "$CONF/autostart/kepprofil.desktop"
echo "A program eltávolítva."

if [ "${1:-}" = "--purge" ]; then
    rm -rf "$CONF/kepprofil"
    echo "A beállítások és presetek is törölve."
else
    echo "A beállítások és presetek megmaradtak: $CONF/kepprofil  (törlésük: ./uninstall.sh --purge)"
fi
