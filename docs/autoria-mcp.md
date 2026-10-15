# Autoria de `.cad` do zero via MCP

O agente **monta o circuito sem nunca escrever `*`/`#`** — só símbolos e fios.

## Ferramentas

| ferramenta | o que faz |
|---|---|
| `cad_symbols` | lista as classes de símbolo (ID + exemplo de rótulo) |
| `cad_build` | cria o `.cad` do zero a partir de `simbolos_json` + `fios_json` |
| `cad_validate` | confere header + `$$$`; devolve modo/versão |
| `cad_inspect` | resume entidades/IDs/rungs/nets |
| `cad_preview` | renderiza o esquema como imagem (o agente **vê**) |
| `cad_from_image` | imagem → inventário de símbolos (kNN) |
| `cad_parse` / `cad_emit` / `cad_new` | round-trip e template mínimo |

### `cad_build`
- `titulo`: string
- `simbolos_json`: `[{"classe":"2001","x":80,"y":125,"rotulo":"-KM1"}]`
  (`classe` vem de `cad_symbols`; `rotulo` substitui o rótulo do símbolo)
- `fios_json`: `[{"x1":50,"y1":120,"x2":250,"y2":120}]` (segmentos retos)
- `out_path`: destino

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

- Sem lógica ladder/PLC embutida: `cad_build` posiciona símbolos e fios; a
  semântica de simulação (nets/rungs) ainda é montada pelo autor.
- Sem roteamento automático de fios (o autor informa os segmentos).
