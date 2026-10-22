//! `cade_sim` — motor de simulacao do CADe_SIMU 4.0, sem GUI (reimplementacao propria).
//!
//! Comportamento observado/documentado em `docs/re-engenharia.md` 9, 11 e 13, validado por
//! **teste diferencial** (`cade conformidade`) contra goldens gravados no app real. O Python
//! `tools/netlist_sim.py` e o oraculo de paridade enquanto o app nao e regravado.
//!
//! - geometria (extremo-a-extremo, pinos por classe, rotacao n17): reaproveitada de `cade_check::geom`;
//! - [`papeis`] papel de cada classe (contato, bobina, polos, temporizador, motor...);
//! - [`circuito`] netlist + relaxacao (OK/RACE/INSTAVEL/CURTO) + temporizadores;
//! - [`casos`] casos declarativos (`entradas`/`inicial`/`esperado`/`passos`/`avanca`);
//! - [`conformidade`] cenario temporal x golden do app;
//! - [`ladder`] CLP modular + ladder por ticks de 100 ms (paridade com `tools/clp_sim.py`).

pub mod casos;
pub mod circuito;
pub mod conformidade;
pub mod executor;
pub mod ladder;
pub mod papeis;

pub use circuito::{entradas_de_json, Circuito, Entradas, EstadoSim, Status};
pub use executor::ExecutorSim;
pub use papeis::{Papel, Papeis};
