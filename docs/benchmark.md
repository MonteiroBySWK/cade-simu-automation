# Benchmark held-out (B6) — resultado

Data: 22/10/2026. Objetivo: medir se um agente resolve pedidos **novos** com o MCP/skill
(critério do eixo B: média ≥ 80, zero falha dura).

## Protocolo

- 12 casos em `tools/eval/heldout/` (8 relé + 4 ladder), enunciados em PT-BR, **sem solução no repo**.
- 3 agentes independentes (4 casos cada), só com `skills/automacao-industrial` + `cad_examples`
  como molde; saída em `.cad` (relé) ou `.ladder.json` → `.cad` (ladder).
- Pontuação automática: `python3 tools/eval/run_eval.py <caso> <arquivo.cad> --json`
  (abre 10, geometria 25, testes 35, fios 10, obrigatórios 20).

## Resultado

| caso | dsl | nota | testes |
|---|---|---|---|
| h_partida_direta | relé | **100** | 7/7 |
| h_reversao_trifasica | relé | **100** | 13/13 |
| h_emergencia | relé | **100** | 8/8 |
| h_liga_desliga_2pontos | relé | **100** | 12/12 |
| h_intercalada_clp | ladder | **100** | 10/10 |
| h_sequencial_ton | ladder | **100** | 5/5 |
| h_sinalizacao | relé | **100** | 7/7 |
| h_falha_termica | relé | **100** | 8/8 |
| h_reversao_monofasica | relé | **100** | 13/13 |
| h_set_rst | ladder | **100** | 8/8 |
| h_contador | ladder | **100** | 7/7 |
| h_comando_trafo | relé | **100** | 6/6 |

**Média: 100,0. Falhas duras: 0. Tempo: ~15 min por grupo de 4.**

## Limites honestos

- Os casos têm **molde próximo** em `tools/examples/` (o protocolo permite “com referência”);
  não mede generalização para padrões sem molde (ex.: estrela-triângulo, que está fora do núcleo).
- Ladder: a nota usa o **modelo geométrico** (`clp_sim`); o caso não foi conferido no app (Wine).
- `h_reversao_monofasica` usou a DSL nova (`tipo:"monofasico"`); `h_contador` cobriu o envelope
  testável do CTU (habilita/selo/para/bloqueia) — o lote completo só em repouso.
- O benchmark deve ser re-rodado a cada mudança de skill/DSL (B7); guarde os `.cad` em `out/heldout/`
  (fora do git) ou anexe em `evidencias/` se quiser histórico.

## Como repetir

```bash
# um caso (o agente gera out/heldout/<id>.cad)
python3 tools/eval/run_eval.py h_partida_direta out/heldout/h_partida_direta.cad --json
# todos os 12 (quando os .cad existirem)
python3 tools/eval/run_eval.py --dir out/heldout
```
