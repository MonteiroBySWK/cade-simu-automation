# Benchmark held-out (eixo B do TODO)

12 casos em PT-BR que o agente resolve **do zero**, so com o MCP + skill
(mais 1 exemplo de referencia quando o caso permitir). Congelados: **nada de
solucao no repo** — nenhum `.cad`, `.layout.json` ou `.ladder.json` destes
casos (as referencias usadas para calibrar os testes ficaram em `/tmp` e
foram descartadas).

## Protocolo

1. O agente recebe so o enunciado (+ restricoes) do caso.
2. Produz `<id>.cad` via `cad_design` (MCP/skill), como nas entregas.
3. Pontua com `python3 tools/eval/run_eval.py <id> <id>.cad`
   (`carregar_caso` resolve ids daqui; `--min 80` no B6).
4. Meta B (TODO): media >= 80, 0 falha dura (arquivo invalido, crash,
   classe inventada), tempo <= 15 min/caso.

## Os 12 casos

| id | tipo | o que mede |
|---|---|---|
| `h_partida_direta` | rele | direta + selo + H1; termico bloqueia/derruba |
| `h_reversao_trifasica` | rele | reversao + intertravamento + H1/H2 |
| `h_reversao_monofasica` | rele | motor 1008 + 2002/6004 (4 polos); comando = reversao trifasica |
| `h_intercalada_clp` | ladder | alternancia SET/RST + RT1/RT2 + H1-H4 + intertravamento |
| `h_sequencial_ton` | ladder | 2 motores em sequencia com TON de 3 s (ticks) |
| `h_emergencia` | rele | emergencia derruba e impede; soltar nao religa |
| `h_sinalizacao` | rele | H1 ligada + H2 desligada + H3 falha |
| `h_set_rst` | ladder | liga/desliga com SET/RST (sem selo fisico) |
| `h_contador` | ladder | contagem com CTU 10063 (envelope simulavel) |
| `h_falha_termica` | rele | diagnostico do termico + rearme |
| `h_liga_desliga_2pontos` | rele | 2 pontos de liga + 2 de desliga |
| `h_comando_trafo` | rele | comando em C1/C2 via transformador 3012 |

## Regras de escrita (para manter o benchmark justo)

- Mesmo formato de `tools/eval/casos/` (`id`, `dsl` quando ladder, `titulo`,
  `dificuldade`, `enunciado`, `restricoes`, `obrigatorios`, `testes`).
- **Sem `golden` e sem solucao**: o `run_eval --golden` ignora esta pasta.
- Todo teste usa chaves que existem num circuito correto (entradas =
  rotulos sem `-`; `inicial` = bobinas/operandos; `esperado` = bobinas 9000;
  `esperado_lampadas` = 9008; `esperado_bits` = operandos I/Q/M/T).
- `obrigatorios.classes` sao **minimos**: solucao com mais simbolos passa.
- Casos `h_reversao_monofasica` e `h_contador` dependem de itens ainda sem
  modelo (A8: potencia 1008/2002/6004 na DSL; A3: CTU 10063): os testes cobrem
  o envelope simulavel e cada caso traz `nota` explicando o gap. Pontuar 100
  neles exige `cad_build` de baixo nivel.
