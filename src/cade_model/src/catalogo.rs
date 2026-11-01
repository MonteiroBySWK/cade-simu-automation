//! Catalogo de entidades-prototipo por classe (`cade_mcp._lib()` sem acervo externo).
//!
//! Fonte: `symbol_lib.json` (as 8 classes que um doador fornecia sao identicas as da lib,
//! verificado) + constantes de formato (`dados::FOOTER`, `dados::FIO_4000_*`) — sem acervo.

use crate::dados;
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
        let lib = dados::symbol_lib().as_object().ok_or("symbol_lib.json: objeto esperado")?;
        let mut protos: HashMap<String, Proto> = HashMap::new();
        for (cid, v) in lib {
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
        let fio = Proto {
            id: "4000".into(),
            labels: dados::FIO_4000_LABELS.iter().map(|s| s.to_string()).collect(),
            nums: dados::FIO_4000_NUMS.iter().map(|s| s.to_string()).collect(),
        };
        Ok(Catalogo { protos, footer: dados::FOOTER.to_string(), fio })
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
        assert_eq!(c.fio.nums.len(), 23);
        assert_eq!(c.fio.labels.len(), 9);
        for k in CLASSES_DOADOR {
            assert!(c.protos.contains_key(k), "{k}");
        }
    }
}
