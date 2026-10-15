# cade-automation

Sistema para automatizar atividades de controle industrial sobre arquivos `.cad` do **CADe_SIMU 4.0 [BR]**.

## Visão (2 frentes)

1. **Editar o existente:** abrir um `.cad`, modificar via código e gerar novo `.cad` válido que o próprio CADe_SIMU abre/simula.
2. **Criar do zero via IA:** gerar `.cad` a partir de descrição texto + imagem (ênfase em imagem). Uso via OpenCode como executor.

Estratégia: transformar `.cad` (texto proprietário com `*`/`#`) em formato IA-friendly (JSON) e voltar sem perda (round-trip).

## Descobertas-chave (14/10/2026)

- `.cad` **não é binário**: é texto ISO-8859, sem quebras de linha, header `CADe_SIMU*...`. Ghidra é overkill para v1.
- EXE é PE32 i386 VC++6 debug (MFC Doc/View: `CCADe_SIMUDoc`), string de serialização encontrada:
  `CADe_SIMU*%1d*%1d*%1d*%1d*%1d*%1d*%1d*%1d*%3d*%3d*%0.4f*...$$$`
- Fontes internas vazadas via strings: `Editar_Cable.cpp`, `Editar_NA_NC.cpp`, `EDITAR_PLC.cpp`, `EDITAR_ARDUINO.cpp`, `Simbolo.cpp`, `Librerias.cpp`, etc.
- Corpus local: `~/Downloads/CADe_SIMU 4.0 [BR]/` com 115+ `.cad`, manual PDF, exemplos PNG/BMP.
- Existe porte Linux: `KelvinNovais/CADe_SIMU-Linux` (AppImage, Wine). Relevante para automação headless.
- Ghidra (fase 2): `analyzeHeadless` + Ghidrathon (Python3) + `pyghidra-mcp` como MCP para LLM.

## Stack proposta

- `cade_core` em **Rust** (parser/serializer round-trip, validador) — `src/cade_core/`
- `cade_cli` em Rust ou Go (CLI para OpenCode chamar) — `src/cade_cli/`
- `C puro` só onde for gargalo (hot loop de parse), via FFI, não por padrão.
- `Python/Lua` para automação: scripts Ghidra (Ghidrathon), conversor imagem→símbolos, glue OpenCode.
- Render/validação: Wine + CADe_SIMU-Linux headless + screenshots diff.

## Layout

- `docs/` — contexto, formato `.cad`, pesquisa web
- `plans/` — plano de execução
- `spec/` — especificação das 2 frentes
- `corpus/` — amostras `.cad` (3 iniciais, resto fica em Downloads)
- `src/cade_core/`, `src/cade_cli/` — código futuro
- `tools/ghidra/` — scripts Ghidra futuros

## Próxima sessão

Abra a sessão do OpenCode **nesta pasta** (`cade-automation/`). Leia nesta ordem:
1. `docs/00-contexto.md`
2. `docs/formato-cad.md`
3. `spec/spec.md`
4. `plans/plano.md`
