//! Port de `tools/geo_check.py`: curtos de fase e pinos soltos por GEOMETRIA.
//!
//! Regras (docs/re-engenharia.md §9.2): fio-fio une so por extremo; 4001 une ao fio cujo segmento a
//! contem; pino so liga a extremo de fio; fontes estampam "char de fase" por pino (L1->1, L2->2,
//! L3->3, N->N, PE->P) e duas estampas diferentes na mesma net sao CURTO.

use crate::geom::{estampa_de, Conectividade, Ponto, FONTE};
use cade_model::latin1;
use std::collections::HashMap;

/// Resultado de [`analisar`].
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Geo {
    /// `"1+N na mesma net: -X.L1, -X.N"` (mesmo texto do Python).
    pub curtos: Vec<String>,
    /// `"-X(3007).L3@(30, 20)"` (mesmo texto do Python; ponto no formato de tupla).
    pub soltos: Vec<String>,
    /// `{(rotulo, classe, pino) -> id da rede}` dos pinos ligados (`redes=` do Python).
    /// Os ids so tem significado dentro desta analise.
    pub redes: HashMap<(String, String, String), usize>,
}

/// Formata um ponto como a tupla do Python: `(30, 20)`.
pub fn tupla(p: Ponto) -> String {
    format!("({}, {})", p.0, p.1)
}

/// `geo_check.analisar` sobre o texto latin1 do `.cad`.
pub fn analisar_texto(cad_latin1: &str) -> Result<Geo, String> {
    let ents = crate::geom::entidades_do_cad(cad_latin1)?;
    Ok(analisar_entidades(&Conectividade::de_entidades(&ents)))
}

/// `geo_check.analisar` sobre os bytes do `.cad`.
pub fn analisar(cad: &[u8]) -> Result<Geo, String> {
    analisar_texto(&latin1::decodificar(cad))
}

/// Curtos/soltos/redes a partir de uma [`Conectividade`] ja construida (reuso pelo simulador).
pub fn analisar_entidades(c: &Conectividade) -> Geo {
    let mut g = Geo::default();
    for p in &c.pinos {
        if c.e_extremo(p.ponto) {
            if let Some(r) = c.rede_do_ponto(p.ponto) {
                g.redes.insert((p.rotulo.clone(), p.classe.clone(), p.nome.clone()), r);
            }
        }
    }
    // raiz -> posicao; cada grupo: [(char, [origens])] na ordem de insercao (dict do Python)
    let mut pos: HashMap<usize, usize> = HashMap::new();
    let mut estampas: Vec<Vec<(&'static str, Vec<String>)>> = Vec::new();
    for p in &c.pinos {
        if !c.e_extremo(p.ponto) {
            g.soltos.push(format!("{}({}).{}@{}", p.rotulo, p.classe, p.nome, tupla(p.ponto)));
            continue;
        }
        if FONTE.contains(&p.classe.as_str()) {
            if let (Some(ch), Some(raiz)) = (estampa_de(&p.nome), c.rede_do_ponto(p.ponto)) {
                let i = *pos.entry(raiz).or_insert_with(|| {
                    estampas.push(Vec::new());
                    estampas.len() - 1
                });
                let grupo = &mut estampas[i];
                let origem = format!("{}.{}", p.rotulo, p.nome);
                match grupo.iter_mut().find(|(k, _)| *k == ch) {
                    Some((_, v)) => v.push(origem),
                    None => grupo.push((ch, vec![origem])),
                }
            }
        }
    }
    for m in &estampas {
        if m.len() > 1 {
            let mut chars: Vec<&str> = m.iter().map(|(k, _)| *k).collect();
            chars.sort_unstable();
            let origens: Vec<&str> = m.iter().flat_map(|(_, v)| v.iter().map(|s| s.as_str())).collect();
            g.curtos.push(format!("{} na mesma net: {}", chars.join("+"), origens.join(", ")));
        }
    }
    g
}

#[cfg(test)]
mod tests {
    use super::*;
    use cade_model::Entidade;

    fn ent(id: &str, rot: &str, x: i64, y: i64, extra: &[(usize, i64)]) -> Entidade {
        let mut n: Vec<String> = vec!["0".into(); 23];
        n[8] = x.to_string();
        n[9] = y.to_string();
        for (i, v) in extra {
            n[*i] = v.to_string();
        }
        Entidade { seq: "0".into(), id: id.into(), labels: vec![rot.into()], nums: n }
    }

    #[test]
    fn tupla_negativa() {
        assert_eq!(tupla((-3, 4)), "(-3, 4)");
    }

    #[test]
    fn fonte_com_pino_sem_fio_e_solto() {
        // 3007 sem nenhum fio: todos os pinos soltos, nenhum curto
        let ents = vec![ent("3007", "-X", 30, 20, &[])];
        let g = analisar_entidades(&Conectividade::de_entidades(&ents));
        assert!(g.curtos.is_empty());
        assert!(g.soltos.iter().any(|s| s.starts_with("-X(3007).L1@(")), "{:?}", g.soltos);
    }

    #[test]
    fn duas_fases_na_mesma_net_dao_curto() {
        // liga L1 e L2 da 3007 ao mesmo fio
        let base = ent("3007", "-X", 30, 20, &[]);
        let c0 = Conectividade::de_entidades(std::slice::from_ref(&base));
        let l1 = c0.pinos.iter().find(|p| p.nome == "L1").unwrap().ponto;
        let l2 = c0.pinos.iter().find(|p| p.nome == "L2").unwrap().ponto;
        let fio = ent("4000", "", l1.0, l1.1, &[(10, l2.0), (11, l2.1)]);
        let g = analisar_entidades(&Conectividade::de_entidades(&[base, fio]));
        assert_eq!(g.curtos, vec!["1+2 na mesma net: -X.L1, -X.L2".to_string()]);
    }
}
