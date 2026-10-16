# Autoria de `.cad` do zero via MCP

O agente **monta o circuito sem nunca escrever `*`/`#`** — só topologia (ou símbolos e fios).

## Caminho recomendado: `cad_design` (topologia → .cad + gate)

O agente **não calcula x/y**: descreve a topologia (DSL de `docs/dsl-layout.md`), o motor
(`tools/layout.py`) posiciona e roteia, e o gate prova. Fluxo:

```
cad_examples → cad_example(nome) → (adaptar layout + testes) → cad_design → corrigir pelo relatório → cad_preview → entregar
```

### Ferramentas de alto nível

| ferramenta | o que faz |
|---|---|
| `cad_examples` | lista os `tools/examples/*.layout.json` (nome, título, resumo, nº de testes) |
| `cad_example(nome)` | devolve o layout.json (DSL + `testes`); pode ir direto a `cad_design` |
| **`cad_design(layout_json, out_path)`** | layout → compila → `cad_build` → gate. Retorna JSON `{ok, path, gate:{build,testes,geo:{curtos,soltos},fios}, avisos, erros, proximo_passo}` |
| `cad_gate(path, testes_json)` | o mesmo gate sobre um `.cad` existente (validate + testes + `geo_check` + `wires_check`) |
| `cad_pins(classe)` | `{nome, uso, largura, altura, pinos{nome:[dx,dy]}, pinos_ab, pinos_binario}`; nome só quando documentado (`tools/symbol_names.json`) |
| `cad_symbols` | catálogo: classe, nome/uso (quando conhecidos), tamanho, pinos nomeados |
| `cad_preview(path, scale=3, png_path="")` | PNG (data URI): pinos nomeados, **cor por fase** (L1 laranja, L2 roxo, L3 azul, N ciano, PE verde; propagada por Q/F/KM), **pino solto = círculo vermelho**, **curto = fio vermelho com X** |

O `ok` de `cad_design`/`cad_gate` = build válido **e** testes passam **e** sem curto de fase
**e** sem pino solto. `fios` (fio atravessando símbolo) é estético: aparece em `avisos`/`gate.fios`
mas não derruba o `ok`. As mensagens são acionáveis, p.ex. `pino L3 da fonte -X (3007) solto em
(42,55): ligue-o ao trilho L3` ou `CURTO N+P na mesma net ... crie trilho PE separado`.
Erros de autoria detectados antes do build (`avisos`): fonte `3004` por fase, PE do motor no neutro,
trilho inexistente; e depois: circuito **sem testes** e chaves de teste que não existem no circuito.

Biblioteca de avaliação (sem LLM): `tools/eval/casos/*.json` (enunciado PT-BR, restrições,
obrigatórios, testes) + `python3 tools/eval/run_eval.py --golden | <caso> <arq.cad> | --dir pasta/`.

### Ferramentas de baixo nível

| ferramenta | o que faz |
|---|---|
| `cad_build` | cria o `.cad` do zero a partir de `simbolos_json` + `conexoes_json`/`fios_json` |
| `cad_validate` | confere header + `$$$`; devolve modo/versão |
| `cad_inspect` | resume entidades/IDs/rungs/nets |
| `cad_test` / `cad_simulate` | tabela-verdade do comando via netlist |
| `cad_from_image` | imagem → inventário de símbolos (kNN) |
| `cad_parse` / `cad_emit` / `cad_new` | round-trip e template mínimo |

### `cad_build`
- `titulo`: string
- `simbolos_json`: `[{"classe":"2001","x":80,"y":125,"rotulo":"-KM1","id":"KM1"}]`
  (`classe` de `cad_symbols`; `id` único é a chave de ligação; `rotulo` é o texto)
- `conexoes_json`: `[{"de":["S1","B"],"para":["KM1","A"]}]` — **ligação lógica por
  nome/pino**; o build roteia o fio e calcula os NETs (recomendado)
- `fios_json`: `[{"x1":50,"y1":120,"x2":250,"y2":120}]` (segmentos manuais, opcional)
- `auto_net`: `true` (padrão) calcula os nets por geometria (pinos×fios)
- `out_path`: destino

Retorno: `N entidades -> path | OK ...`; se houver **`AVISO curto A==B`**, algum
símbolo ficou com os dois pinos no mesmo nó — corrija o layout.

### NETs e geometria de pinos
A simulação do CADe é dada por **NETs** (inteiros): dois pontos com o mesmo net
estão conectados. `cad_build` calcula os nets por geometria usando a **tabela de
pinos aprendida dos exemplos** (`tools/symbol_pins.json`, 105 classes; regerar com
`python3 tools/learn_pins.py`). Contatos: `A` em cima, `B` embaixo; ramos em
paralelo ligam nos **mesmos dois nós**.

Faixa de coordenadas com boa visualização: x∈[40,300], y∈[20,180].

## Cliente CLI (para scripts/agentes que não têm o MCP nativo)

```bash
python3 tools/mcp_call.py cad_symbols
python3 tools/mcp_call.py cad_build '<json-args>'
```

Fala o protocolo MCP (stdio) com `tools/cade_mcp.py`.

## Certificação (teste definitivo)

Um subagente com **contexto zerado** recebeu só a especificação funcional
(partida intercalar de 2 motores, térmicos RT1/RT2 com permissão E, pilotos,
intertravamento) e a instrução de usar apenas o MCP. Resultado:

- descobriu as classes via `cad_symbols`;
- montou **23 símbolos + 18 fios = 41 entidades** numa chamada de `cad_build`;
- `cad_validate` → `OK modo=0 versao=3004`;
- o `.cad` **abriu no CADe_SIMU** (Wine) e renderizou o diagrama (comando +
  potência) coerente.

O teste também **encontrou um bug** (o `rotulo` era inserido como 2º rótulo em
vez de substituir o 1º) — corrigido em `tools/cade_mcp.py`.

## Limites

- Sem lógica ladder/PLC embutida: a semântica de simulação (nets/rungs) é
  responsabilidade do autor da spec.
- O roteamento de fios e os trilhos de fase (L1/L2/L3) existem (`tools/layout.py`,
  `tools/build_spec.py`); o gate falha em curtos/cruzamentos. Ver `docs/dsl-layout.md`.
