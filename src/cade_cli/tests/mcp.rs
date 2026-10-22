//! Teste do servidor MCP (`cade mcp`): sobe o binario, envia `initialize`,
//! `tools/list` e um `tools/call` (`cad_examples`), e valida o JSON.

use serde_json::Value;
use std::io::Write;
use std::process::{Command, Stdio};

fn conversa(linhas: &[&str]) -> Vec<Value> {
    let mut filho = Command::new(env!("CARGO_BIN_EXE_cade"))
        .arg("mcp")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .expect("executar cade mcp");
    let entrada = linhas.join("\n") + "\n";
    filho.stdin.take().unwrap().write_all(entrada.as_bytes()).expect("escrever stdin");
    let saida = filho.wait_with_output().expect("ler stdout");
    assert!(saida.status.success(), "cade mcp saiu com erro");
    String::from_utf8_lossy(&saida.stdout)
        .lines()
        .filter(|l| !l.trim().is_empty())
        .map(|l| serde_json::from_str(l).expect("resposta deve ser JSON"))
        .collect()
}

#[test]
fn mcp_initialize_list_e_call() {
    let r = conversa(&[
        r#"{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}"#,
        r#"{"jsonrpc":"2.0","method":"notifications/initialized"}"#,
        r#"{"jsonrpc":"2.0","id":2,"method":"tools/list"}"#,
        r#"{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"cad_examples","arguments":{}}}"#,
    ]);
    // initialized nao responde: 3 respostas para 4 mensagens.
    assert_eq!(r.len(), 3, "{:?}", r);

    assert_eq!(r[0]["id"], 1);
    assert_eq!(r[0]["result"]["serverInfo"]["name"], "cade-simu");
    assert!(r[0]["result"]["capabilities"]["tools"].is_object());

    let nomes: Vec<&str> =
        r[1]["result"]["tools"].as_array().unwrap().iter().filter_map(|t| t["name"].as_str()).collect();
    for esperada in ["cad_examples", "cad_example", "cad_design", "cad_gate", "cad_validate",
                    "cad_build", "cad_test", "cad_simulate", "cad_symbols", "cad_pins"] {
        assert!(nomes.contains(&esperada), "falta {esperada} em {nomes:?}");
    }
    // preview/app ficam de fora (dependem de render/Wine).
    assert!(!nomes.contains(&"cad_preview"));
    assert!(!nomes.contains(&"cad_simular_no_app"));

    assert_eq!(r[2]["id"], 3);
    let texto = r[2]["result"]["content"][0]["text"].as_str().unwrap();
    let v: Value = serde_json::from_str(texto).expect("cad_examples devolve JSON");
    assert!(v["n"].as_u64().unwrap_or(0) >= 10, "{texto:.200}");
    assert!(v["exemplos"].as_array().unwrap().iter().any(|e| e["nome"] == "partida_direta"));
}

#[test]
fn mcp_design_e_gate_de_ponta_a_ponta() {
    let exemplo = conversa(&[
        r#"{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"cad_example","arguments":{"nome":"partida_direta"}}}"#,
    ]);
    let layout = exemplo[0]["result"]["content"][0]["text"].as_str().unwrap().to_string();
    assert!(layout.to_lowercase().contains("partida"), "{layout:.120}");
    let layout_escapado = serde_json::to_string(&layout).unwrap();
    let out = std::env::temp_dir().join(format!("cade_mcp_test_{}.cad", std::process::id()));
    let chamada = format!(
        "{{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{{\"name\":\"cad_design\",\"arguments\":{{\"layout_json\":{layout_escapado},\"out_path\":{out:?}}}}}}}",
        out = out.to_str().unwrap(),
    );
    let r = conversa(&[&chamada]);
    let texto = r[0]["result"]["content"][0]["text"].as_str().unwrap();
    let rel: Value = serde_json::from_str(texto).expect("cad_design devolve JSON");
    assert_eq!(rel["ok"], true, "{texto:.2000}");
}
