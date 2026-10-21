//! Catalogo de entidades-prototipo por classe (`cade_mcp._lib()` sem acervo externo).
//!
//! Ordem de precedencia (igual ao Python): doador (`corpus/Arranque_1.cad`, 8 classes) ->
//! `symbol_lib.json`. As classes que o Python ainda poderia acrescentar do `corpus/*.cad` ja estao
//! todas em `symbol_lib.json` (verificado); as do acervo do curso (opcional) nao existem aqui.

use crate::dados;
use crate::entidade::{parse_ent, split_entities};
use crate::latin1;
use std::collections::HashMap;
use std::sync::OnceLock;

/// Classes que o doador fornece (`mk_dataset.CLASSES`).
pub const CLASSES_DOADOR: [&str; 8] = ["2001", "1000", "6007", "9008", "8000", "8001", "8017", "8016"];

/// Prototipo de uma classe: rotulos padrao e os 23/24 numeros.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Proto {
    pub id: String,
    pub labels: Vec<String>,
    pub nums: Vec<String>,
}

#[derive(Debug)]
pub struct Catalogo {
    pub protos: HashMap<String, Proto>,
    /// Rodape do doador: de `$$$` ao fim.
    pub footer: String,
    /// Fio 4000 prototipo (1o do doador).
    pub fio: Proto,
}

impl Catalogo {
    /// Catalogo embutido (calculado uma vez).
    pub fn embutido() -> &'static Catalogo {
        static C: OnceLock<Catalogo> = OnceLock::new();
        C.get_or_init(|| Catalogo::carregar().expect("catalogo embutido invalido"))
    }

    fn carregar() -> Result<Catalogo, String> {
        let d = latin1::decodificar(dados::DOADOR_CAD);
        let part = split_entities(&d)?;
        let mut protos: HashMap<String, Proto> = HashMap::new();
        let mut fio: Option<Proto> = None;
        for e in &part.ents {
            let Some(p) = parse_ent(e) else { continue };
            let proto = Proto { id: p.id.clone(), labels: p.labels, nums: p.nums };
            if CLASSES_DOADOR.contains(&p.id.as_str()) && !protos.contains_key(&p.id) {
                protos.insert(p.id.clone(), proto.clone());
            }
            if p.id == "4000" && fio.is_none() {
                fio = Some(proto);
            }
        }
        let lib = dados::symbol_lib().as_object().ok_or("symbol_lib.json: objeto esperado")?;
        for (cid, v) in lib {
            if protos.contains_key(cid) {
                continue;
            }
            let strs = |k: &str| -> Result<Vec<String>, String> {
                v.get(k)
                    .and_then(|a| a.as_array())
                    .ok_or_else(|| format!("symbol_lib[{}].{} ausente", cid, k))?
                    .iter()
                    .map(|s| s.as_str().map(String::from).ok_or_else(|| format!("symbol_lib[{}].{}: nao-string", cid, k)))
                    .collect()
            };
            protos.insert(cid.clone(), Proto { id: cid.clone(), labels: strs("labels")?, nums: strs("nums")? });
        }
        Ok(Catalogo { protos, footer: part.footer, fio: fio.ok_or("doador sem fio 4000")? })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn catalogo_tem_doador_e_lib() {
        let c = Catalogo::embutido();
        assert!(c.protos.len() >= 136);
        assert!(c.footer.starts_with("$$$"));
        assert_eq!(c.fio.id, "4000");
        assert_eq!(c.fio.nums[8], "93");
        for k in CLASSES_DOADOR {
            assert!(c.protos.contains_key(k), "{k}");
        }
    }
}
