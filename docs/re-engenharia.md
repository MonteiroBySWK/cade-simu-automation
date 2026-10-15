# Engenharia reversa do CADe_SIMU (RE)

Objetivo: **entender o modelo real** (formato/estrutura, conectividade, simulação)
para (a) gerar `.cad` que **simulam de verdade** e (b) ter **teste 100% confiável**
(sem depender de GUI) e **impedir curtos**.

## Ferramentas
- Ghidra headless: `/opt/ghidra/support/analyzeHeadless` (PE32 i386 VC++6 debug).
  Projeto: `/tmp/opencode/ghidra_proj` (recriável). Scripts em `tools/ghidra/`:
  - `find_conn.java` — strings-chave + xrefs.
  - `dump2.java` — formatos de serialização + RTTI + decompilação.
  - `dump3.java` — decompila as funções que referenciam os formatos.

## Fatos confirmados (Ghidra)

### Formatos de serialização embutidos no EXE
- **Header** (`0x00b6f5e0`):
  `CADe_SIMU*%1d*%1d*%1d*%1d*%1d*%1d*%1d*%1d*%3d*%3d*%0.4f*%1d*%1d*%3d*%3d*%1d*%1d*%4d$$$`
  → 8 ints + 2 `%3d` + 1 float `%0.4f` + 2 ints + 2 `%3d` + 2 ints + 1 `%4d`.
- **Entidade** (`FUN_00432710`, o writer do doc):
  `*%d*%d#<rótulos %s>#*<ints>#<string final>`
  Duas variantes por nº de rótulos; **IDs especiais** usam a variante longa:
  `0x41c` (1052), faixa `0x2903..0x2937`, `0x431` (1073). **Texto = id 20000**.
- **Conexões do símbolo** (`0x00b723c4`):
  `%2s-%1d-%2s-%1d-%2s-%1d-%2s-%1d-%2s-%1d-%2s-%1d-`
  → **até 6 pinos**, cada um = (nome `%2s`, net `%1d`). É o mesmo padrão de
  `docs/formato-cad.md` (`5-1- 6-1-13-1-...`).
- **Conexão alternativa** (`0x00b73144`): `%2s-%1d-%2s-%1d-%1d`.
- Biblioteca de usuário: string `"%.s.lib" No es una librerias CADe_SIMU`.

### Modelo de objeto
- O doc guarda entidades em **arrays paralelos** (SoA) indexados por entidade
  (ex.: `+0x2024` = id; `+0x5ea4`, `+0x7de4`, `+0x158a4` = outros campos; limite 2000).
- Writers vistos: `FUN_00432710` (doc→arquivo — o `CCADe_SIMUDoc::Serialize`,
  caminho de **store**), `FUN_00878080` (header), `FUN_008907b0`/`FUN_00886680`
  (string de conexões), `FUN_008ab4a0`/`FUN_008aa1b0` (`.lib`).
- RTTI: `CCADe_SIMUDoc`, `CCADe_SIMUView`. Módulos: `Dibujo.cpp`, `Editar_Cable.cpp`,
  `Librerias.cpp`, `SIMBOLOS.CPP`, `Simbolo.cpp`, `Presenta.cpp`, `Pilotos.cpp`…

### Entidade: 2 variantes (`FUN_00432710`)
- **Normal**: `*%d*%d#` + **10** rótulos + `*%d`×**23** + `#%s`
- **Especial**: `*%d*%d#` + **11** rótulos + `*%d`×**24** + `#%s`
  (IDs especiais: `0x41c`, `0x2903..0x2937`, `0x431`.)
- O `#%s` final = **string de conexões** (pinos), presente nos **IDs tipo-conector**.

### Conexões por símbolo (até 6 pinos nome→net)
- Escrita por `FUN_00886680` / `FUN_008907b0` para um conjunto de IDs
  **tipo-conector**: `0x274d`, `0x274e`, `1000`, `0x3e9(1001)`, `0x1b68(7016)`,
  `0x1b6a(7018)`, `0x177f(6015)`, `0x1780(6016)`, `0x434(1076)`, `0x1b6b(7019)`.
- Formato lido/gravado: `%2s-%d-` (até 6 pares) + preenchimento `  -0-`.
- Os nets vêm de campos do **objeto do símbolo** (ex.: `+0xd44,+0xd48,+0xd74,+0xde4…`),
  não só de `nums[21]/[22]`.
- Exemplo real (só `corpus/CADe_S1.cad` traz a string):
  `*2*7018#C1##A1#A2#1#2#3#4#5#6*…*# 5-1- 6-1-13-1-14-1-21-1-22-1-  -0-  -0-  -0`
  → pinos `5,6,13,14,21,22` no net 1.

## O que isso muda para os nossos objetivos

1. **Pinos/net = até 6 por símbolo** (não 2). Nossa leitura `nums[21]/[22]` cobre só
   2 pinos → símbolos trifásicos (`2001`, `6007`, `6009`, `1000`) têm nets extras
   que ainda não mapeamos. **É por isso que a geometria de pino "dança"** entre arquivos.
2. **Conectividade**: a string de conexões guarda (nome do pino, net). O nó elétrico é
   o **net**; a geometria (fio tocando pino) é o **desenho**. Um curto acontece quando
   um fio encosta (geometricamente) num pino **que não é o seu** — o app conecta o que
   o desenho toca. Confirmação empírica: bobina com `A=B=0` conecta por **ponto
   geométrico** (plug net19 encostando o pino).
3. **Serialização robusta**: nosso round-trip (`cade_cli`) já preserva os campos; mas
   para **gerar** circuitos densos sem curto, precisamos da **geometria exata de cada
   pino** — que vive na biblioteca **embutida** (sem `.lib` externo no disco).

## Em aberto (próximos passos de RE)
- [ ] Achar o **caminho de leitura** do `Serialize` (o parser `sscanf`/`strtok`) — o
      store está mapeado (`FUN_00432710`), falta o load.
- [ ] Mapear os **23/24 ints** da entidade → quais são os nets dos 6 pinos.
- [ ] Achar a **biblioteca embutida** de símbolos (tabela de pinos por classe) —
      provavelmente em `SIMBOLOS.CPP`/`Simbolo.cpp` (dados no `.rdata`/`.data`).
- [ ] Achar a **rotina de netlist/simulação** (o que o "Simular" faz) para replicar
      fielmente as regras de conexão (nets × geometria).

## Plano (após RE)
1. **Pinos exatos** por classe (RE) → `tools/symbol_pins.json` corrigido.
2. **Roteador seguro**: grade de ocupação (keep-out do corpo+pinso dos símbolos),
   fios com endpoints **exatamente** nos pinos → **zero curto** por construção.
3. **Netlist fiel** (nós por net/geometria) + `cad_test` (verificação funcional).
4. **Harness E2E**: abrir no app e dirigir "Simular" de forma determinística
   (ideal: entender o botão/atalho e o estado na tela) — fecha o teste "100%".

## Como reproduzir
```bash
/opt/ghidra/support/analyzeHeadless /tmp/opencode/ghidra_proj CADE \
  -import "/home/monteiro/Downloads/CADe_SIMU 4.0 [BR]/CADe_SIMU 4.0 [BR]/CADe_SIMU 4.0 [BR].exe"
/opt/ghidra/support/analyzeHeadless /tmp/opencode/ghidra_proj CADE -process "CADe_SIMU 4.0 [BR].exe" \
  -noanalysis -scriptPath tools/ghidra -postScript dump3.java
```
