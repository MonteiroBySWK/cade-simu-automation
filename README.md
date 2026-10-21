# cade-simu-automation

Reconstruo circuitos do **CADe_SIMU 4.0** a partir de texto ou imagem e entrego
um `.cad` que abre e simula. O formato `.cad` é proprietário mas legível
(texto ISO-8859 com `*`/`#`), então dá para manipular por código com segurança.

> **EN:** Rebuild CADe_SIMU 4.0 circuits from text or images into working `.cad`
> files. The format is proprietary but parseable, so code (and AI) can edit it
> reliably.

## Início rápido (5 minutos, sem Wine e sem o CADe_SIMU)

```bash
git clone https://github.com/MonteiroBySWK/cade-simu-automation && cd cade-simu-automation
python scripts/dev.py setup     # cargo build + venv + deps (precisa de Python>=3.10 e Rust)
python scripts/dev.py doctor    # o que funciona / o que falta / como instalar
python scripts/dev.py test      # 143+ testes (o E2E que abre o Wine é opt-in: `CADE_E2E=1`)
python scripts/dev.py gate      # gera e valida todos os exemplos
```

- **Dependências** (núcleo × opcionais, variáveis `CADE_*`): [`docs/DEPENDENCIAS.md`](docs/DEPENDENCIAS.md)
- **Usar com Claude Code / opencode** (MCP + skill): [`docs/integracao.md`](docs/integracao.md)
- **Para agentes e contribuidores**: [`AGENTS.md`](AGENTS.md), [`CONTRIBUTING.md`](CONTRIBUTING.md), [`CHANGELOG.md`](CHANGELOG.md)

## Como funciona

```
texto/imagem  →  cade.json  →  cade_cli  →  .cad  →  Wine (confere)
```

- `src/cade_core` (Rust): parse/emit byte-fiel. Round-trip 114/114 arquivos.
- `src/cade_cli`: `validate|parse|emit|new-from-json`. É por aqui que o agente trabalha — nunca editando `*`/`#` na mão.
- `tools/img2json.py`: imagem → `cade.json` + preview (baseline; classificação de símbolos ainda é simples).
- `tools/ladder_sim.py`: confere lógica de rungs (permissões, selos) antes de dizer que está pronto.
- `tools/validate_wine.sh`: abre o resultado no CADe_SIMU de verdade via Wine.
- `skills/automacao-industrial`: o passo a passo reutilizável de tudo isso.
- `docs/detector-imagem.md`: motor imagem→símbolos (machine vision + kNN),
  dataset minerado dos próprios `.cad` e métricas honestas.
- `docs/re-engenharia.md`: engenharia reversa do formato/conectividade do CADe
  (Ghidra headless) — formatos, biblioteca de símbolos, o que falta.

## Via agente (OpenCode, Claude Code)

Este repo é um **servidor MCP** (`tools/cade_mcp.py`, stdio): qualquer agente
conecta e passa a validar, gerar, inspecionar e **ver** circuitos:

```bash
uv venv tools/.venv-mcp
uv pip install --python tools/.venv-mcp/bin/python "mcp<2" pillow numpy
cargo build --manifest-path src/cade_cli/Cargo.toml
# claude mcp add cade-simu -- tools/.venv-mcp/bin/python tools/cade_mcp.py
```

Ferramentas (caminho de menor resistência primeiro):

| ferramenta | uso |
|---|---|
| `cad_examples` / `cad_example(nome)` | few-shot: layouts topológicos que passam o gate |
| **`cad_design(layout_json, out_path)`** | **principal**: layout topológico (sem x/y) → `.cad` + gate completo + `proximo_passo` |
| `cad_gate(path, testes_json)` | gate de um `.cad` existente: validate + testes + geometria (curto/pino solto) + fios |
| `cad_pins(classe)` / `cad_symbols` | nome, para que serve, tamanho e pinos de qualquer classe |
| `cad_preview(path)` | PNG: pinos nomeados, cor por fase, soltos/curtos em vermelho |
| `cad_simular_no_app(path, casos_json)` | **confirmação final na verdade do app**: abre no CADe_SIMU (Wine), Play, aciona entradas e lê bobinas/lâmpadas por imagem (~30-90 s; exige Wine + DISPLAY) — ver `docs/app-sim.md` |
| `cad_test`, `cad_simulate`, `cad_validate`, `cad_inspect` | verificação avulsa |
| `cad_build`, `cad_emit`, `cad_parse`, `cad_new`, `cad_from_image` | baixo nível |

Fluxo do agente: `cad_examples` → montar o layout topológico → `cad_design` → corrigir pelo
relatório do gate → `cad_preview` → entregar (ver `skills/automacao-industrial/SKILL.md`).

```bash
python3 tools/mcp_call.py cad_examples
python3 tools/mcp_call.py cad_example '{"nome":"partida_direta"}'
python3 tools/mcp_call.py cad_design '{"layout_json":"<json>","out_path":"out/x.cad"}'
python3 tools/app_sim.py out/x.cad --layout tools/examples/partida_direta.layout.json   # E2E no app (Wine)
python3 tools/eval/run_eval.py --golden      # baseline da biblioteca de avaliação (sem LLM)
python3 -m pytest tools -q
```

Regra do loop: o agente descreve a topologia, deixa o motor posicionar/rotear e só
entrega com o gate verde e o preview conferido — nunca escreve `*`/`#` nem x/y na mão.

## Uso

```bash
cargo build --manifest-path src/cade_cli/Cargo.toml
CLI=src/cade_cli/target/debug/cade_cli

$CLI validate circuito.cad
$CLI parse circuito.cad -o out/a.json
$CLI emit out/a.json -o out/b.cad
cmp circuito.cad out/b.cad && echo BYTE-IDENTICO

# do zero, a partir de descrição:
echo '{"meta":{"titulo":"PARTIDA DIRETA","modo":"0","versao":"3000"}}' > out/m.json
$CLI new-from-json out/m.json -o out/partida.cad
$CLI validate out/partida.cad
```

## Autoria do zero via MCP (agentes)

`tools/cade_mcp.py` expõe um **servidor MCP** com autoria por símbolo/fio — o
agente monta o circuito sem nunca escrever `*`/`#`:

```bash
python3 tools/mcp_call.py cad_symbols          # classes disponíveis
python3 tools/mcp_call.py cad_build '{"titulo":"T","simbolos_json":"[{\"classe\":\"2001\",\"x\":80,\"y\":125,\"rotulo\":\"-KM1\"}]","fios_json":"[{\"x1\":50,\"y1\":120,\"x2\":250,\"y2\":120}]","out_path":"out/novo.cad"}'
python3 tools/mcp_call.py cad_validate '{"path":"out/novo.cad"}'
```

Baixo nível: `cad_symbols`, `cad_build`, `cad_validate`, `cad_inspect`,
`cad_preview`, `cad_from_image`, `cad_parse`, `cad_emit`, `cad_new` (o caminho recomendado é
`cad_design`, acima). Registrado em `~/.config/opencode/opencode.json` como servidor MCP `cade-simu`.

Certificação: um agente (subagente com contexto zerado) montou um circuito de
**partida intercalar de motores** do zero, só via `cad_symbols`+`cad_build` —
41 entidades (23 símbolos + 18 fios) — e o `.cad` resultante **abre no CADe_SIMU**
(validado no Wine). Ver `docs/autoria-mcp.md`.

Detalhes do formato em `docs/formato-cad.md`, símbolos em
`docs/dicionario-simbolos.md`, contrato em `spec/spec-v1.md`.

## Início rápido

```bash
scripts/setup.sh   # build do cade_cli, venv MCP, gera out/intercalada.cad e roda o GATE
```

Gate: `tools/build_spec.py` (gera via `cad_build` + `cad_test`, falha em AVISO/curto) e `tools/wires_check.py`. Esperado: `GATE: OK`.

Variáveis de ambiente (defaults = caminhos do autor): `CADE_ACERVO` (pasta de `.cad` de referência), `CADE_EXE` (CADe_SIMU .exe), `CADE_DIR` (pasta do exe).

Ver `docs/handoff-atividade.md` e `docs/dsl-layout.md`.

## Estado honesto

- Editar `.cad` existente: funciona (round-trip + validação no app real).
- Criar do zero via texto: funciona o esqueleto válido; circuito completo via `cad_build`/specs JSON (ver `docs/autoria-mcp.md`), com roteador de fios e trilhos de fase automáticos; descrição livre depende do agente gerar a spec.
- Criar via imagem: detector de símbolos (kNN sobre dataset minerado dos próprios `.cad`) com P=0,88/R=0,89 no domínio treinado; `tools/img2cad.py` → `cade.json` → `.cad` válido. Limite de domínio documentado em `docs/detector-imagem.md`.

## Nota

Sem vínculo com o autor do CADe_SIMU (shareware, Juan Luis Villanueva
Montoto) nem com o "Ensinando Elétrica". Uso didático. Resoluções de
atividades e enunciados não são publicados (`pratica5/`, `*.pdf` no
`.gitignore`).

Licença GPLv3 ([LICENSE](LICENSE)).
