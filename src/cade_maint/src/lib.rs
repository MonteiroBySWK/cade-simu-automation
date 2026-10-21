//! `cade_maint` — ESQUELETO (fase futura).
//!
//! Regeneracao dos dados embutidos (so roda quando o catalogo muda; o resultado e versionado):
//!
//! - `tools/gen_symbol_lib.py`  -> symbol_lib.json (corpus/*.cad + acervo opcional)
//! - `tools/learn_pins.py`, `learn_pins2.py`, `apply_bin_pins.py` -> symbol_pins.json / pinos-binario.json
//! - `tools/layout.py --gen-dims` -> symbol_dims.json
//! - `tools/extract_ids.py`, `re_connectivity.py`
//!
//! Subcomandos previstos: `cade maint gen-symbol-lib|gen-dims|apply-bin-pins`.
