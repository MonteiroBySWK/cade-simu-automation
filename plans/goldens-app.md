# Plano — goldens reais do app (conformidade)

Objetivo: substituir os 11 `golden_app.json` provisórios (`"fonte":"oraculo_python"`) por goldens
gravados no **app real** (`"fonte":"app"`), rodar `cade conformidade` e tratar cada divergência.

## Passos

- [x] `tools/golden_app.py`: gravador (`cenario.json` → `golden_app.json`) com observador injetável.
  - testes unitários (fake observer, sem Wine): tempo acumulado, uma observação por ação, normalização de rótulo,
    recusa de sobrescrever golden `"fonte":"app"` sem `--forcar`, recusa de dois atuadores.
- [x] Validar o gravador em UM caso (`partida_direta`, 85 ações) — motor `M1` lido, `cade conformidade` 11/11.
  - descoberto: disjuntor inicia **aberto** (motor não gira sem clicar) e **um ponteiro só** (S0 perdido).
- [x] Rodar os 10 casos restantes e revisar os goldens (11/11, motor lido em todos).
- [x] `cade conformidade tests/conformidade` completo: 11 ok, 0 divergentes (transformador 3012 = fonte).
- [x] Atualizar `docs/conformidade.md` + `docs/HANDOFF.md` + `docs/re-engenharia.md`, commit.

## Regras

- Um Wine por vez (`python3 tools/wine_mgr.py status`); `DISPLAY=:1`.
- Sem Play/Stop manual: o gravador usa `AppSim` (Play no botão, Stop vermelho).
- `reiniciar` = Stop + Play. `esperar` = sleep real; `t_ms` = soma dos `ms`.
- Campos do golden: `bobinas`, `lampadas`, `saidas_clp`, `motores` (opcional se ruidoso); `curto` só quando true.
