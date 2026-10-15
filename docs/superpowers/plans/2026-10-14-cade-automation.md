# cade-automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fechar as Fases 1–5 do `plans/plano.md`: gramática `.cad`, `cade_core` Rust round-trip, `cade_cli`, imagem→JSON, validação Wine.

**Architecture:** Texto-primeiro: parser Rust determinístico sobre corpus + `cade.json v1` como contrato IA↔`.cad`; Ghidra/Wine só como validação fase 5.

**Tech Stack:** Rust (cade_core/cade_cli), Python3 (tools/extract_ids.py, imagem), Wine + CADe_SIMU-Linux (validação).

**Spec:** `spec/spec.md` (v0.1, a congelar em `spec/spec-v1.md`)

## Global Constraints

- `.cad` original nunca editado in-place; saída sempre em `out/`.
- Commits em PT-BR, pequenos.
- Testes: `cargo test` round-trip no corpus.
- OpenCode chama `cade_cli`; nunca escreve `*`/`#` na mão.

## Review Focus

- Arquivo `.cad` com encoding ISO-8859 fora do latin1 esperado não deve quebrar o parser — esperar erro legível.
- Header com `modo`/`versao` desconhecidos deve ser preservado no round-trip, não rejeitado.
- Entidade `NNNN#` desconhecida deve fazer round-trip byte-idêntico mesmo sem estar no dicionário.
- Coordenadas negativas devem ser preservadas exatamente.
- `$$$` ausente/truncado no fim deve gerar erro de validação, não panic silencioso.

---

### Task 1: Fase 1 — Gramática (extract_ids + dicionário)

**Files:**
- Create: `tools/extract_ids.py`
- Create: `docs/dicionario-simbolos.md`
- Modify: `docs/formato-cad.md` (anexo achados Fase 1)

**Interfaces:**
- Consumes: `corpus/*.cad` (latin1, sem newline)
- Produces: tabela ID→sub→qtd→exemplo usada pela Task 2 (modelo Rust)

- [ ] **Step 1: Criar `tools/extract_ids.py`** que lê `corpus/*.cad` em latin1, extrai header, IDs `NNNN#SUB`, contagens, fios `4000#`, e imprime markdown
- [ ] **Step 2: Rodar e gerar `docs/dicionario-simbolos.md`**
- [ ] **Step 3: Atualizar `docs/formato-cad.md` com achados reais dos 3 arquivos**
- [ ] **Step 4: Congelar `spec/spec-v1.md` a partir de `spec/spec.md`**
- [ ] **Step 5: Commit PT-BR**

### Task 2: Fase 2 — `cade_core` Rust (parse + emit round-trip)

**Files:**
- Create: `src/cade_core/Cargo.toml`, `src/cade_core/src/lib.rs`
- Test: `src/cade_core/tests/roundtrip.rs` sobre `corpus/*.cad`

**Interfaces:**
- Consumes: gramática da Task 1
- Produces: `parse(cad)->tokens`, `emit(tokens)->cad` usados pela Task 3

- [ ] **Step 1: Scaffold crate + teste round-trip falhando**
- [ ] **Step 2: Implementar parse/emit token-preserving (`*`/`#`/`$$$`)**
- [ ] **Step 3: `cargo test` verde nos 3 .cad**
- [ ] **Step 4: Commit**

### Task 3: Fase 3 — `cade_cli` (parse|emit|validate|new-from-json)

**Files:**
- Create: `src/cade_cli/Cargo.toml`, `src/cade_cli/src/main.rs`
- Test: CLI sobre `corpus/` + `cade.json` exemplo

- [ ] **Step 1: Subcomandos parse/emit/validate/new-from-json**
- [ ] **Step 2: Teste e2e CLI**
- [ ] **Step 3: Commit**

### Task 4: Fase 4 — Imagem→JSON (detector + preview)

**Files:**
- Create: `tools/img2json.py`, `docs/imagem-pipeline.md`

- [ ] **Step 1: Template matching sobre `Exemplos/*.png` (se acessível) ou corpus PNG**
- [ ] **Step 2: Gerar `cade.json` + preview PNG**
- [ ] **Step 3: Commit**

### Task 5: Fase 5 — Validação Wine + Ghidra headless (se preciso)

**Files:**
- Create: `tools/validate_wine.sh`, `tools/ghidra/*.py` (se ambiguidade restar)

- [ ] **Step 1: Abrir gerados no CADe_SIMU-Linux via Wine, screenshot/diff**
- [ ] **Step 2: Só se gramática não fechar: script Ghidra nos `Serialize`**
- [ ] **Step 3: Commit final + aviso de conclusão**
