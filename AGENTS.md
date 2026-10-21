# AGENTS.md — cade-simu-automation

Gera/valida circuitos do **CADe_SIMU 4.0** (`.cad`) por IA. **Nunca escreva `*`/`#` à mão**: use o MCP `cade-simu`.

## Setup (sem Wine)
`python scripts/dev.py setup && python scripts/dev.py doctor` · testes: `python scripts/dev.py test` · todos os exemplos + eval: `python scripts/dev.py gate`.
Dependências e o que é opcional: `docs/DEPENDENCIAS.md`. Instalar o MCP+skill: `python scripts/dev.py install-mcp` (`docs/integracao.md`).

## Como criar um circuito
1. Leia `skills/automacao-industrial/SKILL.md`.
2. `cad_examples` / `cad_example` (few-shot) → escreva o layout **topológico** (`docs/dsl-layout.md`).
3. `cad_design` → corrija pelo relatório do gate (`GATE: OK` = build + testes + geo_check + fios).
4. `cad_preview` para ver. O app real (`cad_simular_no_app`) só se houver Wine.

## Regras que já custaram caro
- Fonte única `3007` (L1,L2,L3,N,PE) e **trilho PE próprio** (PE nunca no N).
- Térmico `6007` e contato `8016/8017` com o **mesmo rótulo**; auxiliares/polos com o rótulo da bobina.
- Conectividade é **geometria** (extremo a extremo); nets gravados no arquivo não valem.
- Folha segura: x ≤ 455, y ≤ 305 (`tools/sheet.json`). Ligue **todos** os pinos.
- Mexeu em pinos/roteador/layout? Rode `python scripts/dev.py test` e `python scripts/dev.py gate` antes e depois.
- Um Ghidra e um Wine por vez; não derrube processo alheio.
