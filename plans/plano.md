# Plano — cade-automation

## Abordagens consideradas

1. **Texto-primeiro (recomendada):** parser Rust do `.cad` como texto + JSON + CLI. Barato, determinístico, sem Ghidra. Risco: algum campo obscuro.
2. **Ghidra-primeiro:** RE completo do EXE antes de codar. Preciso, mas lento e pesado; usuário já achou overkill.
3. **GUI-automation-primeiro:** pilotar o CADe via Wine/auto-click. Frágil, não dá formato IA-friendly.

Escolha: (1) agora, (2) e (3) como validação na fase 2.

## Fases

- [ ] **Fase 0 — Fundação (esta pasta):** README, docs, spec v0.1, git init. ✅ feito
- [ ] **Fase 1 — Gramática:** extrair IDs únicos do corpus (script Python), cruzar com manual, doc de campos do header.
- [ ] **Fase 2 — `cade_core` (Rust):** `parse()` + `emit()` + testes round-trip sobre `corpus/`.
- [ ] **Fase 3 — `cade_cli`:** `parse|emit|validate|new-from-json`; OpenCode usa como ferramenta.
- [ ] **Fase 4 — Imagem→JSON:** detector de símbolos sobre `Exemplos/*.png` (template matching → ML depois) + preview.
- [ ] **Fase 5 — Validação Wine + Ghidra headless:** abrir gerados no CADe_SIMU-Linux; scripts `tools/ghidra/` nos `Serialize` se preciso.

## Convenções

- Commits em PT-BR, pequenos. Testes: `cargo test` round-trip no corpus.
- `.cad` original nunca editado in-place; saída sempre em `out/`.
- Amostras grandes ficam em Downloads; só 3–5 cópias mínimas em `corpus/`.

## Próximo passo imediato (próxima sessão, aqui)

1. `git init` + primeiro commit (pedir confirmação do nome `cade-automation`).
2. Script `tools/extract_ids.py` no corpus → `docs/dicionario-simbolos.md`.
3. Confirmar spec v0.1 → virar `spec/spec-v1.md` congelada.
