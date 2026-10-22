//! `cade` — binario unico do projeto (substitui o antigo `cade_cli` + as ferramentas Python).
//!
//! Subcomandos (nunca escreva `*`/`#` a mao):
//! - `validate <a.cad>`            checa header + `$$$`, imprime modo/versao
//! - `parse <a.cad> [-o a.json]`   `.cad` -> `cade.json v1` (meta + tokens byte-fieis)
//! - `emit <a.json> [-o b.cad]`    `cade.json` -> `.cad` byte-fiel
//! - `new-from-json <a.json> [-o b.cad]`  alias de emit + aceita template minimo `{meta}`
//! - `build <spec|layout.json> -o x.cad`  layout topologico OU spec baixa -> `.cad` (cad_build)
//! - `layout <in> [-o out.spec.json]`     layout topologico -> spec baixa (motor de layout)
//! - `gate <cad> [--testes t.json] [--json]`   gate estatico de um .cad (geo, fios, vinculos; testes: ver docs/rust-port.md)
//! - `design <layout.json> -o x.cad [--json]`  layout -> .cad + gate (equivale ao `cad_design` do MCP)
//!
//! Fases futuras (crates em `src/`): check, sim, render, mcp, app, vision, maint (ver docs/rust-port.md).

mod check;

use clap::{Parser, Subcommand};
use serde_json::Value;
use std::fs;
use std::io::Write;
use std::process::ExitCode;

#[derive(Parser)]
#[command(name = "cade", version, about = "CADe_SIMU: gerar/validar circuitos .cad (binario unico)")]
struct Cli {
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// Valida um .cad (header + secao `$$$`)
    Validate { arquivo: String },
    /// .cad -> cade.json (meta + tokens byte-fieis)
    Parse {
        arquivo: String,
        #[arg(short, long)]
        output: Option<String>,
    },
    /// cade.json -> .cad byte-fiel
    Emit {
        arquivo: String,
        #[arg(short, long)]
        output: Option<String>,
    },
    /// alias de emit; aceita template minimo {"meta": {...}}
    NewFromJson {
        arquivo: String,
        #[arg(short, long)]
        output: Option<String>,
    },
    /// layout topologico (ou spec baixa) -> .cad
    Build {
        arquivo: String,
        #[arg(short, long)]
        output: String,
    },
    /// layout topologico -> spec baixa (JSON)
    Layout {
        arquivo: String,
        #[arg(short, long)]
        output: Option<String>,
    },
    /// gate de um .cad existente: geo_check + wires_check + vinculos (+ testes funcionais quando houver simulador)
    Gate {
        arquivo: String,
        /// casos de teste (lista JSON, ou objeto com a chave `testes`)
        #[arg(long)]
        testes: Option<String>,
        /// relatorio JSON identico ao `cad_gate` do MCP
        #[arg(long)]
        json: bool,
    },
    /// layout topologico (ou spec baixa) -> .cad + gate completo
    Design {
        arquivo: String,
        #[arg(short, long)]
        output: String,
        /// relatorio JSON identico ao `cad_design` do MCP
        #[arg(long)]
        json: bool,
    },
}

/// Extrai titulo do campo versao (texto apos primeiro `#` ate `#`s).
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
    // tokens como latin1-string (byte 0-255 -> char U+0000-U+00FF); .cad e imprimivel.
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

fn json_to_tokens(json: &Value) -> Result<Vec<Vec<u8>>, String> {
    // Formato completo: {"tokens": [...]} -> round-trip byte-fiel.
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
    // Template minimo {"meta": {...}} -> .cad minimo valido.
    let meta = json.get("meta").ok_or("json sem `tokens` nem `meta`")?;
    let modo = meta.get("modo").and_then(|v| v.as_str()).unwrap_or("0");
    let versao = meta.get("versao").and_then(|v| v.as_str()).unwrap_or("3000");
    let titulo = meta.get("titulo").and_then(|v| v.as_str()).unwrap_or("-X");
    let header = format!("CADe_SIMU*{}*{}#{}#########", modo, versao, titulo);
    let minimal = format!("{}*0*0*0*0*0*0*0*0*24*42*0*0*-12*-9*6*3*0*0*0*1*0*0*0#***$$$&&&", header);
    // (formato identico ao do antigo cade_cli)
    Ok(minimal.split('*').map(|t| t.as_bytes().to_vec()).collect())
}

fn escreve_saida(raw: &[u8], out: Option<&str>, rotulo: &str, entrada: &str) -> i32 {
    match out {
        Some(o) => {
            if let Err(e) = fs::write(o, raw) {
                eprintln!("erro escrita {}: {}", o, e);
                return 1;
            }
            println!("{} {} -> {} ({}b)", rotulo, entrada, o, raw.len());
        }
        None => {
            let _ = std::io::stdout().write_all(raw);
        }
    }
    0
}

fn cmd_emit(json_path: &str, out: Option<&str>) -> i32 {
    let text = match fs::read_to_string(json_path) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("erro leitura {}: {}", json_path, e);
            return 1;
        }
    };
    let json: Value = match serde_json::from_str(&text) {
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
    let doc = cade_core::CadFile { modo: vec![], versao_campo: vec![], tokens };
    let raw = cade_core::emit(&doc);
    if let Err(e) = cade_core::parse(&raw) {
        eprintln!("gerado inválido: {}", e);
        return 1;
    }
    escreve_saida(&raw, out, "emit", json_path)
}

fn le_json(path: &str) -> Result<Value, String> {
    let text = fs::read_to_string(path).map_err(|e| format!("erro leitura {}: {}", path, e))?;
    serde_json::from_str(&text).map_err(|e| format!("json invalido {}: {}", path, e))
}

/// `build_spec.main`: um `*.layout.json` "puro" (sem `layout`/`simbolos`) vira `{"layout": spec}`.
fn envelopa(path: &str, spec: Value) -> Value {
    if path.ends_with(".layout.json") && spec.get("layout").is_none() && spec.get("simbolos").is_none() {
        serde_json::json!({ "layout": spec })
    } else {
        spec
    }
}

fn cmd_build(path: &str, out: &str) -> i32 {
    let spec = match le_json(path) {
        Ok(s) => envelopa(path, s),
        Err(e) => {
            eprintln!("{}", e);
            return 1;
        }
    };
    let norm = match cade_layout::normalizar(&spec) {
        Ok(n) => n,
        Err(e) => {
            let msg = match &e {
                cade_layout::LayoutError::Chave(_) => format!("campo obrigatorio ausente: {}", e),
                _ => e.to_string(),
            };
            eprintln!("ERRO: layout invalido: {}", msg);
            return 1;
        }
    };
    let saida = match cade_build::construir(&norm.low) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("{}", e);
            return 1;
        }
    };
    if let Err(e) = fs::write(out, &saida.bytes) {
        eprintln!("erro escrita {}: {}", out, e);
        return 1;
    }
    match cade_core::validate(&saida.bytes) {
        Ok((modo, versao)) => {
            let mut msg = format!("{} entidades -> {} | OK {} modo={} versao={}", saida.n_entidades, out, out, modo, versao);
            if !saida.curtos.is_empty() {
                msg.push_str(" | AVISO curto A==B em: ");
                msg.push_str(&saida.curtos.join(", "));
            }
            println!("{}", msg);
            0
        }
        Err(e) => {
            eprintln!("ERRO ao validar: {}", e);
            1
        }
    }
}

fn cmd_layout(path: &str, out: Option<&str>) -> i32 {
    let spec = match le_json(path) {
        Ok(s) => envelopa(path, s),
        Err(e) => {
            eprintln!("{}", e);
            return 1;
        }
    };
    // Mesma saida de `build_spec.normalizar` (o titulo do envelope vence), que e o que o `build` consome.
    let norm = match cade_layout::normalizar(&spec) {
        Ok(n) => n,
        Err(e) => {
            eprintln!("ERRO: {}", e);
            return 1;
        }
    };
    let txt = cade_layout::json_indent1(&norm.low);
    match out {
        Some(o) => {
            if let Err(e) = fs::write(o, &txt) {
                eprintln!("erro escrita {}: {}", o, e);
                return 1;
            }
            println!("layout {} -> {} ({} simbolos)", path, o, norm.low["simbolos"].as_array().map(|a| a.len()).unwrap_or(0));
        }
        None => println!("{}", txt),
    }
    0
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    let code = match &cli.cmd {
        Cmd::Validate { arquivo } => cmd_validate(arquivo),
        Cmd::Parse { arquivo, output } => cmd_parse(arquivo, output.as_deref()),
        Cmd::Emit { arquivo, output } | Cmd::NewFromJson { arquivo, output } => cmd_emit(arquivo, output.as_deref()),
        Cmd::Build { arquivo, output } => cmd_build(arquivo, output),
        Cmd::Layout { arquivo, output } => cmd_layout(arquivo, output.as_deref()),
        Cmd::Gate { arquivo, testes, json } => check::cmd_gate(arquivo, testes.as_deref(), *json),
        Cmd::Design { arquivo, output, json } => check::cmd_design(arquivo, output, *json),
    };
    ExitCode::from(code as u8)
}
