//! Servidor MCP (stdio) do cade-simu — substituto Rust de `tools/cade_mcp.py`.
//!
//! Protocolo: uma mensagem JSON-RPC 2.0 por linha no stdin; respostas no stdout.
//! - `initialize` -> `{protocolVersion, capabilities:{tools:{}}, serverInfo:{name:"cade-simu", version}}`;
//! - `notifications/initialized` (sem resposta);
//! - `tools/list` -> ferramentas com `name`, `description`, `inputSchema`;
//! - `tools/call` -> executa e devolve `{content:[{type:"text", text:"<texto>"}]}` (`isError` em erro).
//!
//! Ferramentas que dependem de renderizacao (`cad_preview`) ou do app real sob Wine
//! (`cad_simular_no_app`) ficam de fora de proposito.

use serde_json::{json, Map, Value};
use std::collections::HashMap;
use std::io::{BufRead, Write};
use std::path::{Path, PathBuf};

/// Descobre a raiz do repo (para `tools/examples/`): `CADE_ROOT`, senao sobe dos
/// diretorios do binario e do cwd ate achar `tools/examples`.
fn repo_root() -> PathBuf {
    if let Some(r) = std::env::var_os("CADE_ROOT") {
        let p = PathBuf::from(r);
        if p.join("tools").join("examples").is_dir() {
            return p;
        }
    }
    let mut bases: Vec<PathBuf> = Vec::new();
    if let Ok(exe) = std::env::current_exe() {
        if let Some(d) = exe.parent() {
            bases.push(d.to_path_buf());
        }
    }
    if let Ok(cwd) = std::env::current_dir() {
        bases.push(cwd);
    }
    for b in bases {
        let mut d: Option<PathBuf> = Some(b);
        for _ in 0..8 {
            let Some(cur) = d else { break };
            if cur.join("tools").join("examples").is_dir() {
                return cur;
            }
            d = cur.parent().map(Path::to_path_buf);
        }
    }
    std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
}

fn examples_dir() -> PathBuf {
    repo_root().join("tools").join("examples")
}

// --------------------------------------------------------------------------- ferramentas

type Exec = fn(&Map<String, Value>) -> Result<String, String>;

struct Tool {
    name: &'static str,
    desc: &'static str,
    schema: Value,
    exec: Exec,
}

fn schema(props: Value, required: &[&str]) -> Value {
    json!({"type": "object", "properties": props, "required": required})
}

fn str_prop(desc: &str) -> Value {
    json!({"type": "string", "description": desc})
}

fn ferramentas() -> Vec<Tool> {
    vec![
        Tool {
            name: "cad_validate",
            desc: "Valida um .cad (header + secao $$$). Retorna modo/versao ou o erro.",
            schema: schema(json!({"path": str_prop("caminho do .cad")}), &["path"]),
            exec: t_validate,
        },
        Tool {
            name: "cad_symbols",
            desc: "Lista as classes de simbolo (ID, nome/descricao quando conhecidos, tamanho, pinos nomeados). Use para ESCOLHER classes antes de montar o layout; para detalhes use cad_pins(classe).",
            schema: schema(json!({}), &[]),
            exec: |_| t_symbols(),
        },
        Tool {
            name: "cad_pins",
            desc: "Pinos e geometria de UMA classe: nomes, offsets (dx,dy), largura/altura e 'para que serve'. Retorno: {classe, nome, uso, largura, altura, pinos, pinos_ab, pinos_binario}.",
            schema: schema(json!({"classe": str_prop("classe, ex. \"2001\"")}), &["classe"]),
            exec: t_pins,
        },
        Tool {
            name: "cad_examples",
            desc: "Lista os layouts de exemplo (few-shot): nome, titulo, resumo e n de testes. PRIMEIRO passo de qualquer pedido de circuito.",
            schema: schema(json!({}), &[]),
            exec: |_| t_examples(),
        },
        Tool {
            name: "cad_example",
            desc: "Devolve o layout.json (DSL topologica + testes) do exemplo `nome` (veja cad_examples). Pode ser enviado inalterado a cad_design e passa o gate.",
            schema: schema(json!({"nome": str_prop("nome do exemplo, ex. \"partida_direta\"")}), &["nome"]),
            exec: t_example,
        },
        Tool {
            name: "cad_design",
            desc: "FERRAMENTA PRINCIPAL: layout TOPOLOGICO (sem x/y) -> .cad pronto + gate completo, numa chamada. layout_json = string JSON no formato de cad_examples; out_path = .cad de saida. Retorno JSON: {ok, path, gate, avisos, erros, proximo_passo}.",
            schema: schema(
                json!({"layout_json": str_prop("spec do circuito (DSL topologica) como string JSON"),
                       "out_path": str_prop("caminho do .cad de saida")}),
                &["layout_json", "out_path"],
            ),
            exec: t_design,
        },
        Tool {
            name: "cad_gate",
            desc: "Gate completo de um .cad EXISTENTE: validate + testes funcionais + geo_check + wires_check. testes_json: lista de casos (ou {\"testes\": [...]}) — sem casos o gate reprova. Retorno: mesmo JSON de cad_design.",
            schema: schema(
                json!({"path": str_prop("caminho do .cad"),
                       "testes_json": str_prop("casos de teste como string JSON (padrao \"[]\")")}),
                &["path"],
            ),
            exec: t_gate,
        },
        Tool {
            name: "cad_build",
            desc: "Compila layout topologico (ou spec baixa) em .cad, sem o gate (equivale a `cade build`). spec_json = string JSON da spec; out_path = .cad de saida. Para .cad pronto + gate prefira cad_design.",
            schema: schema(
                json!({"spec_json": str_prop("spec (layout topologico ou spec baixa) como string JSON"),
                       "out_path": str_prop("caminho do .cad de saida")}),
                &["spec_json", "out_path"],
            ),
            exec: t_build,
        },
        Tool {
            name: "cad_test",
            desc: "Verificacao funcional (tabela-verdade) via netlist. testes_json: [{\"nome\",\"entradas\":{\"S1\":true},\"inicial\":[\"KM1\"],\"esperado\":[\"KM1\"],\"status\":\"OK|RACE\"}]. Sem casos retorna SEM_TESTES.",
            schema: schema(
                json!({"path": str_prop("caminho do .cad"),
                       "testes_json": str_prop("casos como string JSON (padrao \"[]\")")}),
                &["path"],
            ),
            exec: t_test,
        },
        Tool {
            name: "cad_simulate",
            desc: "Simula a LOGICA do circuito (sem GUI) e devolve as bobinas energizadas. entradas_json: {\"S1\":true}; inicial_json: [\"KM1\"]; avanca: segundos com as entradas constantes. status em {OK, RACE, INSTAVEL, CURTO}.",
            schema: schema(
                json!({"path": str_prop("caminho do .cad"),
                       "entradas_json": str_prop("entradas acionadas, objeto JSON (padrao \"{}\")"),
                       "inicial_json": str_prop("bobinas ja energizadas, lista JSON (padrao \"[]\")"),
                       "avanca": json!({"type": "number", "description": "segundos de simulacao (padrao 0)"})}),
                &["path"],
            ),
            exec: t_simulate,
        },
    ]
}

fn arg(args: &Map<String, Value>, chave: &str, padrao: &str) -> String {
    args.get(chave).map(|v| match v {
        Value::String(s) => s.clone(),
        Value::Number(_) | Value::Bool(_) => v.to_string(),
        _ => padrao.to_string(),
    }).unwrap_or_else(|| padrao.to_string())
}

fn arg_f64(args: &Map<String, Value>, chave: &str) -> f64 {
    args.get(chave).and_then(|v| match v {
        Value::Number(n) => n.as_f64(),
        Value::String(s) => s.parse().ok(),
        _ => None,
    }).unwrap_or(0.0)
}

/// `testes_json`: lista de casos ou objeto com a chave `testes`.
fn parse_casos(txt: &str) -> Result<Vec<Value>, String> {
    let t = txt.trim();
    if t.is_empty() {
        return Ok(vec![]);
    }
    let v: Value = serde_json::from_str(t).map_err(|e| format!("testes_json invalido: {e}"))?;
    match v {
        Value::Array(a) => Ok(a),
        Value::Object(ref o) if o.get("testes").is_some_and(|t| t.is_array()) => {
            Ok(o["testes"].as_array().cloned().unwrap_or_default())
        }
        _ => Err("testes_json invalido: esperava uma lista de casos (ou {\"testes\": [...]})".into()),
    }
}

/// `inicial_json`: lista JSON `["KM1"]` ou texto `KM1,KM2`.
fn parse_inicial(txt: &str) -> Result<Vec<String>, String> {
    let t = txt.trim();
    if t.is_empty() {
        return Ok(vec![]);
    }
    if t.starts_with('[') {
        let v: Value = serde_json::from_str(t).map_err(|e| format!("inicial_json invalido: {e}"))?;
        return Ok(v.as_array().map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect()).unwrap_or_default());
    }
    Ok(t.split(',').map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect())
}

// --- validate

fn t_validate(args: &Map<String, Value>) -> Result<String, String> {
    let path = arg(args, "path", "");
    match std::fs::read(&path) {
        Ok(raw) => match cade_core::validate(&raw) {
            Ok((modo, versao)) => Ok(format!("OK {path} modo={modo} versao={versao}")),
            Err(e) => Ok(format!("ERRO INVALIDO {path}: {e}")),
        },
        Err(e) => Ok(format!("ERRO erro leitura {path}: {e}")),
    }
}

// --- symbols / pins (port de `cad_symbols` / `cad_pins` + `_nomes`)

/// (nome, uso, fonte) de uma classe de simbolo.
type NomeUso = (Option<String>, Option<String>, Option<String>);

fn nomes() -> HashMap<String, NomeUso> {
    let mut d: HashMap<String, NomeUso> = HashMap::new();
    if let Some(o) = cade_model::dados::symbol_names().as_object() {
        for (k, v) in o {
            if k.starts_with('_') {
                continue;
            }
            let s = |c: &str| v.get(c).and_then(|x| x.as_str()).map(String::from);
            d.insert(k.clone(), (s("nome"), s("uso"), s("fonte")));
        }
    }
    if let Some(o) = cade_model::dados::classes_papeis().as_object() {
        for (k, v) in o {
            if k.starts_with('_') || !v.is_object() {
                continue;
            }
            let e = d.entry(k.clone()).or_default();
            let s = |c: &str| v.get(c).and_then(|x| x.as_str()).map(String::from);
            if e.0.is_none() {
                e.0 = s("nome");
            }
            if e.1.is_none() {
                e.1 = s("aciona_por").or_else(|| s("papel"));
            }
            if e.2.is_none() {
                let conf = v.get("confianca").and_then(|x| x.as_str()).unwrap_or("?");
                e.2 = Some(format!("binario (docs/classes-papeis.json, confianca {conf})"));
            }
        }
    }
    d
}

const IGNORADAS: [&str; 8] = ["4000", "4001", "4002", "4009", "4010", "4011", "4003", "4004"];

fn t_symbols() -> Result<String, String> {
    let cat = cade_model::Catalogo::embutido();
    let nomes = nomes();
    let pins = cade_model::dados::symbol_pins();
    let dims = cade_model::dados::symbol_dims();
    let mut ids: Vec<&String> = cat.protos.keys().filter(|c| !IGNORADAS.contains(&c.as_str())).collect();
    ids.sort();
    let mut itens = Vec::new();
    for cid in ids {
        let p = &cat.protos[cid];
        let lab = p.labels.iter().find(|x| !x.is_empty()).cloned().unwrap_or_default();
        let (nome, uso, _) = nomes.get(cid).cloned().unwrap_or_default();
        let (w, h) = dims.get(cid).copied().unwrap_or((0, 0));
        let pn: Vec<String> = pins.get(cid).map(|c| {
            let mut v: Vec<String> = c.pins.keys().cloned().collect();
            v.sort();
            v
        }).unwrap_or_default();
        itens.push(json!({
            "classe": cid, "nome": nome, "uso": uso,
            "exemplo_rotulo": lab,
            "largura": if w == 0 { Value::Null } else { json!(w) },
            "altura": if h == 0 { Value::Null } else { json!(h) },
            "pinos": if pn.is_empty() { Value::Null } else { json!(pn) },
        }));
    }
    Ok(json!({"simbolos": itens, "n": itens.len()}).to_string())
}

fn t_pins(args: &Map<String, Value>) -> Result<String, String> {
    let cid = arg(args, "classe", "").trim().to_string();
    let cat = cade_model::Catalogo::embutido();
    let pins = cade_model::dados::symbol_pins();
    let bin = cade_model::dados::pinos_binario()
        .get("classes").and_then(|c| c.as_object()).cloned().unwrap_or_default();
    if !cat.protos.contains_key(&cid) && !pins.contains_key(&cid) && !bin.contains_key(&cid) {
        return Ok(json!({"erro": format!("classe {cid} desconhecida. Use cad_symbols.")}).to_string());
    }
    let nomes = nomes();
    let (nome, uso, fonte) = nomes.get(&cid).cloned().unwrap_or_default();
    let dims = cade_model::dados::symbol_dims();
    let (w, h) = dims.get(&cid).copied().unwrap_or((0, 0));
    let lab = cat.protos.get(&cid)
        .and_then(|p| p.labels.iter().find(|x| !x.is_empty()).cloned())
        .unwrap_or_default();
    let mut pinos = Map::new();
    let mut ab = Map::new();
    if let Some(c) = pins.get(&cid) {
        let mut ns: Vec<&String> = c.pins.keys().collect();
        ns.sort();
        for n in ns {
            pinos.insert(n.clone(), json!(c.pins[n]));
        }
        if let Some(a) = c.a {
            ab.insert("A".into(), json!(a));
        }
        if let Some(b) = c.b {
            ab.insert("B".into(), json!(b));
        }
    }
    let pbin = bin.get(&cid).and_then(|v| v.get("pins")).cloned().unwrap_or(json!({}));
    let mut out = json!({
        "classe": cid, "nome": nome, "uso": uso, "fonte_nome": fonte,
        "largura": if w == 0 { Value::Null } else { json!(w) },
        "altura": if h == 0 { Value::Null } else { json!(h) },
        "exemplo_rotulo": lab,
        "pinos": Value::Object(pinos),
        "pinos_ab": Value::Object(ab),
        "pinos_binario": pbin,
    });
    if nome.is_none() {
        out["aviso"] = json!("nome desconhecido (nao documentado); use exemplo_rotulo e os pinos como guia");
    }
    Ok(out.to_string())
}

// --- examples (port de `cad_examples` / `cad_example`)

fn t_examples() -> Result<String, String> {
    let dir = examples_dir();
    let mut itens = Vec::new();
    let mut lads: Vec<PathBuf> = Vec::new();
    let mut lays: Vec<PathBuf> = Vec::new();
    if let Ok(rd) = std::fs::read_dir(&dir) {
        for e in rd.filter_map(|e| e.ok()) {
            let p = e.path();
            let Some(n) = p.file_name().and_then(|n| n.to_str()) else { continue };
            if n.ends_with(".ladder.json") {
                lads.push(p);
            } else if n.ends_with(".layout.json") {
                lays.push(p);
            }
        }
    }
    lads.sort();
    lays.sort();
    for f in lads {
        let nome = f.file_name().unwrap().to_str().unwrap().strip_suffix(".json").unwrap().to_string();
        let d: Value = std::fs::read_to_string(&f).ok()
            .and_then(|t| serde_json::from_str(&t).ok()).unwrap_or(Value::Null);
        let lay = d.get("layout").unwrap_or(&Value::Null);
        let rungs = lay.get("ladder").and_then(|l| l.get("rungs")).and_then(|r| r.as_array()).map(|a| a.len()).unwrap_or(0);
        let nin = lay.get("clp").and_then(|l| l.get("entradas")).and_then(|r| r.as_array()).map(|a| a.len()).unwrap_or(0);
        let nsa = lay.get("clp").and_then(|l| l.get("saidas")).and_then(|r| r.as_array()).map(|a| a.len()).unwrap_or(0);
        itens.push(json!({"nome": nome, "titulo": d.get("titulo"),
            "dsl": "ladder/1",
            "descricao": format!("{rungs} degrau(s) ladder, {nin} entrada(s), {nsa} saida(s) de CLP"),
            "n_testes": d.get("testes").and_then(|t| t.as_array()).map(|a| a.len()).unwrap_or(0)}));
    }
    for f in lays {
        let nome = f.file_name().unwrap().to_str().unwrap().strip_suffix(".layout.json").unwrap().to_string();
        let d: Value = std::fs::read_to_string(&f).ok()
            .and_then(|t| serde_json::from_str(&t).ok()).unwrap_or(Value::Null);
        let lay = d.get("layout").unwrap_or(&d);
        let ramos: usize = lay.get("comando").and_then(|c| c.as_array()).map(|cs| {
            cs.iter().map(|b| b.get("ramos").and_then(|r| r.as_array()).map(|a| a.len()).unwrap_or(0)).sum()
        }).unwrap_or(0);
        let pot = lay.get("potencia").and_then(|p| p.as_array()).map(|a| a.len()).unwrap_or(0);
        let titulo = d.get("titulo").or_else(|| lay.get("titulo")).cloned().unwrap_or(Value::Null);
        let n_testes = d.get("testes").or_else(|| lay.get("testes")).and_then(|t| t.as_array()).map(|a| a.len()).unwrap_or(0);
        let descricao = d.get("descricao").and_then(|x| x.as_str()).map(String::from)
            .unwrap_or_else(|| format!("{ramos} degrau(s) de comando, {pot} grupo(s) de potencia"));
        itens.push(json!({"nome": nome, "titulo": titulo, "descricao": descricao, "n_testes": n_testes}));
    }
    let n = itens.len();
    Ok(json!({"exemplos": itens, "n": n,
        "uso": "cad_example(nome) devolve o layout.json completo; adapte e envie a cad_design"}).to_string())
}

fn t_example(args: &Map<String, Value>) -> Result<String, String> {
    let dir = examples_dir();
    let base = Path::new(&arg(args, "nome", "")).file_name()
        .and_then(|n| n.to_str()).unwrap_or("").to_string();
    for cand in [format!("{base}.layout.json"), format!("{base}.json"), base.clone()] {
        let p = dir.join(&cand);
        if p.is_file() && (cand.ends_with(".layout.json") || cand.ends_with(".ladder.json")) {
            return std::fs::read_to_string(&p).map_err(|e| format!("erro leitura {}: {e}", p.display()));
        }
    }
    let mut disp: Vec<String> = Vec::new();
    if let Ok(rd) = std::fs::read_dir(&dir) {
        for e in rd.filter_map(|e| e.ok()) {
            let n = e.file_name().into_string().unwrap_or_default();
            if let Some(b) = n.strip_suffix(".layout.json") {
                disp.push(b.to_string());
            } else if let Some(b) = n.strip_suffix(".ladder.json") {
                disp.push(b.to_string());
            }
        }
    }
    disp.sort();
    Ok(json!({"erro": format!("exemplo '{base}' nao existe"), "disponiveis": disp}).to_string())
}

// --- design / gate (port de `cad_design` / `cad_gate` sobre `cade_check` + `cade_sim`)

fn executor() -> Box<dyn cade_check::ExecutorTestes> {
    Box::new(cade_sim::ExecutorSim)
}

fn t_design(args: &Map<String, Value>) -> Result<String, String> {
    let layout = arg(args, "layout_json", "");
    let out = arg(args, "out_path", "");
    Ok(cade_check::design_texto(&layout, &out, executor().as_ref()).to_json())
}

fn t_gate(args: &Map<String, Value>) -> Result<String, String> {
    let path = arg(args, "path", "");
    let testes_txt = arg(args, "testes_json", "[]");
    let casos = match parse_casos(&testes_txt) {
        Ok(c) => c,
        Err(e) => return Ok(json!({"ok": false, "path": path, "erros": [e]}).to_string()),
    };
    match cade_check::gate_arquivo(&path, &casos, executor().as_ref()) {
        Ok(r) => Ok(r.to_json()),
        Err(e) => Ok(json!({"ok": false, "path": path, "erros": [e]}).to_string()),
    }
}

// --- build (equivale a `cade build`: layout topologico ou spec baixa -> .cad)

fn t_build(args: &Map<String, Value>) -> Result<String, String> {
    let spec_txt = arg(args, "spec_json", "");
    let out = arg(args, "out_path", "");
    let spec: Value = serde_json::from_str(&spec_txt).map_err(|e| format!("spec_json invalido: {e}"))?;
    let norm = cade_layout::normalizar(&spec).map_err(|e| format!("layout invalido: {e}"))?;
    let saida = cade_build::construir(&norm.low).map_err(|e| e.to_string())?;
    if let Some(pai) = Path::new(&out).parent().filter(|p| !p.as_os_str().is_empty()) {
        std::fs::create_dir_all(pai).map_err(|e| format!("erro criando diretorio: {e}"))?;
    }
    std::fs::write(&out, &saida.bytes).map_err(|e| format!("erro escrita {out}: {e}"))?;
    match cade_core::validate(&saida.bytes) {
        Ok((modo, versao)) => {
            let mut msg = format!("{} entidades -> {out} | OK {out} modo={modo} versao={versao}", saida.n_entidades);
            if !saida.curtos.is_empty() {
                msg.push_str(" | AVISO curto A==B em: ");
                msg.push_str(&saida.curtos.join(", "));
            }
            Ok(msg)
        }
        Err(e) => Err(format!("ERRO ao validar: {e}")),
    }
}

// --- test (equivale a `cade test`)

fn t_test(args: &Map<String, Value>) -> Result<String, String> {
    let path = arg(args, "path", "");
    let testes_txt = arg(args, "testes_json", "[]");
    let casos = match parse_casos(&testes_txt) {
        Ok(c) => c,
        Err(e) => return Ok(format!("ERRO {e}")),
    };
    let raw = std::fs::read(&path).map_err(|e| format!("erro leitura {path}: {e}"))?;
    match executor().executar(&raw, &casos) {
        Some(s) => {
            let mut txt = s.texto;
            for c in &s.chaves_invalidas {
                txt.push_str(&format!("\n  CHAVE INVALIDA: {c}"));
            }
            Ok(txt)
        }
        None => Ok("ERRO simulador indisponivel".to_string()),
    }
}

// --- simulate (equivale a `cade simulate`)

fn t_simulate(args: &Map<String, Value>) -> Result<String, String> {
    let path = arg(args, "path", "");
    let ent_txt = arg(args, "entradas_json", "{}");
    let ini_txt = arg(args, "inicial_json", "[]");
    let avanca = arg_f64(args, "avanca");
    let ent_txt = ent_txt.trim();
    let ent_v: Value = serde_json::from_str(if ent_txt.is_empty() { "{}" } else { ent_txt })
        .map_err(|e| format!("entradas_json invalido: {e}"))?;
    let inicial = parse_inicial(&ini_txt).map_err(|e| e.to_string())?;
    let raw = std::fs::read(&path).map_err(|e| format!("erro leitura {path}: {e}"))?;
    if cade_sim::ladder::tem_clp(&raw) {
        let c = cade_sim::ladder::CircuitoClp::de_bytes(&raw).map_err(|e| e.to_string())?;
        let ent: std::collections::BTreeMap<String, bool> = ent_v.as_object().map(|o| {
            o.iter().map(|(k, v)| (k.clone(), match v {
                Value::Bool(b) => *b,
                Value::Number(n) => n.as_i64().unwrap_or(0) != 0,
                _ => false,
            })).collect()
        }).unwrap_or_default();
        let caso = json!({"entradas": ent_v, "inicial": inicial});
        let img = c.imagem_inicial(&caso);
        let (_, r) = c.regime(&ent, Some(img), cade_sim::ladder::MAX_TICKS);
        let bits: Map<String, Value> = r.bits.iter().filter(|(_, v)| **v).map(|(k, v)| (k.clone(), json!(v))).collect();
        return Ok(json!({
            "status": r.status, "bobinas_energizadas": r.bobinas, "lampadas_acesas": r.lampadas,
            "curtos": r.curtos, "bits": Value::Object(bits), "ticks": r.ticks,
            "entradas": c.entradas, "bobinas": c.bobinas_fisicas(), "operandos": c.operandos,
        }).to_string());
    }
    let c = cade_sim::Circuito::abrir(&path).map_err(|e| e.to_string())?;
    let e = c.estado(&cade_sim::entradas_de_json(&ent_v), &inicial, avanca, None);
    let mut v = e.to_json();
    v["bobinas_energizadas"] = v["bobinas"].clone();
    v["lampadas_acesas"] = v["lampadas"].clone();
    v["entradas"] = json!(c.entradas);
    v["bobinas"] = json!(c.bobinas.keys().collect::<Vec<_>>());
    v["pinos_soltos"] = json!(c.soltos);
    Ok(v.to_string())
}

// --------------------------------------------------------------------------- protocolo

fn resposta_ok(id: &Value, result: Value) -> String {
    json!({"jsonrpc": "2.0", "id": id, "result": result}).to_string()
}

fn resposta_erro(id: &Value, codigo: i64, mensagem: &str) -> String {
    json!({"jsonrpc": "2.0", "id": id, "error": {"code": codigo, "message": mensagem}}).to_string()
}

fn atende(msg: &Value) -> Option<String> {
    let metodo = msg.get("method").and_then(|m| m.as_str()).unwrap_or("");
    let id = msg.get("id").cloned().unwrap_or(Value::Null);
    let tem_id = msg.get("id").is_some();
    match metodo {
        "initialize" => {
            let r = json!({
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "cade-simu", "version": env!("CARGO_PKG_VERSION")},
            });
            Some(resposta_ok(&id, r))
        }
        "notifications/initialized" | "notifications/cancelled" => None,
        "ping" => Some(resposta_ok(&id, json!({}))),
        "tools/list" => {
            let ts: Vec<Value> = ferramentas().iter().map(|t| {
                json!({"name": t.name, "description": t.desc, "inputSchema": t.schema})
            }).collect();
            Some(resposta_ok(&id, json!({"tools": ts})))
        }
        "tools/call" => {
            let p = msg.get("params").cloned().unwrap_or(Value::Null);
            let nome = p.get("name").and_then(|n| n.as_str()).unwrap_or("").to_string();
            let argmap: Map<String, Value> = p.get("arguments").and_then(|a| a.as_object()).cloned().unwrap_or_default();
            let Some(t) = ferramentas().into_iter().find(|t| t.name == nome) else {
                let r = json!({"content": [{"type": "text", "text": format!("ferramenta desconhecida: {nome}")}], "isError": true});
                return Some(resposta_ok(&id, r));
            };
            match (t.exec)(&argmap) {
                Ok(texto) => Some(resposta_ok(&id, json!({"content": [{"type": "text", "text": texto}]}))),
                Err(e) => Some(resposta_ok(&id, json!({"content": [{"type": "text", "text": e}], "isError": true}))),
            }
        }
        _ => {
            if tem_id {
                Some(resposta_erro(&id, -32601, &format!("metodo desconhecido: {metodo}")))
            } else {
                None
            }
        }
    }
}

/// Loop do servidor: le uma mensagem JSON-RPC por linha do stdin, escreve a resposta no stdout.
pub fn servir() -> i32 {
    let stdin = std::io::stdin();
    let mut saida = std::io::stdout();
    for linha in stdin.lock().lines() {
        let linha = match linha {
            Ok(l) => l,
            Err(_) => break,
        };
        if linha.trim().is_empty() {
            continue;
        }
        let msg: Value = match serde_json::from_str(&linha) {
            Ok(m) => m,
            Err(_) => continue,
        };
        if let Some(resp) = atende(&msg) {
            if writeln!(saida, "{resp}").is_err() {
                break;
            }
            if saida.flush().is_err() {
                break;
            }
        }
    }
    0
}
