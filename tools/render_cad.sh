#!/usr/bin/env bash
# Renderiza um .cad no CADe_SIMU (Wine): desbloqueia (senha 4962 pelo teclado
# do diálogo), maximiza a janela MDI e aplica Ver > Zoom Todo; salva screenshot.
# Uso: render_cad.sh <arquivo.cad> <saida.png>
set -u
CAD="$1"; SHOT="$2"
EXE_DIR="${CADE_DIR:?defina CADE_DIR com a pasta do CADe_SIMU (veja docs/DEPENDENCIAS.md)}"
cp "$CAD" "$EXE_DIR/rv_tmp.cad"
timeout 150 xvfb-run -a -s "-screen 0 1280x1024x24" sh -c '
cd "'"$EXE_DIR"'" && wine "CADe_SIMU 4.0 [BR].exe" "rv_tmp.cad" &
sleep 20
# teclado de senha (4962): cliques nos dígitos + OK  (layout 1-2-3 / 4-5-6 / 7-8-9)
xdotool mousemove 455 410 click 1; sleep 1
xdotool mousemove 505 433 click 1; sleep 1
xdotool mousemove 505 410 click 1; sleep 1
xdotool mousemove 480 387 click 1; sleep 1
xdotool mousemove 459 460 click 1; sleep 4
# maximiza a janela filha MDI (duplo-clique na barra de título)
xdotool mousemove 300 25 click --repeat 2 1; sleep 2
# Ver > Zoom Todo
xdotool mousemove 212 40 click 1; sleep 1
xdotool mousemove 225 120 click 1; sleep 3
import -window root "'"$SHOT"'"
' 2>&1 | grep -viE 'fixme|MESA|wine-staging|X connection|DRI3' | tail -1
rm -f "$EXE_DIR/rv_tmp.cad"
[ -f "$SHOT" ] && echo "PNG: $SHOT" || echo "FALHOU: $SHOT"
