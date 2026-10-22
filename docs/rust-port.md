# Porte para Rust — binário único `cade`

**Meta:** o projeto 100% em Rust, um único binário (`cade`, `cade.exe` no Windows), sem Python em
runtime. Enquanto isso, o **Python é o ORÁCULO de paridade**: só é apagado quando o binário tiver
paridade total (matriz abaixo). Este documento é o guia das fases seguintes.

```bash
cargo build --release          # -> target/release/cade
cargo test --workspace         # inclui tests/paridade (byte-a-byte contra o Python)
cargo clippy --workspace --all-targets
cade build tools/examples/reversao.layout.json -o out/reversao.cad
cade layout tools/examples/reversao.layout.json -o out/reversao.spec.json
cade design tools/examples/reversao.layout.json -o out/reversao.cad --json   # layout -> .cad + gate (como cad_design)
cade gate out/reversao.cad [--testes t.json] [--json]                        # gate de um .cad existente (como cad_gate)
```

Sem rede em runtime; os dados (`tools/*.json`, `docs/*.json`, doador `corpus/Arranque_1.cad`) são
embutidos com `include_str!`/`include_bytes!` em `cade_model::dados` — o binário não lê arquivo
nenhum além do que o usuário passa.

## Arquitetura (workspace na raiz, crates em `src/`)

| crate | papel | estado |
|---|---|---|
| `cade_core` | formato `.cad`: parse/emit byte-fiel (tokens por `*`), `validate` | pronto (já existia) |
| `cade_model` | entidades (`split_entities`, `split_all`, `parse_ent` = `tools/dissect.py`), catálogo de protótipos (`Catalogo` = `cade_mcp._lib()` + `mk_dataset.load_donor`), dados embutidos (`dados::*`), `pyfmt` (repr/int/`//` do Python p/ mensagens idênticas) | pronto |
| `cade_build` | `cad_build`: símbolos/fios/conexões/trilhos → `.cad`; roteador `_rotear`, `_assign_nets`, `_shorts`; entidade 0 = 1ª gerada | pronto, byte-idêntico |
| `cade_layout` | `layout.py`: `compilar` (spec topológica → spec baixa: rede série-paralelo, rungs, serpentina, faixas, `trilhos_comando`, fontes, terra, `potencia` com paralelo/`ordem`) e `build_spec.normalizar` | pronto, byte-idêntico |
| `cade_cli` | binário `cade`: `validate|parse|emit|new-from-json|build|layout|gate|design` | pronto |
| `cade_check` | `geo_check`, `wires_check`, vínculos por rótulo, `lint_layout`, mensagens acionáveis, `gate`/`construir` (relatório idêntico ao MCP); **testes funcionais via trait** | **pronto (parte estática)** |
| `cade_sim` | motor de simulação (`netlist_sim` + temporizadores + papéis do RE), casos de teste, `conformidade`, executor do gate; **ladder/CLP: só o trait `ModeloLadder`** | **pronto** (ladder pendente) |
| `cade_render` | `cad_render` (preview PNG) | **esqueleto** |
| `cade_mcp` | servidor MCP stdio (`cade mcp`) | **esqueleto** |
| `cade_app` | Wine/CADe_SIMU real (`app_sim`, `wine_mgr`, `cade_open`, `cade_config`) | **esqueleto** |
| `cade_vision` | detector de símbolos em imagem | **esqueleto** |
| `cade_maint` | `gen_symbol_lib`, `learn_pins*`, `apply_bin_pins`, `--gen-dims` | **esqueleto** |
| `tests/paridade` | crate de testes: compara Rust × goldens do Python | pronto |

Dependências: `serde`/`serde_json` (feature `preserve_order`, **obrigatória**: a ordem das chaves do
JSON define a ordem de conexões/fios e portanto os bytes do `.cad`) e `clap`.

## Paridade (matriz Python → Rust)

| feature Python | crate Rust | status |
|---|---|---|
| `dissect.split_entities/split_all/parse_ent` | `cade_model::entidade` | feito (testes unitários + indiretamente nos goldens) |
| `cade_mcp._lib` / `mk_dataset.load_donor` | `cade_model::Catalogo` | feito (só `symbol_lib.json` + doador; acervo externo opcional **não** é lido) |
| `cade_mcp.cad_build` (+`_rotear`,`_pin_coord`,`_symboxes`,`_cruza`,`_assign_nets`,`_shorts`) | `cade_build` | **byte-idêntico** (16 layouts + 3 specs baixas) |
| `layout.compilar` (todas as formas) | `cade_layout::compilar` | **byte-idêntico** (spec baixa em JSON `indent=1`) |
| `build_spec.normalizar` | `cade_layout::normalizar` | feito |
| mensagens de erro do `ValueError` do layout | `LayoutError` | idênticas (8 casos de erro) |
| `build_spec.lint_layout`, `conferir_vinculos`, `acionavel_*` | `cade_check::{lint,vinculos,acionavel}` | **idêntico** (goldens `tests/golden/check`) |
| `build_spec.gate/construir`, `cad_gate`/`cad_design` (relatório JSON) | `cade_check::{gate_arquivo,construir}` + `cade gate/design` | **idêntico na parte estática**; testes funcionais executados pelo `cade_sim::ExecutorSim` |
| `build_spec.conferir_chaves_de_teste`, `_parse_testes` | `cade_check::gate` (`parse_testes`; chaves vêm do executor) | parse portado; chaves: `cade_sim::executor::mensagens_chaves` |
| `geo_check.py`, `wires_check.py` | `cade_check::{geo,fios}` (+ `geom`, geometria compartilhada) | **idêntico** |
| `netlist_sim.py`, `cad_test`/`cad_simulate` | `cade_sim` (`cade simulate`, `cade test`, executor do gate) | **feito** (estado idêntico ao Python em 11 exemplos × ~1000 combinações + temporizadores) |
| `ladder_sim.py` | `cade_sim::ladder` (`ModeloLadder`) | pendente (outro agente) |
| `cad_render.py`, `cad_preview.py` | `cade_render` | pendente |
| `cade_mcp.py` (tools MCP), `mcp_call.py` | `cade_mcp` + `cade mcp` | pendente (`cad_build`/`cad_design` já têm núcleo) |
| `app_sim.py`, `wine_mgr.py`, `cade_open.py`, `cade_config.py` | `cade_app` | pendente |
| `detect_symbols.py`, `img2cad.py`, `img2json.py`, `classifier.py`, `mk_dataset.py` (dataset) … | `cade_vision` | pendente |
| `gen_symbol_lib.py`, `learn_pins*.py`, `apply_bin_pins.py`, `layout.py --gen-dims` | `cade_maint` | pendente |
| `scripts/dev.py`, `doctor.py`, `eval/run_eval.py` | `cade doctor/gate` | pendente |

### Como a paridade é medida

`tests/golden/gerar.py` roda o **Python** e grava, para cada caso:

- `<n>.layout.json` (entrada), `<n>.spec.json` (spec baixa, `json.dumps(indent=1, ensure_ascii=False)`), `<n>.cad`;
- `<n>.erro.txt` (texto exato do `ValueError`) para entradas inválidas;
- `<n>.baixa.json` + `.cad` (roteador sem o motor de layout: sem trilhos, `via`, `fios` manuais, motor+contator).

Casos: os 11 `tools/examples/*.layout.json` + extras `x_*` (9 degraus → faixas, serpentina de 30, forma
legada que vira rede, paralelo aninhado, uma lâmpada) + 8 erros + 3 baixas. O teste
`tests/paridade/tests/paridade.rs` compara **bytes** do `.cad` e **texto** do `.spec.json`;
`src/cade_cli/tests/cli.rs` repete pelo binário real. O teste `todos_os_exemplos_de_tools_tem_golden`
falha se um exemplo novo/alterado não tiver golden — rode `python3 tests/golden/gerar.py` e commite.

**Resultado atual: byte-idêntico em todos os casos**, sem exceção documentada.

#### Paridade do gate (`cade_check`)

`tests/golden/check/gerar.py` roda `build_spec.construir` (layouts) e `build_spec.gate` (`.cad`) no **Python**
com a parte funcional neutralizada (`cad_test` → `SEM_TESTES`, chaves de teste → `[]`) e grava a parte
**estática** do relatório: `build{ok,mensagem}`, `geo{curtos,soltos,curtos_msg,soltos_msg}`, `fios{ok,n,atravessam}`,
`avisos`, `erros` (sem os de teste, prefixos `teste `/`sem testes`/`testes:`), `estatico_ok`. Casos:

- `<n>.design.json` (27): todos os `tests/golden/*.layout.json` (exemplos, `x_*` e os 8 `e_*` de erro) + fixtures
  layout; o teste Rust roda `cade_check::construir` e compara campo a campo;
- `<n>.gate.json` (27): todos os `.cad` de `tests/golden`, `corpus/*.cad` e as fixtures defeituosas;
- fixtures defeituosas (geradas pelo Python): `defeito_3004x3_pe_no_n` (3004 por fase, fases soltas), `defeito_curto_pe_n_e_fases`
  (PE no N e L2 no L1 → `CURTO`), `defeito_termico_rotulo` (6007 × 8017 com rótulos diferentes), `defeito_pino_solto`,
  `defeito_fio_atravessa` (fio manual atravessando o corpo do 9000).

O teste fica em `src/cade_check/tests/paridade.rs` (e `src/cade_cli/tests/check.rs` repete pelo binário). O gerador é
separado de `tests/golden/gerar.py` (que apaga tudo em `tests/golden/*`; ele preserva subdiretórios). Rode
`cargo build && python3 tests/golden/check/gerar.py` (o Python chama `target/debug/cade`) quando o oráculo mudar de propósito.

**Testes funcionais:** `cade_check` define `trait ExecutorTestes { fn executar(&self, cad, casos) -> Option<SaidaTestes> }`
(`SaidaTestes` = texto do `cad_test` + mensagens de `conferir_chaves_de_teste`; o gate interpreta como o Python:
`PASSOU`/`SEM_TESTES`/`[FALHA]`/`RESULTADO: n/m`). O `cade_sim::ExecutorSim` implementa o trait e é o executor do binário
(`executor()` em `src/cade_cli/src/check.rs`): `cade gate`/`cade design` rodam os testes funcionais de verdade. `NaoPortado`
continua em `cade_check` para quem precisar do gate só estático. Sem casos = `SEM_TESTES` = gate reprovado; chave inexistente
= teste vacuo = reprovado.

**Geometria compartilhada (`cade_check::geom`)**: `pinos_da_classe` (binário primeiro, depois `symbol_pins.json` **na ordem do
arquivo** — a ordem define a dos pinos soltos), `rotacionar`, `entidades_do_cad`, `Conectividade::de_entidades` (união de nets
por extremo/junta 4001, `pinos` em coordenada absoluta, `rede_do_ponto`, `e_extremo`) e `geo::analisar_entidades`. O `cade_sim`
constrói o `Circuito` em cima disso (não reimplementa a conectividade).

### Simulação (`cade_sim`)

`cade simulate|test|conformidade|gate|design`. Detalhes de conformidade, formato dos goldens do app, Docker e licença:
**`docs/conformidade.md`**.

- **Paridade com `tools/netlist_sim.py`** (o oráculo): `tests/golden/sim/gerar.py` grava, para os 11 exemplos, os casos
  declarados + uma varredura (entradas vazias, cada uma, pares, todas × bobinas iniciais nenhuma/cada/todas) com o `estado()`
  completo do Python, e `timers.sim.json` (ON/OFF-delay por `contato_temp`). O teste `tests/paridade/tests/simulacao.rs`
  compara status, bobinas, lâmpadas, curtos, temporizadores (tipo/tempo/decorrido/saída), entradas, bobinas e pinos soltos.
  Rode `python3 tests/golden/sim/gerar.py` só quando o oráculo mudar de propósito.
- **Modelo em duas camadas** (`papeis.rs`): (1) tabela embutida idêntica à do Python (contatos NA/NC `8000/8001/8016/8017/7000/7001/
  10050/10051`, bobinas `9000/10060`, lâmpada `9008`, polos `2001`, passam-sempre `6007/6009/6010`); (2) derivada de
  `docs/classes-papeis.json` para o resto, **por `contatos[].fecha_quando`**: NA-NC/comutados (`7002/7003/8002/8003/8018/8019`),
  botões/fins de curso/sensores, interruptores e disjuntores (iniciam **abertos**, `estado==1`), fusíveis (`estado==0`), seletor,
  contatos temporizados `7004..7015` (ligam ao temporizador de **mesmo rótulo**), temporizadores-carga `9004/9005/9006`
  (tempo = rótulo 6, unidade = rótulo 5, tick 100 ms) e motores (`gira` com dois pinos de fase de estampas diferentes). A
  camada 1 prevalece. O Rust é **superconjunto** do Python (o Python ignora a camada 2 quase inteira).
- **Ainda sem modelo** (ignorados, não inventados): temporizador intermitente `9007`, gerador de pulsos `9015`, sensores
  eletrônicos de 3 fios, lógica/GRAFCET/pneumática, e todo o **ladder/CLP** (`10050..10083`, `10204..10206`: o contato ladder
  10050/10051 hoje cai no modelo legado do Python — contato NA/NC bidirecional sem fonte).
- Diferenças deliberadas vs Python: entradas aceitam inteiro (seletor 0..2); `esperado_motores`; tempo contínuo (não quantizado
  em ticks); `tonof`.

### Armadilhas de paridade (já resolvidas, não reintroduza)

- **Ordem de inserção** importa: `serde_json` com `preserve_order`; union-find do layout mantém a
  ordem de inserção dos tokens (`list(uf.p)`), e a ordem dos grupos é `sorted(..., key=str)` da
  tupla Python (`Tok::py_str`).
- **Divisão com piso** do Python (`//` com negativos): use `cade_model::pyfmt::fdiv`.
- **Float vs inteiro**: `(a+b)/2` comparado com inteiros foi reescrito como `2*v <= a+b`.
- **Quirks copiados de propósito**: `_assign_nets` só conhece os pinos topo `A`/`B` de `symbol_pins`
  (multi-pinos só pela geometria no `geo_check`); marcadores 4018/4009/4001 gravam `nums[22]`;
  `_rotear` usa `info.get(pino)` de topo (só `A`/`B`) para o lado de escape; `_ultima(rows[0][-1])`
  na espinha de saída; `titulo` do `cad_build` é ignorado.
- Mensagens de erro usam `cade_model::pyfmt::repr*` (repr de dict/list/str do Python).
- Diferença deliberada: `cade layout` usa `normalizar` (o `titulo` do envelope vence, como no `build`),
  enquanto `python tools/layout.py` imprimia `"NOVO"` quando o título estava só no envelope.
- Gate: `wires_check` com campo numérico ausente usa 0 (o Python abortaria com `IndexError`); erro de build que não começa com `ERRO` vira `layout invalido: ...` (no Python seria `<Exceção>: ...`); JSON malformado usa a mensagem do `serde_json`.
- Limitações vs Python: classes que só existem no acervo externo (`CADE_ACERVO`: 5009, 1055) não
  estão no catálogo embutido; `IndexError` de listas curtas vira `ValueError` com a mesma mensagem.

## Ladder / CLP (contrato no PR #5, branch `feat/ladder`)

O contrato (`docs/ladder.md`, `docs/ladder.schema.json`, `tools/examples/*.ladder.json`,
`tools/eval/casos/ladder/`) fica fora da fase 1. Preparação feita aqui:

- As chaves de topo `ladder` e `clp` são **reservadas** em `cade_layout::SECOES_RESERVADAS`; `normalizar`
  falha com mensagem explícita em vez de ignorá-las em silêncio. A fase `cade_sim`/`cade_layout` implementa
  a compilação ladder → spec baixa (mesmo funil `normalizar` → `cade_build::construir`) e a simulação.
- Correções de pinos medidas pelo RE, **ainda não aplicadas** nos JSON (aplicar em `tools/symbol_pins.json` /
  `docs/pinos-binario.json` e regenerar os goldens com `tests/golden/gerar.py`): saída `10205` com pino em
  `(0,24)` (não `(0,27)`); PE da CPU `10206` em `(12,0)`; pino direito da bobina ladder `10060` em `(12,0)`;
  entradas/saídas `10204`/`10205` precisam de `n16=1` (hoje o catálogo gera `n16=0`: ajustar o protótipo
  em `symbol_lib.json` ou sobrescrever no `cade_build`).

## Próximas fases (podem rodar em paralelo — cada uma toca só o seu crate)

Regras comuns:

1. Comece escrevendo os **goldens** a partir do Python (estenda `tests/golden/gerar.py` ou crie
   `tests/golden/<fase>/gerar.py`), versione-os e só então porte. Use `cade_model::{split_all,parse_ent}`
   e `cade_model::dados::*` (pinos, dims, classes-papéis, nomes) — nada de ler `tools/`/`docs/` em runtime.
2. Mantenha as **mesmas mensagens** do Python (são o contrato do MCP e das skills).
3. Cada crate expõe uma API de biblioteca; o subcomando de `cade_cli` é só casca (`cade check`,
   `cade sim`, `cade preview`, `cade mcp`, `cade maint ...`). Acrescente dependências no `Cargo.toml` do
   crate, não no workspace (exceto versões compartilhadas em `[workspace.dependencies]`).
4. Antes do PR: `cargo test --workspace`, `cargo clippy --workspace --all-targets`, e o Python
   (`python scripts/dev.py test`) ainda verde.

Por fase:

- **cade_check**: FEITO (ver "Paridade do gate"). Falta só ligar o executor de testes do `cade_sim`.
- **cade_sim**: FEITO (ver "Simulação"). Falta o ladder/CLP (`cade_sim::ladder::ModeloLadder`).
- **cade_render**: `renderizar(path, scale)` → PNG; golden por hash de pixels ou comparação com tolerância.
- **cade_mcp**: JSON-RPC stdio; reaproveite `cade_layout::normalizar` + `cade_build::construir` para
  `cad_design`/`cad_build`; `tools/mcp_call.py`/`test_mcp.py` descrevem o contrato.
- **cade_app / cade_vision / cade_maint**: ver comentários de topo de cada `lib.rs`.
- **Fim do porte**: quando todas as linhas da matriz estiverem feitas, mover `tools/*.json`,
  `docs/*.json` e `corpus/Arranque_1.cad` para um diretório de dados (ajustar só `cade_model::dados`),
  apagar o Python e trocar `scripts/`/CI/skills para chamar `cade`.
