# Integração com Claude Code e opencode

Este repo é um **servidor MCP** (`cade-simu`, stdio) + uma **skill** (`skills/automacao-industrial`).

## 0. Pré-requisito (uma vez) — Linux, macOS ou Windows
> O `.mcp.json`/`opencode.json` chamam `python`. Em Linux sem o comando `python` (só `python3`), use
> `python scripts/dev.py mcp-config` para gerar a config com o caminho absoluto do seu Python.
```bash
python scripts/dev.py setup     # cargo build + venv + deps (sem Wine)
python scripts/dev.py doctor    # confere o ambiente
```

## 1. Claude Code
- **Dentro do repo**: o `.mcp.json` da raiz já registra o servidor — abra o Claude Code na pasta e aprove o servidor
  `cade-simu` (`/mcp` lista as ferramentas).
- **Em qualquer projeto** (escopo de usuário):
  ```bash
  python scripts/dev.py mcp-config   # imprime o comando/JSON certo p/ o seu SO, com caminhos absolutos
  ```
- **Skill**: copie ou linke a pasta da skill:
  ```bash
  ln -s /CAMINHO/ABSOLUTO/cade-simu-automation/skills/automacao-industrial ~/.claude/skills/automacao-industrial
  ```
- `CLAUDE.md`/`AGENTS.md` da raiz já orientam o agente quando ele trabalha neste repo.

## 2. opencode
- **Dentro do repo**: o `opencode.json` da raiz registra o MCP local (`python scripts/mcp_server.py`).
- **Global** (`~/.config/opencode/opencode.json`), com caminho absoluto:
  ```json
  { "mcp": { "cade-simu": { "type": "local",
      "command": ["python", "/CAMINHO/ABSOLUTO/cade-simu-automation/scripts/mcp_server.py"], "enabled": true } } }
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
