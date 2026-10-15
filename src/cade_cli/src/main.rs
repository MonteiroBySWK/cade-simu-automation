//! cade_cli v0.1 — CLI para OpenCode chamar (nunca escreve `*`/`#` na mão).
//!
//! Subcomandos:
//! - `validate <a.cad>` → checa header + `$$$`, imprime modo/versao
//! - `parse <a.cad> [-o a.json]` → `.cad` → `cade.json v1` (meta + tokens byte-fieis)
//! - `emit <a.json> [-o b.cad]` → `cade.json` → `.cad` byte-fiel
//! - `new-from-json <a.json> [-o b.cad]` → alias de emit + aceita template mínimo `{meta}`

use std::fs;
use std::path::PathBuf;

fn usage() -> ! {
    eprintln!("uso: cade_cli <validate|parse|emit|new-from-json> <arq> [-o saida]");
    std::process::exit(2);
}

/// Extrai titulo do campo versao (texto após primeiro `#` até `#`s).
fn titulo_de(versao_campo: &[u8]) -> String {
    let s = String::from_utf8_lossy(versao_campo);
    let mut parts = s.split('#');
    parts.next();
    parts.next().unwrap_or("").to_string()
}

fn cmd_validate(path: &str) -> i32 {
    match fs::read(path) {
        Ok(raw) => match cade_core::validate(&raw) {
            Ok((modo, versao)) => {
                println!("OK {} modo={} versao={}", path, modo, versao);
                0
            }
            Err(e) => {
                eprintln!("INVALIDO {}: {}", path, e);
                1
            }
        },
        Err(e) => {
            eprintln!("erro leitura {}: {}", path, e);
            1
        }
    }
}

fn cmd_parse(path: &str, out: Option<&str>) -> i32 {
    let raw = match fs::read(path) {
        Ok(r) => r,
        Err(e) => {
            eprintln!("erro leitura {}: {}", path, e);
            return 1;
        }
    };
    let doc = match cade_core::parse(&raw) {
        Ok(d) => d,
        Err(e) => {
            eprintln!("INVALIDO {}: {}", path, e);
            return 1;
        }
    };
    let modo = String::from_utf8_lossy(&doc.modo).into_owned();
    let versao_full = String::from_utf8_lossy(&doc.versao_campo).into_owned();
    let versao = versao_full.split('#').next().unwrap_or("").to_string();
    let titulo = titulo_de(&doc.versao_campo);
    // tokens como latin1-string (byte 0-255 → char U+0000-U+00FF); .cad é imprimível.
    let tokens: Vec<String> = doc.tokens.iter().map(|t| t.iter().map(|b| *b as char).collect()).collect();
    let json = serde_json::json!({
        "meta": {"titulo": titulo, "modo": modo, "versao": versao, "fonte": path},
        "tokens": tokens,
    });
    let text = serde_json::to_string_pretty(&json).unwrap();
    match out {
        Some(o) => {
            if let Err(e) = fs::write(o, &text) {
                eprintln!("erro escrita {}: {}", o, e);
                return 1;
            }
            println!("parse {} -> {} ({} tokens)", path, o, doc.tokens.len());
        }
        None => println!("{}", text),
    }
    0
}

fn json_to_tokens(json: &serde_json::Value) -> Result<Vec<Vec<u8>>, String> {
    // Formato completo: {"tokens": [...]} → round-trip byte-fiel.
    if let Some(arr) = json.get("tokens").and_then(|t| t.as_array()) {
        return arr
            .iter()
            .map(|v| {
                v.as_str()
                    .map(|s| s.chars().map(|c| c as u32 as u8).collect())
                    .ok_or_else(|| "token não-string em `tokens`".to_string())
            })
            .collect();
    }
    // Template mínimo {"meta": {...}} → .cad mínimo válido (F2: template vazio).
    let meta = json.get("meta").ok_or("json sem `tokens` nem `meta`")?;
    let modo = meta.get("modo").and_then(|v| v.as_str()).unwrap_or("0");
    let versao = meta.get("versao").and_then(|v| v.as_str()).unwrap_or("3000");
    let titulo = meta.get("titulo").and_then(|v| v.as_str()).unwrap_or("-X");
    let header = format!("CADe_SIMU*{}*{}#{}#########", modo, versao, titulo);
    let minimal = format!("{}*0*0*0*0*0*0*0*0*24*42*0*0*-12*-9*6*3*0*0*0*1*0*0*0#***$$$&&&", header);
    Ok(minimal.split('*').map(|t| t.as_bytes().to_vec()).collect())
}

fn cmd_emit(json_path: &str, out: Option<&str>) -> i32 {
    let text = match fs::read_to_string(json_path) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("erro leitura {}: {}", json_path, e);
            return 1;
        }
    };
    let json: serde_json::Value = match serde_json::from_str(&text) {
        Ok(j) => j,
        Err(e) => {
            eprintln!("json inválido {}: {}", json_path, e);
            return 1;
        }
    };
    let tokens = match json_to_tokens(&json) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("erro: {}", e);
            return 1;
        }
    };
    let doc = cade_core::CadFile {
        modo: vec![],
        versao_campo: vec![],
        tokens,
    };
    let raw = cade_core::emit(&doc);
    // valida o que gerou
    if let Err(e) = cade_core::parse(&raw) {
        eprintln!("gerado inválido: {}", e);
        return 1;
    }
    match out {
        Some(o) => {
            if let Err(e) = fs::write(o, &raw) {
                eprintln!("erro escrita {}: {}", o, e);
                return 1;
            }
            println!("emit {} -> {} ({}b)", json_path, o, raw.len());
        }
        None => {
            // stdout binário: escreve bytes brutos
            use std::io::Write;
            let _ = std::io::stdout().write_all(&raw);
        }
    }
    0
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 {
        usage();
    }
    let cmd = args[1].as_str();
    let input = args[2].clone();
    let mut out: Option<String> = None;
    let mut i = 3;
    while i < args.len() {
        if args[i] == "-o" && i + 1 < args.len() {
            out = Some(args[i + 1].clone());
            i += 2;
        } else {
            i += 1;
        }
    }
    let _ = PathBuf::from(&input); // reserva para validações futuras de caminho
    let code = match cmd {
        "validate" => cmd_validate(&input),
        "parse" => cmd_parse(&input, out.as_deref()),
        "emit" | "new-from-json" => cmd_emit(&input, out.as_deref()),
        _ => usage(),
    };
    std::process::exit(code);
}
