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
| `cade_cli` | binário `cade`: `validate|parse|emit|new-from-json|build|layout` | pronto |
| `cade_check` | `geo_check`, `wires_check`, vínculos por rótulo, `lint_layout`, mensagens acionáveis do gate | **esqueleto** |
| `cade_sim` | `netlist_sim` (+temporizadores), `ladder_sim`, `teste_casos` | **esqueleto** |
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
| `build_spec.lint_layout`, `conferir_vinculos`, `acionavel_*`, `gate` | `cade_check` | pendente |
| `geo_check.py`, `wires_check.py` | `cade_check` | pendente |
| `netlist_sim.py`, `ladder_sim.py`, `cad_test`/`cad_simulate` | `cade_sim` | pendente |
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
- Limitações vs Python: classes que só existem no acervo externo (`CADE_ACERVO`: 5009, 1055) não
  estão no catálogo embutido; `IndexError` de listas curtas vira `ValueError` com a mesma mensagem.

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

- **cade_check**: `geo_check.analisar(path, redes)` (regras de docs/re-engenharia.md §9.2), `wires_check.analisar`,
  `conferir_vinculos`, `lint_layout`, `acionavel_solto/curto`. Golden: JSON de `(curtos, soltos)` e `(n, ruins)`
  por `.cad` de `tests/golden/*.cad` + `corpus/*.cad`.
- **cade_sim**: `Circuito` (nets por geometria, entradas/bobinas/lâmpadas), `estado`, temporizadores, `teste_casos`.
  Golden: `tools/eval/casos/*.json` e os casos `testes` dos exemplos (`RESULTADO: n/n OK`).
- **cade_render**: `renderizar(path, scale)` → PNG; golden por hash de pixels ou comparação com tolerância.
- **cade_mcp**: JSON-RPC stdio; reaproveite `cade_layout::normalizar` + `cade_build::construir` para
  `cad_design`/`cad_build`; `tools/mcp_call.py`/`test_mcp.py` descrevem o contrato.
- **cade_app / cade_vision / cade_maint**: ver comentários de topo de cada `lib.rs`.
- **Fim do porte**: quando todas as linhas da matriz estiverem feitas, mover `tools/*.json`,
  `docs/*.json` e `corpus/Arranque_1.cad` para um diretório de dados (ajustar só `cade_model::dados`),
  apagar o Python e trocar `scripts/`/CI/skills para chamar `cade`.
