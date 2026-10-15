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
