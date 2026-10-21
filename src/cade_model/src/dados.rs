//! Dados embutidos no binario (`include_str!`): nada e lido do disco em runtime.
//!
//! Fontes (versionadas no repo): `tools/*.json` e `docs/*.json`. Quando o Python for removido,
//! estes arquivos migram para um diretorio de dados do workspace e so os caminhos abaixo mudam.

use serde_json::Value;
use std::collections::{BTreeMap, HashMap};
use std::sync::OnceLock;

pub const SYMBOL_LIB_JSON: &str = include_str!("../../../tools/symbol_lib.json");
pub const SYMBOL_PINS_JSON: &str = include_str!("../../../tools/symbol_pins.json");
pub const SYMBOL_DIMS_JSON: &str = include_str!("../../../tools/symbol_dims.json");
pub const SYMBOL_NAMES_JSON: &str = include_str!("../../../tools/symbol_names.json");
pub const SHEET_JSON: &str = include_str!("../../../tools/sheet.json");
pub const PINOS_BINARIO_JSON: &str = include_str!("../../../docs/pinos-binario.json");
pub const CLASSES_PAPEIS_JSON: &str = include_str!("../../../docs/classes-papeis.json");
/// Doador do catalogo (`mk_dataset.load_donor`): fornece o rodape (`$$$...`) e o fio 4000 prototipo.
pub const DOADOR_CAD: &[u8] = include_bytes!("../../../corpus/Arranque_1.cad");

fn json(txt: &str, nome: &str) -> Value {
    serde_json::from_str(txt).unwrap_or_else(|e| panic!("dado embutido {} invalido: {}", nome, e))
}

/// `docs/pinos-binario.json` (inteiro).
pub fn pinos_binario() -> &'static Value {
    static V: OnceLock<Value> = OnceLock::new();
    V.get_or_init(|| json(PINOS_BINARIO_JSON, "pinos-binario.json"))
}

/// `docs/classes-papeis.json` (inteiro).
pub fn classes_papeis() -> &'static Value {
    static V: OnceLock<Value> = OnceLock::new();
    V.get_or_init(|| json(CLASSES_PAPEIS_JSON, "classes-papeis.json"))
}

/// `tools/symbol_names.json` (inteiro).
pub fn symbol_names() -> &'static Value {
    static V: OnceLock<Value> = OnceLock::new();
    V.get_or_init(|| json(SYMBOL_NAMES_JSON, "symbol_names.json"))
}

/// `tools/symbol_lib.json`: classe -> {labels, nums}.
pub fn symbol_lib() -> &'static Value {
    static V: OnceLock<Value> = OnceLock::new();
    V.get_or_init(|| json(SYMBOL_LIB_JSON, "symbol_lib.json"))
}

/// Geometria de pinos de uma classe (`tools/symbol_pins.json`), offsets (dx, dy) em px.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct ClassePins {
    pub a: Option<[i64; 2]>,
    pub b: Option<[i64; 2]>,
    /// Pinos nomeados (1/3/5, U1/V1/W1/PE, p1..pN ...). Ordenado por nome (como `sorted()`).
    pub pins: BTreeMap<String, [i64; 2]>,
}

impl ClassePins {
    /// Offset de um pino: nomeado, ou A/B (`_pin_coord` / `pin_off`).
    pub fn offset(&self, pino: &str) -> Option<[i64; 2]> {
        self.pins.get(pino).copied().or(match pino {
            "A" => self.a,
            "B" => self.b,
            _ => None,
        })
    }

    /// `info.get(pino, ...)` do Python: so as chaves de topo A/B (nao os nomeados).
    pub fn topo(&self, pino: &str) -> Option<[i64; 2]> {
        match pino {
            "A" => self.a,
            "B" => self.b,
            _ => None,
        }
    }
}

fn par(v: &Value, ctx: &str) -> [i64; 2] {
    let a = v.as_array().unwrap_or_else(|| panic!("{}: esperado [dx,dy]", ctx));
    [a[0].as_i64().unwrap_or_else(|| panic!("{}: dx nao inteiro", ctx)),
     a[1].as_i64().unwrap_or_else(|| panic!("{}: dy nao inteiro", ctx))]
}

/// `tools/symbol_pins.json` tipado.
pub fn symbol_pins() -> &'static HashMap<String, ClassePins> {
    static V: OnceLock<HashMap<String, ClassePins>> = OnceLock::new();
    V.get_or_init(|| {
        let raw = json(SYMBOL_PINS_JSON, "symbol_pins.json");
        let mut out = HashMap::new();
        for (cid, v) in raw.as_object().expect("symbol_pins.json: objeto") {
            let mut c = ClassePins::default();
            if let Some(a) = v.get("A") {
                c.a = Some(par(a, &format!("{}.A", cid)));
            }
            if let Some(b) = v.get("B") {
                c.b = Some(par(b, &format!("{}.B", cid)));
            }
            if let Some(p) = v.get("pins").and_then(|p| p.as_object()) {
                for (n, o) in p {
                    c.pins.insert(n.clone(), par(o, &format!("{}.{}", cid, n)));
                }
            }
            out.insert(cid.clone(), c);
        }
        out
    })
}

/// `tools/symbol_dims.json`: classe -> (w, h).
pub fn symbol_dims() -> &'static HashMap<String, (i64, i64)> {
    static V: OnceLock<HashMap<String, (i64, i64)>> = OnceLock::new();
    V.get_or_init(|| {
        let raw = json(SYMBOL_DIMS_JSON, "symbol_dims.json");
        raw.as_object()
            .expect("symbol_dims.json: objeto")
            .iter()
            .map(|(k, v)| {
                let p = par(v, k);
                (k.clone(), (p[0], p[1]))
            })
            .collect()
    })
}

/// Folha segura `(x_seguro_max, y_seguro_max)` de `tools/sheet.json` (fallback 455x295 como o Python).
pub fn folha() -> (i64, i64) {
    static V: OnceLock<(i64, i64)> = OnceLock::new();
    *V.get_or_init(|| {
        let d: Option<Value> = serde_json::from_str(SHEET_JSON).ok();
        let g = |k: &str| d.as_ref().and_then(|d| d.get(k)).and_then(|v| v.as_i64());
        match (g("x_seguro_max"), g("y_seguro_max")) {
            (Some(x), Some(y)) => (x, y),
            _ => (455, 295),
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dados_embutidos_carregam() {
        assert_eq!(folha(), (455, 305));
        assert!(symbol_pins().len() > 300);
        assert!(symbol_dims().contains_key("2001"));
        assert!(pinos_binario().get("classes").is_some());
        assert!(classes_papeis().is_object());
        assert!(symbol_names().is_object());
        assert!(symbol_lib().as_object().unwrap().len() > 100);
    }

    #[test]
    fn pinos_da_bobina() {
        let c = &symbol_pins()["9000"];
        assert!(c.offset("A").is_some() || c.offset("p1").is_some());
    }
}
