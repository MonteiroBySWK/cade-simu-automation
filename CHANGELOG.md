# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/). Datas em AAAA-MM-DD.

## [0.3.0] — 2026-10-22

Conformidade **com o app real** (11/11), ladder/CLP no Rust e benchmark held-out.

### Conformidade com o app (teste diferencial)
- 11 goldens gravados no CADe_SIMU (`"fonte":"app"`) com o novo `tools/golden_app.py` (Wine): estado
  lido por imagem depois de cada ação; `cade conformidade` compara o motor Rust passo a passo
  (bobinas, lâmpadas, motores, saídas do CLP). **11 ok, 0 divergentes, 0 provisórios.**
- Fatos do app provados/corrigidos: disjuntores iniciam **abertos** (sem clique o motor não gira);
  **um ponteiro só** (não dá para segurar S1 e apertar S0); a captura pega **quadro parcial** (settle
  antes de ler); `soltar` no mesmo ponto do clique; o aviso de **CURTO é janela separada**
  (detectada/fechada, `curto:true` no golden).
- Transformador `3012` é **fonte** (secundário p4=L/p3=N): somar `3003` no mesmo par de trilhos dá
  CURTO no app — exemplo `partida_trafo_comando` corrigido; Python e Rust tratam `3012` como fonte.
- `geo_check`/`vinculos`: disjuntor (6002/6003/6009/6010) também comanda o contato 8016/8017.

### Ladder/CLP no Rust
- `cade_sim::ladder::CircuitoClp`: port fiel de `clp_sim.py` (tick de 100 ms, 10204/10205, contatos
  10050/10051, bobinas 10060/10061/10062, TON 10066, regime/oscilação), com os mesmos textos.
- `cade gate`/`design` rodam testes de ladder (ramo CLP sem `wires_check`); `cade conformidade`
  preenche `saidas_clp`. Paridade Rust×Python nos 5 exemplos (`tests/ladder_paridade.rs`).
- Corrigido `_desgruda` do `split_entities` (entidade colada ao IP do 10206 sumia no Rust).

### Avaliação e recusa explícita
- `tools/eval/heldout/`: 12 casos held-out em PT-BR, sem solução no repo (relé + ladder).
- `run_eval` pontua ladder (`clp_sim`, operandos, folha) e inclui `casos/ladder/` + `heldout/`;
  `--golden` = 100 em 11 relé + 5 ladder (16 casos).
- O gate **recusa classe sem modelo** (A11): pneumática, GRAFCET, 9007/9015, instruções de ladder não
  portadas, sensores 3+ fios, CLPs fora de 10204/5/6, 6015/6017 — erro acionável em vez de falso verde.

### Documentação e distribuição
- `docs/TODO.md` (100% funcional × ≥80% autônomo), `docs/bibliografia/automacao-industrial.md`
  (digest da disciplina + livro Miyagi), roadmap do `ladder/1` (§2.6), skill atualizada (reversão
  monofásica × trifásica, inversor, fatos do app, roteiro de projeto).
- CI publica o binário estático (`cade-<tag>-x86_64-unknown-linux-musl` + `SHA256SUMS`) no GitHub
  Release a cada tag `v*`.

### Porte para Rust (fase 1)
- Workspace Cargo na raiz; binário único `cade` (`validate|parse|emit|new-from-json|build|layout`).
  Novos crates `cade_model`, `cade_build` (cad_build) e `cade_layout` (layout.py) com saída **byte-idêntica**
  ao Python (goldens em `tests/golden`, testes em `tests/paridade`); crates-esqueleto para as próximas fases.
  Veja `docs/rust-port.md`. O binário agora fica em `target/{debug,release}/cade` (antes `src/cade_cli/target/...`).

### Porte para Rust (cade_sim + conformidade)
- Crate `cade_sim`: motor de simulação próprio (geometria de `cade_check::geom`, papéis por classe, contatos
  NA/NC/NA-NC/comutados, bobinas, lâmpadas, motores, disjuntores/fusíveis, temporizadores 9004/9005/9006 + 7004..7015,
  curto de fase, relaxação OK/RACE/INSTAVEL/CURTO). Estado idêntico ao `netlist_sim.py` (goldens em `tests/golden/sim`).
- `cade simulate|test|conformidade`; `cade gate`/`cade design` agora rodam os testes funcionais de verdade
  (`ExecutorSim` implementa `cade_check::ExecutorTestes`).
- Teste diferencial `tests/conformidade/<caso>/{circuito.cad,cenario.json,golden_app.json}` (goldens provisórios do
  oráculo Python; o app sobrescreve com `"fonte":"app"`), `Dockerfile` (imagem `scratch` só com o binário) e job de CI.
  Ver `docs/conformidade.md`. Ladder/CLP: só o trait `ModeloLadder` (outro agente).

### Porte para Rust (cade_check)
- Crate `cade_check`: `geo_check`, `wires_check`, vínculos por rótulo, `lint_layout` e mensagens acionáveis, mais
  `cade gate <cad> [--testes t.json] [--json]` e `cade design <layout.json> -o x.cad [--json]` com o mesmo relatório do
  MCP. Testes funcionais via trait `ExecutorTestes` (sem o `cade_sim`: `nao_portado`, gate reprovado). Paridade com o
  Python em `tests/golden/check` (27 layouts + 27 `.cad`, incluindo fixtures defeituosas).

### Instalação
- `python scripts/dev.py install-mcp|uninstall-mcp`: registra MCP + skill via `claude mcp add -s user` e
  `opencode mcp add --global` (caminhos absolutos, idempotente). Removidos `.mcp.json`/`opencode.json` do repo
  (geravam servidor duplicado em dois escopos).

### Adicionado
- Setup amigável e independente da máquina: `make setup|doctor|test|gate`, `scripts/setup.sh` (uv ou venv),
  `tools/doctor.py`, `requirements.txt`, `scripts/mcp-server.sh`, `.mcp.json` (Claude Code), `opencode.json`,
  `AGENTS.md`/`CLAUDE.md`, `CONTRIBUTING.md`, CI (GitHub Actions), `docs/DEPENDENCIAS.md`, `docs/integracao.md`.
- `tools/symbol_lib.json`: catálogo de classes versionado — **o repo não precisa mais do acervo/app** para gerar `.cad`.
- `tools/cade_config.py`: localização opcional do app/acervo (`CADE_DIR`, `CADE_EXE`, `CADE_ACERVO`).

### Corrigido
- `cad_test`/gate aplicavam a suite fixa da intercalada a QUALQUER circuito com KM1+KM2 (reversão correta
  reprovava 13/15). Agora, sem `"testes"`, o gate reprova com `SEM_TESTES`.
- Removido `tools/examples/intercalada.spec.json` (legado): tinha curto real (3×`3004` + PE no N) e só passava
  porque a suite antiga não checava curto. Use `intercalada.layout.json`.
- `cad_build` com lista vazia criava um botão `8000` fantasma; agora retorna erro.
- `cad_simulate` passa a expor lâmpadas acesas, curtos, temporizadores e pinos soltos.
- `cad_pins`/`cad_symbols` usam os nomes do binário (`docs/classes-papeis.json`) quando não há nome curado.
- Parser (`dissect`): arquivos com 1ª entidade de id curto (`Bardella 5.cad`) ou negativo (`Variador_II/III.cad`)
  agora são lidos (108/108 do acervo).
- Lint do layout não acusa mais "não é um trilho" para os trilhos de comando (`trilhos_comando`).
- Núcleo roda no Windows (UTF-8 explícito, `cade_cli.exe`, venv `Scripts\`, sem `/tmp`); CI em Ubuntu + Windows.

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
