# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/). Datas em AAAA-MM-DD.

## [Unreleased]

### Adicionado
- Setup amigável e independente da máquina: `make setup|doctor|test|gate`, `scripts/setup.sh` (uv ou venv),
  `tools/doctor.py`, `requirements.txt`, `scripts/mcp-server.sh`, `.mcp.json` (Claude Code), `opencode.json`,
  `AGENTS.md`/`CLAUDE.md`, `CONTRIBUTING.md`, CI (GitHub Actions), `docs/DEPENDENCIAS.md`, `docs/integracao.md`.
- `tools/symbol_lib.json`: catálogo de classes versionado — **o repo não precisa mais do acervo/app** para gerar `.cad`.
- `tools/cade_config.py`: localização opcional do app/acervo (`CADE_DIR`, `CADE_EXE`, `CADE_ACERVO`).

### Alterado
- Removidos todos os caminhos pessoais do código; scripts de Wine exigem `CADE_DIR`/`CADE_EXE` com mensagem clara.

## [0.2.0] — 2026-10-16

Geração de `.cad` do CADe_SIMU por IA, com conectividade e simulação **fiéis ao app real**
(engenharia reversa dirigida por Ghidra + verificação E2E no Wine).

### Adicionado
- **Motor de layout topológico** (`tools/layout.py`, `docs/dsl-layout.md`): a spec descreve
  trilhos, fontes, comando e potência **sem coordenadas**; o motor posiciona e roteia.
  - Rede de comando série-paralelo **recursiva**, vários degraus, vários pontos de liga/desliga.
  - Trilhos de comando com transformador, quebra automática em faixas/colunas.
  - Potência trifásica com contatores em paralelo e permutação de fases (reversão).
- **Ferramentas MCP de alto nível** (`tools/cade_mcp.py`): `cad_design` (layout → build → gate),
  `cad_gate`, `cad_pins`, `cad_examples`/`cad_example`, `cad_simular_no_app`; `cad_symbols` com
  nome/pinos/tamanho; `cad_preview` com cor por fase e destaque de pino solto/curto.
- **Gate de qualidade** (`tools/build_spec.py`): validação do arquivo, testes funcionais
  declarados na spec (`"testes"`), `geo_check` (curto de fase e pino solto), `wires_check`
  (fio atravessando símbolo) e vínculos por rótulo (térmico ↔ contato 95-96).
- **`tools/geo_check.py`**: conectividade por geometria seguindo as regras decompiladas do app
  (extremo a extremo, junção `4001`, estampa de fase por pino).
- **Simulador offline v2** (`tools/netlist_sim.py`): por geometria (ignora nets do arquivo),
  papéis por classe, lâmpadas, status `CURTO`, relaxação de temporizadores por injeção de papéis.
- **Verificador E2E no app** (`tools/app_sim.py`, `docs/app-sim.md`): abre no Wine, dá Play,
  aciona entradas e lê o estado por imagem; calibração coordenada→pixel automática.
- **Harness de avaliação** (`tools/eval/`): 11 casos em PT-BR com `--golden` (média 99,6/100).
- **Exemplos sem coordenadas** (`tools/examples/`): intercalada, partida direta, reversão,
  emergência, sinalização, dois motores, liga/desliga de 2 pontos, partida sequencial,
  3 degraus com lâmpadas, intertravamento com sinalização, comando por transformador.
- **Engenharia reversa** (`docs/re-engenharia.md` §9–12): layout das entidades, conectividade
  por geometria, orientação (n17), pinos reais de ~312 classes (`docs/pinos-binario.json`),
  semântica de 366 classes (`docs/classes-papeis.json`), temporizadores 9004–9007, botão 3D
  (`docs/3d.md`: apenas troca por bitmap, nada a preencher no gerador).
- `scripts/setup.sh`; variáveis `CADE_ACERVO`, `CADE_EXE`, `CADE_DIR`.
- Skill `automacao-industrial` reescrita (fluxo `cad_examples → cad_design → cad_preview`),
  com exemplos enunciado → layout.

### Corrigido
- **Fonte órfã em todo `.cad` gerado**: a entidade 0 (colada ao `CADe_SIMU*`) era copiada do
  arquivo-doador (um `3004` sem fio em (93,45) — os "4 pinhos soltos"). Agora a entidade 0 é a
  nossa primeira entidade; a numeração começa em 0.
- **Fontes erradas**: 3×`3004` estampavam fase 1 nas três fases e o PE (`3002`) no neutro dava
  curto N×PE no app. Agora fonte única `3007` (L1,L2,L3,N,PE) e trilho PE separado.
- **Gate que não reprovava**: o resultado de `cad_test` nunca era lido (imprimia `GATE: OK` com
  10/15 testes). Agora reprova teste falho, circuito sem testes e chave de teste inexistente.
- **Térmico nunca disparava no app**: o contato 8016/8017 só segue o `6007` de **mesmo
  rótulo**; os exemplos usavam `-F1`/`-RT1`. Rótulos unificados e gate de vínculos por rótulo.
- **Área da folha**: o limite 960×750 estava na unidade da barra de status do app (~3,3×);
  correto em unidades do `.cad` é **455×305** (`tools/sheet.json`).
- **Pinos**: geometria agora vem do binário (`tools/apply_bin_pins.py`), não de estatística do acervo.
- Papéis do RE só acrescentam classes ao simulador (nomes de pino do RE não existem na tabela do binário).

### Limitações conhecidas
- Temporizadores (9004–9007) e estrela-triângulo: semântica mapeada no RE, **ainda não**
  integrados ao gerador/validados no app (trabalho incompleto na branch `wip/temporizadores-bancada`).
- Matriz de cobertura por classe (bancada de teste de cada item da paleta): não concluída.
- O verificador no app não lê contato aberto/fechado isolado (só via lâmpada/bobina), nem
  temporizadores; depende de Wine + X11.
- Disjuntores/seccionadores começam abertos no Play; os testes cobrem o comando, não a potência.
- Classes de pneumática, PLC, GRAFCET e sensores: só nome/pinos, sem verificação.
- Sem vínculo com o autor do CADe_SIMU; uso didático (ver README).

## [0.1.0] — 2026-10-15

- Parser/emitter byte-fiel em Rust (`cade_core`, round-trip 114/114) e CLI `cade_cli`.
- Servidor MCP inicial, detector imagem→símbolos (kNN), autoria por símbolo/fio, simulador de
  netlist, validação no Wine.
