# 00 — Contexto

## Software alvo

- **CADe_SIMU 4.0 [BR]**, por Juan Luis Villanueva Montoto. Shareware didático para diagramas de comandos elétricos, automação e pneumática + simulação.
- Instalador local: `~/Downloads/CADe_SIMU 4.0 [BR]/CADe_SIMU 4.0 [BR]/CADe_SIMU 4.0 [BR].exe`
  - PE32 i386 GUI, VC++6 debug (`MFC42D.DLL`, `MSVCRTD.DLL`, `MFCO42D.DLL`).
  - Classes MFC: `CCADe_SIMUDoc`, `CCADe_SIMUView` (Doc/View → serialização em `CADe_SIMUDoc.cpp` / `Dibujo.cpp`).
  - `libnodave.dll` (PE32 DLL) — comunicação Siemens S7 via MPI/Profibus; indica via PLC.
- Arquivos relevantes na pasta:
  - `CADe_S1.cad` (7132b), `CADe_S1` (3135b), `CADe_S1 - 17.01` (2230b), `CIRCUITO FV` (18907b), `config.cfg` (64b)
  - `Exemplos (diagramas)/Comandos Elétricos/*.png|jpg|bmp`, `Linguagem Ladder/*.png`
  - `Atividades para Simular/115 arquivos CADe_SIMU/Arquivos .cad/*.cad` (~115 amostras)
  - `Ajuda/Manual CADe_SIMU.pdf` (4.1MB) — fonte da tabela de símbolos
  - `BR.jpg`

## Objetivo do usuário

Automatizar controle industrial:
- (1) abrir `.cad` existente, manipular e regerar usando as funções do próprio software;
- (2) criar `.cad` do zero a partir de descrição texto, imagem (ênfase) ou nada, via agente (OpenCode).
- Colocar `.cad` num formato fácil de IA trabalhar (JSON intermediário).
- Stack sugerida: Rust/Go + C puro onde for crítico, Lua/Python para automação.
- Ghidra instalado, mas usuário considera pesado — delegar RE ao agente.
- Tudo versionado em git, nesta pasta, para abrir sessão OpenCode aqui.

## Decisão arquitetural inicial

Ghidra **não** é caminho crítico v1. O `.cad` é texto parseável. Prioridade:
1. Gramática do `.cad` por corpus + strings do EXE (barato, determinístico).
2. Round-trip byte-idêntico (ou semanticamente idêntico) em Rust.
3. JSON intermediário versionado (`cade.json v1`) como contrato IA↔`.cad`.
4. Ghidra/headless + Wine + visão computacional só na fase 2 (validação de simulação e extração de comportamento).
