//! Paridade do gate estatico com o oraculo Python (`tests/golden/check/gerar.py`).
//!
//! Cada `<n>.design.json` (layout -> `construir`) e `<n>.gate.json` (.cad -> `gate`) guarda a parte
//! ESTATICA do relatorio do Python: build, geo, fios, avisos e erros (sem os de teste, que dependem do
//! simulador). Aqui rodamos o gate Rust com [`NaoPortado`] e comparamos campo a campo.

use cade_check::{construir, gate_bytes, NaoPortado, Relatorio};
use serde_json::{json, Value};
use std::fs;
use std::path::PathBuf;

fn raiz() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..")
}

fn dir_check() -> PathBuf {
    raiz().join("tests").join("golden").join("check")
}

fn le_json(p: &std::path::Path) -> Value {
    serde_json::from_str(&fs::read_to_string(p).unwrap_or_else(|e| panic!("{}: {e}", p.display())))
        .unwrap_or_else(|e| panic!("{}: json invalido: {e}", p.display()))
}

fn goldens(sufixo: &str) -> Vec<(String, Value)> {
    let mut v: Vec<(String, Value)> = fs::read_dir(dir_check())
        .expect("tests/golden/check ausente (rode python3 tests/golden/check/gerar.py)")
        .filter_map(|e| e.ok())
        .filter_map(|e| {
            let n = e.file_name().into_string().ok()?;
            let base = n.strip_suffix(sufixo)?.to_string();
            Some((base, le_json(&e.path())))
        })
        .collect();
    v.sort_by(|a, b| a.0.cmp(&b.0));
    v
}

const PREFIXOS_TESTE: [&str; 3] = ["teste ", "sem testes", "testes:"];

/// Recorta o relatorio Rust no mesmo formato do golden (parte estatica).
fn estatico(r: &Relatorio, troca: (&str, &str)) -> Value {
    let sub = |s: &String| s.replace(troca.0, troca.1);
    let erros: Vec<String> = r
        .erros
        .iter()
        .filter(|e| !PREFIXOS_TESTE.iter().any(|p| e.starts_with(p)))
        .map(sub)
        .collect();
    let v = r.to_value();
    json!({
        "titulo": r.titulo,
        "n_simbolos": r.n_simbolos,
        "build": {"ok": r.build.ok, "mensagem": sub(&r.build.mensagem)},
        "geo": {
            "curtos": r.geo.curtos, "soltos": r.geo.soltos,
            "curtos_msg": r.geo.curtos_msg, "soltos_msg": r.geo.soltos_msg,
        },
        "fios": v["gate"]["fios"],
        "avisos": r.avisos.iter().map(sub).collect::<Vec<_>>(),
        "erros": erros,
        "estatico_ok": r.estatico_ok(),
    })
}

fn esperado(g: &Value) -> Value {
    let mut o = g.clone();
    let m = o.as_object_mut().unwrap();
    m.remove("entrada");
    m.remove("tipo");
    o
}

fn compara(nome: &str, rust: &Value, py: &Value, falhas: &mut Vec<String>) {
    for k in py.as_object().unwrap().keys() {
        if rust.get(k) != py.get(k) {
            falhas.push(format!("[{nome}] campo `{k}` diverge\n  rust  : {}\n  python: {}", rust.get(k).unwrap_or(&Value::Null), py[k]));
        }
    }
}

#[test]
fn design_estatico_identico_ao_python() {
    let casos = goldens(".design.json");
    assert!(casos.len() >= 27, "poucos casos design: {}", casos.len());
    let tmp = std::env::temp_dir().join(format!("cade_check_design_{}", std::process::id()));
    let mut falhas = Vec::new();
    for (nome, g) in &casos {
        let entrada = le_json(&raiz().join(g["entrada"].as_str().unwrap()));
        let out = tmp.join(format!("{nome}.cad"));
        let out_s = out.to_str().unwrap();
        let r = construir(&entrada, out_s, &NaoPortado);
        // a parte funcional NUNCA finge verde
        assert!(!r.ok, "[{nome}] gate aprovou sem testes");
        compara(nome, &estatico(&r, (out_s, "{OUT}")), &esperado(g), &mut falhas);
    }
    assert!(falhas.is_empty(), "{} divergencia(s) do oraculo:\n{}", falhas.len(), falhas.join("\n"));
}

#[test]
fn gate_de_cad_estatico_identico_ao_python() {
    let casos = goldens(".gate.json");
    assert!(casos.len() >= 26, "poucos casos gate: {}", casos.len());
    let mut falhas = Vec::new();
    for (nome, g) in &casos {
        let cad = fs::read(raiz().join(g["entrada"].as_str().unwrap())).unwrap();
        let r = gate_bytes(&cad, "{PATH}", &[], &NaoPortado).unwrap_or_else(|e| panic!("[{nome}] {e}"));
        assert!(!r.ok, "[{nome}] gate aprovou sem testes");
        compara(nome, &estatico(&r, ("{PATH}", "{PATH}")), &esperado(g), &mut falhas);
    }
    assert!(falhas.is_empty(), "{} divergencia(s) do oraculo:\n{}", falhas.len(), falhas.join("\n"));
}

#[test]
fn fixtures_defeituosas_sao_reprovadas_pelo_motivo_certo() {
    let gate = |n: &str| {
        let cad = fs::read(dir_check().join(format!("{n}.cad"))).unwrap();
        gate_bytes(&cad, "x.cad", &[], &NaoPortado).unwrap()
    };
    let curto = gate("defeito_curto_pe_n_e_fases");
    assert_eq!(curto.geo.curtos, ["1+2 na mesma net: -X.L1, -X.L2", "N+P na mesma net: -X.N, -X.PE"]);
    assert!(!curto.estatico_ok());

    let solto = gate("defeito_pino_solto");
    assert_eq!(solto.geo.soltos.len(), 2);
    assert!(solto.geo.soltos[0].starts_with("-KM1(9000).p2@("), "{:?}", solto.geo.soltos);
    assert!(!solto.estatico_ok());

    let termico = gate("defeito_termico_rotulo");
    assert!(termico.erros.iter().any(|e| e.starts_with("contato termico -RT1 (8017) nao segue nenhum rele termico 6007")));

    let fio = gate("defeito_fio_atravessa");
    assert_eq!(fio.fios.ok, Some(false));
    assert_eq!(fio.fios.atravessam, ["fio (20, 110)->(120, 110) atravessa o simbolo -KM1"]);

    let leg = gate("defeito_3004x3_pe_no_n");
    assert!(!leg.geo.soltos.is_empty());
}

#[test]
fn exemplos_bons_tem_a_parte_estatica_verde() {
    // todos os tools/examples compilam e passam geo/vinculos (so os testes ficam pendentes)
    let tmp = std::env::temp_dir().join(format!("cade_check_bons_{}", std::process::id()));
    let mut n = 0;
    for (nome, g) in goldens(".design.json") {
        let nome_ex = nome.as_str();
        if nome_ex.starts_with("e_") || nome_ex.starts_with("defeito_") || nome_ex.starts_with("x_") {
            continue;
        }
        let entrada = le_json(&raiz().join(g["entrada"].as_str().unwrap()));
        let r = construir(&entrada, tmp.join(format!("{nome}.cad")).to_str().unwrap(), &NaoPortado);
        assert!(r.estatico_ok(), "[{nome}] {:?}", r.erros);
        assert!(r.geo.curtos.is_empty() && r.geo.soltos.is_empty());
        assert!(r.proximo_passo().contains("NAO rodaram"), "[{nome}] {}", r.proximo_passo());
        n += 1;
    }
    assert!(n >= 11, "exemplos: {n}");
}
