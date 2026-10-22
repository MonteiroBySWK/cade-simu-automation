# HANDOFF — leia isto primeiro (próximo modelo/sessão)

Atualizado: 2026-10-22 ~10h (horário de Brasília). Repo: `~/dev/codes/personal/cade-automation` (GitHub
`MonteiroBySWK/cade-simu-automation`). O MCP `cade-simu` do usuário roda **deste checkout** (Claude Code e opencode).

## Objetivo do usuário
1. **Hoje até 12h:** duas entregas em CLP + ladder no CADe_SIMU (A: Prática 5; B: partida sequencial de
   3 motores). Exigem ladder no MCP, que **não existia** — está sendo implementado (seção abaixo).
2. Projeto **100% Rust** (binário único `cade`, sem Python), com **motor de simulação próprio** validado por
   **teste diferencial contra o app real** e rodando em **Docker sem Wine**. Python = oráculo até a paridade.
3. Confiabilidade ≥ 80% de um modelo usando o MCP para resolver pedidos novos (benchmark held-out).

## Regras do usuário (valem sempre)
- Subagentes em **Sonnet**; no máximo ~3 em paralelo (limite de uso já derrubou sessões).
- **Pode mergear PR sozinho** quando pronto e validado (CI verde + testes). Pode commitar direto no main.
- Não commitar nos arquivos das entregas em `~/docs/uema/...` sem o usuário pedir (outro repo).
- **Wine: um por vez**, nunca derrubar processo alheio (`python3 tools/wine_mgr.py status`). DISPLAY=:1.
- **Ghidra: um por vez**, `GHIDRA_HEADLESS_MAXMEM=3G`, projeto `~/cade-ghidra` (programa
  `CADe_SIMU 4.0 [BR].exe.0`), `-noanalysis`. Caminho de projeto sem `.`.
- Não declarar "funciona" sem prova (testes; para comportamento do app, screenshot no Wine).
- Responder em PT-BR, direto.

## Estado (main)
- `main` = `562852e`: Python completo (layout, gate, MCP, simulador, `app_sim`), Rust fase 1 (`cade build`,
  `cade layout`, paridade byte-a-byte) e `cade_check` (`cade gate`, `cade design` — testes funcionais marcados
  `nao_portado` até o `cade_sim` Rust ligar o executor).
- Setup: `python3 scripts/dev.py setup|doctor|test|gate|install-mcp`; Rust: `cargo test --workspace`.
- Docs-chave: `AGENTS.md`, `docs/rust-port.md` (matriz de paridade), `docs/ladder.md` (contrato ladder/1),
  `docs/re-engenharia.md` (§9 geometria, §11 papéis, §13 ladder), `docs/app-sim.md`, `docs/integracao.md`.

## Trabalho em andamento quando esta sessão acabou
### Ladder + entregas A/B (agente Sonnet, no checkout principal)
- Implementando a DSL `ladder/1` em Python (`cad_design`), correções de pinos do CLP (10050/10051/10060/
  10066/10204/10205/10206, catálogo via `tools/gen_symbol_lib.py`), `tools/dissect.py` (string final `#%s`),
  `tools/app_sim.py` (detecção de Play pelo **Stop (528,32) vermelho** ou status "Simulación"; MENU_VER/
  ITEM_ZOOM_TODO; ler saídas do CLP 10205 e bobinas ladder; alternar DJ1 antes dos testes).
- Ele foi autorizado a commitar/push no main em passos pequenos e a atualizar esta seção.
- **Entrega A** (base intacta: `~/docs/uema/.claude/worktrees/cade-simu-atividade-5f2849/disciplinas/automacao-industrial/atividade-partidas-intercalares/cad/Pratica5_Part_Intercalada.base.cad`):
  corrigir R2 → `Q0.2` (bug confirmado no app), H1/H2, RT1/RT2 (6007 + 8017/8016 de MESMO rótulo) em entradas
  livres, H3/H4 em saídas livres, PERMISSAO = RT1_OK·RT2_OK nos dois degraus, legenda + tabela de I/O,
  relatório T1–T7 + screenshots em `../evidencias/`. Saída: `Pratica5_Complementar_<Aluno>.cad`.
- **Entrega B**: `.../automacao-industrial/partida-sequencial-3-motores/` (README.md, cad/, evidencias/):
  M3 → 2 s → M2 → 2 s → M1, CLP -CLP, DJ1, B0/B1, TON em linha; screenshots t=0/2/4 s.
- **3ª tarefa ladder**: enunciado ainda não informado — só deixar a infraestrutura pronta.
- **Como retomar:** `git -C ~/dev/codes/personal/cade-automation status` / `git log`; ver o que falta pelos
  testes (`python3 scripts/dev.py test`, exemplos `tools/examples/*.ladder.json`, `tools/eval/casos/ladder/`).

### Rust `cade_sim` + conformidade + Docker (agente Sonnet, worktree, branch `feat/rust-sim`)
- Motor de simulação próprio com paridade com `tools/netlist_sim.py`; `cade simulate`, `cade test`,
  `cade conformidade tests/conformidade` (formato: `circuito.cad` + `cenario.json` + `golden_app.json`;
  goldens provisórios do oráculo Python marcados `"fonte":"oraculo_python"`), `Dockerfile` só com o binário,
  implementar `cade_check::ExecutorTestes` e ligar em `src/cade_cli/src/check.rs`.
- Instruído a abrir PR (draft se incompleto) e mergear se ficar verde. **Retomar:** `gh pr list`, branch
  `feat/rust-sim`.

## Próximos passos (ordem)
1. Fechar entregas A e B (validadas no Wine) — prazo do usuário.
2. Mergear `feat/rust-sim` quando verde; gate Rust passa a rodar testes funcionais.
3. **Gravar goldens do app** (`tools/app_sim.py` em lote sobre o acervo + exemplos → `tests/conformidade/*/
   golden_app.json` com `"fonte":"app"`); `cade conformidade` deve passar; divergência = bug do motor ou RE.
4. Portar ladder para o `cade_sim` (contrato `docs/ladder.md`, oráculo = Python novo).
5. Restante do port (crates esqueleto em `src/`): `cade_render` (preview PNG), `cade_mcp` (servidor MCP stdio +
   `cade install-mcp`), `cade_app` (Wine), `cade_vision` (detector), `cade_maint` (gen_symbol_lib/learn_pins/
   apply_bin_pins). Depois: PR que **apaga o Python** (dev.py, requirements, tools/*.py) quando tudo tiver paridade.
6. Benchmark de confiabilidade (≥ 80%): 12 casos held-out em `tools/eval/heldout/` (ainda NÃO criados — o
   agente que ia criá-los caiu), agentes resolvendo só com o MCP, `run_eval.py` pontua; iterar skill/DSL/erros.
7. Temporizadores 9004–9007 + bancada de cobertura por classe: rascunho não verificado na branch
   `wip/temporizadores-bancada` (remota).

## Fatos que custaram caro (não reaprender)
- Conectividade do app é **geometria** (extremo a extremo; T só com `4001`); nets gravados são descartados.
- Entidade 0 fica colada ao `CADe_SIMU*` (seq 0); nunca reaproveitar a do doador.
- Fonte única `3007` + trilho PE; PE no N = curto. Térmico `6007` e contato 8016/8017 com **mesmo rótulo**.
- Folha segura em unidades do `.cad`: x ≤ 455, y ≤ 305 (a barra de status do app usa unidade ~3,3× maior).
- Botão 3D só troca bitmap (n16); nada a gerar. Para 10204/10205, `n16=1` = 24 V DC (muda a simulação).
- opencode v2 grava MCP em `mcp.servers.<nome>`; `opencode mcp` não tem `remove`.
