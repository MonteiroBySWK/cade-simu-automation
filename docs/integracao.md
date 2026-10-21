# Integração com Claude Code e opencode

Este repo é um **servidor MCP** (`cade-simu`, stdio) + uma **skill** (`skills/automacao-industrial`).

## 0. Pré-requisito (uma vez)
```bash
make setup     # cargo build + venv + deps (sem Wine)
make doctor    # confere o ambiente
```

## 1. Claude Code
- **Dentro do repo**: o `.mcp.json` da raiz já registra o servidor — abra o Claude Code na pasta e aprove o servidor
  `cade-simu` (`/mcp` lista as ferramentas).
- **Em qualquer projeto** (escopo de usuário):
  ```bash
  claude mcp add cade-simu -- bash /CAMINHO/ABSOLUTO/cade-simu-automation/scripts/mcp-server.sh
  ```
- **Skill**: copie ou linke a pasta da skill:
  ```bash
  ln -s /CAMINHO/ABSOLUTO/cade-simu-automation/skills/automacao-industrial ~/.claude/skills/automacao-industrial
  ```
- `CLAUDE.md`/`AGENTS.md` da raiz já orientam o agente quando ele trabalha neste repo.

## 2. opencode
- **Dentro do repo**: o `opencode.json` da raiz registra o MCP local (`scripts/mcp-server.sh`).
- **Global** (`~/.config/opencode/opencode.json`), com caminho absoluto:
  ```json
  { "mcp": { "cade-simu": { "type": "local",
      "command": ["bash", "/CAMINHO/ABSOLUTO/cade-simu-automation/scripts/mcp-server.sh"], "enabled": true } } }
  ```
  > Formato conforme a documentação do opencode na data da escrita — confira o `$schema` da sua versão.
- O `AGENTS.md` da raiz é lido automaticamente; ele aponta para a skill.

## 3. Fluxo que o agente deve seguir
`cad_examples` → escrever o **layout topológico** (sem x/y, ver `docs/dsl-layout.md`) → `cad_design` →
corrigir pelo relatório do gate → `cad_preview` → entregar o `.cad`.
Confirmação opcional no app real: `cad_simular_no_app` (exige Wine; ver `docs/DEPENDENCIAS.md`).

## 4. Teste rápido de que o MCP responde
```bash
python3 tools/mcp_call.py cad_examples
```
