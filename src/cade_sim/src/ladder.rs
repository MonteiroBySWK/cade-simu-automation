//! Ponto de extensao do ladder / CLP (docs/ladder.md, docs/re-engenharia.md 13).
//!
//! **Nao implementado aqui** — outro agente porta o `tools/ladder_sim.py`. O motor eletrico
//! (`Circuito`) foi estruturado para recebe-lo sem mudar o contrato de conformidade:
//!
//! - o golden ja tem o campo `saidas_clp` (hoje sempre vazio no motor);
//! - o ladder e um circuito CC de um fio (fonte 3008 estampa `+`), avaliado pela mesma relaxacao
//!   de 8 passadas; contatos 10050/10051 sao *direcionais*; bobinas 10060..10062 comandam por
//!   rotulo; entradas 10204 / saidas 10205 do CLP modular 10206 fazem a ponte com o eletrico.
//!
//! Um modelo ladder implementa [`ModeloLadder`] e o motor o consulta por passo.

use crate::circuito::{Entradas, EstadoSim};

/// Extensao consultada apos cada assentamento do motor eletrico.
pub trait ModeloLadder {
    /// Nomes dos operandos de saida do CLP (`Q0.0`...) energizados no estado atual.
    fn saidas_clp(&self, estado: &EstadoSim, entradas: &Entradas) -> Vec<String>;
}

/// Implementacao nula: circuitos sem CLP.
pub struct SemLadder;

impl ModeloLadder for SemLadder {
    fn saidas_clp(&self, _estado: &EstadoSim, _entradas: &Entradas) -> Vec<String> {
        Vec::new()
    }
}
