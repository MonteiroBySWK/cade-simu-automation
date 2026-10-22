#!/usr/bin/env bash
# Display virtual dedicado para gravar goldens do app (Wine) sem usar a tela do usuario.
#
#   scripts/golden-display.sh            # sobe Xvfb :2 + openbox (1600x1200)
#   DISPLAY=:2 python3 tools/golden_app.py --todos
#
# Por que: o app abre em ~2 px/unidade e a folha tem ~610 px de altura. Com o WM do usuario
# ladrilhando a janela em 523 px, a folha e cortada e o gravador recusa ("simbolos fora da
# janela"). No display dedicado a janela cabe inteira (>= 650 px).
set -euo pipefail
DISP="${1:-:2}"
W="${2:-1600}"
H="${3:-1200}"

if ! command -v Xvfb >/dev/null; then
  echo "Xvfb ausente: sudo pacman -S --needed xorg-server-xvfb" >&2
  exit 1
fi
if ! command -v openbox >/dev/null; then
  echo "openbox ausente: sudo pacman -S --needed extra/openbox" >&2
  exit 1
fi

if ! pgrep -f "Xvfb ${DISP} " >/dev/null 2>&1; then
  Xvfb "$DISP" -screen 0 "${W}x${H}x24" >/tmp/cade-xvfb.log 2>&1 &
  sleep 1
fi
if ! DISPLAY="$DISP" pgrep -x openbox >/dev/null 2>&1; then
  DISPLAY="$DISP" openbox >/tmp/cade-openbox.log 2>&1 &
  sleep 1
fi

DISPLAY="$DISP" xdpyinfo >/dev/null 2>&1 || { echo "display ${DISP} nao respondeu" >&2; exit 1; }
echo "display ${DISP} pronto (${W}x${H}); use: DISPLAY=${DISP} python3 tools/golden_app.py ..."
