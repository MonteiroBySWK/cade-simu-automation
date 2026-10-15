# Estado da sessão — 2026-10-15 (pausa)

Branch: `claude/mcp-ai-automation-project-32fea4` (worktree). Retome lendo este arquivo,
`docs/handoff-atividade.md`, `docs/dsl-layout.md` e `docs/re-engenharia.md`.

## Pronto e verde
- `scripts/setup.sh` — cargo build + venv + gate (idempotente). Env: `CADE_ACERVO`, `CADE_EXE`, `CADE_DIR`.
- `tools/layout.py` — motor de layout topológico (spec sem x/y → spec baixa). Exemplos:
  `tools/examples/intercalada.layout.json`, `partida_direta.layout.json`. `pytest tools/test_layout.py` → 6 passam.
- Gate corrigido (`2c05d32`): `build_spec.py` lê o resultado real do `cad_test`; casos vão na
  chave `"testes"` da spec; sem testes = REPROVADO.
- RE parcial (commit `818e6b7`): layout SoA do doc, conectividade por geometria, regras de nets
  — ver `docs/re-engenharia.md`.

## Em andamento (RE Ghidra, agente Opus)
Objetivo: `docs/pinos-binario.json` (pinos reais por classe) + resposta net × geometria + semântica
dos 23/24 ints. Rascunhos: `tools/ghidra/draw_dump.java`, `pins_dump.java`, `pins_from_dump.py`.
Projeto Ghidra local: `~/cade-ghidra` (nome `CADE`; **fora do repo, só nesta máquina**; caminho
sem `.` — o Ghidra rejeita). Máquina tem 11 GiB: **um Ghidra por vez, `-max-memory 3G`**,
sem decompilador em lote.

## Próximos passos (ordem)
1. Terminar RE de pinos → `docs/pinos-binario.json`; comparar com `tools/symbol_pins.json`.
2. Aplicar diff de pinos em `symbol_pins.json`; regenerar intercalada
   (`python3 tools/build_spec.py tools/examples/intercalada.layout.json out/i.cad`) e `wires_check.py`.
3. Validar no Wine (`tools/wine_mgr.py up/shot`) e comparar com `Intercalar_atv.cad` do acervo (gabarito real).
4. `3004#-X`: medir terminais reais (hoje só A/B).
5. Menores: `detect_symbols.py` e `pratica5_build.py` ainda com caminho absoluto; ramos aninhados/temporizadores no layout.

## Regras
- Sempre rodar o gate (`GATE: OK`) + `wires_check.py` (`FIOS: ok`) antes/depois de mexer no roteador/pinos.
- Teste do gate valida contra o próprio modelo de pinos → só o app (Wine) / binário é verdade.
