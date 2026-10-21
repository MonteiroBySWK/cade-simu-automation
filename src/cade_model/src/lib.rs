//! `cade_model` — entidades do `.cad`, catalogo de classes e dados embutidos.
//!
//! Equivalentes Rust de `tools/dissect.py` (`split_entities`, `split_all`, `parse_ent`), de
//! `cade_mcp._lib()` (catalogo de prototipos) e dos JSON de `tools/` e `docs/` (embutidos com
//! `include_str!`: o binario nao le arquivo nenhum em runtime).
//!
//! Convencao de texto: o `.cad` e latin1 (ISO-8859-1). Aqui ele vira `String` (cada byte -> um
//! `char` U+0000..U+00FF) por [`latin1::decodificar`] e volta por [`latin1::codificar`].

pub mod catalogo;
pub mod dados;
pub mod entidade;
pub mod latin1;
pub mod pyfmt;

pub use catalogo::{Catalogo, Proto};
pub use entidade::{parse_ent, split_all, split_entities, Entidade, Particao};
