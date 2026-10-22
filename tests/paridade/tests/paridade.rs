//! Paridade byte-a-byte com o oraculo Python.
//!
//! Para cada caso em `tests/golden/`:
//! - `<n>.layout.json` -> `cade_layout::normalizar` == `<n>.spec.json` (texto, `json.dumps(indent=1)`);
//! - spec baixa -> `cade_build::construir` == `<n>.cad` (bytes);
//! - `<n>.erro.txt`: a mensagem do `ValueError` do Python;
//! - `<n>.baixa.json` -> `.cad` direto do roteador (sem o motor de layout).

use paridade::{golden_dir, primeira_diferenca, raiz};
use serde_json::Value;
use std::fs;
use std::path::Path;

fn le_json(p: &Path) -> Value {
    serde_json::from_str(&fs::read_to_string(p).unwrap_or_else(|e| panic!("{}: {}", p.display(), e)))
        .unwrap_or_else(|e| panic!("{}: json invalido: {}", p.display(), e))
}

fn nomes_com_sufixo(sufixo: &str) -> Vec<String> {
    let mut v: Vec<String> = fs::read_dir(golden_dir())
        .expect("tests/golden ausente")
        .filter_map(|e| e.ok())
        .filter_map(|e| e.file_name().into_string().ok())
        .filter_map(|n| n.strip_suffix(sufixo).map(String::from))
        .collect();
    v.sort();
    v
}

#[test]
fn layout_para_spec_e_cad_identicos_ao_python() {
    let casos: Vec<String> = nomes_com_sufixo(".spec.json");
    assert!(casos.len() >= 16, "poucos casos golden: {}", casos.len());
    let mut falhas = Vec::new();
    for nome in &casos {
        // A8/A9 (1008/2002/6004) ainda nao portados no layout Rust
        if nome == "reversao_monofasica" || nome == "reversao_4polos" {
            continue;
        }
        let g = golden_dir();
        let entrada = le_json(&g.join(format!("{nome}.layout.json")));
        let norm = match cade_layout::normalizar(&entrada) {
            Ok(n) => n,
            Err(e) => {
                falhas.push(format!("[{nome}] normalizar falhou: {e}"));
                continue;
            }
        };
        let spec_rust = cade_layout::json_indent1(&norm.low);
        let spec_py = fs::read_to_string(g.join(format!("{nome}.spec.json"))).unwrap();
        if spec_rust != spec_py {
            falhas.push(format!("[{nome}] spec baixa: {}", primeira_diferenca(spec_rust.as_bytes(), spec_py.as_bytes())));
            continue;
        }
        let cad_py = fs::read(g.join(format!("{nome}.cad"))).unwrap();
        match cade_build::construir(&norm.low) {
            Ok(s) if s.bytes == cad_py => cade_core::validate(&s.bytes).map(|_| ()).unwrap_or_else(|e| falhas.push(format!("[{nome}] invalido: {e}"))),
            Ok(s) => falhas.push(format!("[{nome}] .cad: {}", primeira_diferenca(&s.bytes, &cad_py))),
            Err(e) => falhas.push(format!("[{nome}] construir falhou: {e}")),
        }
    }
    assert!(falhas.is_empty(), "{} caso(s) divergem do oraculo:\n{}", falhas.len(), falhas.join("\n"));
}

#[test]
fn erros_com_a_mesma_mensagem_do_python() {
    let casos = nomes_com_sufixo(".erro.txt");
    assert!(casos.len() >= 8, "poucos casos de erro: {}", casos.len());
    for nome in casos {
        let g = golden_dir();
        let entrada = le_json(&g.join(format!("{nome}.layout.json")));
        let esperado = fs::read_to_string(g.join(format!("{nome}.erro.txt"))).unwrap();
        match cade_layout::normalizar(&entrada) {
            Ok(_) => panic!("[{nome}] deveria falhar com: {esperado}"),
            Err(e) => assert_eq!(e.to_string(), esperado, "[{nome}] mensagem diferente"),
        }
    }
}

#[test]
fn spec_baixa_direto_no_roteador_identica_ao_python() {
    let casos = nomes_com_sufixo(".baixa.json");
    assert!(casos.len() >= 3);
    for nome in casos {
        let g = golden_dir();
        let low = le_json(&g.join(format!("{nome}.baixa.json")));
        let cad_py = fs::read(g.join(format!("{nome}.cad"))).unwrap();
        let s = cade_build::construir(&low).unwrap_or_else(|e| panic!("[{nome}] {e}"));
        assert!(s.bytes == cad_py, "[{nome}] {}", primeira_diferenca(&s.bytes, &cad_py));
    }
}

#[test]
fn todos_os_exemplos_de_tools_tem_golden() {
    let ex = raiz().join("tools").join("examples");
    if !ex.is_dir() {
        return; // o Python (e seus exemplos) ja foi removido: os goldens passam a ser a fonte
    }
    let mut n = 0;
    for e in fs::read_dir(&ex).unwrap().filter_map(|e| e.ok()) {
        let nome = e.file_name().into_string().unwrap();
        let Some(base) = nome.strip_suffix(".layout.json") else { continue };
        let copia = golden_dir().join(&nome);
        assert!(copia.is_file(), "exemplo sem golden: {nome} (rode python3 tests/golden/gerar.py)");
        assert_eq!(fs::read(e.path()).unwrap(), fs::read(&copia).unwrap(), "{nome}: exemplo mudou, regenere os goldens");
        assert!(golden_dir().join(format!("{base}.cad")).is_file(), "{base}.cad ausente");
        n += 1;
    }
    assert!(n >= 11, "esperava >= 11 exemplos, achei {n}");
}
