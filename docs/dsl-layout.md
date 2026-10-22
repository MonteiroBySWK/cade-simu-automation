# DSL de layout (pseudo-linguagem) — proposta

**Problema:** hoje a spec exige **coordenadas x/y à mão** para cada símbolo — frágil,
gera "pontinhos soltos", degraus e elementos fora do quadro. Não escala.

**Objetivo:** descrever o circuito pela **topologia** (o que liga em quê) e deixar o
motor de layout calcular as posições.

## Forma proposta (v1)

```jsonc
{
  "titulo": "PARTIDA INTERCALAR",
  "trilhos": { "L1": 14, "L2": 20, "L3": 26, "N": 290, "x0": 25, "x1": 395 },
  "fontes": [ {"classe":"3004", "id":"X1", "fases":["L1","L2","L3"], "neutro":"N"} ],
  "comando": [
    { "id":"m1", "de":"L1", "para":"N",
      "serie":  [ ["RT1","8017","-F2"], ["RT2","8017","-F2"], ["S0","8001","-S0"] ],
      "msel_abre":"L1",
      "ramos": [
        { "via":["S1","8000","-S1"], "selo":["KM1","7000","-KM1"], "entra":"m1",
          "serie":[ ["nkm2","7001","-KM2"] ], "carga":["KM1","9000","-KM1"],
          "indica":["H1","9008","-H1"] },
        { "via":["S2","8000","-S2"], "selo":["KM2","7000","-KM2"], "entra":"m1",
          "serie":[ ["nkm1","7001","-KM1"] ], "carga":["KM2","9000","-KM2"],
          "indica":["H2","9008","-H2"] }
      ] }
  ],
  "potencia": [
    { "id":"m1", "fases":["L1","L2","L3"], "neutro":"N",
      "colunas": [
        ["Q1","6009"], ["F1","6007"], ["KM1","2001"], ["M1","1000","U1/V1/W1/PE"]
      ] }
  ]
}
```

### Regras que o motor de layout deve aplicar
1. **Colunas entre trilhos**: elementos em `serie` descem numa coluna (x fixo, y
   crescente, passo fixo); o primeiro pino `A` recebe o trilho `de`, o último `B`
   vai ao trilho `para`.
2. **Ramo paralelo**: `via`+`selo` formam uma coluna ao lado (x += dx) ligada nos
   **mesmos dois nós** de entrada/saída.
3. **Potência trifásica**: cada `coluna` é um **conjunto de 3 colunas** (uma por
   fase, 6 unidades apart), descendo alinhadas; `PE` desce ao neutro.
4. **Fontes**: um `-X` por fase OU um símbolo com múltiplos terminais (medir os
   pinos reais); a fonte fica **colada no trilho** (queda curta), nunca solta.
5. **Sem sobreposição**: o motor calcula as larguras e afasta as colunas
   (`dx = largura_max + 20`).
6. **Gate**: o resultado tem de passar `build_spec.py` (`GATE: OK`) e
   `wires_check.py` (`FIOS: ok`).

### Ganho esperado
- **Zero coordenadas manuais**; nada de "pontinhos soltos" nem degraus.
- Ramos paralelos e ramos de potência idênticos → layout **consistente**.
- Mudar um símbolo não exige reposicionar nada.

### Estado atual (implementado)
- **Motor**: `tools/layout.py` (`compilar(spec)` -> spec baixa). CLI:
  `python3 tools/layout.py in.layout.json [out.spec.json]`.
- **Integração**: `build_spec.py` detecta a chave `"layout"` (ou extensão
  `.layout.json`) e compila antes do build:
  `python3 tools/build_spec.py tools/examples/intercalada.layout.json out/x.cad`.
- **Dimensões**: `tools/symbol_dims.json` (w,h por classe, gerado do acervo via
  `python3 tools/layout.py --gen-dims`); pinos vêm de `tools/symbol_pins.json`.
- **Exemplos**: `intercalada.layout.json` (2 motores, equivalente à spec manual),
  `partida_direta.layout.json` (1 motor) e os do comando v2 (seção abaixo). Nenhuma coordenada na entrada.
- **Testes**: `python3 -m pytest tools/test_layout.py` (folha, sobreposição,
  alinhamento da potência, GATE e FIOS dos dois circuitos).

### Forma efetivamente aceita (v1 real)
Diferenças em relação à proposta acima:
- `trilhos`: `{"L1":14,...,"N":290,"x0":25,"x1":395}` (o maior y é o neutro/base).
- Símbolo = `[id, classe, rotulo]`; **ids únicos** (ex.: selo `selo1`, contato `nkm2`).
- `comando[].serie` desce numa coluna (passo = h+20); cada **ramo** é uma
  **fileira horizontal** (via ∥ selo, série, carga ∥ indica), fileiras empilhadas
  com passo 60 (comprimido se não couber). Colunas de mesmo papel alinham em x
  entre ramos (`dx = largura_max + 20`). Fileira (e não coluna ao lado) porque é
  o que cabe na folha de 300 de altura e o roteador já validou.
- `potencia[].colunas`: cada item vira 3 colunas (fases a 6 de distância);
  pinos `1/3/5`->`2/4/6` ou `U1/V1/W1`; `PE` do motor ao neutro. Grupos de
  motores ficam lado a lado (`largura + 20`).
- `fontes`: uma `-X` por fase em escada logo abaixo dos trilhos, A->trilho da fase,
  B->neutro. `terra`: `3002` encostado no neutro.
- `msel_abre` e `entra` da proposta **não** são usados (ramos entram no fim da série).
- O motor levanta `ValueError` se algo sair da folha (`layout.SHEET_X/Y`, de `tools/sheet.json`:
  455x305, unidades do .cad) ou se dois símbolos se sobrepuserem; a rede v2 quebra em colunas/faixas antes disso.

### Contatores em paralelo e inversao de fases (reversao)
Em `potencia[].colunas`, um item pode ser:
- `[id, classe, rotulo]` — simbolo simples (como antes);
- `[id, classe, rotulo, {"ordem": ["L3","L2","L1"]}]` — o pino 1/3/5 (ou U1/V1/W1) recebe
  as fases nessa ordem (nomes de `fases`); permite inverter 2 fases;
- `{"paralelo": [item, item, ...]}` — varios contatores lado a lado, no mesmo estagio,
  ligados a mesma entrada e a mesma saida.

O motor cria **trilhos auxiliares** por fase (`<id>_e1..3` na entrada, `<id>_s1..3` na saida,
nomes reservados) para unir os membros: fio so se encontra com fio por extremo (regra de
geometria), entao nao ha T sem junta nem cruzamento ambiguo. O estagio seguinte (motor) fica
alinhado ao 1o membro. Exemplo: `tools/examples/reversao.layout.json` (KM1 direto, KM2 com
`ordem` L3,L2,L1; intertravamento por NF cruzado e selo no `comando`; 13 testes).
Verificado por netlist geometrico (`geo_check.analisar(path, redes)`) e no app (Wine):
S1 energiza KM1 (selo mantem), S0 desliga, S2 energiza KM2, S1 com KM2 ligado nao liga KM1.
Caixa do circuito: ~x 288, y 215 (cabe em 455x295). No app, fios nao mudam de cor por fase;
a conferencia de fases e pela netlist (`test_reversao_fases_na_geometria`).

### Quarto polo (`polos: 4`) — reversao trifasica como no desenho do professor
O desenho da disciplina usa disjuntor `6004` e contatores `2002` de **4 polos** (o 4o polo
comuta o neutro). No grupo de `potencia`, `"polos": 4` troca as linhas para
`fases + [neutro]` (ex.: L1,L2,L3,N):

```jsonc
"potencia": [{ "id":"m1", "fases":["L1","L2","L3"], "neutro":"N", "pe":"PE", "polos": 4,
  "colunas": [["Q1","6004","-Q1"], ["F1","6007","-RT1"],
    {"paralelo": [["KM1p","2002","-KM1"],
                  ["KM2p","2002","-KM2", {"ordem": ["L3","L2","L1","N"]}]]},
    ["M1","1000","-M1"]] }]
```

- `ordem` usa os nomes das 4 linhas (o `N` segue reto no exemplo: 4o pino <- N).
- Estagio de 3 polos em grupo de 4 (ex.: termico `6007`) e permitido **so em estagio
  simples**: as 3 primeiras linhas passam por ele e a 4a (N) faz **bypass** direto para o
  proximo estagio. Em `paralelo` todos os membros precisam ter os 4 polos.
- O motor (`1000`, 3 fases + PE) consome as 3 primeiras linhas; a 4a termina nos
  trilhos de saida (`<id>_s4`); o PE vai ao trilho proprio (`"pe":"PE"`, nunca no N).
- `polos` so aceita 3 ou 4; com 4 o grupo exige `6004`/`2002` nas colunas (erro claro
  caso contrario). Exemplo: `tools/examples/reversao_4polos.layout.json` (mesmos 13
  testes do `reversao`; `test_reversao_4polos_fases_na_geometria` confere o bypass do N
  e o cruzamento L1<->L3 por geometria).
- Simulador (`netlist_sim`): `2002` = polos NA por rotulo; `6002`/`6004` = protecao
  passante (FECHADO — no app, fechar a mao, como os demais disjuntores da DSL).

### Reversao monofasica (`tipo: "monofasico"`)
Motor `1008` (U1/V1/PE/U2/V2 = p1..p5 no binario), contatores `2002` (4 polos) e
disjuntor 2 polos `6002`. A reversao **nao** troca fase e neutro: o 1o contator faz a
**ligacao de referencia** (U1/V1 no L, U2/V2 no N) e o 2o **cruza o enrolamento
auxiliar** (V1<->V2 nas saidas). Ver `docs/bibliografia/automacao-industrial.md` §1.

```jsonc
"potencia": [{ "id":"m1", "tipo":"monofasico", "fase":"L1", "neutro":"N", "pe":"PE",
  "colunas": [["Q1","6002","-Q1"],
    {"paralelo": [["KM1p","2002","-KM1"], ["KM2p","2002","-KM2"]}]},
    ["M1","1008","-M1"]] }]
```

- `"fase"` (ex. `L1`) + `"neutro"` (ex. `N`) em vez de `"fases"`; `"pe"` e obrigatorio e
  precisa de trilho proprio (PE nunca no neutro — senao e curto N x PE).
- Forma fixa: `[disjuntor 2 polos, {paralelo: [KM1, KM2 de 4 polos]}, motor 1008]`
  (outra forma da erro explicito). Entradas retas (L' nos pinos 1-2, N' nos 3-4) e saidas
  em trilhos `m1_s1..s4` (U1/V1/U2/V2); o motor alinha ao 1o contator.
- O `comando` e o mesmo da reversao trifasica (S0 NF; S1/S2 NA com selo `7000` do
  proprio contator e NF cruzado `7001`; bobinas `9000` KM1/KM2).
- Exemplo: `tools/examples/reversao_monofasica.layout.json` (fonte `3003` L/N; 10 testes:
  repouso, S1→KM1, selo, intertravamentos, S0 desliga, S2 apos soltar, sem
  auto-religamento). `test_reversao_monofasica_fases_na_geometria` confere o cruzamento
  por geometria. Validacao no app (sentido de giro) pendente — sem Wine aqui.

## Comando v2: rede série-paralelo recursiva

O `comando` aceita, **por bloco**, duas formas. A legada (`serie` + `ramos`, acima) continua
igual (mesma saída byte a byte). A nova descreve o degrau como uma **expressão** série/paralelo
aninhável; o motor desenha, liga e amarra tudo.

```jsonc
"comando": [
  { "id": "c1", "de": "L1", "para": "N",
    "rede": { "serie": [
      ["RT1","8017","-RT1"],                                   // folha = [id, classe, rotulo]
      ["S0","8001","-S0"], ["S3","8001","-S3"],                // desligas em SERIE
      { "paralelo": [ ["S1","8000","-S1"], ["S2","8000","-S2"], ["selo1","7000","-KM1"] ] },  // ligas em PARALELO + selo
      { "paralelo": [ ["KM1","9000","-KM1"], ["H1","9008","-H1"] ] }   // cargas em paralelo (bobina, lampada, outra bobina...)
    ] } }
]
```

- **Expressão**: folha = `[id, classe, rotulo]`; `{"serie":[...]}` e `{"paralelo":[...]}` aninham
  em qualquer profundidade (série dentro de paralelo dentro de série...). Uma lista solta de
  expressões vale como série; `serie`-em-`serie` e `paralelo`-em-`paralelo` são achatados;
  grupo de 1 elemento some. Folha = símbolo de **2 terminais** (A em cima, B embaixo): botão,
  contato auxiliar NA/NF de qualquer classe, térmico, bobina, lâmpada... Classe com 3+
  terminais (contator 2001, disjuntor) não entra na rede (vai em `potencia`).
- **Vários degraus**: `"rungs": [expr, expr, ...]` (alias `"degraus"`) no lugar de `rede`: cada
  expressão é um degrau independente entre os **mesmos** `de`/`para`. Vários blocos `comando`
  também valem (cada um com seu par de trilhos).
- **Desenho**: o degrau é uma **coluna vertical** entre o trilho `de` (em cima) e `para` (embaixo).
  Série desce com eixo comum; paralelo põe os ramos **lado a lado** (alinhados pelo topo,
  passo múltiplo de 6) e o eixo do grupo fica no centro. Cada nó elétrico vira um barramento
  horizontal com verticais retas nos pinos e vértice em todo ponto de ligação (fio só une
  fio por extremo): sem T solto, sem pino solto, fio reto quando A e B estão no mesmo x.
  Elementos ligados direto ao trilho usam o roteador (vértice no trilho).
- **Altura**: o trilho `para` desce sozinho (e os que estão abaixo dele, ex. PE, descem junto)
  para caber o degrau mais alto.
- **Ordem dos símbolos**: percurso em profundidade (primeiro contato do primeiro degrau tem o A
  no trilho `de`, regra de leitura do simulador legado).

### Trilhos de comando separados (`trilhos_comando`)

```jsonc
"trilhos_comando": {
  "nomes": ["C1","C2"],                                        // [topo, base]; default C1/C2
  "transformador": {"id":"T1","classe":"3012","rotulo":"-T1","primario":["L1","L2"]},
  "fonte": {"id":"X2","classe":"3003","rotulo":"-X2"}          // fonte monofasica propria (L/N), opcional
}
// e o bloco de comando: {"id":"c1","de":"C1","para":"C2","rede":{...}}
```

Cria o par de trilhos `C1`/`C2` (y automático; `C2` desce conforme a rede) ao lado das fontes.
`transformador`: classe `3012` (`-T`, pinos do binário `p1..p4`: primário p1/p2 no topo ligado
aos trilhos de `primario`, secundário p4->C1 e p3->C2). `fonte`: classe `3003`, por padrão
L->C2 e N->C1 (sem cruzar fio; `"pinos":{"L":"C1","N":"C2"}` inverte). **Pelo menos um dos dois** é
obrigatório. Atenção: o simulador (netlist e, provavelmente, o app) **não** propaga fase pelo
transformador; para simular, declare também `fonte` no secundário (o exemplo
`partida_trafo_comando` faz isso). Que o 3012 é transformador é inferência (rótulo `-T`, 4
pinos 2+2); confira no app.

### Quebra automática (não cabe na folha)
A folha segura vem de `tools/sheet.json` (`layout.SHEET_X/Y` = 455x305, unidades do .cad):
1. **Série alta demais** (mais que `y_max` entre os trilhos): o degrau vira **serpentina**: a
   série é repartida em colunas equilibradas; a saída de uma coluna volta ao topo da seguinte
   por um fio único (sobe pelo lado direito da coluna). Um *paralelo* alto demais não quebra
   (erro explícito com a altura).
2. **Paralelo largo demais** (os ramos de um mesmo `paralelo` somam mais que a faixa): os ramos
   se repartem em **linhas** empilhadas; as barras de entrada/saída das linhas se unem por
   uma **espinha** vertical (esquerda na entrada, direita na saída). Em trilho, a linha de
   baixo (`para`) / de cima (`de`) liga pelo roteador e as demais pela espinha.
3. **Largura demais** (degraus não cabem na linha, já descontada a reserva da `potencia`):
   os degraus excedentes vão para uma **faixa** abaixo, com novo par de trilhos
   (`<de>~<id><k>`, `<para>~<id><k>`) **amarrado** ao primeiro por fios nas margens (esquerda
   para `de`, direita para `para`; nenhum cruza símbolo), de modo que seguem sendo o mesmo nó
   elétrico. Cada degrau cabe inteiro numa faixa. Se nem assim couber (folha 455x305 comporta ~2 faixas),
   `ValueError` explícito ("faixa extra nao cabe na folha...").
4. **Forma legada que estoura**: `compilar()` traduz os blocos `serie`/`ramos` para `rede`
   (via ∥ selo, série, carga ∥ indica) e tenta de novo, em vez de falhar (a função interna
   `_compilar` mantém o erro original).

### Exemplos do comando v2 (todos com `testes`, sem coordenadas)
| exemplo | mostra |
|---|---|
| `liga_desliga_2pontos` | 2 liga em paralelo (+selo), 2 desliga em série, 1 motor |
| `partida_sequencial` | 2 degraus; `S0 ∥ NA(KM2)` (desliga em ordem), NA de KM1 em série com S2 |
| `tres_degraus_lampadas` | 3 degraus independentes, lâmpadas, fonte monofásica 3003, `N` desce sozinho |
| `intertravamento_sinalizacao` | paralelo de séries com paralelos; NA e NF de KM1/KM2 em 4 degraus |
| `partida_trafo_comando` | `trilhos_comando` (transformador 3012 + fonte 3003), degrau em C1/C2 |

Testes: `python3 -m pytest tools/test_layout_v2.py` (geometria, conectividade por geometria,
gate dos 5 exemplos, faixas, serpentina, fallback legado, erros de entrada). Casos de
avaliação em `tools/eval/casos/` (golden = exemplo de mesmo nome).

### Ladder / CLP (`ladder/1`, especificado — não implementado)
Seções `clp` (CPU 10206 + entradas 10204 ligadas a botões/térmicos + saídas 10205 ligadas a
bobinas/lâmpadas) e `ladder` (fonte 3008, `rungs` série-paralelo de contatos `NA`/`NF` com
operandos I/Q/M/T/C e saídas `OUT`/`SET`/`RST`/`TON`), junto da `potencia` atual. Contrato
completo (semântica do RE, validação, simulação síncrona, geometria, testes com `sequencia`):
`docs/ladder.md` + `docs/ladder.schema.json`. Exemplos: `tools/examples/*.ladder.json`
(fora do `*.layout.json`, portanto fora do gate atual); casos: `tools/eval/casos/ladder/`.

### Limitações / pendências
- `potencia`: `paralelo` só em um nível (`ordem` vale para qualquer estágio); não quebra em
  faixas (se a potência não couber depois do comando, erro explícito de folha). O comando v2
  reserva o espaço estimado dos grupos de potência na faixa 0.
- Rede v2: só símbolos de 2 terminais verticais (A em cima, B embaixo); sem ramo cruzado
  (ponte) nem rede não série-paralela; sem temporizadores/contatos multipolares no degrau.
- Quebra em faixas: no máximo 2 blocos com faixa (uma amarração por bloco na margem
  esquerda); o fio de `para` na direita fica depois do último símbolo da folha.
- Rótulos de texto não são considerados no espaçamento (usa `GAP`=20 entre ramos); rótulos
  longos podem encostar no fio vizinho.
- `trilhos_comando.transformador`: simuladores não passam fase pelo 3012 (ver acima).
- `build_spec.lint_layout` ainda avisa "não é um trilho" para `C1`/`C2` de `trilhos_comando`
  (aviso apenas; o gate ignora).
- `cad_test` sem `testes` na spec só vale p/ KM1+KM2; os exemplos trazem seus casos.
- **Pendência de RE**: pinos reais do `3004#-X` (só `A`/`B` medidos).
