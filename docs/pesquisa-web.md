# Pesquisa web — 14/10/2026

## CADe_SIMU

- Sem spec pública do `.cad` (buscas só retornam tutoriais YouTube e papers didáticos). Confirma necessidade de RE próprio.
- Porte Linux: `github.com/KelvinNovais/CADe_SIMU-Linux` (AppImage, senha 4962). Base para automação Wine/headless sem Windows.
- Manual local `Ajuda/Manual CADe_SIMU.pdf` é a melhor fonte de símbolos; `Scribd: CADe-SIMU-Manual-in-Practice` como backup.

## Ghidra (fase 2, não v1)

- `analyzeHeadless` em `support/`: roda análise sem GUI; pre/post-scripts possíveis.
- Limite: Ghidra usa Jython (Python2). Para Python3 usar **Ghidrathon** (blog Google Threat Intel) ou **PyGhidra**.
- `pyghidra-mcp` (clearbluejar): MCP server headless para análise multi-binária assistida por LLM — encaixa no pedido "você mexa no Ghidra melhor que eu".
- Estratégia: só levar ao Ghidra as funções `Serialize`/`OnOpenDocument`/`Cdib` se o corpus não fechar a gramática.

## Automação de GUI / validação

- Wine + CADe_SIMU-Linux AppImage → abrir `.cad` gerado, screenshot, diff contra referência.
- `libnodave.dll` indica integração PLC Siemens — fora do escopo v1, anotar para fase PLC.

## Alternativas consideradas

- Parser só em Python: mais rápido de prototipar, mas round-trip byte-fiel e performance de corpus favorecem Rust com binding Python (PyO3) depois.
- Conversão direta imagem→`.cad` end-to-end (ML): descartado v1; usar pipeline em 2 etapas (imagem→`cade.json` via visão + regras, `cade.json`→`.cad` determinístico).
