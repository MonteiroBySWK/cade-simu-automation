//! `cade simulate`, `cade test` e `cade conformidade` pelo binario real.

use serde_json::Value;
use std::fs;
use std::path::PathBuf;
use std::process::Command;

fn raiz() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..")
}

fn cade(args: &[&str]) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_cade")).args(args).current_dir(raiz()).output().expect("executar cade")
}

fn json(o: &std::process::Output) -> Value {
    serde_json::from_slice(&o.stdout).unwrap_or_else(|e| panic!("stdout nao e JSON ({e}): {}", String::from_utf8_lossy(&o.stdout)))
}

const CAD: &str = "tests/golden/partida_direta.cad";

#[test]
fn simulate_json() {
    let o = cade(&["simulate", CAD, "--entradas", r#"{"S1":true}"#, "--json"]);
    assert!(o.status.success());
    let v = json(&o);
    assert_eq!(v["status"], "OK");
    assert_eq!(v["bobinas"], serde_json::json!(["KM1"]));
    assert_eq!(v["lampadas"], serde_json::json!(["H1"]));
    assert_eq!(v["motores"], serde_json::json!(["M1"]));
    // selo: sem entradas, KM1 ja energizada permanece
    let o = cade(&["simulate", CAD, "--inicial", "KM1", "--json"]);
    assert_eq!(json(&o)["bobinas"], serde_json::json!(["KM1"]));
    let o = cade(&["simulate", CAD, "--inicial", r#"["KM1"]"#, "--entradas", r#"{"S0":true}"#, "--json"]);
    assert_eq!(json(&o)["bobinas"], serde_json::json!([]));
}

#[test]
fn simulate_erros_de_uso() {
    assert_eq!(cade(&["simulate", "/nao/existe.cad"]).status.code(), Some(2));
    assert_eq!(cade(&["simulate", CAD, "--entradas", "{ruim"]).status.code(), Some(2));
}

#[test]
fn test_roda_os_casos_do_formato_python() {
    let ex: Value = serde_json::from_str(&fs::read_to_string(raiz().join("tools/examples/partida_direta.layout.json")).unwrap()).unwrap();
    let t = std::env::temp_dir().join(format!("cade_sim_casos_{}.json", std::process::id()));
    fs::write(&t, ex["testes"].to_string()).unwrap();
    let o = cade(&["test", CAD, "--testes", t.to_str().unwrap()]);
    let txt = String::from_utf8_lossy(&o.stdout);
    assert!(o.status.success(), "{txt}");
    assert!(txt.contains("RESULTADO: 6/6 OK"), "{txt}");
    let o = cade(&["test", CAD, "--testes", t.to_str().unwrap(), "--json"]);
    let v = json(&o);
    assert_eq!(v["aprovado"], true);
    assert_eq!(v["total"], 6);
    // caso errado -> exit 1 e FALHA
    fs::write(&t, r#"[{"nome":"errado","entradas":{"S1":true},"esperado":[]}]"#).unwrap();
    let o = cade(&["test", CAD, "--testes", t.to_str().unwrap()]);
    assert_eq!(o.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&o.stdout).contains("[FALHA] errado"));
    // chave inexistente (teste vacuo) reprova
    fs::write(&t, r#"[{"nome":"v","entradas":{"ZZ":true},"esperado":[]}]"#).unwrap();
    let o = cade(&["test", CAD, "--testes", t.to_str().unwrap()]);
    assert_eq!(o.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&o.stdout).contains("CHAVE INVALIDA"));
    let _ = fs::remove_file(&t);
}

#[test]
fn conformidade_dos_11_exemplos() {
    let o = cade(&["conformidade", "tests/conformidade", "--json"]);
    let v = json(&o);
    assert_eq!(o.status.code(), Some(0), "{v}");
    assert!(v["ok"].as_u64().unwrap() >= 11);
    assert_eq!(v["divergentes"], 0);
    assert_eq!(v["erros"], 0);
}

#[test]
fn conformidade_acusa_divergencia_do_golden() {
    let d = std::env::temp_dir().join(format!("cade_conf_{}", std::process::id()));
    let caso = d.join("partida_direta");
    fs::create_dir_all(&caso).unwrap();
    fs::copy(raiz().join(CAD), caso.join("circuito.cad")).unwrap();
    fs::write(
        caso.join("cenario.json"),
        r#"{"versao":1,"acoes":[{"acao":"pressionar","alvo":"S1"},{"acao":"esperar","ms":200}]}"#,
    )
    .unwrap();
    // golden errado de proposito: diz que KM1 NAO liga
    fs::write(
        caso.join("golden_app.json"),
        r#"{"versao":1,"fonte":"app","passos":[{"i":0,"bobinas":[]},{"i":1,"bobinas":[]}]}"#,
    )
    .unwrap();
    let o = cade(&["conformidade", d.to_str().unwrap(), "--json"]);
    assert_eq!(o.status.code(), Some(1));
    let v = json(&o);
    assert_eq!(v["divergentes"], 1);
    assert_eq!(v["goldens_provisorios"], 0);
    assert_eq!(v["casos"][0]["diffs"][0]["campo"], "bobinas");
    assert_eq!(v["casos"][0]["diffs"][0]["motor"], serde_json::json!(["KM1"]));
    // rotulo inexistente no cenario = erro (nao teste vacuo)
    fs::write(caso.join("cenario.json"), r#"{"acoes":[{"acao":"pressionar","alvo":"FANTASMA"}]}"#).unwrap();
    let o = cade(&["conformidade", d.to_str().unwrap(), "--json"]);
    assert_eq!(o.status.code(), Some(1));
    assert_eq!(json(&o)["erros"], 1);
    let _ = fs::remove_dir_all(&d);
}
