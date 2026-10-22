# Integração com Claude Code e opencode

O repo expõe um **servidor MCP** (`cade-simu`, stdio, launcher `scripts/mcp_server.py`) e uma **skill**
(`skills/automacao-industrial`). A instalação usa os **próprios CLIs** de cada ferramenta — nada de editar
config à mão, nada de `.mcp.json` no repo (evita servidor duplicado em dois escopos).

## Instalar (Linux, macOS, Windows)
```bash
python scripts/dev.py setup          # cargo build + venv + deps (uma vez)
python scripts/dev.py install-mcp    # registra MCP + skill no Claude Code e no opencode
```
O `install-mcp` é idempotente (remove o registro antigo e recria). Por baixo ele roda:

```bash
claude   mcp add -s user  cade-simu -- <python-absoluto> <repo>/scripts/mcp_server.py
opencode mcp add --global cade-simu -- <python-absoluto> <repo>/scripts/mcp_server.py
```
e linka a skill em `~/.claude/skills/` e `~/.config/opencode/skills/` (no Windows sem permissão de symlink, copia).
O caminho é absoluto: funciona de qualquer projeto. Mover o repo de lugar = rodar `install-mcp` de novo.
`git pull` no repo atualiza servidor e skill sem reinstalar.

> **Nota**: o MCP roda **deste checkout** (sem release — não há versão publicada do
> servidor). Depois de `git pull`, **reconecte** o MCP no cliente (`/mcp` no Claude
> Code / opencode) para carregar a versão nova. O binário do Release serve para usar
> o `cade` fora do repo (validate/parse/emit sem o checkout).

## Conferir
```bash
claude mcp get cade-simu      # Status: Connected
opencode mcp list             # cade-simu connected
python tools/mcp_call.py cad_examples   # o servidor responde sem cliente nenhum
```

## Desinstalar
```bash
python scripts/dev.py uninstall-mcp
```
`claude mcp remove` nos escopos user/local/project; no opencode (o CLI não tem `remove`) a chave `cade-simu`
sai de `~/.config/opencode/opencode.json` com backup `.bak`; os links da skill são removidos.

## Fluxo que o agente deve seguir
`cad_examples` → layout **topológico** (sem x/y, `docs/dsl-layout.md`) → `cad_design` → corrigir pelo gate →
`cad_preview` → entregar o `.cad`. Confirmação no app real (`cad_simular_no_app`) só com Wine (`docs/DEPENDENCIAS.md`).

## MCP em Rust (`cade-rust`) ao lado do Python

Quando `target/release/cade` existe, o `install-mcp` tambem registra o servidor **Rust** (stdio,
`cade mcp`) com o nome **`cade-rust`** nos dois clientes:

```bash
claude   mcp add -s user  cade-rust -- <repo>/target/release/cade mcp
opencode mcp add --global cade-rust -- <repo>/target/release/cade mcp
```

Ele expoe 10 ferramentas (`cad_validate`, `cad_symbols`, `cad_pins`, `cad_examples`, `cad_example`,
`cad_design`, `cad_gate`, `cad_build`, `cad_test`, `cad_simulate`) **sem Python**. O `cade-simu`
(Python) continua com as 17, incluindo `cad_preview` e `cad_simular_no_app` (que dependem de
`cade_render`/`cade_app`, ainda pendentes no port). Os dois podem coexistir: use `cade-rust` para
testar o motor Rust e `cade-simu` para o fluxo completo.

