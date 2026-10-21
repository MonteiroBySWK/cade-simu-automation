//! Teste de ponta a ponta do binario `cade` (CARGO_BIN_EXE_cade) contra os goldens do oraculo Python.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

fn raiz() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..")
}

fn tmp(nome: &str) -> PathBuf {
    let d = std::env::temp_dir().join(format!("cade_cli_test_{}", std::process::id()));
    fs::create_dir_all(&d).unwrap();
    d.join(nome)
}

fn cade(args: &[&str]) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_cade")).args(args).output().expect("executar cade")
}

fn s(p: &Path) -> &str {
    p.to_str().unwrap()
}

#[test]
fn build_e_layout_batem_com_os_goldens() {
    let g = raiz().join("tests").join("golden");
    let mut n = 0;
    for e in fs::read_dir(&g).unwrap().filter_map(|e| e.ok()) {
        let nome = e.file_name().into_string().unwrap();
        let Some(base) = nome.strip_suffix(".layout.json") else { continue };
        if !g.join(format!("{base}.spec.json")).is_file() {
            continue; // caso de erro
        }
        let saida = tmp(&format!("{base}.cad"));
        let o = cade(&["build", s(&e.path()), "-o", s(&saida)]);
        assert!(o.status.success(), "[{base}] {}", String::from_utf8_lossy(&o.stderr));
        assert_eq!(fs::read(&saida).unwrap(), fs::read(g.join(format!("{base}.cad"))).unwrap(), "[{base}] .cad");
        let spec = tmp(&format!("{base}.spec.json"));
        let o = cade(&["layout", s(&e.path()), "-o", s(&spec)]);
        assert!(o.status.success(), "[{base}] {}", String::from_utf8_lossy(&o.stderr));
        assert_eq!(
            fs::read_to_string(&spec).unwrap(),
            fs::read_to_string(g.join(format!("{base}.spec.json"))).unwrap(),
            "[{base}] spec"
        );
        let v = cade(&["validate", s(&saida)]);
        assert!(v.status.success());
        n += 1;
    }
    assert!(n >= 16, "casos: {n}");
}

#[test]
fn spec_baixa_e_aceita_no_build() {
    let g = raiz().join("tests").join("golden");
    let saida = tmp("baixa.cad");
    let o = cade(&["build", s(&g.join("b_motor_e_contator.baixa.json")), "-o", s(&saida)]);
    assert!(o.status.success(), "{}", String::from_utf8_lossy(&o.stderr));
    assert_eq!(fs::read(&saida).unwrap(), fs::read(g.join("b_motor_e_contator.cad")).unwrap());
}

#[test]
fn layout_invalido_sai_com_erro() {
    let g = raiz().join("tests").join("golden");
    let o = cade(&["build", s(&g.join("e_id_duplicado.layout.json")), "-o", s(&tmp("nunca.cad"))]);
    assert!(!o.status.success());
    assert!(String::from_utf8_lossy(&o.stderr).contains("id duplicado: K"));
}

#[test]
fn corpus_round_trip_byte_identico() {
    let dir = raiz().join("corpus");
    let mut n = 0;
    for e in fs::read_dir(&dir).unwrap().filter_map(|e| e.ok()) {
        let p = e.path();
        if p.extension().map(|x| x != "cad").unwrap_or(true) {
            continue;
        }
        let nome = p.file_name().unwrap().to_str().unwrap().to_string();
        let j = tmp(&format!("{nome}.json"));
        let b = tmp(&format!("{nome}.rt.cad"));
        assert!(cade(&["validate", s(&p)]).status.success());
        assert!(cade(&["parse", s(&p), "-o", s(&j)]).status.success());
        assert!(cade(&["emit", s(&j), "-o", s(&b)]).status.success());
        assert_eq!(fs::read(&p).unwrap(), fs::read(&b).unwrap(), "{nome}");
        n += 1;
    }
    assert!(n >= 3);
}

#[test]
fn new_from_json_template_minimo() {
    let j = tmp("meta.json");
    fs::write(&j, r#"{"meta":{"titulo":"-X","modo":"0","versao":"3000"}}"#).unwrap();
    let out = tmp("meta.cad");
    assert!(cade(&["new-from-json", s(&j), "-o", s(&out)]).status.success());
    assert!(cade(&["validate", s(&out)]).status.success());
}
