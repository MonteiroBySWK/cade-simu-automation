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
- **Exemplos**: `intercalada.layout.json` (2 motores, equivalente à spec manual) e
  `partida_direta.layout.json` (1 motor). Nenhuma coordenada na entrada.
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
- O motor levanta `ValueError` se algo sair da folha (x>455, y>295) ou se dois
  símbolos se sobrepuserem.

### Limitações / pendências
- Um único nível de ramos paralelos; sem ramos aninhados nem temporizadores.
- Muitos ramos (>3) ou série longa estouram a folha (erro explícito, sem quebra
  automática em colunas).
- `cad_test` (netlist) é fixo para a intercalada: em outros circuitos reporta
  FALHA nos casos KM2/RT2 e o gate ainda imprime OK (só procura `FALHOU`/`AVISO`).
  Os testes novos conferem só os casos de KM1/RT1 na partida direta.
- **Pendência de RE**: pinos reais do `3004#-X` (só `A`/`B` medidos).
