//! Casos de teste declarativos (`teste_casos` / `executar_caso` / `chaves_invalidas` do Python).
//!
//! Caso: `{"nome","entradas":{k:bool},"inicial":[...],"esperado":[bobinas]|null,
//! "esperado_lampadas":[...]|null,"esperado_motores":[...]|null,"esperado_temporizadores":[...]|null,
//! "status":"OK"|"RACE"|"CURTO"|null,"avanca":s (alias "tempo"),"tempos":{rotulo:s},
//! "passos":[{"entradas":{..},"avanca":s, + esperado*}, ...]}` (sequencia com estado persistente).

use crate::circuito::{entradas_de_json, Circuito, EstadoSim};
use cade_model::pyfmt::{repr, repr_lista};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};

fn lista(v: Option<&Value>) -> Option<BTreeSet<String>> {
    v.and_then(|x| x.as_array()).map(|a| a.iter().filter_map(|s| s.as_str().map(String::from)).collect())
}

fn lista_vec(v: Option<&Value>) -> Vec<String> {
    v.and_then(|x| x.as_array()).map(|a| a.iter().filter_map(|s| s.as_str().map(String::from)).collect()).unwrap_or_default()
}

fn num(v: Option<&Value>) -> f64 {
    v.and_then(|x| x.as_f64()).unwrap_or(0.0)
}

/// Compara so os campos esperados presentes no caso.
pub fn confere(cs: &Value, e: &EstadoSim) -> bool {
    let mut cond = true;
    if let Some(s) = cs.get("status").and_then(|s| s.as_str()) {
        cond &= e.status.as_str() == s;
    }
    if let Some(esp) = lista(cs.get("esperado")) {
        cond &= e.bobinas.iter().cloned().collect::<BTreeSet<_>>() == esp;
    }
    if let Some(esp) = lista(cs.get("esperado_lampadas")) {
        cond &= e.lampadas.iter().cloned().collect::<BTreeSet<_>>() == esp;
    }
    if let Some(esp) = lista(cs.get("esperado_motores")) {
        cond &= e.motores.iter().cloned().collect::<BTreeSet<_>>() == esp;
    }
    if let Some(esp) = lista(cs.get("esperado_temporizadores")) {
        cond &= e.temporizadores_on() == esp;
    }
    cond
}

/// Chaves citadas por um caso que nao existem no circuito -> `(campo, chave)`.
/// Teste com chave inexistente seria vacuo (falso verde): o chamador deve reprovar.
pub fn chaves_invalidas(c: &Circuito, cs: &Value) -> Vec<(String, String)> {
    let ids = c.ids_temporizadores();
    let mut inicial_ok: BTreeSet<String> = c.bobinas.keys().cloned().collect();
    inicial_ok.extend(ids.iter().cloned());
    inicial_ok.extend(c.chaves_temporizadores());
    let esp_bob: BTreeSet<String> = c.bobinas.keys().cloned().collect();
    let esp_lamp: BTreeSet<String> = c.lampadas.keys().cloned().collect();
    let esp_mot: BTreeSet<String> = c.rotulos_motores().into_iter().collect();
    let esp_tim: BTreeSet<String> = ids.into_iter().collect();
    let mut ruim = Vec::new();
    let mut blocos: Vec<&Value> = vec![cs];
    if let Some(p) = cs.get("passos").and_then(|p| p.as_array()) {
        blocos.extend(p.iter());
    }
    for b in blocos {
        if let Some(o) = b.get("entradas").and_then(|e| e.as_object()) {
            for k in o.keys() {
                if !c.entradas.contains(k) && !c.bobinas.contains_key(k) {
                    ruim.push(("entradas".to_string(), k.clone()));
                }
            }
        }
        for (campo, validas) in [
            ("inicial", &inicial_ok),
            ("esperado", &esp_bob),
            ("esperado_lampadas", &esp_lamp),
            ("esperado_motores", &esp_mot),
            ("esperado_temporizadores", &esp_tim),
        ] {
            for k in lista_vec(b.get(campo)) {
                if !validas.contains(&k) {
                    ruim.push((campo.to_string(), k));
                }
            }
        }
    }
    ruim
}

fn tempos_do_caso(cs: &Value) -> Option<BTreeMap<String, f64>> {
    cs.get("tempos").and_then(|t| t.as_object()).map(|o| o.iter().filter_map(|(k, v)| v.as_f64().map(|f| (k.clone(), f))).collect())
}

fn avanca_de(b: &Value) -> f64 {
    num(b.get("avanca").or_else(|| b.get("tempo")))
}

/// Executa um caso (simples ou com `passos`) -> `(aprovado, estado_final)`.
pub fn executar_caso(c: &Circuito, cs: &Value) -> (bool, EstadoSim) {
    let tempos = tempos_do_caso(cs);
    let mut st = c.novo_estado(&lista_vec(cs.get("inicial")), tempos.as_ref());
    if let Some(passos) = cs.get("passos").and_then(|p| p.as_array()).filter(|p| !p.is_empty()) {
        let mut cond = true;
        let mut ult: Option<EstadoSim> = None;
        for p in passos {
            let e = c.avancar(&mut st, &entradas_de_json(p.get("entradas").unwrap_or(&Value::Null)), avanca_de(p));
            cond &= confere(p, &e);
            ult = Some(e);
        }
        let e = ult.expect("passos nao vazio");
        return (cond && confere(cs, &e), e);
    }
    let e = c.avancar(&mut st, &entradas_de_json(cs.get("entradas").unwrap_or(&Value::Null)), avanca_de(cs));
    (confere(cs, &e), e)
}

/// Linha de um caso, no formato do Python.
pub struct LinhaCaso {
    pub nome: String,
    pub aprovado: bool,
    pub texto: String,
    pub estado: EstadoSim,
}

pub struct Resultado {
    pub linhas: Vec<LinhaCaso>,
    pub ok: usize,
}

impl Resultado {
    pub fn aprovado(&self) -> bool {
        !self.linhas.is_empty() && self.ok == self.linhas.len()
    }

    /// Saida de texto identica a `netlist_sim.teste_casos`.
    pub fn texto(&self) -> String {
        let mut s = String::new();
        for l in &self.linhas {
            s.push_str(&l.texto);
            s.push('\n');
        }
        s.push_str(&format!("RESULTADO: {}/{} OK\n", self.ok, self.linhas.len()));
        s
    }
}

fn opt_repr(v: Option<&Value>) -> String {
    match v {
        None | Some(Value::Null) => "None".into(),
        Some(x) => repr(x),
    }
}

/// Roda casos declarados (ver doc do modulo).
pub fn teste_casos(c: &Circuito, casos: &[Value]) -> Resultado {
    let mut linhas = Vec::new();
    let mut ok = 0;
    for cs in casos {
        let (cond, e) = executar_caso(c, cs);
        ok += cond as usize;
        let mut extra = String::new();
        if cs.get("esperado_lampadas").is_some_and(|v| !v.is_null()) || !e.lampadas.is_empty() {
            extra.push_str(&format!(" lampadas={} esperado_lampadas={}", repr_lista(&e.lampadas), opt_repr(cs.get("esperado_lampadas"))));
        }
        if cs.get("esperado_motores").is_some_and(|v| !v.is_null()) {
            extra.push_str(&format!(" motores={} esperado_motores={}", repr_lista(&e.motores), opt_repr(cs.get("esperado_motores"))));
        }
        if cs.get("esperado_temporizadores").is_some_and(|v| !v.is_null()) {
            let on: Vec<String> = e.temporizadores_on().into_iter().collect();
            extra.push_str(&format!(" temporizadores={} esperado_temporizadores={}", repr_lista(&on), opt_repr(cs.get("esperado_temporizadores"))));
        }
        let nome = cs.get("nome").and_then(|n| n.as_str()).unwrap_or("?").to_string();
        let texto = format!(
            "  [{}] {}: KM={} status={} esperado={}{}",
            if cond { "OK " } else { "FALHA" },
            nome,
            repr_lista(&e.bobinas),
            e.status.as_str(),
            opt_repr(cs.get("esperado")),
            extra
        );
        linhas.push(LinhaCaso { nome, aprovado: cond, texto, estado: e });
    }
    Resultado { linhas, ok }
}
