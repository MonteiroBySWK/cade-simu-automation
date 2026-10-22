//! `cade gate` / `cade design` pelo binario real, contra os goldens do oraculo Python.

use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

fn raiz() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..")
}

fn tmp(nome: &str) -> PathBuf {
    let d = std::env::temp_dir().join(format!("cade_cli_check_{}", std::process::id()));
    fs::create_dir_all(&d).unwrap();
    d.join(nome)
}

fn cade(args: &[&str]) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_cade")).args(args).output().expect("executar cade")
}

fn s(p: &Path) -> &str {
    p.to_str().unwrap()
}

fn json(o: &std::process::Output) -> Value {
    serde_json::from_slice(&o.stdout).unwrap_or_else(|e| panic!("stdout nao e JSON ({e}): {}", String::from_utf8_lossy(&o.stdout)))
}

#[test]
fn gate_json_tem_a_forma_do_relatorio_do_mcp() {
    let cad = raiz().join("tests/golden/partida_direta.cad");
    let o = cade(&["gate", s(&cad), "--json"]);
    // sem casos de teste o gate NUNCA aprova (sem prova funcional): exit 1
    assert_eq!(o.status.code(), Some(1));
    let v = json(&o);
    for k in ["ok", "path", "gate", "avisos", "erros", "proximo_passo"] {
        assert!(v.get(k).is_some(), "falta `{k}`");
    }
    for k in ["build", "testes", "geo", "fios"] {
        assert!(v["gate"].get(k).is_some(), "falta gate.{k}");
    }
    assert_eq!(v["ok"], false);
    assert_eq!(v["gate"]["testes"]["ok"], false);
    assert!(v["erros"][0].as_str().unwrap().starts_with("sem testes"));
    assert_eq!(v["gate"]["build"]["ok"], true);
    assert_eq!(v["gate"]["geo"]["curtos"], serde_json::json!([]));
    assert_eq!(v["gate"]["fios"]["ok"], true);
}

#[test]
fn gate_reprova_curto_e_pino_solto_com_mensagem_acionavel() {
    let g = raiz().join("tests/golden/check");
    let curto = json(&cade(&["gate", s(&g.join("defeito_curto_pe_n_e_fases.cad")), "--json"]));
    let curtos = curto["gate"]["geo"]["curtos"].as_array().unwrap();
    assert!(curtos[0].as_str().unwrap().starts_with("CURTO 1+2 na mesma net"), "{curtos:?}");
    assert!(curtos[1].as_str().unwrap().contains("crie trilho PE separado"));

    let solto = json(&cade(&["gate", s(&g.join("defeito_pino_solto.cad")), "--json"]));
    assert!(solto["gate"]["geo"]["soltos"][0].as_str().unwrap().starts_with("pino p2 de -KM1 (9000) solto em"));
    assert!(solto["proximo_passo"].as_str().unwrap().starts_with("Ligue o pino solto"));
}

#[test]
fn gate_de_arquivo_inexistente_e_json_minimo() {
    let o = cade(&["gate", "/nao/existe.cad", "--json"]);
    assert_eq!(o.status.code(), Some(1));
    let v = json(&o);
    assert_eq!(v["erros"][0], "arquivo nao existe: /nao/existe.cad");
    assert!(v.get("gate").is_none());
}

#[test]
fn gate_executa_os_testes_funcionais_de_verdade() {
    let cad = raiz().join("tests/golden/partida_direta.cad");
    let t = tmp("testes.json");
    fs::write(&t, r#"[{"nome":"x","entradas":{},"esperado":[],"status":"OK"}]"#).unwrap();
    let o = cade(&["gate", s(&cad), "--testes", s(&t), "--json"]);
    assert_eq!(o.status.code(), Some(0), "{}", String::from_utf8_lossy(&o.stdout));
    let v = json(&o);
    assert_eq!(v["ok"], true);
    assert_eq!(v["gate"]["testes"]["passaram"], 1);
    // teste que o circuito reprova: o gate reprova (nunca verde falso)
    fs::write(&t, r#"[{"nome":"errado","entradas":{"S1":true},"esperado":[]}]"#).unwrap();
    let o = cade(&["gate", s(&cad), "--testes", s(&t), "--json"]);
    assert_eq!(o.status.code(), Some(1));
    assert_eq!(json(&o)["ok"], false);
    // chave de teste inexistente (teste vacuo) tambem reprova
    fs::write(&t, r#"[{"nome":"fantasma","entradas":{"ZZ":true},"esperado":[]}]"#).unwrap();
    let o = cade(&["gate", s(&cad), "--testes", s(&t), "--json"]);
    assert_eq!(o.status.code(), Some(1));
    assert!(json(&o)["erros"].to_string().contains("entrada 'ZZ' nao existe"));
    fs::write(&t, "{ruim").unwrap();
    let o = cade(&["gate", s(&cad), "--testes", s(&t), "--json"]);
    assert!(json(&o)["erros"][0].as_str().unwrap().starts_with("testes_json invalido"));
}

#[test]
fn design_gera_o_cad_do_golden_e_reporta_o_gate() {
    let g = raiz().join("tests/golden");
    for base in ["partida_direta", "reversao", "intercalada"] {
        let out = tmp(&format!("{base}.cad"));
        let o = cade(&["design", s(&g.join(format!("{base}.layout.json"))), "-o", s(&out), "--json"]);
        let v = json(&o);
        assert_eq!(fs::read(&out).unwrap(), fs::read(g.join(format!("{base}.cad"))).unwrap(), "[{base}] .cad");
        assert_eq!(v["gate"]["build"]["ok"], true, "[{base}]");
        assert_eq!(v["gate"]["geo"]["soltos"], serde_json::json!([]), "[{base}]");
        // os `testes` do proprio layout rodam no motor Rust e passam
        assert_eq!(v["gate"]["testes"]["ok"], true, "[{base}]");
        assert_eq!(v["ok"], true, "[{base}]");
        assert_eq!(o.status.code(), Some(0), "[{base}]");
    }
}

#[test]
fn design_de_layout_invalido_explica_o_erro() {
    let g = raiz().join("tests/golden");
    let out = tmp("invalido.cad");
    let o = cade(&["design", s(&g.join("e_duas_chaves.layout.json")), "-o", s(&out), "--json"]);
    assert_eq!(o.status.code(), Some(1));
    let v = json(&o);
    let esperado = fs::read_to_string(g.join("e_duas_chaves.erro.txt")).unwrap();
    assert_eq!(v["erros"][0], format!("layout invalido: {esperado}"));
    assert!(v["proximo_passo"].as_str().unwrap().starts_with("Corrija o layout_json"));
    assert_eq!(v["gate"]["fios"]["ok"], Value::Null);
}

#[test]
fn saida_humana_traz_o_veredito() {
    let g = raiz().join("tests/golden/check");
    let o = cade(&["gate", s(&g.join("defeito_curto_pe_n_e_fases.cad"))]);
    let txt = String::from_utf8_lossy(&o.stdout);
    assert!(txt.contains("CURTO: 1+2 na mesma net: -X.L1, -X.L2"), "{txt}");
    assert!(txt.contains("GATE: REPROVADO"), "{txt}");
}
