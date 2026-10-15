# Plano — cade-automation

## Abordagens consideradas

1. **Texto-primeiro (adotada):** parser Rust do `.cad` como texto + JSON + CLI. Barato, determinístico. Risco: algum campo obscuro (mitigado por corpus + Wine).
2. **GUI-automation-primeiro:** pilotar o CADe via Wine/auto-click. Frágil, não dá formato IA-friendly (virou validação, não construção).

Escolha: (1) agora, (2) como validação na fase 2.

## Fases

- [x] **Fase 0 — Fundação (esta pasta):** README, docs, spec v0.1, git init. ✅ feito
- [x] **Fase 1 — Gramática:** `tools/extract_ids.py` → `docs/dicionario-simbolos.md`; `spec/spec-v1.md` congelada. ✅ 15/10/2026
- [x] **Fase 2 — `cade_core` (Rust):** `parse()` + `emit()` + testes round-trip. ✅ 4 testes verdes; round-trip byte-idêntico em 114/114 `.cad` do acervo
- [x] **Fase 3 — `cade_cli`:** `validate|parse|emit|new-from-json` e2e OK. ✅ 15/10/2026
- [x] **Fase 4 — Imagem→JSON (baseline):** `tools/img2json.py` + `docs/imagem-pipeline.md`. ✅ gera `.cad` válido; classificação de símbolos (80%) fica p/ ML futuro
- [x] **Fase 5 — Validação Wine:** `tools/validate_wine.sh` PASS (sem erro fatal; exit=124 = app segue aberto). ✅ 15/10/2026

## Convenções

- Commits em PT-BR, pequenos. Testes: `cargo test` round-trip no corpus.
- `.cad` original nunca editado in-place; saída sempre em `out/`.
- Amostras grandes ficam em Downloads; só 3–5 cópias mínimas em `corpus/`.

