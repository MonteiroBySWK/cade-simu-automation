# Ladder (CLP) no CADe_SIMU — semântica e contrato da DSL `ladder/1`

Status: **implementado em Python** (`tools/ladder_dsl.py` gerador/validação/modelo lógico, `tools/clp_sim.py` modelo
geométrico, `cad_design`/`cad_test`/`cad_gate`) e **verificado no app (Wine)** nas Práticas A/B; contrato do port em Rust.
Extensões §2.5: TON em linha, `potencia` `dj_comum`, cargas em paralelo, `textos`. Os casos `tools/eval/casos/ladder/*.json` seguem só como dados.
Evidência de engenharia reversa em `docs/re-engenharia.md` §13 (endereços do EXE). Esquema
formal: `docs/ladder.schema.json`.

Confiança: **A** = alta (decompilado linha a linha e/ou consistente nos 6 `.cad` do acervo),
**M** = média (decompilado parcialmente ou deduzido do código sem exemplo no acervo),
**B** = baixa (só nome/pinos). Itens M/B que afetam o gerador estão em "Pendências no app".

---

## 1. Modelo do CADe_SIMU (resumo do RE)

| # | item | conf. |
|---|---|---|
| 1 | O ladder é um **circuito CC de um fio**: trilho esquerdo = fio alimentado por fonte `3008` (`'+'`); não há trilho direito. | A |
| 2 | Contato `10050` NA / `10051` NF: A (0,0) à esquerda, B (12,0) à direita. Conduz `'+'` **só de A para B**, se NA∧bit=1 ou NF∧bit=0. | A |
| 3 | Bobina `10060` (OUT): energiza com `'+'` no A e pino B **sem fio** (lido como `'-'`). Fio no B sem fonte `'-'` ⇒ bobina nunca liga. | A |
| 4 | Operando = **label0** do símbolo (string exata). Bobina/entrada/temporizador escrevem o bit em todos os contatos ladder com o mesmo label0. | A |
| 5 | Bobina `10060`/`10061`/`10062` com label0 igual ao de um polo `2000/2001/2002/2006/2008` também comanda esse polo (atalho perigoso). Auxiliares `7000..7003` **não** são comandados pelo ladder. | A |
| 6 | `10061` SET: energizada ⇒ bit=1; `10062` RESET: energizada ⇒ bit=0; desenergizadas ⇒ mantém. SET e RESET juntos: indefinido (ordem das entidades). | M |
| 7 | `10066` TON: IN (0,0), Q (15,6). `T = tempo × base` ticks; Q=1 após T ticks com IN; IN=0 zera. Q estampa `'+'` no fio de Q e escreve o bit no contato de mesmo label0. | M-A |
| 8 | `10063` contador: R (0,0), C (0,6), D (0,12), Q (15,12); preset em label6/label7. | M |
| 9 | `10067` TOF, `10068` intermitente, `10069` gerador, `10081` pulso, `10052/10053` flancos, `10064` RS, `10075` contador ±. | B |
| 10 | CPU `10206`: L (0,0), N (6,0), PE (12,0), `+` (18,0), `-` (24,0). Com fase+N (ou 2 fases) em L/N estampa `'+'`/`'-'` (fonte 24 Vcc interna). | A |
| 11 | Entrada `10204` (pino (0,0), em cima; `n16=1` ⇒ ativa com `'+'`) ⇒ bit do label0 (`I0.x`). | A |
| 12 | Saída `10205` (pino **(0,24)**, em baixo; `n16=1`): bit do label0 (`Q0.x`, vindo da bobina 10060/61/62 de mesmo nome) ⇒ estampa `'+'` na net. | A |
| 13 | **Avaliação síncrona**: as bobinas comitam juntas na passada 7 do tick (§11.3); cada tick usa a imagem de bits do tick anterior. Tick padrão 100 ms. | A (mecanismo) / M (consequência) |
| 14 | 10202 LOGO / 10203 S7-1200 / 10209.. (CLPs "imagem"): sem pinos extraídos ⇒ fora do contrato. | B |

Correções de dados de pinos (o port deve usar estes, não os JSON antigos):
`10205.p1 = (0,24)` (não 27); `10206.p5 = (12,0)` (não 11); `10060.p2 = (12,0)` (o
`symbol_pins.json` traz B=(-30,18), errado); `10204` tem 1 pino só, (0,0); `6002` pinos
`1`(0,0) `3`(6,0) `2`(0,12) `4`(6,12) (labels na ordem 1,3,2,4).

---

## 2. DSL `ladder/1`

Arquivo `<nome>.ladder.json`. Mesmo envelope do layout topológico (`docs/dsl-layout.md`):
`titulo`, `layout`, `testes`. **Nenhuma coordenada** de símbolo; os únicos números de posição
são os `trilhos` (y dos barramentos de potência), como no DSL atual.

```jsonc
{
  "titulo": "PARTIDA DIRETA EM LADDER",
  "dsl": "ladder/1",
  "layout": {
    "trilhos": {"L1":14,"L2":20,"L3":26,"N":282,"PE":291,"x0":25,"x1":160},
    "fontes":  [ {"id":"X1","classe":"3007","rotulo":"-X","pinos":{"L1":"L1","L2":"L2","L3":"L3","N":"N","PE":"PE"}} ],
    "potencia":[ /* igual ao DSL atual */ ],
    "clp": {
      "id":"CLP1", "classe":"10206", "rotulo":"-CLP",
      "alimentacao": {"fonte": {"id":"X2","classe":"3011","rotulo":"-X2"}},
      "entradas": [ {"operando":"I0.0", "dispositivo":["S0","8001","-S0"]} ],
      "saidas":   [ {"operando":"Q0.0", "serie":[], "carga":["KM1","9000","-KM1"]} ]
    },
    "ladder": {
      "fonte": {"id":"XL","classe":"3008","rotulo":"+L"},
      "trilho_direito": "aberto",
      "rungs": [
        {"id":"r1", "comentario":"liga/desliga com selo",
         "logica": {"serie":[ ["NA","I0.0"], {"paralelo":[ ["NA","I0.1"], ["NA","Q0.0"] ]} ]},
         "saida": ["OUT","Q0.0"]}
      ]
    }
  },
  "testes": [ /* §5 */ ]
}
```

### 2.1 `layout.clp` — a ponte com o hardware
| campo | obrig. | significado |
|---|---|---|
| `id`, `classe`, `rotulo` | sim | CPU; `classe` só `"10206"` em `ladder/1` |
| `alimentacao` | sim | `{"fonte": {id, classe:"3011", rotulo}}` (fonte L/N/PE própria, como o acervo) **ou** `{"trilhos": {"L":"L1","N":"N","PE":"PE"}}` (usa trilhos do layout) |
| `protecao` | não | `[id,"6002",rotulo]` disjuntor bipolar entre a alimentação e L/N da CPU |
| `ip` | não | string final serializada do 10206 (default `"192.128.0.1"`, valor do acervo) |
| `entradas[]` | sim | `{operando, dispositivo, serie?}`: `dispositivo` = folha `[id, classe, rotulo]` de 2 terminais (8000 NA, 8001 NF, 8017 NF do térmico, 8016 NA do térmico, 8012.. fim de curso, 8008.. chave); `serie` = folhas extras em série antes da entrada. Ligação: `+24V (CPU p3) → serie… → dispositivo → 10204(operando)` |
| `saidas[]` | sim | `{operando, serie?, carga}`: `carga` = folha 9000 (bobina) ou 9008 (lâmpada); `serie` = folhas em série (ex.: NF do térmico, NF de intertravamento 7001). Ligação: `10205(operando) → serie… → carga → 0V (CPU p4)` |

Regras da ponte: `operando` de entrada casa com contatos ladder de mesmo nome (via 10204); de
saída, com a bobina ladder de mesmo nome (via 10205). Um botão **NF** físico numa entrada dá
bit **1 no repouso** — no ladder use contato **NA** desse operando para "parar quando pressionar"
(armadilha didática clássica; o validador só avisa).

### 2.2 `layout.ladder`
| campo | obrig. | significado |
|---|---|---|
| `fonte` | sim | `{id, classe:"3008", rotulo}`: alimenta o trilho esquerdo. Cada coluna extra de degraus ganha um 3008 próprio (`<id>~2`…) |
| `trilho_direito` | não | `"aberto"` (default; bobinas com pino B sem fio — único modo visto no acervo, A) ou `"fonte_menos"` (fio vertical ligando os pinos B a uma fonte `3009`; M, confirmar no app) |
| `rungs[]` (alias `degraus`) | sim | `{id, comentario?, logica, saida}` |

**`logica`** — expressão série-paralelo (mesma álgebra do comando v2):
- folha `[tipo, operando]`, `tipo` ∈ `NA` (10050), `NF` (10051), `P` (10052 flanco ↑, B),
  `N` (10053 flanco ↓, B). `ladder/1` exige `NA`/`NF`; `P`/`N` são reservados.
  Desambiguação: array cujo 1º item é **string** = folha (`["NA","I0.0"]`); array de
  arrays/objetos = série.
- `{"serie":[…]}`, `{"paralelo":[…]}` aninháveis; lista solta = série; grupos de 1 somem;
  série-em-série e paralelo-em-paralelo achatam. Pelo menos 1 contato por degrau. Sem ponte
  (rede não série-paralela) — o contato ladder é direcional e o motor não desenha ramos cruzados.

**`saida`** — uma saída ou `{"paralelo":[saída, …]}` (várias bobinas no mesmo nó final):
| saída | classe | labels gravados | conf. | `ladder/1` |
|---|---|---|---|---|
| `["OUT", op]` | 10060 | `[op]` | A | obrigatório |
| `["SET", op]` | 10061 | `[op]` | M | obrigatório |
| `["RST", op]` | 10062 | `[op]` | M | obrigatório |
| `["TON", op, {"tempo":n, "base":"0.1s"\|"1s"\|"10s"\|"100s", "q": op_q?}]` | 10066 | `[op,"","IN","Q",u,str(n)]`, `u` = `3`/`0`/`1`/`2` | M-A | obrigatório |
| `["CTU", op, {"preset":n, "reset": expr, "desce": expr?, "q": op_q?}]` | 10063 | `[op,"","R","C","D","Q",n,n]` | M | opcional (v2) |
| `["TOF"…]`, `["TP"…]` | 10067, 10081 | como TON | B | reservado |

`TON`: o pino Q **sempre** recebe fio até uma bobina OUT de operando `q` (default `op + ".Q"`),
porque Q sem fio estampa na entidade 0 (M). Contatos podem ler o temporizador pelo próprio `op`
(`["NA","T1"]`, A) ou por `q`. Base `"100s"` é o rádio "x 60 Seg" do diálogo (o código usa
×1000 ticks; §11.4).

### 2.3 Operandos
String de 1–15 caracteres, `^[A-Za-z][A-Za-z0-9._:/]*$` (sem `#`/`*`, delimitadores do `.cad`).
Convenção do gerador (o app aceita qualquer string; acervo usa também `B3:L`, `T4:0`, `DN/1`):

| família | exemplo | produzida por | lida por |
|---|---|---|---|
| `I` entrada | `I0.0`..`I1.7` | `clp.entradas` (10204) | contatos |
| `Q` saída | `Q0.0`..`Q1.7` | `OUT`/`SET`/`RST` (e lida pela 10205 de `clp.saidas`) | contatos, 10205 |
| `M` memória | `M0.0`.. | `OUT`/`SET`/`RST` | contatos |
| `T` temporizador | `T1`.. | `TON` (e `T1.Q` pela bobina do Q) | contatos |
| `C` contador | `C1`.. | `CTU` | contatos |

### 2.4 Regras de validação (erro, salvo "aviso")
- V1 todo operando lido por contato é produzido (I por `clp.entradas`, Q/M por OUT/SET/RST, T/C
  pelo bloco).
- V2 no máximo **um** `OUT` por operando; `OUT` e `SET`/`RST` no mesmo operando é erro.
- V3 todo `clp.saidas[].operando` tem bobina (`OUT`/`SET`/`RST`) no ladder; aviso para bobina `Q`
  sem saída física.
- V4 operando ≠ qualquer `rotulo` físico (`-KM1`, `-S1`…), por causa do item 5 de §1.
- V5 operandos de `clp.entradas` e de `clp.saidas` únicos; ids únicos em todo o arquivo.
- V6 `SET` e `RST` do mesmo operando não podem ser verdadeiros juntos em nenhum caso de teste
  (o simulador reporta `INDEFINIDO`).
- V7 (aviso) contato `NF` de uma entrada ligada a dispositivo NF.
- V8 tudo cabe na folha (`tools/sheet.json`: x ≤ 455, y ≤ 305) — ver §4.

---

### 2.5 Extensões implementadas (Python)
- `layout.potencia` = `{"tipo":"dj_comum","fonte":{"classe":"3005"},"disjuntor":[id,"6003","DJ1"],"motores":[{"contator","termico"?,"motor"}]}`:
  um disjuntor + n colunas contator → (térmico) → motor; o 6002 de `clp.alimentacao.protecao` e o aux `8016` usam o MESMO rótulo (o app alterna todos).
- TON **em linha** na série principal: `["TON","T1",{"tempo":1,"base":"1s"}]` (IN = nó anterior, Q segue a série, +6 em y).
- `clp.saidas[].carga` pode ser lista (cargas em paralelo, ex.: bobina + lâmpada). `textos`: classe 8.
- Medido no app: bobina ladder, TON em linha, SET/RST e entrada/saída 10204/10205 funcionam; tick ≈ 100 ms.

## 3. Simulação (contrato do `cad_test`/netlist em Rust)

### 3.1 Modelo lógico (direto da DSL) — o "esperado"
Estado: bits (todos 0 no início, salvo `inicial`), acumuladores de TON/CTU, estado físico dos
contatores/lâmpadas. **Um tick** (100 ms):
1. **Hardware de entrada**: CPU alimentada ⇔ a alimentação (fonte/trilhos e `protecao`, que
   começa **fechada** como os demais disjuntores no `netlist_sim` atual) entrega fase+N. Para cada
   entrada: `bit[op] = CPU ∧ todos os elementos da cadeia conduzem` (botão NA conduz se
   acionado; NF conduz se **não** acionado; 8017 conduz se o térmico **não** disparou).
2. **Degraus**, todos com a imagem `bits_ant` do tick anterior (síncrono): `v = logica(bits_ant)`
   (NA: `bit`, NF: `¬bit`, série = ∧, paralelo = ∨). `OUT`: `bit[op]=v`. `SET`: `v ⇒ bit[op]=1`.
   `RST`: `v ⇒ bit[op]=0`. `TON`: `v ? acc+=1 : acc=0`; `bit[op] = bit[q] = (acc ≥ T)` com
   `T = max(1, tempo × {0.1s:1, 1s:10, 10s:100, 100s:1000})`.
3. **Hardware de saída**: `energizada[carga] = CPU ∧ bit[op] ∧ série conduz` (série física usa o
   estado de **contatores do tick anterior**, ex.: NF 7001 de intertravamento).
4. Polos (2001 de mesmo rótulo da bobina) seguem as bobinas físicas; motor gira se as 3 fases
   chegam (como hoje).

**Imagem em t=0** (antes de aplicar as `entradas` do caso): bits = `inicial` (1) ∪ bits de
entrada calculados com o hardware **em repouso** (nenhum dispositivo acionado); físicos = saídas
avaliadas com esses bits (contator de saída com bit 1 já começa energizado). Sem isso o selo de
um caso com `inicial` cairia no 1º tick (entradas ainda 0) — artefato de teste, não do circuito.
Em `sequencia`, só o 1º passo parte dessa imagem; os seguintes partem do regime anterior.

**Regime**: repete ticks com as entradas fixas até que (bits, físicos) não mudem por 2 ticks
seguidos (máx. 2000 ticks, cobre TON de 100 s). Ciclo detectado ⇒ `status:"OSCILA"`. SET∧RST
verdadeiros no mesmo operando e tick ⇒ `status:"INDEFINIDO"`.

### 3.2 Modelo geométrico (do `.cad` gerado) — a conferência
Deve dar o mesmo resultado que 3.1. Nets por geometria (§9.2). Por tick, chars `'0'` em todos os
fios; fontes estampam (3007/3011 fases e N; 3008 `'+'`; 3009 `'-'`; CPU alimentada estampa `'+'`
em p3 e `'-'` em p4); relaxação de 8 passadas: contatos elétricos copiam nos dois sentidos,
contatos ladder só de A→B; na passada 7 comitam bobinas 9000 (`(+,-)`, fase/N…), bobinas
ladder (A=`'+'` ∧ B∈{sem fio, `'-'`}), entradas 10204 (net = `'+'`), TON/CTU. Saídas 10205 e
bobinas ladder repassam o bit por label0 como em §1. A verificação estrutural do netlist inclui:
cada degrau desenhado reproduz a expressão de `logica` (série/paralelo entre o nó do trilho e o
nó da bobina) e cada 10204/10205 está na cadeia física declarada.

---

## 4. Geometria (regras do motor de layout; medidas do acervo)

Unidades do `.cad`; grade de 3. Caixas (dx,dy,w,h): 10050/10051/10060/10061/10062 `(-3,-9,15,9)`;
10066 `(-3,-9,21,15)`; 10063 `(-3,-9,21,21)`; 10204/10205 `(-12,-3,12,27)`; 10206
`(-12,-3,30,27)`; 3008/3009 `(-12,-9,6,3)`; 3011 `(-12,-9,18,3)`. Flags gravadas (acervo):
ladder `n19=1`, demais 0; 10204/10205 `n0=n1=n2=1, n16=1, n19=1`; 10206 `n19=1` + string `ip`;
3008 tudo 0; 3011 `n19=0`.

**Zonas** (o motor escolhe x; nada vem da entrada): A = potência pendurada nos trilhos
`L1..L3/N/PE` (motor atual), à esquerda; B = hardware do CLP; C = ladder, à direita. Se C não
couber em altura, os degraus continuam numa 2ª coluna à direita com `3008` próprio; se não couber
em largura, C desce para baixo de B. Erro explícito se ainda assim não couber.

**Ladder (zona C)**, como no `.cad` intercalado do acervo:
- trilho: `3008` em (xL, y₁−9) + fio 4018 vertical até abaixo do último degrau; **4001** em cada
  derivação (xL, yᵢ). Trilho → 1º contato: fio de 9.
- série: passo 21 (símbolo 12 + fio 9), todos no y do degrau; bobinas de todos os degraus de uma
  coluna alinhadas no mesmo x (depois do degrau mais largo).
- paralelo: ramos empilhados a +18 em y, alinhados pelo início do grupo; nós de entrada/saída no
  meio do fio entre elementos, com verticais e **4001** em todo T. Grupo mais curto completa com
  fio até o nó de saída.
- passo entre degraus: 18 × (ramos extras) + 21. Pino B das bobinas: sem fio (`aberto`).
- TON: IN no nó final do degrau; Q (15,6) → fio de 6 → bobina `q` em (x+21, y+6).

**Hardware (zona B)**, como no acervo (CPU em (xc,yc)):
- alimentação: 3011 em (xc, yc−27) com L/N/PE caindo direto em p1/p2/p5 (com `protecao`, o
  6002 fica entre eles: 1/3 em cima, 2/4 embaixo).
- barra +24 V (4018) horizontal acima dos dispositivos, ligada a p3; barra 0 V (4019) abaixo das
  cargas, ligada a p4; 4001 em todo T.
- entradas 10204 na linha da CPU, x = xc + 36 + 18k; dispositivo de cada entrada logo acima
  (pino B → pino da entrada, fio vertical), `serie` empilhada acima dele.
- saídas 10205 numa linha abaixo (y ≥ yc + 30), x alinhado em passo 18; pino (0,24) → `serie` →
  carga (A1 em cima) → 0 V.
- regra geral do repositório: todo pino ligado, salvo o pino B das bobinas ladder em
  `trilho_direito:"aberto"` (exceção explícita do gate) e o `ip` do 10206.

Estimativa de ocupação dos exemplos (folha 455×305): partida direta ≈ x 25..330, y 14..291;
reversão ≈ x 25..400; intercalada ≈ x 25..445 (ladder com 6 contatos no degrau mais largo:
xL+9+6·21+15 ≈ xL+150). Se o port medir mais que a folha, a 2ª coluna/faixa da regra acima
resolve.

---

## 5. Testes (`testes` no `.ladder.json` e nos casos)

Formato = o atual (`entradas` com ids físicos, `true` = acionado; térmico `true` = disparado),
mais:
- `inicial`: lista de **operandos** com bit 1 no início (físicos seguem no 1º tick);
- `esperado`: bobinas físicas (9000) energizadas no regime; `esperado_lampadas`: 9008 acesas;
- `esperado_bits` (opcional): `{op: 0|1}` conferidos no regime;
- `sequencia` (opcional): lista de passos `{entradas, esperado, esperado_lampadas?,
  esperado_bits?, nome?}`; o estado passa de um passo ao seguinte (cada passo roda até o regime;
  botões não listados no passo estão soltos). Quando há `sequencia`, `entradas`/`esperado` do caso
  não existem;
- `status`: `OK` | `OSCILA` | `INDEFINIDO` (`CURTO` como hoje).

---

## 6. Exemplos e casos

| exemplo | o que exercita | testes |
|---|---|---|
| `tools/examples/partida_direta.ladder.json` | CLP + 3 entradas (S0 NF, S1 NA, RT1 NF) + 3 saídas (KM1, H1, H2); selo em ladder | 8 |
| `tools/examples/reversao.ladder.json` | intertravamento lógico (NF de Q0.x) **e** elétrico (7001 em série na saída); inversão de fases na potência; caso `OSCILA` | 12 + sequência de 6 passos |
| `tools/examples/intercalada.ladder.json` | memória SET/RST (`M0.0`) alterna M1/M2 a cada partida; 2 térmicos | 9 + sequência de 12 passos |

Os esperados foram conferidos com uma implementação descartável do modelo §3.1 (fora do
repositório, por decisão de escopo: o simulador será escrito em Rust). Todos os casos passam,
inclusive o `OSCILA`.

Casos de avaliação: `tools/eval/casos/ladder/*.json` (mesmo formato dos casos atuais; `golden`
aponta o exemplo `.ladder.json`). Ficam em subpasta para não entrarem no `run_eval.py` atual.

---

## 7. Pendências no app (só quando o usuário pedir o Wine)
1. Bobina 10060 com B aberto energiza; `trilho_direito:"fonte_menos"` (3009) também.
2. CPU 10206 alimentada por 3011 direto dá `+`/`-`; entrada `n16=1` lê 24 V; saída `n16=1`
   energiza 9000/9008 ligados ao p4.
3. SET/RST com `n7=0` mantêm `M0.0` entre partidas (intercalada).
4. Contato `["NA","T1"]` segue o TON; Q sem fio estampa na entidade 0 (por isso exigimos fio).
5. 6002 (`protecao`) inicia aberto ou fechado.
6. Latência/oscilação do intertravamento síncrono (reversão, S1+S2 "juntos").
7. Faixa/coluna extra de ladder com 3008 próprio.
