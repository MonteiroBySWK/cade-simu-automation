//! `cade_check` — ESQUELETO (fase futura).
//!
//! Portar de Python (oraculo), mantendo as mesmas mensagens:
//! - `tools/geo_check.py`   -> `geo::analisar(path, redes) -> (curtos, soltos)`  (conectividade por geometria,
//!   docs/re-engenharia.md §9.2: fio-fio por extremo, junta 4001, pino so liga a extremo de fio, estampas de fase)
//! - `tools/wires_check.py` -> `fios::analisar(path) -> (n_fios, ruins)`          (fio atravessando corpo de simbolo)
//! - `tools/build_spec.py`  -> `conferir_vinculos`, `acionavel_solto`, `acionavel_curto`, `lint_layout`,
//!   `conferir_chaves_de_teste` (parte que nao depende do simulador)
//!
//! Use `cade_model::{split_all, parse_ent}` e `cade_model::dados::{pinos_binario, symbol_pins}`.
//! Paridade: gere goldens com o Python (ver docs/rust-port.md, "Proximas fases").
