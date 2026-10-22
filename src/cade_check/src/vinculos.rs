//! Port de `build_spec.conferir_vinculos`: vinculos por ROTULO que o app usa (achado do app_sim).
//!
//! Contato 8016..8019 so segue um 6007 (termico) de MESMO rotulo; auxiliares 7000/7001 e polos 2001
//! so seguem bobina 9xxx de mesmo rotulo.

use cade_model::pyfmt::repr_lista;
use cade_model::{latin1, Entidade};
use std::collections::BTreeSet;

/// Classes de bobina que comandam auxiliares/polos de mesmo rotulo.
pub const BOBINAS: [&str; 10] = ["9000", "9001", "9002", "9004", "9005", "9006", "9007", "9014", "9015", "10060"];

fn rot(e: &Entidade) -> String {
    e.labels.first().map(|s| s.trim().to_string()).unwrap_or_default()
}

/// `(erros, avisos)` sobre as entidades.
pub fn conferir_entidades(ps: &[Entidade]) -> (Vec<String>, Vec<String>) {
    // termico OU disjuntor (DJ1): o app deixa o 8016/8017 seguir o breaker de mesmo rotulo
    // (arquivo de aula usa `8016 DJ1` com `6003 DJ1`) — igual a `build_spec.conferir_vinculos`.
    let termicos: BTreeSet<String> = ps
        .iter()
        .filter(|p| ["6007", "6002", "6003", "6009", "6010"].contains(&p.id.as_str()))
        .map(rot)
        .collect();
    let bobinas: BTreeSet<String> = ps.iter().filter(|p| BOBINAS.contains(&p.id.as_str())).map(rot).collect();
    let (mut erros, mut avisos) = (Vec::new(), Vec::new());
    for p in ps {
        let r = rot(p);
        if ["8016", "8017", "8018", "8019"].contains(&p.id.as_str()) && !termicos.contains(&r) {
            let lista: Vec<&String> = termicos.iter().collect();
            let lista = if lista.is_empty() { "nenhum".to_string() } else { repr_lista(&lista) };
            erros.push(format!(
                "contato termico {} ({}) nao segue nenhum rele termico 6007 de mesmo rotulo (6007: {}): no app o \
                 termico NUNCA dispara. Use o MESMO rotulo no 6007 e no contato 95-96.",
                if r.is_empty() { &p.id } else { &r },
                p.id,
                lista
            ));
        }
        if ["7000", "7001", "2001"].contains(&p.id.as_str()) && !r.is_empty() && !bobinas.contains(&r) {
            avisos.push(format!("{} {}: nenhuma bobina de mesmo rotulo (contato nunca e comandado)", p.id, r));
        }
    }
    (erros, avisos)
}

/// `conferir_vinculos(path)` sobre o texto latin1 do `.cad`: `(erros, avisos)`.
pub fn conferir_texto(cad_latin1: &str) -> Result<(Vec<String>, Vec<String>), String> {
    let ps = crate::geom::entidades_do_cad(cad_latin1)?;
    Ok(conferir_entidades(&ps))
}

/// `conferir_vinculos(path)` sobre os bytes do `.cad`.
pub fn conferir(cad: &[u8]) -> Result<(Vec<String>, Vec<String>), String> {
    conferir_texto(&latin1::decodificar(cad))
}
