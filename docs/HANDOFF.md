# HANDOFF — leia isto primeiro (próxima sessão)

Atualizado: **2026-11-01**. Repo: `~/dev/codes/personal/cade-automation` (GitHub
`MonteiroBySWK/cade-simu-automation`, **público**, GPL-3.0). O MCP roda **deste checkout**
(Claude Code e opencode: `cade-simu` Python 17 tools + `cade-rust` 10 tools).

## Objetivo
1. **100% Rust**: binário único `cade` (build/layout/check/sim/mcp), sem Python; Python = oráculo
   até a paridade. Motor de simulação próprio validado contra o app real (Wine) e Docker sem Wine.
2. **≥ 80%** de confiabilidade de um agente usando o MCP em casos novos (benchmark held-out).

## Regras (valem sempre)
- Subagentes no máximo ~3 em paralelo; responder em PT-BR, direto. Pode commitar/mergear no main
  com **CI verde + testes**.
- **Nunca** commitar no repo da UEMA (`~/docs/uema`) sem o usuário pedir.
- **Senha do app**: `CADE_SENHA` no ambiente — **nunca** no repo (histórico já purgado).
- **Wine: um por vez** (DISPLAY dedicado). **Ghidra: um por vez**, `GHIDRA_HEADLESS_MAXMEM=3G`,
  projeto `~/cade-ghidra`, programa `CADe_SIMU 4.0 [BR].exe.0`, `-noanalysis`.
- Não declarar "funciona" sem prova (teste; no app, screenshot/leitura no Wine).

## Estado (main `c513c69`, CI **verde** Linux+Windows)
- **Rust**: workspace com 34 suítes (`cargo test --workspace`); `cade mcp` (10 tools); paridade
  byte-a-byte com o Python nos goldens; A8/A9 (mono/4 polos), A11 (recusa sem modelo), 9007,
  ladder (TON/TOF/borda/CTU), 3012 como fonte.
- **Python (oráculo)**: `python3 scripts/dev.py test` → **244 passed, 1 skipped**.
  `dev.py gate` → média 100 (18-21 exemplos); `run_eval --golden` → 100 em 16 casos.
- **App (Wine)**: A4/A5 provados (9004, 9007 pisca, sensor 2 fios); CTU/TOF provados.
  `cade conformidade tests/conformidade` → 13 ok / 0 divergentes / 3 sem golden.
- **Benchmark B6**: 12/12 held-out × 100 (3 grupos).
- **Doador**: rodapé (621 chars) e proto do fio 4000 são **constantes** em
  `src/cade_model/src/dados.rs` (o binário não embute `.cad`). `corpus/` = só fixtures + `NOTICE.md`.

## Histórico reescrito (2026-11-01)
- `git filter-repo`: removidos `pratica5/`, o histórico antigo de `corpus/` e
  `tools/render_cad.sh`; senha do app (literal) → `CADE_SENHA`; `/home/monteiro` → `~`; nome do professor
  e `murillous` anonimizados. `main`, tags e **branches antigas apagadas**; worktrees removidos.
- Release/tag **v0.3.0 apagados** (o asset antigo embutia o corpus). `v0.2.0` (sem assets) mantida.
- **Residual**: as refs de PR do GitHub (#5–#9 mesclados, #7 fechado) e o fork do colega ainda
  alcançam o histórico antigo via páginas de PR/fork — para sumir de vez: repo privado ou recriar
  o repo (ou suporte GitHub). Backup da história antiga: `/tmp/opencode/rewrite/` (bundle+mirror).
- O corpus voltou num commit **novo** só como fixture (`corpus/NOTICE.md`); o histórico antigo dele
  não existe mais.

## Pendências
- **Ladder com temporizador na conformidade** (`intercalada`, `partida_sequencial_3`,
  `pratica5_complementar`): app ~0,41× tempo de parede; comparar por janela/fator (goldens ainda
  sem `fonte:app`).
- **3 fios (7501/7502) e 9015**: sem protótipo/geometria no `symbol_lib` (Ghidra/desenho no app).
- **A13**: portar `cade_render` (preview PNG), `cade_app` (Wine), `cade_vision`, `cade_maint`;
  depois remover o Python.
- **PR #7** (colega): fechado, não mesclado; trabalho coberto pelo main.
- Benchmark: repetir com casos novos (o B6 usou moldes próximos).

## Comandos
```bash
python3 scripts/dev.py setup && python3 scripts/dev.py doctor   # sem Wine
python3 scripts/dev.py test                                    # 244 passed
cargo test --workspace                                         # 34 suites
python3 scripts/dev.py gate                                    # exemplos + eval
./target/release/cade conformidade tests/conformidade           # goldens do app
DISPLAY=:2 python3 tools/golden_app.py --todos                 # regravar goldens (Wine)
./target/release/cade mcp                                      # MCP Rust (stdio)
```
