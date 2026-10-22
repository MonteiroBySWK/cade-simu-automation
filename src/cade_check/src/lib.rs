//! `cade_check` — gate estatico do projeto (port de `geo_check.py`, `wires_check.py` e do gate de
//! `build_spec.py`). O Python continua sendo o ORACULO: `tests/golden/check/` guarda a saida dele.
//!
//! | modulo | Python | papel |
//! |---|---|---|
//! | [`geom`] | `geo_check.pinos_da_classe/_rot` + uniao de nets | **geometria compartilhada** (API publica p/ o `cade_sim`) |
//! | [`geo`] | `geo_check.analisar` | curtos de fase e pinos soltos |
//! | [`fios`] | `wires_check.analisar` | fio atravessando o corpo de simbolo |
//! | [`vinculos`] | `build_spec.conferir_vinculos` | termico/bobina por rotulo |
//! | [`lint`] | `build_spec.lint_layout` | avisos de autoria do layout |
//! | [`acionavel`] | `acionavel_solto/curto` | mensagens que dizem o que fazer |
//! | [`gate`] | `build_spec.gate/construir`, `cad_gate/cad_design` | relatorio JSON identico ao do MCP |
//!
//! Testes funcionais **nao** ficam aqui: dependem do simulador (`cade_sim`). O gate recebe um
//! [`ExecutorTestes`]; sem ele ([`NaoPortado`]) o campo `testes` sai `nao_portado` e o gate NAO
//! aprova (`ok=false`), expondo a parte estatica em [`Relatorio::estatico_ok`].

pub mod acionavel;
pub mod fios;
pub mod gate;
pub mod geo;
pub mod geom;
pub mod lint;
pub mod vinculos;

pub use gate::{
    construir, design_texto, gate_arquivo, gate_bytes, parse_testes, ExecutorTestes, NaoPortado, Relatorio, SaidaTestes,
};
