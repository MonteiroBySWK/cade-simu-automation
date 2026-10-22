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
  `nao_portado` até o `cade_sim` Rust ligar o executor — ligado no PR do cade_sim).
- Setup: `python3 scripts/dev.py setup|doctor|test|gate|install-mcp`; Rust: `cargo test --workspace`.
- Docs-chave: `AGENTS.md`, `docs/rust-port.md` (matriz de paridade), `docs/ladder.md` (contrato ladder/1),
  `docs/re-engenharia.md` (§9 geometria, §11 papéis, §13 ladder), `docs/app-sim.md`, `docs/integracao.md`.

## Trabalho em andamento quando esta sessão acabou
### Ladder + entregas A/B — CONCLUÍDO (main `836dc4a`)
- DSL `ladder/1` em Python: `tools/ladder_dsl.py` (V1–V8, modelo lógico 100 ms = geométrico `tools/clp_sim.py`),
  `tools/cadfile.py` (round-trip .cad), pinos do CLP corrigidos, `app_sim` (Play via Stop vermelho, DJ1, saídas
  10205/bobinas ladder, `--roteiro`), SKILL/docs. 173 testes; gate: 5 `.ladder.json` OK.
- **Entrega A**: `~/docs/uema/.../atividade-partidas-intercalares/cad/Pratica5_Complementar_Monteiro.cad`
  (+ `.ladder.json`); R2 → Q0.2 corrigida (bug provado no app), RT1/RT2 em I0.4–I0.7, H3/H4 em Q0.4/Q0.5;
  T1–T7 aprovados no app — `../evidencias/relatorio_T1_T7.md` + `evidencias/app/*.png`.
- **Entrega B**: `.../partida-sequencial-3-motores/` (README, cad/, evidencias/): M3 ~0,6 s, M2 2,4 s, M1 4,4 s
  no app. B0: M1 cai ~0,7 s depois (cascata do ladder sugerido; documentado).
- Pendências: ladder no Rust; `potencia` em lista + `dj_comum`; casos `tools/eval/casos/ladder/` fora do
  `run_eval`; H1–H3/térmicos da B (opcional). Arquivos das entregas NÃO commitados no repo da UEMA.
- Observação: tempos no app variam com carga da máquina (atrasos chegaram a ~3,9 s sob compilação Rust).

### Rust (cade_sim / conformidade / Docker) — PR da branch `feat/rust-sim-conformidade`
- **Feito:** crate `cade_sim` (geometria reaproveitada de `cade_check::geom`; papéis em duas camadas: tabela embutida = a do
  Python + derivada de `docs/classes-papeis.json`; NA/NC/NA-NC/comutados, disjuntor/interruptor iniciam abertos, fusível
  íntegro, temporizadores 9004/9005/9006 + contatos 7004..7015 por rótulo, motores, curto, relaxação). `ExecutorSim`
  implementa `cade_check::ExecutorTestes` e está ligado em `src/cade_cli/src/check.rs` (`cade gate`/`design` rodam testes
  de verdade). CLI `cade simulate|test|conformidade`. Paridade com o Python: `tests/golden/sim/gerar.py` +
  `tests/paridade/tests/simulacao.rs`. Conformidade: `tests/conformidade/<caso>/` (11 goldens **provisórios**,
  `"fonte":"oraculo_python"`; regere com `python3 tests/conformidade/gerar.py`, que preserva goldens `"fonte":"app"`).
  `Dockerfile` (scratch + binário musl), job de CI, `docker/wine-golden/Dockerfile` (opcional, NÃO executado).
  Doc: `docs/conformidade.md` (formato, como gravar no app, Docker, licença) e seção "Simulação" de `docs/rust-port.md`.
- **Falta:** (1) gravar `golden_app.json` reais com `app_sim` (Wine) — divergências esperadas listadas em
  `docs/conformidade.md` (disjuntor 6009/6010 inicia aberto no app; térmico por rótulo; ticks de 100 ms);
  (2) ladder/CLP em `cade_sim::ladder::ModeloLadder` (hoje só o trait; `saidas_clp` sempre `[]`);
  (3) sem modelo: temporizador intermitente 9007, pulsos 9015, sensores 3 fios, GRAFCET/pneumática;
  (4) motor "gira" = dois pinos de fase com estampas diferentes (confiança média, validar no app).

### Se os agentes tiverem caído sem commitar
- Ladder/entregas: o trabalho fica **não commitado no checkout principal** (`git status` mostra `tools/dissect.py`,
  `tools/app_sim.py`, `docs/pinos-binario.json`, …). Revise, rode `python3 scripts/dev.py test`, commite com
  `wip:` se incompleto e continue de onde parou.
- Rust sim: worktree `.claude/worktrees/agent-aa61b087d86f7595a` (branch `feat/rust-sim`); idem.

### PR de terceiro aberto
- **#7** (autor `murillous`, colega do usuário): "exercicio de partida sequencial de 3 motores com CLP". Não foi
  revisado nesta sessão. Sobrepõe a Entrega B; pergunte ao usuário antes de mergear/fechar.

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
