//! `cade_sim` — ESQUELETO (fase futura).
//!
//! Portar de Python (oraculo):
//!
//! - `tools/netlist_sim.py` -> `Circuito`, `estado`, `teste_casos`, `chaves_invalidas` (status OK/RACE/INSTAVEL/CURTO,
//!   bobinas, lampadas, temporizadores 9004..9007, semantica de docs/re-engenharia.md §11)
//! - `tools/ladder_sim.py`  -> simulador ladder
//!
//! Os testes de referencia estao em `tools/test_netlist_sim.py` e `tools/eval/casos/*.json`.
