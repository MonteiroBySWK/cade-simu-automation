# Engenharia reversa do CADe_SIMU — relatório consolidado

**Objetivo:** entender o modelo real (formato, conectividade, simulação) para
(a) gerar `.cad` que **simulam de verdade**, (b) ter **teste 100% confiável**
(sem depender de GUI) e (c) **impedir curtos**.

**Alvo:** `CADe_SIMU 4.0 [BR].exe` — PE32 i386, VC++6 **debug** (MFC Doc/View).
RTTI: `CCADe_SIMUDoc`, `CCADe_SIMUView`.

---

## 1. Resumo executivo (o que já sabemos)

- O `.cad` é texto; header + entidades + rodapé, com **formatos de `sprintf`
  embutidos no EXE** que confirma nosso parser.
- Cada símbolo tem **até 6 pinos** (nome → net). Nossa leitura atual
  (`nums[21]/[22]`) cobre só **2** → símbolos trifásicos ficam incompletos.
- **Conectividade é por NET** (nó elétrico), não por geometria — mas os dois
  coexistem (bobina com `A=B=0` conecta por **ponto**). Ainda **não 100%
  confirmado** qual é autoritativo (ver §5).
- Existe uma **biblioteca de símbolos embutida** (sem `.lib` no disco) que define
  os pinos por classe.
- **Falta**: o caminho de **leitura** (parser), o **mapeamento dos ints → nets**, e
  a **rotina de simulação** ("Simular").
- **Experimento no app**: inconclusivo (ver §5).

**Confiança:** formatos de serialização = **alta**; biblioteca = **alta**
(localizada, não decodificada); semântica de conexão = **média/baixa**.

---

## 2. Ferramentas e como reproduzir

- Ghidra headless: `/opt/ghidra/support/analyzeHeadless` (GUI: `/opt/ghidra/ghidraRun`).
  **PyGhidra NÃO está habilitado no headless** → scripts têm de ser **Java**
  (GhidraScript). Python falha com "Ghidra was not started with PyGhidra".
- Projeto Ghidra: `/tmp/opencode/ghidra_proj` (nome `CADE`), recriável.
- Scripts em `tools/ghidra/`:
  - `find_conn.java` — strings-chave + xrefs.
  - `dump2.java` — formatos de serialização + RTTI + decompilação.
  - `dump3.java` — decompila funções que referenciam os formatos.
  - `dump4.java` — caça o **parser** (formatos de leitura) e a netlist.
  - `dump5.java` — caça a **biblioteca de símbolos**/"Simular".
  - `dump6.java` — decompila uma função por endereço (recebe o addr).

```bash
EXE="/home/monteiro/Downloads/CADe_SIMU 4.0 [BR]/CADe_SIMU 4.0 [BR]/CADe_SIMU 4.0 [BR].exe"
/opt/ghidra/support/analyzeHeadless /tmp/opencode/ghidra_proj CADE -import "$EXE" -analysisTimeoutPerFile 3600   # ~150s
/opt/ghidra/support/analyzeHeadless /tmp/opencode/ghidra_proj CADE -process "CADe_SIMU 4.0 [BR].exe" \
  -noanalysis -scriptPath tools/ghidra -postScript dump6.java 0087aca0
```

---

## 3. Formatos de serialização (embutidos no EXE) — CONFIANÇA ALTA

- **Header** (`0x00b6f5e0`):
  `CADe_SIMU*%1d*%1d*%1d*%1d*%1d*%1d*%1d*%1d*%3d*%3d*%0.4f*%1d*%1d*%3d*%3d*%1d*%1d*%4d$$$`
  → 8 ints + 2×`%3d` + 1 float + 2 ints + 2×`%3d` + 2 ints + 1 `%4d`.
- **Entidade** — 2 variantes (em `FUN_00432710` = `CCADe_SIMUDoc::Serialize`,
  caminho **store**; e `FUN_004315f0` = store "Save As", quase idêntico):
  - **Normal**: `*%d*%d#` + **10** rótulos `%s` + `*%d`×**23** + `#%s`
  - **Especial**: `*%d*%d#` + **11** rótulos `%s` + `*%d`×**24** + `#%s`
    (IDs especiais: `0x41c`, faixa `0x2903..0x2937`, `0x431`.)
  - **Texto = id 20000.**
- **Conexões do símbolo** (`0x00b723c4`): `%2s-%1d-` repetido até 6× → **(pino
  nome, net)** ×6 + preenchimento `  -0-`. É o campo `#%s` final da entidade,
  emitido por **IDs tipo-conector**: `0x274d`, `0x274e`, `1000`, `0x3e9(1001)`,
  `0x1b68(7016)`, `0x1b6a(7018)`, `0x177f(6015)`, `0x1780(6016)`, `0x434(1076)`,
  `0x1b6b(7019)`. (Variante `%2s-%1d-%2s-%1d-%1d` em `0x00b73144`.)
- **Rodapé**: `&&&` + `*%d`×9 + `*%3d*%3d` + legendas `*%-11s*%-25s…` + `*%1d`×14.
- **Exemplo real** (único arquivo com a string: `corpus/CADe_S1.cad`):
  `*2*7018#C1##A1#A2#1#2#3#4#5#6*…*# 5-1- 6-1-13-1-14-1-21-1-22-1-  -0-  -0-  -0`
  → pinos `5,6,13,14,21,22` no net 1.

> Lembrete: nosso `cade_cli` já faz **round-trip byte-idêntico** nesses formatos
> (114/114 do acervo). O RE aqui serve para **gerar** circuitos corretos, não para
> preservar.

---

## 4. Modelo de objeto e funções

- **SoA**: o doc guarda entidades em **arrays paralelos** indexados por entidade —
  `+0x2024` = id (limite **2000**), `+0x5ea4`, `+0x7de4`, `+0x158a4` = outros
  campos. Texto é uma entidade sintética id 20000 (injetada no save se ausente).
- **Writers**: `FUN_00432710`/`FUN_004315f0` (doc→arquivo), `FUN_00878080`
  (header), `FUN_00886680`/`FUN_008907b0` (string de conexões),
  `FUN_008ab4a0`/`FUN_008aa1b0` (`.lib`).
- **Biblioteca de símbolos embutida** = **`FUN_0087aca0`** (~2.6k linhas):
  referencia todos os nomes ("Contactor", "Motor trifase", "Pulsador",
  "Cable fase", "Contacto NA/NC", "Contactor I/II/III/IIII", "Motor Dahalander",
  "Contactos ON/OFF Delay"…). Marca a **máscara de pinos** do tipo em campos do
  objeto (`+0xd84..0xd94`, `+0xdb8..0xdc0`, `+0xdcc/0xdd0/0xdd8`, `+0xde0`) com 0/1.
  Famílias: `FUN_0088e7f0` (cabos), `FUN_00899910` (aux NA/NC), `FUN_008c8f40`
  (ON/OFF delay), `FUN_0089d050` (motores). `Simbolo.cpp` em `FUN_008b50c0`.
- Nets dos pinos vivem em campos do objeto (ex.: `+0xd44,+0xd48,+0xd74,+0xde4…`),
  **não só** em `nums[21]/[22]`.

---

## 5. Conectividade: net × geometria (CONFIANÇA MÉDIA)

- **Net é o nó elétrico**; a string de conexões lista (pino, net). Símbolos até 6 pinos.
- **Geometria** (fio tocando pino) também conecta: bobina com `A=B=0` conecta por
  **ponto** (plug net19 encostando o pino). Hipótese: **curto = fio encostando um
  pino alheio**.
- **Evidência estatística** (`tools/re_connectivity.py`, 108 arquivos):
  - só **76%** dos endpoints-de-fio-sobre-pino têm net igual → **nets e geometria
    NÃO são redundantes**;
  - **67.9%** dos pinos não têm fio no ponto exato (com o mapa de pinos **ruidoso**
    por moda — o offset dominante `(0,12)` é artefato de orientação/multi-pino).
- **Offsets reais observados** (amostra manual em `partidadireta.cad`):
  `8017` A=(0,−3) B=(0,+12); `8001` A=(0,−12) B=(0,+12); `7000` A=(0,−6) B=(0,+18);
  `6010` A=(0,−3) B=(0,+21); `9000` (bobina) conecta por ponto.
- **Experimento no app (inconclusivo):** zerei todos os nets de um `.cad`, abri no
  Wine e salvei (Ctrl+S) → os nets **permaneceram 0**. Não decide se o app
  recomputa (pode não ter salvado) → a questão **net × geometria segue aberta**.

---

## 6. Em aberto (próximos passos de RE)

- [ ] **Caminho de LEITURA** do `Serialize` (parser `sscanf`/`strtok`) — o store
      está mapeado; falta o load.
- [ ] **Mapear os 23/24 ints** da entidade → os 6 nets por pino (correlacionar com
      a ordem de pinos da `FUN_0087aca0`).
- [ ] **Decodificar a biblioteca** (`FUN_0087aca0`): extrair pinos + coordenadas por
      classe (a "máscara de pinos" 0/1 + posições).
- [ ] **Rotina de simulação** ("Simular"): como agrupa pinos em nós (net × geometria).

---

## 7. Plano após o RE (para os objetivos)

1. **Pinos exatos** por classe → `tools/symbol_pins.json` corrigido (6 pinos + coords).
2. **Roteador seguro**: grade de ocupação (keep-out do corpo+pinos), fios com
   endpoints **exatamente** nos pinos → **zero curto por construção**.
3. **Netlist fiel** (nós por net/geometria) + `cad_test` (verificação funcional).
4. **Harness E2E**: dirigir "Simular" de forma determinística → fecha o teste "100%".

---

## 8. Notas de licença

O CADe_SIMU é **shareware**. Este trabalho é de **interoperabilidade/formato** (para
editar os próprios arquivos do usuário); **não redistribuir** o binário nem dados
derivados dele. O RE fica documentado aqui para propósito de compatibilidade.

---

## 9. Resultados da RE dirigida (Ghidra) — 15/10/2026

Método: `tools/ghidra/srv.java` (GhidraScript "REPL": mantém o programa e o
decompilador abertos; comandos `dec/xref/str/dis/bytes/callers/callees/imm/immaddr/fn`
via arquivos `*.cmd`). Evidência = endereços do EXE (imagem base 0x400000).

### 9.1 Layout da entidade em memória (SoA) e mapeamento dos ints — CONFIANÇA ALTA
Doc (`this`) guarda arrays de 2000 entradas (stride 0x1F40 bytes). Ordem exata de
serialização (push dos args do `sprintf` em `FUN_00432710` @0x432e8d, formato
normal `0xb4cdac`... e loader `FUN_0042c290`):

| campo do .cad | array (+off) | significado |
|---|---|---|
| `*seq` | +0xe4 | índice original da entidade |
| `*id` | +0x2024 | classe (id do símbolo) |
| labels 0..9 (10, ou 11 p/ especiais) | +0x3f64, +0x21424, +0x465e4, +0x48524, +0x4a464, +0x4c3a4, +0x4e2e4, +0x50224, +0x52164, +0x540a4 (+0x55fe4) | rótulo/designação (label0), nomes dos pinos (label2..7 = pinos na ordem do desenho), etc. |
| n0..n5 | +0x57f24,+0x59e64,+0x5bda4,+0x5dce4,+0x5fc24,+0x61b64 | flags "mostrar rótulo do pino k" (1 = mostra o nome; 0 = escondido) — NÃO são nets |
| n6,n7 | +0x63aa4, +0x659e4 | flags/estado de usuário (ex.: posição de chave/seletor) |
| n8,n9 | +0x5ea4, +0x7de4 | X, Y (origem do símbolo; 1 unidade = 1 px da grade) |
| n10,n11 | +0x9d24, +0xbc64 | X2, Y2 (fios/linhas; símbolos 0) |
| n12..n15 | +0xdba4,+0xfae4,+0x11a24,+0x13964 | caixa de seleção: dx, dy, w, h (relativos a X,Y) |
| n16 | +0x177e4 | usado p/ id de imagem (classe 9 = figura) |
| n17 | +0x19724 | **orientação**: 0..3 = rotação 0/90/180/270; 4..7 = idem espelhado (ver 9.4) |
| n18 | +0x1b664 | variante/estado |
| n19 | +0x1d5a4 | mostrar label0 (designação) |
| n20 | +0x1f4e4 | mostrar 2º texto (valor) |
| n21,n22 | +0x23364, +0x252a4 | "net" do fio (fios) / **índice do fio no pino A e B** em runtime (ver 9.3) |
| n23 (só especiais) | +0x67924 | extra |
| `#%s` final | +0x69864 | string livre (propriedades; só classes especiais/texto) |

`FUN_0042c290` (Abrir arquivo, string `Archivos CADe_SIMU (*.cad)`) é um parser
char-a-char (`atoi`) que apenas **preenche os arrays**; **não recalcula nets** ao abrir.
Validação: só confere `CADe_` + `SIMU` no início (sem checagem de valores).

### 9.2 Conectividade no Simular: GEOMETRIA, não nets do arquivo — CONFIANÇA ALTA
- `FUN_0043d540` (Iniciar simulação, seta `+0xa1b60=1`): para toda entidade viva
  (id>0, não apagada, id≠8) **zera n21 (se id≠1) e n22**, o char de fase (+0x7156c)
  = '0', estados ON, etc. => **nets gravados no arquivo são descartados**.
- `FUN_00869c80` (montagem dos nós): zera n21 dos "tipos fio" {4000, 4009, 4010,
  4018, 4019, 10104/05/06, 10112} e dos marcadores 4001/4002/4003/4004/4012; contador
  de net = 1; 2 passadas; para cada fio sem net: net novo + propagação
  (`FUN_0086a4a0`, `FUN_0086b5a0`, `FUN_0086c4a0`, `FUN_0086bae0`).
- Regras (decompiladas):
  1. **Fio–fio**: une se algum **extremo** de um coincide com algum extremo do outro
     (`FUN_0086a4a0`, comparações exatas de inteiros × zoom).
  2. **Ponto de junção 4001 (e 4012)**: adota a net do fio cujo segmento
     (horizontal ou vertical) **contém** o ponto (`x1<=px<=x2` com `y1==py`, ou
     vice‑versa) e propaga para todos os fios com extremo no ponto (`FUN_0086b5a0`,
     `FUN_0086bae0`). => **T / cruzamento só conecta se houver 4001 no ponto**;
     fio encostando no meio de outro SEM 4001 NÃO conecta. O teste assume
     x1<=x2 e y1<=y2 (normalizar ao gerar).
  3. **Marcadores 4003/4004**: adotam a net do fio sob eles (`FUN_0086c4a0`).
  4. **Pino de símbolo ↔ fio**: nas rotinas de desenho de cada classe, em modo
     simulação, varre os fios e compara o **ponto-pino** com `(X1,Y1)` ou `(X2,Y2)`
     do fio (igualdade exata, tipos 4000/4009/4010/4018/4019). **Pino no meio de um
     fio não conecta**; só extremo. O fio achado dá o "char de fase" ('1','2','3',
     'N','+','-','R','A','Z','0'); pares incompatíveis (1×2, 1×N, +×-...) ⇒ curto.
- Conclusão: o simulador é por **geometria** (extremo-a-extremo + 4001). As nets
  `nums[21..22]` do arquivo são **irrelevantes** para simular (só cosméticas até o
  Simular recalcular). O teste `cad_test/netlist_sim` deve calcular nets por
  geometria seguindo as regras acima, não ler nums[21/22].

### 9.3 Semântica de n21/n22 — CONFIANÇA ALTA
Fios: n21 = id da net (arquivo = último cálculo do editor). Símbolos: n21/n22 =
nets dos pinos A e B (1º e 2º pinos) no momento do salvar; em runtime viram índice
do fio. Pinos 3..6 não têm campo de net no arquivo (conexão só por geometria).

### 9.4 Orientação (n17) — CONFIANÇA MÉDIA-ALTA
Interpretador de desenho `FUN_008462f0` (comandos de 4 letras `PUNT LINE ELIP ARCO
CUER POLI RELL NUME TEXT`, coords "+ddd" em **1/5 px**) aplica a cada ponto (x,y):
`n17=0:(x,y)  1:(-y,x)  2:(-x,-y)  3:(y,-x)  4:(-x,y)`; 5..7 = espelho+rotação
(não lidos linha a linha; ver incerteza). Exemplo no acervo: 3001 com n17=3 tem caixa
(dx,dy,w,h)=(-9,-6,3,12) em vez de (-12,-9,6,3).

### 9.5 Pinos nas rotinas de desenho — CONFIANÇA MÉDIA (método validado em 9008 e 9000)
- Cada classe tem uma função de desenho (despachada por `FUN_0040d2b0` por
  `if (id==X) call thunk`; tabela classe→thunk extraída do desassembly, ex.: 1000→
  0x402581, 2001→0x4011ef, 3004→0x401a5a, 6007→0x4020e5, 6009→0x4032c9, 7000→
  0x40169a, 8017→0x4016c2, 9000→0x4028ab, 9008→0x402fef).
- O ponto-pino é o último `NUME,+xxx,+yyy` executado (globais `0xbd9660/0xbd9664`
  setados em `FUN_008462f0`): **pino = (x'-5, y' se y'<=0 senão y'+15)** em 1/5 px,
  ÷5 → px relativos a (X,Y) (rotação 0). Ex.: bobina 9000/lâmpada 9008:
  `NUME,+005,+000`→(0,0); `NUME,+005,+045`→(0,60)/5=(0,12) ✓ (bate com o acervo).
- Estatística do acervo (112 arquivos, endpoints de fio a ≤40 px) corrobora:
  2001/6007: pinos em x∈{0,6,12}, y∈{0,12}; 6009: x∈{0,6,12}, y∈{0,21};
  1000: x∈{0,6,12,18}, y=0 (U1,V1,W1,PE); contatos/botões 7000/8000/8001/8017: (0,0),(0,12).

---

## 11. Semântica de simulação por classe (Ghidra, 15/10/2026)

Entrega: **`docs/classes-papeis.json`** (366 classes: todas de `pinos-binario.json` + as do
despacho `FUN_0040d2b0` + as nomeadas nos diálogos). Gerado por
`tools/ghidra/gen_classes_papeis.py` a partir de três extrações do `srv.java` (novos comandos
`cmpstr` e `sem`). Chaves por classe: `nome` (espanhol, string do binário), `aba`, `papel`,
`pinos` (nomes padrão na ordem de desenho = p1..pN de `pinos-binario.json`), `contatos`
(`[{pinos:[a,b], fecha_quando:"estado==1|0|sempre"}]`), `aciona_por`, `estado_inicial`,
`parametros`, `designacao_padrao`, `evidencia`, `confianca` (`alta|media|baixa`;
`nome_ausente_no_binario:true` = nome deduzido).

### 11.1 Método
- **Nomes**: `FUN_0087aca0` (OnInitDialog das propriedades) faz `if (DAT_00bd95cc == classe)
  SetWindowText("nome")` → 159 classes. `srv cmpstr 00bd95cc` varre o programa inteiro por
  `CMP [0x00bd95cc],imm` + `PUSH string` seguinte (outros diálogos: `FUN_00899910` aux/lógica,
  `FUN_00888e00` sensores, `FUN_008c8f40` temporizadores, `FUN_008a4d20` PLC) → +120.
  Sem nome no binário (só pinos): 8016..8022, 1008.., 9040..9045 etc. (fallback marcado).
- **Papel**: `srv sem <funções de desenho>` lista, em ordem, as strings empurradas (rótulo
  padrão, nome de cada pino antes do seu `NUME`), os testes `CMP [ent+0x78a9c],v` da etapa de
  propagação (= condição de condução), as classes comparadas e as chamadas `Ordinal_812`
  (CString `==`, comparação de rótulo). 12 funções decompiladas linha a linha para validar.

### 11.2 Estado em runtime (arrays SoA, stride 4 por entidade) — CONFIANÇA ALTA
| offset | significado |
|---|---|
| `+0x78a9c` | **estado** (1 = acionado/energizado). Contatos testam este campo |
| `+0x7a9dc` | estado anterior (detecção de borda: carga energiza quando `novo && ant∈{0,-1}`) |
| `+0x2eee4` | contador do temporizador (ticks restantes) |
| `+0x30e24` | **saída temporizada** do temporizador (copiada aos contatos 7004..7015) |
| `+0x7156c` (stride 0xf) | char de tensão do **fio** |
| `+0x8e25c`,`+0x8f1fc`,`+0x9019c`… (stride 2) | char visto no pino 1, 2, 3… do símbolo |
`FUN_0043d540` (Play) zera todos esses campos → **estado_inicial = 0 para todas as classes**.

### 11.3 Modelo de simulação — CONFIANÇA ALTA (decompilado)
- **Tensão = char propagado**. Fonte estampa `'1','2','3','N','P','+','-'` (L1,L2,L3,N,PE,+,-)
  no fio do pino. Cada elemento fechado copia o char do fio de um pino para o fio do outro
  (se este estiver `'0'`), marcando a origem com `'*'` (`FUN_005b00d0` etc.).
- **Relaxação**: `OnDraw` percorre todas as entidades **8 passadas** (`DAT_00bd959c=0..7`,
  `FUN_0040d2b0` @0x41e9a4). Só na **passada 7** cargas comitam estado e temporizadores contam.
  Cada `WM_TIMER 1` (`FUN_008691f0`) zera os chars dos fios e redesenha.
- **Contato** (NA/NC/polos): conduz se `estado == 1` (NA) ou `estado == 0` (NC) — lido do
  `CMP` na etapa de propagação: 7000/8000/8016/2001 `==1`; 7001/8001/8017 `==0`;
  NA-NC (7002/8002/8018) pinos `11,13,12,14` → 11-12 `==0`, 13-14 `==1`; comutado
  (7003/8003/8019) `11,12,14` → 11-12 `==0`, 11-14 `==1`.
- **Carga energizada** (bobina 9000, temporizador 9004, lâmpada 9008, `FUN_006292a0`/
  `FUN_0062dbe0`/`FUN_006367b0`): par de chars nos 2 pinos ∈ {(fase,N), (N,fase),
  (fase_i,fase_j) i≠j, (+,-), (-,+)}; lâmpada também (+,N). **Não há "fase estampada" na
  lâmpada**: ela só lê os dois lados. Lâmpada sem retorno estampa marcas de carga-em-série
  (`'R','S','T'` / `'A','B','C'`, `'W'`) no lado aberto; duas cargas em série acendem com
  **meia luz** (flag `local_84`, pares com `'Z'`/`'B'`) — confiança média.
- **Acionamento por rótulo**: a bobina, na passada 7, copia seu estado a toda entidade cujo
  **label0 é igual** (Ordinal_812) e cuja classe ∈ {2000,2001,2002,2006,2008} (polos) ∪
  {7000..7003} (auxiliares). Temporizadores copiam também a 7004..7007 (9004), 7008..7011
  (9005), …, mas com o valor de `+0x30e24` (temporizado).
- **Entradas (clique, `FUN_0043ee20`)**: pulsadores 8000..8007, fins de curso 8012..8015, 8023
  e sensores 7500..7605 → `estado=1` ao pressionar (momentâneo) e propagam a mesmo rótulo;
  interruptores 2003..2005/2007, 8008..8011, 8022, fusíveis/seccionadores 5000..5009,
  disjuntores 6000..6020 → **alternam**; 8021 cicla 0→1→2; **relé térmico 6007**: clique
  alterna e copia o estado para 8016..8019 de **mesmo rótulo** (os polos 1-2/3-4/5-6 do 6007
  **sempre conduzem**).
- **Consequências p/ o gerador/simulador**: disjuntores/seccionadores (6000..6020,
  5005..5009) e interruptores começam **abertos** (conduzem com estado==1; inicial 0) —
  confiança média (validar no app); fusíveis 5000..5004 conduzem com estado==0 (íntegros).
  NC do térmico (8017) fecha no repouso. Contato/polo só é comandado por bobina de **rótulo
  idêntico** (string exata, incl. o `-`).

### 11.4 Temporizadores — CONFIANÇA ALTA (código) / MÉDIA (unidade "x60")
- Classes: **9004** ON-delay (Temporizador a la conexión), **9005** OFF-delay, **9006**
  ON+OFF, **9007** intermitente, **9015** gerador de pulsos; contatos **7004..7007** (ON:
  NA 67-68, NC 55-56, NA-NC, comutado), **7008..7011** (OFF), **7012..7015** (ON/OFF). CLP:
  10066..10069, 10081; relé de zócalo 7017; blocos 7020/7021 ("Contactos ON/OFF Delay")
  acoplados ao contator 7018.
- Ligação contato↔temporizador: **por rótulo (label0 igual)**, como bobina↔contato.
- 9004 (`FUN_0062dbe0`, passada 7): na borda de energização `estado=1` e
  `contador = atoi(label5) × mult(label4)`; a cada tick `contador--`; quando `<1`,
  `saida(+0x30e24)=1`. Desenergizou: `estado=saida=contador=0` (reset imediato). Contatos
  7004.. recebem `saida`; contatos instantâneos 7000..7003 e polos recebem `estado`.
- **Tempo** = label5 (6º rótulo; no `.cad` `#A1#A2#0#5#` → unidade `0`, tempo `5`).
  **Unidade** = label4 ∈ `'3'`→×1, `'0'`→×10, `'1'`→×100, `'2'`→×1000 ticks; diálogo
  (`FUN_008c8f40`, rádios) mostra "x 0,1 Seg / x 1 Seg / x 10 Seg / x 60 Seg" ⇒ com tick de
  100 ms: 0,1 s / 1 s / 10 s / **100 s** (o "x60" da UI não bate com ×1000 — inconsistência
  do app). `atoi` ⇒ fração ("0.5") vira 0 (comuta no 1º tick).
- **Tick** = `SetTimer(1, 1000 − 18×vel)` ms; `vel` = `DAT_00b80804` = **último `%4d` do
  header** (`FUN_00878080`), padrão 50 ⇒ **100 ms**.

### 11.5 Confiança por item
| item | conf. | evidência |
|---|---|---|
| contatos NA/NC/NA-NC/comutado (7000-7003, 8000-8003, 8016-8019) | alta | CMP na propagação, 4 decompiladas |
| polos 2000-2002/2006/2008 por rótulo da bobina | alta | `FUN_006292a0` + `FUN_00516240` |
| bobina 9000 / lâmpada 9008: energiza c/ tensão entre pinos | alta | decompilado |
| lâmpada meia-luz em série | média | decompilado parcialmente |
| temporizador 9004 (borda, contador, label4/5, tick) | alta | `FUN_0062dbe0`, `FUN_008691f0` |
| 9005/9006/9007 (OFF/ON-OFF/intermitente) | média | mesma estrutura (sem), não lidos linha a linha |
| 6007 polos sempre fechados; clique propaga a 8016-8019 | alta | `FUN_005727b0`, `FUN_0043ee20` |
| disjuntores/seccionadores iniciam abertos | média | CMP `==1` + zeragem no Play; falta prova no app |
| motores 1000.. (gira com fases distintas) | média | campo 0x7a9dc, não lido linha a linha |
| sensores 7500.., pneumática 10500.., PLC/GRAFCET/lógica 10000.. | baixa | só nome + pinos + família |
