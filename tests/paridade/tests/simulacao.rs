//! Paridade do motor de simulacao (`cade_sim`) com o oraculo Python `tools/netlist_sim.py`.
//!
//! Goldens em `tests/golden/sim/*.sim.json` (gerados por `tests/golden/sim/gerar.py`): estado
//! completo (status, bobinas, lampadas, temporizadores, curtos) para os 11 exemplos — casos
//! declarados + varredura de entradas x bobinas iniciais — e para temporizadores ON/OFF-delay.

use cade_sim::casos::executar_caso;
use cade_sim::papeis::{Modo, Papel, Papeis, TipoTemp};
use cade_sim::{entradas_de_json, Circuito, EstadoSim};
use paridade::golden_dir;
use serde_json::Value;
use std::fs;
use std::path::Path;

fn le_json(p: &Path) -> Value {
    serde_json::from_str(&fs::read_to_string(p).unwrap_or_else(|e| panic!("{}: {e}", p.display()))).unwrap_or_else(|e| panic!("{}: {e}", p.display()))
}

fn strs(v: &Value) -> Vec<String> {
    v.as_array().expect("lista").iter().map(|s| s.as_str().expect("str").to_string()).collect()
}

fn aprox(a: f64, b: f64) -> bool {
    (a - b).abs() < 1e-6
}

/// Compara o estado Rust com o `estado_json` do Python; devolve a lista de divergencias.
fn diff_estado(r: &EstadoSim, py: &Value) -> Vec<String> {
    let mut d = Vec::new();
    if r.status.as_str() != py["status"].as_str().unwrap() {
        d.push(format!("status rust={} py={}", r.status.as_str(), py["status"]));
    }
    for (campo, rust) in [("bobinas", &r.bobinas), ("lampadas", &r.lampadas), ("curtos", &r.curtos)] {
        if *rust != strs(&py[campo]) {
            d.push(format!("{campo} rust={rust:?} py={}", py[campo]));
        }
    }
    let tp = py["temporizadores"].as_object().unwrap();
    let ids: Vec<&str> = r.temporizadores.iter().map(|t| t.id.as_str()).collect();
    let ids_py: Vec<&str> = tp.keys().map(|k| k.as_str()).collect();
    if ids != ids_py {
        d.push(format!("temporizadores ids rust={ids:?} py={ids_py:?}"));
    } else {
        for t in &r.temporizadores {
            let p = &tp[&t.id];
            if t.tipo != p["tipo"].as_str().unwrap()
                || t.saida != p["saida"].as_bool().unwrap()
                || !aprox(t.tempo, p["tempo"].as_f64().unwrap())
                || !aprox(t.decorrido, p["decorrido"].as_f64().unwrap())
            {
                d.push(format!("temporizador {} rust={t:?} py={p}", t.id));
            }
        }
    }
    d
}

fn goldens_sim() -> Vec<String> {
    let mut v: Vec<String> = fs::read_dir(golden_dir().join("sim"))
        .expect("tests/golden/sim ausente (rode tests/golden/sim/gerar.py)")
        .filter_map(|e| e.ok())
        .filter_map(|e| e.file_name().into_string().ok())
        .filter_map(|n| n.strip_suffix(".sim.json").map(String::from))
        .filter(|n| n != "timers")
        .collect();
    v.sort();
    v
}

#[test]
fn estados_identicos_ao_python_nos_exemplos() {
    let nomes = goldens_sim();
    assert!(nomes.len() >= 11, "poucos goldens de simulacao: {}", nomes.len());
    let mut falhas = Vec::new();
    let mut total = 0;
    for nome in &nomes {
        let g = le_json(&golden_dir().join("sim").join(format!("{nome}.sim.json")));
        let c = Circuito::abrir(golden_dir().join(format!("{nome}.cad")).to_str().unwrap()).unwrap();
        if c.entradas != strs(&g["entradas"]) {
            falhas.push(format!("[{nome}] entradas rust={:?} py={}", c.entradas, g["entradas"]));
        }
        if c.bobinas.keys().cloned().collect::<Vec<_>>() != strs(&g["bobinas"]) {
            falhas.push(format!("[{nome}] bobinas diferem"));
        }
        if c.lampadas.keys().cloned().collect::<Vec<_>>() != strs(&g["lampadas"]) {
            falhas.push(format!("[{nome}] lampadas diferem"));
        }
        if c.soltos != strs(&g["soltos"]) {
            falhas.push(format!("[{nome}] pinos soltos rust={:?} py={}", c.soltos, g["soltos"]));
        }
        for d in g["declarados"].as_array().unwrap() {
            total += 1;
            let (ok, e) = executar_caso(&c, &d["caso"]);
            let mut df = diff_estado(&e, &d["estado"]);
            if ok != d["aprovado"].as_bool().unwrap() {
                df.push(format!("aprovado rust={ok} py={}", d["aprovado"]));
            }
            if !df.is_empty() {
                falhas.push(format!("[{nome}] caso {}: {}", d["caso"]["nome"], df.join("; ")));
            }
        }
        for v in g["varredura"].as_array().unwrap() {
            total += 1;
            let ini = strs(&v["inicial"]);
            let e = c.estado(&entradas_de_json(&v["entradas"]), &ini, 0.0, None);
            let df = diff_estado(&e, &v["estado"]);
            if !df.is_empty() {
                falhas.push(format!("[{nome}] entradas={} inicial={ini:?}: {}", v["entradas"], df.join("; ")));
            }
        }
    }
    assert!(falhas.is_empty(), "{} de {total} caso(s) divergem do oraculo:\n{}", falhas.len(), falhas.join("\n"));
    assert!(total > 500, "varredura pequena demais: {total}");
}

fn papeis_override(o: &Value) -> Papeis {
    let mut p = Papeis::padrao();
    for (cid, e) in o.as_object().unwrap() {
        assert_eq!(e["papel"], "contato_temp");
        let modo = if e["modo"] == "NC" { Modo::Nc } else { Modo::Na };
        let tipo = if e["tipo"] == "ton" { TipoTemp::Ton } else { TipoTemp::Tof };
        p.insert(cid, Papel::ContatoTemp { modo, tipo, tempo: e["tempo"].as_f64() });
    }
    p
}

#[test]
fn temporizadores_identicos_ao_python() {
    let g = le_json(&golden_dir().join("sim").join("timers.sim.json"));
    let raw = fs::read(golden_dir().join(format!("{}.cad", g["circuito"].as_str().unwrap()))).unwrap();
    let mut falhas = Vec::new();
    let mut n = 0;
    for grupo in g["grupos"].as_array().unwrap() {
        let c = Circuito::de_bytes(&raw, papeis_override(&grupo["override"])).unwrap();
        for k in grupo["casos"].as_array().unwrap() {
            n += 1;
            let cs = &k["caso"];
            let tempos = cs.get("tempos").map(|t| t.as_object().unwrap().iter().map(|(a, b)| (a.clone(), b.as_f64().unwrap())).collect());
            let e = c.estado(&entradas_de_json(&cs["entradas"]), &[], cs["avanca"].as_f64().unwrap(), tempos.as_ref());
            let df = diff_estado(&e, &k["estado"]);
            if !df.is_empty() {
                falhas.push(format!("caso {cs}: {}", df.join("; ")));
            }
        }
        let mut st = c.novo_estado(&[], None);
        for k in grupo["sequencia"].as_array().unwrap() {
            n += 1;
            let p = &k["passo"];
            let e = c.avancar(&mut st, &entradas_de_json(&p["entradas"]), p["avanca"].as_f64().unwrap());
            let df = diff_estado(&e, &k["estado"]);
            if !df.is_empty() {
                falhas.push(format!("passo {p}: {}", df.join("; ")));
            }
        }
    }
    assert!(n >= 10);
    assert!(falhas.is_empty(), "{}", falhas.join("\n"));
}
