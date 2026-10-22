//! Port de `tools/wires_check.py`: trechos de fio que atravessam o CORPO de um simbolo.
//!
//! Pin-aware: ignora a vizinhanca (raio [`TOL`]) de qualquer pino — o fio SAI do pino, mesmo que o
//! pino esteja dentro do corpo. So usa os pinos de `symbol_pins.json` (como o Python; nao o binario).

use crate::geom::{num, rotulo};
use cade_model::pyfmt::fdiv;
use cade_model::{dados, latin1};

/// Classes tratadas como fio nesta checagem (`wires_check.WIRE`; inclui a juncao 4001).
pub const FIO: [&str; 5] = ["4000", "4018", "4009", "4001", "4010"];
/// Recuo do corpo do simbolo.
pub const PAD: i64 = 2;
/// Raio em volta do pino em que o fio pode encostar.
pub const TOL: i64 = 4;

/// Trecho que atravessa: `(simbolo, (x1,y1), (x2,y2))`.
pub type Ruim = (String, (i64, i64), (i64, i64));

/// Resultado de [`analisar`]: numero de fios e trechos ruins.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Fios {
    pub n: usize,
    pub ruins: Vec<Ruim>,
}

impl Fios {
    /// `"fio (x1, y1)->(x2, y2) atravessa o simbolo -K"` (texto do gate Python).
    pub fn mensagens(&self) -> Vec<String> {
        self.ruins
            .iter()
            .map(|(nome, a, b)| format!("fio ({}, {})->({}, {}) atravessa o simbolo {}", a.0, a.1, b.0, b.1, nome))
            .collect()
    }
}

/// `wires_check.analisar` sobre os bytes do `.cad`.
pub fn analisar(cad: &[u8]) -> Result<Fios, String> {
    analisar_texto(&latin1::decodificar(cad))
}

/// `wires_check.analisar` sobre o texto latin1.
///
/// Divergencia deliberada: campo numerico ausente vale 0 (o Python abortaria com `IndexError`).
pub fn analisar_texto(cad_latin1: &str) -> Result<Fios, String> {
    let ents = crate::geom::entidades_do_cad(cad_latin1)?;
    let mut syms: Vec<(String, i64, i64, i64, i64)> = Vec::new();
    let mut fios: Vec<(i64, i64, i64, i64)> = Vec::new();
    let mut pinos: Vec<(i64, i64)> = Vec::new();
    for p in &ents {
        if FIO.contains(&p.id.as_str()) {
            fios.push((num(p, 8), num(p, 9), num(p, 10), num(p, 11)));
        } else if p.id != "8" {
            let (x, y, w, h) = (num(p, 8), num(p, 9), num(p, 14), num(p, 15));
            syms.push((rotulo(p), x, y, x + w, y + h));
            if let Some(info) = dados::symbol_pins().get(&p.id) {
                for off in info.pins.values() {
                    pinos.push((x + off[0], y + off[1]));
                }
                for off in [info.a, info.b].into_iter().flatten() {
                    pinos.push((x + off[0], y + off[1]));
                }
            }
        }
    }
    let perto_de_pino = |px: i64, py: i64| pinos.iter().any(|&(a, b)| (px - a).abs() <= TOL && (py - b).abs() <= TOL);
    let mut ruins = Vec::new();
    for &(x1, y1, x2, y2) in &fios {
        let l = (x2 - x1).abs().max((y2 - y1).abs());
        let l = if l == 0 { 1 } else { l };
        let mut achou: Option<&str> = None;
        'amostras: for i in 0..=l {
            let (px, py) = (x1 + fdiv((x2 - x1) * i, l), y1 + fdiv((y2 - y1) * i, l));
            if perto_de_pino(px, py) {
                continue;
            }
            for (nome, a, b, c, e2) in &syms {
                if *a + PAD < px && px < *c - PAD && *b + PAD < py && py < *e2 - PAD {
                    achou = Some(nome);
                    break 'amostras;
                }
            }
        }
        if let Some(nome) = achou {
            ruins.push((nome.to_string(), (x1, y1), (x2, y2)));
        }
    }
    Ok(Fios { n: fios.len(), ruins })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mensagem_no_formato_do_python() {
        let f = Fios { n: 1, ruins: vec![("-K".into(), (1, 2), (3, 4))] };
        assert_eq!(f.mensagens(), vec!["fio (1, 2)->(3, 4) atravessa o simbolo -K".to_string()]);
    }
}
