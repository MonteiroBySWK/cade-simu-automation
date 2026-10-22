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

## Estado atual: goldens do APP (22/10/2026)

Os 11 casos de `tests/conformidade/` tem `golden_app.json` com `"fonte": "app"`, gravado por
`tools/golden_app.py` (Wine + `app_sim`). O relatorio conta quantos ainda sao provisorios
(`goldens_provisorios`); `tests/conformidade/gerar.py` **nao** sobrescreve golden `"fonte": "app"`
(so com `--forcar`).

Dois fatos do app que o cenario precisa respeitar (custaram caro em 22/10/2026):

- **um ponteiro so**: nao existe segurar S1 e apertar S0 ao mesmo tempo (ver a tabela acima). Sem
  isso, o golden saia mentiroso: o clique em S0 era engolido pelo `mousedown` de S1 que estava
  sendo segurado, e `KM1` continuava ligado.
- **disjuntores iniciam ABERTOS** em cada Play (`6009`/`6010`/`6003`/`6002`, `estado_inicial 0`).
  Sem fechar, o **motor nunca gira**: em `partida_direta`, S1 energiza `KM1`/`H1`, mas `M1` fica
  parado ate um clique em `Q1`. O gravador clica cada disjuntor depois de Play e de cada
  `reiniciar`; `--sem-disjuntores` grava o app cru (util para provar o estado inicial).

Divergencias conhecidas que o motor ainda nao cobre (a gravar/tratar no `cade_sim`):

- o motor Rust trata `6009`/`6010` como **sempre fechados** (camada 1 de `papeis.rs`) e nao os expoe
  como entrada; por isso o golden e comparado com os disjuntores ja fechados. Modelar o estado do
  disjuntor (aberto no Play, `alternar` fecha) mexe no modelo e nos `testes` dos exemplos;
- tempo: o app conta em ticks de 100 ms; o motor avanca em tempo continuo (diferenca de ate 1 tick
  ao redor da comutacao). O campo extra `t_parede_ms` guarda o tempo real do app (o relogio dele
  anda tambem durante cliques e screenshots) — e o dado para calibrar cenarios com temporizador;
- motor trifasico (`gira`): modelado como "dois pinos de fase com estampas diferentes" (confianca
  media); a leitura de `motores` por imagem (disco cinza) foi exercitada nos 11 casos.

### Achados do app na gravacao (22/10/2026)

- **aviso de CURTO e uma janela separada** (titulo `Erro`, ~150x82): o `import -window` da principal
  nao a mostra e o app fica bloqueado. `AppSim.janela_dialogo()/fechar_dialogo()` detectam e fecham
  (Return, senao clique no OK); o gravador marca `curto:true` no passo.
- **transformador `3012` ja e fonte**: o app estampa no secundario (`p4`=L, `p3`=N). Somar uma fonte
  `3003` no mesmo par de trilhos de comando = **CURTO** (foi o que derrubou `partida_trafo_comando`;
  o gate nao via porque o modelo nao tratava `3012` como fonte). Corrigido no Python e no Rust.
- **o app repinta em ticks de 100 ms**: logo apos uma acao a captura pode pegar um **quadro parcial**
  (bobina ja vermelha, contato auxiliar/lampada/motor ainda nao). O gravador espera 0,5 s apos a acao
  e 0,25 s antes de ler; sem isso os goldens saiam mentirosos.
- **soltar no ponto**: `mouseup` na esquina da janela nao liberava a botoeira no app (ficava presa).
  `AppSim.soltar()` agora solta no mesmo ponto do `mousedown`.
- **filha MDI pequena**: com a janela menor que a folha, o app desenha em zoom ~2 px/unidade e corta
  a parte de baixo. `calibrar` agora descobre a area visivel (corta o fundo cinza do MDI) e varre
  escalas de 0,5 a 4,0; `zoom_todo` nao falha mais se nao conseguir maximizar.

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

**Um atuador por vez**: no app ha um ponteiro so. `pressionar` segura; para acionar outro elemento e
preciso `soltar` antes (segurar S1 e apertar S0 ao mesmo tempo nao existe — o segundo clique vira o
`mouseup` do primeiro e some). O gravador **recusa** cenario nessa situacao em vez de gravar um
estado falso. `tests/conformidade/gerar.py` ja gera os pares em sequencia (aperta A, solta, aperta B).

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

## Como regravar os goldens (Wine)

Requer Wine + o CADe_SIMU 4.0 (o `.exe` **nao** e distribuido neste repositorio) e **um unico**
Wine por vez (`AGENTS.md`).

### Display dedicado (recomendado)

O app abre em ~2 px/unidade e a folha tem ~610 px de altura. Se o WM do usuario ladrilhar a janela
em menos que isso (ex.: 523 px), a folha e cortada e o gravador recusa ("simbolos fora da janela").
Para gravar sem depender da tela do usuario:

```bash
./scripts/golden-display.sh :2 1600 1200      # Xvfb + openbox (dependencia do host)
DISPLAY=:2 python3 tools/golden_app.py --todos
```

Arch: `sudo pacman -S --needed xorg-server-xvfb extra/openbox`. O `openbox`/`Xvfb` sao do **host**
(nao entram no Docker); o Wine continua um por vez.

```bash
python3 tools/golden_app.py tests/conformidade/reversao --verbose   # um caso
python3 tools/golden_app.py --todos                                 # todos (preserva golden "app")
python3 tools/golden_app.py --todos --forcar                        # regrava inclusive os do app
python3 tools/golden_app.py --todos --json out/app_sim/goldens.json # resumo
```

O gravador abre o caso, faz Play, maximiza a vista, **fecha os disjuntores** e le o estado por imagem
depois de **cada** acao (bobinas, lampadas, motores, saidas do CLP), escrevendo `golden_app.json` com
`"fonte": "app"`. Ele recusa cenario com dois atuadores segurados ao mesmo tempo e sempre derruba o
Wine que ele mesmo subiu (`--manter` para nao derrubar). Para um caso novo: crie a pasta com
`circuito.cad` + `cenario.json` (sem golden) e rode o gravador.

Depois rode `cade conformidade tests/conformidade` e analise cada divergencia: cada uma e um **bug do
motor** (corrija o `cade_sim` e a tabela de papeis) ou um **achado sobre o app** (documente em
`docs/re-engenharia.md`). **Nunca** ajuste o golden para "passar".

Prioridades de cenarios novos: temporizadores (`9004/9005/9006` + `7004..7015`), disjuntor como
entrada do modelo (`alternar Q1` — precisa do modelo primeiro), contatos NA-NC/comutados, motor sem
fase, curto.

Container opcional para regravar (`docker/wine-golden/`): Wine + Xvfb + xdotool + ImageMagick. **Nao
foi executado neste PR.**

## Conformidade de ladder

Os casos `tests/conformidade/ladder_<nome>/` sao gerados por `tools/ladder_conformance.py` a partir
de `tools/examples/<nome>.ladder.json`: ele compila o `.cad` com o `ladder_dsl` e escreve um
`cenario.json` fisicamente possivel (reiniciar -> parte 1 -> solta/selo -> espera TON -> para ->
parte 2 -> termico -> rearma -> reiniciar). O golden e gravado no app como os demais e o
`cade conformidade` compara **`saidas_clp` (Q0.x) + bobinas + lampadas**.

O gravador fecha os disjuntores automaticamente; por isso o cenario **nao** inclui `alternar DJ1`
(abriria o disjuntor que o modelo assume fechado).

Notas de gravacao de ladder (22/10/2026):
- as celulas **10205** (saidas do CLP) podem "piscar" na captura (o app repinta a cada 100 ms):
  grave com `--leituras 3` (maioria por simbolo) e `--settle 0.4`;
- o campo `motores` **nao** e comparado nos casos de ladder (`--sem-motores`): o lado eletrico
  (contator -> motor) ja e provado pelos 11 casos de rele; aqui a prova e o CLP + bobinas + lampadas
  + `saidas_clp` (Q0.x);
- o `zoom_todo` NAO e chamado pelo gravador (os cliques na barra da MDI mexem na vista e o primeiro
  clique da acao se perde). No display dedicado a folha cabe no zoom automatico (~2 px/unidade).

**Relogio do app**: sob Xvfb/Wine o app avanca ~0,41x o tempo de parede (medido com o TOF de 1 s:
2,43 s de parede). Para temporizadores, `t_parede_ms` puro **nao** alinha; calibre o fator ou compare
por janela.

**Limite atual (22/10/2026)**: a comparacao instantanea funciona para ladder **combinacional**
(`ladder_partida_direta`, `ladder_reversao`). Casos com **temporizador/oscilacao** (`intercalada`,
`partida_sequencial_3`, `pratica5_complementar`) ainda nao sao comparaveis: o app repinta em ticks e
o relogio real nao bate tick a tick com a soma dos `esperar` (nem com o `t_parede_ms`). Precisa de
comparacao por janela (conjunto de saidas ao longo de N ticks) — TODO A2.

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
