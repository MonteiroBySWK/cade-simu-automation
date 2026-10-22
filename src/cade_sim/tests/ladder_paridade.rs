//! Paridade do simulador ladder com o oraculo Python (`tools/clp_sim.py`).
//!
//! Para cada exemplo `tools/examples/*.ladder.json`: gera o `.cad` com o proprio
//! `tools/ladder_dsl.py` (a mesma rota do `scripts/dev.py gate`), roda o `clp_sim` no
//! Python capturando a saida e compara string a string com `cade_sim::ladder::teste_casos`.
//! Inclui sanidade (repouso + liga + selo) e `saidas_clp` da conformidade, so no motor Rust.

use cade_sim::conformidade::{executar_clp, Acao, Cenario};
use cade_sim::ladder::{self, CircuitoClp};
use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

fn raiz() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
}

fn tmp() -> PathBuf {
    let d = std::env::temp_dir().join(format!("cade_sim_ladder_{}", std::process::id()));
    fs::create_dir_all(&d).unwrap();
    d
}

/// Subdiretorio proprio por exemplo (os testes rodam em paralelo no mesmo processo).
fn tmp_ex(exemplo: &str) -> PathBuf {
    let d = tmp().join(exemplo);
    fs::create_dir_all(&d).unwrap();
    d
}

fn python3() -> String {
    "python3".to_string()
}

/// Gera o `.cad` do exemplo com o gerador Python; devolve (cad_bytes, casos).
fn gerar(exemplo: &str) -> (Vec<u8>, Vec<Value>) {
    let spec = raiz()
        .join("tools")
        .join("examples")
        .join(format!("{exemplo}.ladder.json"));
    let out = tmp_ex(exemplo).join(format!("{exemplo}.cad"));
    let st = Command::new(python3())
        .arg(raiz().join("tools").join("ladder_dsl.py"))
        .arg(&spec)
        .arg(&out)
        .output()
        .unwrap_or_else(|e| panic!("{exemplo}: sem python3 ({e})"));
    assert!(
        st.status.success(),
        "{exemplo}: ladder_dsl falhou:\n{}",
        String::from_utf8_lossy(&st.stdout)
    );
    let spec_v: Value = serde_json::from_str(&fs::read_to_string(&spec).unwrap()).unwrap();
    let casos = spec_v
        .get("testes")
        .and_then(|t| t.as_array())
        .cloned()
        .unwrap_or_default();
    assert!(!casos.is_empty(), "{exemplo}: sem testes na spec");
    (fs::read(&out).unwrap(), casos)
}

/// Saida do oraculo Python (`clp_sim.teste_casos`) para o `.cad` e os casos dados.
fn oraculo(exemplo: &str, cad: &Path, casos: &[Value]) -> (bool, String) {
    let dir = tmp_ex(exemplo);
    let casos_path = dir.join("casos.json");
    fs::write(&casos_path, serde_json::to_string(casos).unwrap()).unwrap();
    let out = Command::new(python3())
        .arg(raiz().join("tools").join("clp_sim.py"))
        .arg(cad)
        .arg(&casos_path)
        .output()
        .unwrap_or_else(|e| panic!("sem python3 ({e})"));
    (out.status.success(), String::from_utf8(out.stdout).unwrap())
}

fn confere_paridade(exemplo: &str) {
    let (cad, casos) = gerar(exemplo);
    let cad_path = tmp_ex(exemplo).join(format!("{exemplo}.cad"));
    fs::write(&cad_path, &cad).unwrap();
    let (ok_py, texto_py) = oraculo(exemplo, &cad_path, &casos);
    let c = CircuitoClp::de_bytes(&cad).unwrap_or_else(|e| panic!("{exemplo}: parse Rust: {e}"));
    let (ok_rs, texto_rs) = ladder::teste_casos(&c, &casos);
    assert_eq!(texto_rs, texto_py, "{exemplo}: texto diverge do oraculo");
    assert_eq!(ok_rs, ok_py, "{exemplo}: veredito diverge do oraculo");
    assert!(ok_rs, "{exemplo}: casos reprovam (oraculo tambem reprova?)");
}

#[test]
fn paridade_partida_direta() {
    confere_paridade("partida_direta");
}

#[test]
fn paridade_reversao() {
    confere_paridade("reversao");
}

#[test]
fn paridade_intercalada() {
    confere_paridade("intercalada");
}

#[test]
fn paridade_pratica5_complementar() {
    confere_paridade("pratica5_complementar");
}

#[test]
fn paridade_partida_sequencial_3() {
    confere_paridade("partida_sequencial_3");
}

#[test]
fn paridade_borda() {
    confere_paridade("borda");
}

#[test]
fn paridade_tof() {
    confere_paridade("tof");
}

#[test]
fn paridade_ctu() {
    confere_paridade("ctu");
}

#[test]
fn sanidade_repouso_liga_selo() {
    let (cad, _) = gerar("partida_direta");
    let c = CircuitoClp::de_bytes(&cad).unwrap();
    assert!(
        c.entradas.contains(&"S1".to_string()),
        "entradas: {:?}",
        c.entradas
    );
    assert!(
        c.operandos.contains(&"Q0.0".to_string()),
        "operandos: {:?}",
        c.operandos
    );
    let solto: std::collections::BTreeMap<String, bool> =
        [("S1".to_string(), false)].into_iter().collect();
    // repouso: NF fecha, NA abre
    let (e, r) = c.regime(&solto, None, ladder::MAX_TICKS);
    assert_eq!(r.status, "OK");
    assert!(r.bobinas.is_empty());
    assert!(
        r.bits["I0.0"] && !r.bits["I0.1"] && r.bits["I0.2"],
        "bits: {:?}",
        r.bits
    );
    assert!(c.saidas_energizadas(&e).is_empty());
    // S1 liga KM1, Q0.0/Q0.1 e as saidas; o selo mantem depois de soltar
    let liga: std::collections::BTreeMap<String, bool> =
        [("S1".to_string(), true)].into_iter().collect();
    let (e, r) = c.regime(&liga, Some(e), ladder::MAX_TICKS);
    assert_eq!(r.bobinas, ["KM1"]);
    assert!(r.bits["Q0.0"]);
    assert_eq!(c.saidas_energizadas(&e), ["Q0.0", "Q0.1"]);
    let (e, r) = c.regime(&solto, Some(e), ladder::MAX_TICKS);
    assert_eq!(r.bobinas, ["KM1"], "selo caiu");
    assert_eq!(
        c.saidas_energizadas(&e),
        ["Q0.0", "Q0.1"],
        "selo caiu na saida"
    );
}

#[test]
fn executor_ladder_reprova_chave_invalida_sem_verde_falso() {
    use cade_check::{ExecutorTestes, SaidaTestes};
    use cade_sim::ExecutorSim;
    let (cad, _) = gerar("partida_direta");
    let casos = serde_json::from_value::<Vec<Value>>(serde_json::json!([
        {"nome": "x", "entradas": {"FANTASMA": true}, "esperado": []},
        {"nome": "y", "entradas": {}, "esperado_bits": {"Q9.9": 0}}
    ]))
    .unwrap();
    let s: SaidaTestes = ExecutorSim.executar(&cad, &casos).unwrap();
    assert!(s.texto.starts_with("PASSOU\n"), "texto: {}", s.texto);
    assert_eq!(s.chaves_invalidas.len(), 2, "{:?}", s.chaves_invalidas);
    assert!(
        s.chaves_invalidas[0].contains("entrada 'FANTASMA' nao existe"),
        "{}",
        s.chaves_invalidas[0]
    );
    assert!(
        s.chaves_invalidas[1].contains("'esperado_bits' cita 'Q9.9'"),
        "{}",
        s.chaves_invalidas[1]
    );
}

#[test]
fn conformidade_preenche_saidas_clp() {
    let (cad, _) = gerar("partida_direta");
    let c = CircuitoClp::de_bytes(&cad).unwrap();
    let cen = Cenario {
        tempo_parede: false,
        descricao: "liga e desliga".into(),
        acoes: vec![
            Acao::Pressionar("S1".into()),
            Acao::Soltar("S1".into()),
            Acao::Pressionar("S0".into()),
            Acao::Reiniciar,
        ],
    };
    let obs = executar_clp(&c, &cen, None).unwrap();
    assert_eq!(obs.len(), 4);
    assert_eq!(obs[0].saidas_clp, ["Q0.0", "Q0.1"], "S1 liga as saidas");
    assert_eq!(obs[1].saidas_clp, ["Q0.0", "Q0.1"], "selo mantem as saidas");
    assert!(
        obs[2].saidas_clp.is_empty(),
        "S0 desliga: {:?}",
        obs[2].saidas_clp
    );
    assert!(obs[3].saidas_clp.is_empty());
    assert!(obs
        .iter()
        .all(|o| o.estado.bobinas.is_empty() || o.estado.bobinas == ["KM1"]));
}
