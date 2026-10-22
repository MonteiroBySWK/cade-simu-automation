//! Subcomandos `cade gate` e `cade design` (casca fina sobre `cade_check`).
//!
//! Saida `--json`: o MESMO relatorio do MCP (`cad_gate`/`cad_design`): `{ok, path, gate:{build, testes,
//! geo, fios}, avisos, erros, proximo_passo}`, com `json.dumps(indent=1, ensure_ascii=False)`.
//! Sem `--json`: texto humano no estilo de `build_spec.py`. Exit 0 so se `ok`.
//!
//! Os testes funcionais usam o executor entregue por [`executor`]; enquanto o `cade_sim` nao esta
//! ligado e o `NaoPortado` (testes = "nao_portado", gate reprovado, nunca verde falso).

use cade_check::{gate_arquivo, ExecutorTestes, NaoPortado, Relatorio};
use serde_json::Value;
use std::fs;

/// Executor de testes funcionais em uso. Ponto unico para ligar o `cade_sim` depois.
pub fn executor() -> Box<dyn ExecutorTestes> {
    Box::new(NaoPortado)
}

/// `--testes t.json`: lista de casos, ou objeto com a chave `testes`.
fn le_testes(path: &str) -> Result<Vec<Value>, String> {
    let txt = fs::read_to_string(path).map_err(|e| format!("erro leitura {path}: {e}"))?;
    let v: Value = serde_json::from_str(&txt).map_err(|e| format!("testes_json invalido: {e}"))?;
    match v {
        Value::Array(a) => Ok(a),
        Value::Object(ref o) if o.get("testes").map(|t| t.is_array()).unwrap_or(false) => {
            Ok(o["testes"].as_array().cloned().unwrap_or_default())
        }
        _ => Err("testes_json invalido: esperava uma lista de casos (ou {\"testes\": [...]})".into()),
    }
}

fn imprime(r: &Relatorio, json: bool) -> i32 {
    if json {
        println!("{}", r.to_json());
    } else {
        humano(r);
    }
    if r.ok {
        0
    } else {
        1
    }
}

/// Texto humano (estilo `build_spec.main`): build, testes, CURTO/SOLTO crus, avisos, erros, veredito.
fn humano(r: &Relatorio) {
    if r.build.mensagem.is_empty() {
        for e in &r.erros {
            println!("ERRO: {e}");
        }
    } else {
        println!("{}", r.build.mensagem);
    }
    match r.testes.status {
        Some(s) => println!("TESTES: {s} (cade_sim ainda nao portado; sem prova funcional)"),
        None if !r.testes.saida.is_empty() => println!("{}", r.testes.saida),
        None => {}
    }
    for c in &r.geo.curtos {
        println!("CURTO: {c}");
    }
    for s in &r.geo.soltos {
        println!("SOLTO: {s}");
    }
    for a in &r.avisos {
        println!("AVISO: {a}");
    }
    if !r.build.mensagem.is_empty() {
        for e in &r.erros {
            if !e.starts_with("CURTO") && !e.contains("solto") && !e.starts_with("build:") {
                println!("ERRO: {e}");
            }
        }
    }
    if r.ok {
        println!("GATE: OK (validado, sem curto/fase cruzada/pino solto, testes passando)");
    } else if r.testes.status == Some("nao_portado") && r.estatico_ok() {
        println!("GATE: REPROVADO (parte estatica OK; testes funcionais nao executados)");
    } else {
        println!("GATE: REPROVADO (corrija antes de seguir)");
    }
}

/// `cade gate <cad> [--testes t.json] [--json]`.
pub fn cmd_gate(cad: &str, testes: Option<&str>, json: bool) -> i32 {
    let casos = match testes.map(le_testes).transpose() {
        Ok(c) => c.unwrap_or_default(),
        Err(e) => {
            return imprime(&Relatorio::so_erro(cad, e), json);
        }
    };
    match gate_arquivo(cad, &casos, executor().as_ref()) {
        Ok(r) => imprime(&r, json),
        Err(e) => {
            eprintln!("{e}");
            1
        }
    }
}

/// `cade design <layout.json> -o x.cad [--json]`.
pub fn cmd_design(layout: &str, out: &str, json: bool) -> i32 {
    let txt = match fs::read_to_string(layout) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("erro leitura {layout}: {e}");
            return 1;
        }
    };
    let r = cade_check::design_texto(&txt, out, executor().as_ref());
    imprime(&r, json)
}
