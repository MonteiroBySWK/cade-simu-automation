#!/usr/bin/env bash
# Validação Fase 5: (1) cade_cli validate em corpus/ + out/, (2) abertura via Wine+Xvfb.
# Limite honesto: checa que o EXE sobe sem crash/popup de erro no log; NÃO afirma
# conteúdo renderizado (sem automação de GUI/screenshot-diff ainda).
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXE="${CADE_EXE:?defina CADE_EXE com o caminho do .exe (veja docs/DEPENDENCIAS.md)}"
CLI="$ROOT/src/cade_cli/target/debug/cade_cli"
LOG="$ROOT/out/wine-validate.log"
mkdir -p "$ROOT/out"
: > "$LOG"

fail=0
echo "== cade_cli validate ==" | tee -a "$LOG"
for f in "$ROOT"/corpus/*.cad "$ROOT"/out/*.cad; do
  [ -e "$f" ] || continue
  if ! "$CLI" validate "$f" >>"$LOG" 2>&1; then fail=1; echo "FAIL(parser): $f" | tee -a "$LOG"; fi
done

echo "== wine open ==" | tee -a "$LOG"
for f in "$ROOT"/out/CADe_S1.cad "$ROOT"/out/template.cad "$ROOT"/out/exemplo01.cad; do
  [ -e "$f" ] || continue
  zpath="Z:${f//\//\\}"
  echo "--- wine: $f" >>"$LOG"
  tmplog="$(mktemp)"
  timeout 25 xvfb-run -a wine "$EXE" "$zpath" >"$tmplog" 2>&1
  code=$?
  cat "$tmplog" >>"$LOG"
  # 124 = timeout matou o app ainda aberto (bom: não crashou); 0 = saiu sozinho (ok)
  if grep -aiE "exception|unhandled|page fault|stack overflow|segfault" "$tmplog" | head -3 | grep -qiE "exception|unhandled|page fault|stack overflow|segfault"; then
    fail=1; echo "FAIL(wine-crash): $f" | tee -a "$LOG"
  else
    echo "wine OK (sem erro fatal no log): $f (exit=$code)" | tee -a "$LOG"
  fi
  rm -f "$tmplog"
done

if [ "$fail" -eq 0 ]; then echo "VALIDATE-WINE: PASS" | tee -a "$LOG"; else echo "VALIDATE-WINE: FAIL" | tee -a "$LOG"; fi
exit "$fail"
