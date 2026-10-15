# Spec — cade-automation v0.1 (rascunho para revisão)

## F1 — Editar `.cad` existente

- **IN:** caminho `.cad` + operação (ex: `mover simbolo id X,Y`, `trocar rotulo`, `adicionar fio A-B`, `exportar json`).
- **OUT:** novo `.cad` que o CADe_SIMU 4.0 abre sem erro + diff legível + `cade.json` correspondente.
- **Critério de aceite:** round-trip `*.cad → json → *.cad` semanticamente idêntico em 100% do corpus inicial (byte-idêntico onde o formato for canônico); abrir 3 amostras geradas no Wine sem popup de erro.

## F2 — Criar `.cad` do zero via IA

- **IN:** (a) texto livre, (b) imagem de diagrama (foco), (c) nada (template vazio com legenda).
- **OUT:** `.cad` válido + preview PNG + `cade.json` + log de decisões (símbolos detectados com confiança).
- **Critério de aceite:** a partir de 1 foto de partida-direta simples, gerar `.cad` que abre e simula; precisão de símbolos ≥80% no conjunto de `Exemplos/*.png`.
- **Contrato IA:** OpenCode chama `cade_cli` (`parse`, `emit`, `validate`, `new-from-json`); nunca escreve `*`/`#` na mão.

## `cade.json v1` (contrato)

```json
{
  "meta": {"titulo": "220V", "modo": 0, "versao": 3005},
  "simbolos": [{"id": "6017", "sub": "DJ", "x": 48, "y": 63, "rotulo": "DJ1"}],
  "fios": [{"de": [5,1], "para": [6,1], "pontos": [[39,57],[45,75]]}],
  "textos": []
}
```

Campos exatos mudam após gramática final; versão fixa em `v1`.

## Fora de escopo v1

Simulação elétrica fiel, PLC/Arduino, pneumática completa, editor GUI próprio, análise de binário do EXE.

## Riscos

- IDs `NNNN#` sem catálogo oficial → mitigar com dicionário extraído do corpus + manual.
- Wine pode não rodar AppImage headless → fallback: validação só por parser + diff visual manual.
- Riscos de formato fecham por corpus + Wine; sem dependência de análise de binário.

---
Congelada em 15/10/2026 a partir da v0.1 (Fase 1 concluída, sem alteração de conteúdo).
