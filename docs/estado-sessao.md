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

## RE Ghidra — CONCLUÍDO (agente Opus)
(Ver `docs/re-engenharia.md` §9–10 e `docs/pinos-binario.json`; resumo em `docs/handoff-atividade.md`.)

## (histórico) RE em andamento
Objetivo: `docs/pinos-binario.json` (pinos reais por classe) + resposta net × geometria + semântica
dos 23/24 ints. Rascunhos: `tools/ghidra/draw_dump.java`, `pins_dump.java`, `pins_from_dump.py`.
Projeto Ghidra local: `~/cade-ghidra` (nome `CADE`; **fora do repo, só nesta máquina**; caminho
sem `.` — o Ghidra rejeita). Máquina tem 11 GiB: **um Ghidra por vez, `-max-memory 3G`**,
sem decompilador em lote.

## Próximos passos (ordem)
1. ✅ pinos do binário aplicados; ✅ fonte 3007 + PE; ✅ geo_check no gate; ✅ validado no Wine (KM1/selo/lâmpada).
2. Descobrir tamanho real da folha (gabarito usa y até 440; layout limita 455x295).
3. Layout: ramos aninhados/temporizadores; mais circuitos (reversão, estrela-triângulo) com `testes`.
4. Atualizar `skills/automacao-industrial/SKILL.md` (fonte 3007, PE, geo_check) — ainda cita 3004 e folha 300.
5. Menores: `detect_symbols.py` e `pratica5_build.py` ainda com caminho absoluto; ramos aninhados/temporizadores no layout.

## Regras
- Sempre rodar o gate (`GATE: OK`) + `wires_check.py` (`FIOS: ok`) antes/depois de mexer no roteador/pinos.
- Teste do gate valida contra o próprio modelo de pinos → só o app (Wine) / binário é verdade.
