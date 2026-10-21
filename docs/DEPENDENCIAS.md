# Dependências

O repo foi escrito numa máquina específica; tudo que dependia dela agora é **opcional e configurável**.
`make doctor` mostra o que está presente, o que falta e como instalar.

## Núcleo — o que basta para usar e contribuir

| Item | Versão | Para quê |
|---|---|---|
| Python | ≥ 3.10 | layout, gate, MCP, testes |
| Rust (`cargo`) | stable recente | compila o `cade_cli` (parse/emit/validate do `.cad`) |
| Pacotes Python | `requirements.txt` (`mcp<2`, `pillow`, `numpy`, `pytest`) | instalados por `make setup` em `tools/.venv-mcp` |
| `uv` | opcional | acelera o setup (sem ele usa `python -m venv`) |

**Não precisa** do CADe_SIMU, do Wine nem do Ghidra para: gerar `.cad` (`cad_design`), rodar o gate,
simular offline, usar o MCP e rodar os testes (143 passam; o E2E que abre o Wine só roda com `CADE_E2E=1`).
O catálogo de símbolos vem versionado em `tools/symbol_lib.json`; pinos em `docs/pinos-binario.json`
e `tools/symbol_pins.json`; semântica por classe em `docs/classes-papeis.json`.

## Opcionais — só para quem for fazer isso

| Recurso | O que habilita | Como configurar |
|---|---|---|
| **CADe_SIMU 4.0 [BR]** (shareware, Juan Luis Villanueva Montoto) | abrir/validar no app real (`tools/wine_mgr.py`, `app_sim.py`, `cad_simular_no_app`) | `CADE_DIR=<pasta>` ou `CADE_EXE=<exe>` (auto-detecta em `~/Downloads`, `~`, `/opt`) |
| **Acervo de `.cad` do curso** | regenerar catálogo/pinos (`gen_symbol_lib.py`, `learn_pins2.py`) | `CADE_ACERVO=<pasta com os .cad>` (default: dentro de `CADE_DIR`) |
| **Wine + xdotool + ImageMagick (`import`)** + sessão X11 | `app_sim` (aciona botões e lê o estado por imagem) | pacotes da distro; `DISPLAY` definido |
| **Ghidra ≥ 11 + Java 21** | refazer a engenharia reversa (`tools/ghidra/*.java`, `docs/re-engenharia.md`) | importar o `.exe` num projeto **sem `.` no caminho**; um Ghidra por vez, `-max-memory 3G` |

Os arquivos do app e do curso **não** são redistribuídos aqui (ver licença/nota no README).

## Variáveis de ambiente

`CADE_DIR`, `CADE_EXE`, `CADE_ACERVO` (resolvidas em `tools/cade_config.py`). Scripts `.sh` de Wine exigem
`CADE_DIR`/`CADE_EXE` e param com mensagem clara se faltarem.
