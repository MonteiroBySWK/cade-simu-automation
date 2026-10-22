# Conformidade: motor Rust x app real (teste diferencial)

O `cade_sim` e uma **reimplementacao propria** do motor de simulacao do CADe_SIMU 4.0, sem GUI e sem
Wine. A prova de que ele se comporta como o app e um **teste diferencial**: os mesmos cenarios
(sequencia temporal de acoes) rodam no motor Rust e no app real; o estado observado no app e o
**golden**. `cade conformidade` compara os dois.

```text
tests/conformidade/<caso>/
  circuito.cad       o desenho (gerado por `cade design`/`cade build`, nunca a mao)
  cenario.json       o que fazer (acoes) — igual para o app e para o motor
  golden_app.json    o que o app mostrou apos CADA acao ("fonte": "app")
```

```bash
cade conformidade tests/conformidade            # texto; exit 0 so se tudo ok
cade conformidade tests/conformidade --json     # relatorio {ok, divergentes, erros, sem_golden, casos[{diffs}]}
```

## Estado atual: goldens PROVISORIOS

Ainda **nao ha golden gravado no app**. Para o pipeline funcionar ponta a ponta, os 11
`tools/examples` tem goldens gerados pelo **oraculo Python** (`tools/netlist_sim.py`), marcados
`"fonte": "oraculo_python"` (`python3 tests/conformidade/gerar.py`). O relatorio conta quantos goldens
ainda sao provisorios (`goldens_provisorios`). Quando o gravador do app sobrescrever um
`golden_app.json` com `"fonte": "app"`, esse caso passa a ser a prova de verdade — e `gerar.py`
**nao** o sobrescreve (so com `--forcar`).

Um golden provisorio so prova que Rust == Python; ele **nao** prova nada sobre o app. Divergencias
ja conhecidas entre o modelo (Python e Rust) e o app, que a gravacao real deve expor
(`docs/app-sim.md`, `docs/re-engenharia.md` 11.3):

- disjuntor `6009`/`6010` e rele termico `6007`: o modelo embutido trata os polos como **sempre
  fechados**; no app o disjuntor **inicia aberto** em cada Play (conduz com `estado==1`);
- termico: o contato `8016/8017` so acompanha o `6007` de **mesmo rotulo** (`-RT1` x `-F1` nos
  exemplos atuais nao se enxergam no app);
- tempo: o app conta em ticks de 100 ms; o motor avanca em tempo continuo (diferenca de ate 1 tick
  ao redor do instante de comutacao);
- motor trifasico (`gira`): modelado como "dois pinos de fase com estampas diferentes" (confianca media).

## Formato

### `cenario.json`

```json
{"versao": 1, "descricao": "texto livre",
 "acoes": [
   {"acao": "reiniciar"},
   {"acao": "esperar", "ms": 300},
   {"acao": "pressionar", "alvo": "S1"},
   {"acao": "soltar", "alvo": "S1"},
   {"acao": "alternar", "alvo": "RT1"}
 ]}
```

| acao | no app | no motor |
|---|---|---|
| `pressionar` | `mousedown` no corpo do simbolo e **segura** (botoeira, fim de curso) | entrada `alvo` = 1 |
| `soltar` | `mouseup` | entrada `alvo` = 0 |
| `alternar` | um clique (termico `6007`, disjuntor, interruptor: travam) | inverte a entrada `alvo` |
| `esperar` | espera `ms` ms (ticks de 100 ms) | avanca o tempo `ms` ms |
| `reiniciar` | Stop + Play (zera bobinas, disjuntores, termico, temporizadores) | estado inicial, entradas soltas |

`alvo` e o rotulo do simbolo **sem o `-`** (`-S1` -> `S1`); o motor recusa (erro, nao "ok vazio")
um `alvo` que nao existe no circuito. A observacao e feita **depois de cada acao**: `esperar` e a
forma de dar tempo ao app antes de ler (use >= 300 ms por acao; 1 tick = 100 ms).

### `golden_app.json`

```json
{"versao": 1, "fonte": "app", "gravado_em": "2026-10-22T10:00:00-03:00",
 "passos": [
   {"i": 0, "t_ms": 0,   "bobinas": [], "lampadas": [], "motores": [], "saidas_clp": [],
    "temporizadores": [], "curto": false},
   {"i": 1, "t_ms": 300, "bobinas": ["KM1"], "lampadas": ["H1"], "motores": ["M1"], "saidas_clp": [],
    "temporizadores": [], "curto": false}
 ]}
```

- um passo por acao do cenario, na mesma ordem (`i` = indice da acao; `t_ms` = soma dos `esperar`);
- `bobinas`/`lampadas`/`motores`/`saidas_clp`/`temporizadores` = **rotulos ativos** (sem `-`), em
  qualquer ordem; `temporizadores` = contatos/saidas temporizadas ligadas; `curto` = o app acusou curto;
- **todo campo e opcional**: o que o golden omite nao e comparado (o gravador por imagem so precisa
  registrar o que consegue ler; hoje `app_sim` le bobinas e lampadas — motor e disco cinza);
- `saidas_clp` e reservado para o ladder/CLP (o motor devolve sempre `[]` ate o ladder entrar; ver
  `cade_sim::ladder::ModeloLadder`).

### Relatorio

```text
  [OK        ] partida_direta (85 passos, golden: oraculo_python)
  [DIVERGENTE] reversao (153 passos, golden: app)
      passo 12 bobinas: golden=["KM1"] motor=[]
CONFORMIDADE: 10 ok, 1 divergente(s), 0 erro(s), 0 sem golden; 0 golden(s) provisorio(s) (fonte != app)
```

Exit code 0 so se nenhum caso diverge/da erro e ha ao menos um ok. Pasta sem `golden_app.json` conta
como `sem_golden` (nao reprova).

## Como gravar goldens do app (por outro agente/maquina)

Requer Wine + o CADe_SIMU 4.0 (o `.exe` **nao** e distribuido neste repositorio) e **um unico**
Wine por vez (`AGENTS.md`).

1. Para cada `tests/conformidade/<caso>/`, execute `cenario.json` no app com `tools/app_sim.py`
   (`AppSim.abrir()/play()/pressionar()/soltar()/alternar()/estado()`), lendo o estado **depois de cada
   acao** e escrevendo `golden_app.json` no formato acima com `"fonte": "app"`. `reiniciar` = `stop()` + `play()`.
2. Rode `cade conformidade tests/conformidade` e analise as divergencias: cada uma e um **bug do
   motor** (corrija o `cade_sim` e a tabela de papeis) ou um **achado sobre o app** (documente em
   `docs/re-engenharia.md`). So depois ajuste o modelo — nunca o golden.
3. Novos cenarios: crie a pasta com `circuito.cad` + `cenario.json` (sem golden ainda) e grave.
   Prioridades: temporizadores (`9004/9005/9006` + `7004..7015`), disjuntor/interruptor (estado
   inicial aberto), contatos NA-NC/comutados, motor sem fase, curto.

Container opcional para regravar (`docker/wine-golden/`): Wine + Xvfb + xdotool + ImageMagick. **Nao
foi executado neste PR.**

## Como rodar no Docker (sem Wine)

```bash
docker build -t cade .                      # imagem `scratch` so com /cade (binario musl estatico)
docker run --rm -v "$PWD/tests/conformidade:/conformidade:ro" cade conformidade /conformidade
docker run --rm -v "$PWD:/w:ro" cade simulate /w/tests/golden/partida_direta.cad --entradas '{"S1":true}' --json
```

O CI roda `cade conformidade` (Linux) e faz o build da imagem.

## Outros comandos do motor

```bash
cade simulate x.cad --entradas '{"S1":true}' [--inicial '["KM1"]'] [--avanca 5] [--json]
cade test x.cad --testes casos.json [--json]     # mesmo formato de casos do Python (entradas/inicial/esperado/
                                                 # esperado_lampadas/esperado_motores/esperado_temporizadores/
                                                 # status/avanca/tempos/passos); chave inexistente reprova
cade gate x.cad --testes casos.json              # gate completo; os testes funcionais rodam no cade_sim
```

## Nota de licenca

O `cade_sim` e uma **reimplementacao de comportamento para interoperabilidade**: a semantica vem do
que foi **observado** (leitura do estado do app, formato `.cad`) e documentado em
`docs/re-engenharia.md`. **Nenhum codigo decompilado foi copiado**, nenhum bitmap do aplicativo e
usado e o executavel do CADe_SIMU **nao e redistribuido** (nem na imagem Docker). Os dados embutidos
(`tools/*.json`, `docs/*.json`) sao tabelas de nomes/pinos/papeis escritas por este projeto.
