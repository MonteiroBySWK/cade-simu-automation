#!/usr/bin/env bash
# Abre .cad no CADe_SIMU via Wine de forma robusta e tira screenshot.
# Uso: wine_open.sh <arquivo.cad> <saida.png> [cliques-zoom-mais]
# - copia p/ o dir do EXE (argv curto), unlock SENHA 4962 com retry, maximiza, Zoom Todo.
set -u
CAD="$1"; SHOT="$2"; ZOOMPLUS="${3:-0}"
EXE_DIR="/home/monteiro/Downloads/CADe_SIMU 4.0 [BR]/CADe_SIMU 4.0 [BR]"
EXE="CADe_SIMU 4.0 [BR].exe"
BASE="$(basename "$CAD")"
cp "$CAD" "$EXE_DIR/wv_tmp.cad"

timeout 180 xvfb-run -a -s "-screen 0 1280x1024x24" sh -c '
cd "'"$EXE_DIR"'" && wine "'"$EXE"'" "wv_tmp.cad" &
sleep 12; xdotool key Return; sleep 2
for i in $(seq 1 20); do
  if xdotool search --name "SENHA" >/dev/null 2>&1; then
    W=$(xdotool search --name "SENHA" | head -1)
    xdotool windowactivate "$W" 2>/dev/null; sleep 1
    xdotool mousemove 512 335 click 1; sleep 1
    xdotool type 4962; sleep 1
    xdotool key Return; sleep 4
  fi
  sleep 4
done
xdotool mousemove 300 25 click --repeat 2 1; sleep 2
xdotool mousemove 212 40 click 1; sleep 1
xdotool mousemove 225 120 click 1; sleep 3
for i in $(seq 1 '"$ZOOMPLUS"'); do
  xdotool mousemove 212 40 click 1; sleep 1
  xdotool mousemove 222 90 click 1; sleep 2
done
import -window root "'"$SHOT"'"
' 2>&1 | grep -v fixme | tail -1
rm -f "$EXE_DIR/wv_tmp.cad"
ls -la "$SHOT"
