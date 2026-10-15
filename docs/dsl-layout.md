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

### Estado atual (para o próximo agente)
- `cade_mcp.cad_build` já aceita `trilhos` (`rails_json`) e ligação **por nome de
  pino** (`conexoes_json`) — falta o **motor de posicionamento** (esta DSL).
- Pinos medidos em `tools/symbol_pins.json` (contator/térmico/DJ/motor com
  `1-3-5`/`2-4-6`, motor `U1/V1/W1/PE`).
- **Pendência de RE**: medir os pinos reais do `3004#-X` (o símbolo desenha ~3
  terminais; os dados atuais só têm `A`/`B`).
