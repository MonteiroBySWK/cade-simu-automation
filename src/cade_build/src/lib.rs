//! `cade_build` — port de `cade_mcp.cad_build` (+ `_rotear`, `_pin_coord`, `_symboxes`, `_cruza`,
//! `_assign_nets`, `_shorts`). Entrada: spec "baixa" (JSON) `{simbolos, conexoes?, fios?, rails?}`;
//! saida: bytes do `.cad` (entidade 0 = primeira entidade gerada, colada ao `CADe_SIMU`).
//!
//! Os algoritmos (ordem de emissao dos fios, colunas de desvio, numeracao de nets) sao copias
//! literais do Python para dar saida byte-identica; qualquer mudanca aqui deve ser feita junto
//! com o oraculo e os goldens de `tests/golden`.

mod nets;
mod roteador;

use cade_model::dados;
use cade_model::latin1;
use cade_model::pyfmt;
use cade_model::Catalogo;
use serde_json::Value;

pub use roteador::Ent;

/// Resultado de [`construir`].
#[derive(Debug, Clone)]
pub struct Saida {
    /// Conteudo do `.cad` (latin1).
    pub bytes: Vec<u8>,
    /// Numero de entidades emitidas.
    pub n_entidades: usize,
    /// Simbolos com o mesmo net em A e B (`_shorts`); o Python avisa "AVISO curto A==B em: ...".
    pub curtos: Vec<String>,
}

fn lista<'a>(spec: &'a Value, chave: &str) -> Result<&'a [Value], String> {
    match spec.get(chave) {
        None | Some(Value::Null) => Ok(&[]),
        Some(Value::Array(a)) => Ok(a),
        Some(_) => Err(format!("ERRO: {} deve ser uma lista", chave)),
    }
}

/// `cad_build(auto_net=True)` sobre uma spec baixa. Erros vem no mesmo texto do Python (`ERRO ...`).
pub fn construir(spec: &Value) -> Result<Saida, String> {
    construir_com(spec, true)
}

pub fn construir_com(spec: &Value, auto_net: bool) -> Result<Saida, String> {
    let cat = Catalogo::embutido();
    let simbolos = match spec.get("simbolos") {
        Some(Value::Array(a)) => a.as_slice(),
        _ => return Err("ERRO: simbolos_json deve ser uma lista".into()),
    };
    let fios = lista(spec, "fios")?;
    let conexoes = lista(spec, "conexoes")?;
    let rails = lista(spec, "rails")?;

    let mut faltando: Vec<String> = simbolos
        .iter()
        .filter(|s| {
            s.get("classe")
                .and_then(|c| c.as_str())
                .map(|c| !cat.protos.contains_key(c))
                .unwrap_or(true)
        })
        .map(|s| s.get("classe").map(pyfmt::str_de).unwrap_or_else(|| "None".into()))
        .collect();
    if !faltando.is_empty() {
        faltando.sort();
        faltando.dedup();
        return Err(format!(
            "ERRO classe(s) sem entidade-prototipo: {}. O catalogo versionado (tools/symbol_lib.json) nao tem essas \
             classes: troque por uma de cad_symbols, OU forneca um .cad que as contenha (CADE_ACERVO=<pasta>) e rode \
             `python tools/gen_symbol_lib.py`.",
            pyfmt::repr_lista(&faltando)
        ));
    }

    let mut ents: Vec<Ent> = Vec::new();
    for f in fios {
        let mut n = cat.fio.nums.clone();
        for (k, c) in ["x1", "y1", "x2", "y2"].iter().enumerate() {
            let v = f.get(*c).ok_or_else(|| format!("campo obrigatorio ausente: '{}'", c))?;
            n[8 + k] = pyfmt::int(v)?.to_string();
        }
        ents.push(Ent { id: "4000".into(), labels: cat.fio.labels.clone(), nums: n });
    }
    for s in simbolos {
        let classe = s.get("classe").and_then(|c| c.as_str()).unwrap_or_default();
        let p = &cat.protos[classe];
        let mut n = p.nums.clone();
        n[0] = "1".into();
        n[1] = "1".into();
        let x = s.get("x").ok_or("campo obrigatorio ausente: 'x'")?;
        let y = s.get("y").ok_or("campo obrigatorio ausente: 'y'")?;
        n[8] = pyfmt::int(x)?.to_string();
        n[9] = pyfmt::int(y)?.to_string();
        let mut labs = p.labels.clone();
        if let Some(r) = s.get("rotulo") {
            if pyfmt::verdadeiro(r) && !labs.is_empty() {
                labs[0] = pyfmt::str_de(r);
            }
        }
        ents.push(Ent { id: classe.to_string(), labels: labs, nums: n });
    }
    if ents.is_empty() {
        return Err("ERRO: nenhum simbolo nem fio — simbolos_json/fios_json/conexoes vazios".into());
    }
    if !conexoes.is_empty() || !rails.is_empty() {
        roteador::rotear(&mut ents, simbolos, conexoes, &cat.fio, rails)?;
    }
    if auto_net {
        nets::assign_nets(&mut ents, dados::symbol_pins())?;
    }
    let curtos = nets::shorts(&ents);
    let corpo: Vec<String> = ents.iter().enumerate().map(|(i, e)| e.serializar(&i.to_string())).collect();
    let cad = format!("CADe_SIMU{}#{}", corpo.join("#"), cat.footer);
    let bytes = latin1::codificar(&cad)?;
    Ok(Saida { bytes, n_entidades: ents.len(), curtos })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn spec_minima_gera_cad_valido() {
        let spec = json!({
            "simbolos": [{"classe": "8000", "x": 40, "y": 40, "rotulo": "-S1", "id": "S1"},
                         {"classe": "9000", "x": 40, "y": 100, "rotulo": "-KM1", "id": "KM1"}],
            "conexoes": [{"de": ["S1", "B"], "para": ["KM1", "A"]}]
        });
        let s = construir(&spec).unwrap();
        assert!(s.bytes.starts_with(b"CADe_SIMU*0*8000#-S1#"));
        cade_core::validate(&s.bytes).unwrap();
        assert!(s.n_entidades >= 3);
    }

    #[test]
    fn classe_inexistente_da_erro() {
        let spec = json!({"simbolos": [{"classe": "99999", "x": 1, "y": 1}]});
        let e = construir(&spec).unwrap_err();
        assert!(e.starts_with("ERRO classe(s) sem entidade-prototipo: ['99999']"), "{e}");
    }

    #[test]
    fn sem_nada_da_erro() {
        let e = construir(&json!({"simbolos": []})).unwrap_err();
        assert!(e.contains("nenhum simbolo nem fio"));
    }
}
