//! Port de `build_spec.lint_layout`: avisos de AUTORIA sobre o layout topologico, antes do build.

use cade_model::dados;
use cade_model::pyfmt::{repr_lista, str_de, verdadeiro};
use serde_json::Value;
use std::collections::BTreeSet;

/// Classes de uma coluna de potencia: `[id, cls, rot, ...]` ou `{"paralelo": [item, ...]}`.
fn classes_da_coluna(c: &Value) -> Vec<String> {
    match c {
        Value::Object(_) => c
            .get("paralelo")
            .and_then(|p| p.as_array())
            .map(|a| a.iter().flat_map(classes_da_coluna).collect())
            .unwrap_or_default(),
        Value::Array(a) if a.len() > 1 => vec![str_de(&a[1])],
        _ => vec![],
    }
}

fn get_str(v: &Value, k: &str, padrao: &str) -> String {
    match v.get(k) {
        Some(x) => str_de(x),
        None => padrao.to_string(),
    }
}

/// `lint_layout(layout_d)`. `layout` vazio/nulo -> sem avisos.
pub fn lint_layout(layout: Option<&Value>) -> Vec<String> {
    let mut av = Vec::new();
    let Some(l) = layout.filter(|l| verdadeiro(l)) else { return av };
    let mut trilhos: BTreeSet<String> = l
        .get("trilhos")
        .and_then(|t| t.as_object())
        .map(|o| o.keys().filter(|k| *k != "x0" && *k != "x1").cloned().collect())
        .unwrap_or_default();
    if let Some(nomes) = l.get("trilhos_comando").and_then(|t| t.get("nomes")).and_then(|n| n.as_array()) {
        for n in nomes {
            trilhos.insert(str_de(n));
        }
    }
    if let Some(fontes) = l.get("fontes").and_then(|f| f.as_array()) {
        for f in fontes {
            let sem_pinos = !f.get("pinos").map(verdadeiro).unwrap_or(false);
            let n_fases = f.get("fases").and_then(|x| x.as_array()).map(|a| a.len()).unwrap_or(0);
            if sem_pinos && n_fases > 1 {
                av.push(format!(
                    "fonte {} por fase ({}): desenho legado que gera curto N x PE e fase solta. Use UMA fonte 3007: \
                     {{\"id\":\"X1\",\"classe\":\"3007\",\"rotulo\":\"-X\",\"pinos\":{{\"L1\":\"L1\",\"L2\":\"L2\",\
                     \"L3\":\"L3\",\"N\":\"N\",\"PE\":\"PE\"}}}}",
                    get_str(f, "classe", "3004"),
                    f.get("id").map(str_de).unwrap_or_else(|| "None".into())
                ));
            }
        }
    }
    if let Some(pot) = l.get("potencia").and_then(|p| p.as_array()) {
        for g in pot {
            let classes: Vec<String> = g
                .get("colunas")
                .and_then(|c| c.as_array())
                .map(|a| a.iter().flat_map(classes_da_coluna).collect())
                .unwrap_or_default();
            let tem_pe = classes
                .iter()
                .any(|cl| dados::symbol_pins().get(cl).map(|c| c.pins.contains_key("PE")).unwrap_or(false)
                    || ["1002", "1008", "1010"].contains(&cl.as_str()));
            if tem_pe {
                let pe = g.get("pe");
                let id = g.get("id").map(str_de).unwrap_or_else(|| "None".into());
                let neutro = g.get("neutro").cloned().unwrap_or_else(|| Value::String("N".into()));
                if !pe.map(verdadeiro).unwrap_or(false) || pe == Some(&neutro) {
                    av.push(format!(
                        "potencia '{}': o PE do motor vai ao neutro (curto N x PE). Declare um trilho \"PE\" em \
                         'trilhos' e \"pe\":\"PE\" no grupo.",
                        id
                    ));
                } else if let Some(pe) = pe {
                    let existe = pe.as_str().map(|s| trilhos.contains(s)).unwrap_or(false);
                    if !existe {
                        av.push(format!("potencia '{}': \"pe\":\"{}\" nao existe em 'trilhos'.", id, str_de(pe)));
                    }
                }
            }
        }
    }
    if let Some(cmd) = l.get("comando").and_then(|c| c.as_array()) {
        for b in cmd {
            for k in ["de", "para"] {
                let v = b.get(k);
                let existe = v.and_then(|x| x.as_str()).map(|s| trilhos.contains(s)).unwrap_or(false);
                if !existe {
                    let lista: Vec<&String> = trilhos.iter().collect();
                    av.push(format!(
                        "comando '{}': '{}'='{}' nao e um trilho (trilhos: {}).",
                        b.get("id").map(str_de).unwrap_or_else(|| "None".into()),
                        k,
                        v.map(str_de).unwrap_or_else(|| "None".into()),
                        repr_lista(&lista)
                    ));
                }
            }
        }
    }
    av
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn layout_vazio_nao_avisa() {
        assert!(lint_layout(None).is_empty());
        assert!(lint_layout(Some(&json!({}))).is_empty());
    }

    #[test]
    fn comando_com_trilho_inexistente() {
        let l = json!({"trilhos": {"L1": 14, "N": 100, "x0": 25, "x1": 395},
                       "comando": [{"id": "c1", "de": "L1", "para": "X"}]});
        let av = lint_layout(Some(&l));
        assert_eq!(av, vec!["comando 'c1': 'para'='X' nao e um trilho (trilhos: ['L1', 'N']).".to_string()]);
    }

    #[test]
    fn pe_no_neutro_e_fonte_legada() {
        let l = json!({"trilhos": {"L1": 14, "N": 100},
                       "fontes": [{"id": "X1", "classe": "3004", "fases": ["L1", "L2", "L3"]}],
                       "potencia": [{"id": "m1", "colunas": [["M1", "1000", "-M1"]]}]});
        let av = lint_layout(Some(&l));
        assert_eq!(av.len(), 2, "{av:?}");
        assert!(av[0].starts_with("fonte 3004 por fase (X1)"));
        assert!(av[1].contains("o PE do motor vai ao neutro"));
    }
}
