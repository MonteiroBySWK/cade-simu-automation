//! Gate completo (`build_spec.gate` / `construir`, `cade_mcp.cad_gate` / `cad_design`).
//!
//! O resultado tem a MESMA forma do relatorio do Python (`cade_mcp._relatorio`):
//! `{ok, path, gate:{build, testes, geo:{curtos, soltos}, fios}, avisos, erros, proximo_passo}`.
//!
//! Os testes funcionais dependem do simulador (`cade_sim`, outra fase): o gate recebe um
//! [`ExecutorTestes`]. Com [`NaoPortado`] (padrao do `cade`), `testes` sai com `status =
//! "nao_portado"`, `ok = false` e um erro explicito — **nunca** um verde falso. A parte estatica
//! (build, geo, fios, vinculos, lint) e sempre calculada e vem em [`Relatorio::estatico_ok`].

use crate::acionavel::{acionavel_curto, acionavel_solto};
use crate::geom::Conectividade;
use crate::{fios, geo, lint, vinculos};
use cade_layout::LayoutError;
use cade_model::latin1;
use serde_json::{json, Map, Value};
use std::path::Path;

/// Saida de um executor de testes funcionais (o que `cad_test` + `conferir_chaves_de_teste` produzem).
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct SaidaTestes {
    /// Texto do `cad_test`: `PASSOU ...`, `FALHOU ...`, `SEM_TESTES ...` (+ linhas `[FALHA] ...` e
    /// `RESULTADO: n/m`). O gate interpreta exatamente como o Python (`_parse_testes`).
    pub texto: String,
    /// Mensagens de `conferir_chaves_de_teste` (chave de teste inexistente = teste vacuo). So e
    /// consultado quando ha casos declarados.
    pub chaves_invalidas: Vec<String>,
}

/// Executor dos testes funcionais. Implementado pelo `cade_sim` quando portado.
///
/// `casos` sao os `testes` do layout/CLI (lista de `{nome, entradas, inicial, esperado, status}`).
/// Devolva `None` se o simulador nao esta disponivel: o gate marca `nao_portado` e reprova.
pub trait ExecutorTestes {
    fn executar(&self, cad: &[u8], casos: &[Value]) -> Option<SaidaTestes>;
}

/// Executor padrao enquanto o `cade_sim` nao existe: nunca executa nada.
#[derive(Debug, Clone, Copy, Default)]
pub struct NaoPortado;

impl ExecutorTestes for NaoPortado {
    fn executar(&self, _cad: &[u8], _casos: &[Value]) -> Option<SaidaTestes> {
        None
    }
}

/// Texto do erro quando os testes funcionais nao puderam rodar. Comeca com `testes:` (o mesmo
/// prefixo dos erros de teste do Python), entao os filtros de paridade o tratam como parte de teste.
pub const ERRO_NAO_PORTADO: &str = "testes: funcionais nao executados — o simulador (cade_sim) ainda nao foi portado \
                                    para Rust; sem prova funcional o circuito NAO esta aprovado (rode o gate Python/MCP)";

/// `{ok, mensagem}` do build.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Build {
    pub ok: bool,
    pub mensagem: String,
}

/// Estado dos testes funcionais.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct Testes {
    pub ok: bool,
    pub passaram: Option<u64>,
    pub total: Option<u64>,
    /// `groupdict` de cada `[FALHA]` (`nome` [, `obtido`, `status`, `esp`, `resto`]).
    pub falhas: Vec<Value>,
    /// Texto cru do `cad_test`.
    pub saida: String,
    /// `Some("nao_portado")` quando nao havia executor. Ausente no JSON quando `None`.
    pub status: Option<&'static str>,
}

/// Curtos/soltos: cru (`geo_check`) e acionavel (`acionavel_*`).
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct GeoRel {
    pub curtos: Vec<String>,
    pub soltos: Vec<String>,
    pub curtos_msg: Vec<String>,
    pub soltos_msg: Vec<String>,
}

/// `{ok, n, atravessam}` do wires_check.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct FiosRel {
    /// `None` = nao checado (erro antes do gate).
    pub ok: Option<bool>,
    /// `None` = omitido no JSON (como o `cad_gate` do Python em arquivo invalido).
    pub n: Option<usize>,
    pub atravessam: Vec<String>,
}

/// Relatorio do gate (`construir` / `gate`).
#[derive(Debug, Clone, Default, PartialEq)]
pub struct Relatorio {
    pub ok: bool,
    pub path: String,
    pub titulo: Option<String>,
    pub n_simbolos: Option<usize>,
    pub build: Build,
    pub testes: Testes,
    pub geo: GeoRel,
    pub fios: FiosRel,
    pub avisos: Vec<String>,
    pub erros: Vec<String>,
    /// So `ok`, `path`, `erros` (e `proximo_fixo`) no JSON (arquivo inexistente / entrada invalida).
    pub minimo: bool,
    /// `proximo_passo` fixo do relatorio minimo (JSON malformado no `cad_design`).
    pub proximo_fixo: Option<String>,
}

impl Relatorio {
    /// build ok E sem curto E sem pino solto: a parte do veredito que NAO depende do simulador.
    pub fn estatico_ok(&self) -> bool {
        self.build.ok && self.geo.curtos.is_empty() && self.geo.soltos.is_empty()
    }

    fn vazio(path: &str) -> Self {
        Relatorio {
            path: path.to_string(),
            fios: FiosRel { ok: None, n: Some(0), atravessam: vec![] },
            ..Default::default()
        }
    }

    /// Relatorio so com erro (`{"ok": false, "path", "erros"}`), sem a arvore `gate`.
    pub fn so_erro(path: &str, erro: String) -> Self {
        Relatorio { path: path.to_string(), erros: vec![erro], minimo: true, ..Default::default() }
    }

    /// `_proximo_passo`.
    pub fn proximo_passo(&self) -> String {
        let path = &self.path;
        if self.ok && self.fios.ok != Some(false) {
            return format!(
                "Gate verde. Chame cad_preview(path='{path}') e confira: nenhuma fase misturada, nenhum pino \
                 vermelho. Se estiver certo, entregue o .cad e resuma os testes que passaram."
            );
        }
        if self.ok {
            return format!(
                "Gate verde, mas {} fio(s) atravessam simbolo (estetico). Veja cad_preview; se o desenho estiver \
                 legivel, entregue; senao reordene serie/ramos.",
                self.fios.atravessam.len()
            );
        }
        if let Some(e) = self.erros.first() {
            if self.testes.status == Some("nao_portado") && self.estatico_ok() && e == ERRO_NAO_PORTADO {
                return "A parte estatica esta verde (build, geo, vinculos), mas os testes funcionais NAO rodaram: \
                        o simulador Rust ainda nao foi portado. Rode o gate Python/MCP (cad_gate) para a prova \
                        funcional antes de entregar."
                    .to_string();
            }
            if e.starts_with("layout invalido") {
                return format!("Corrija o layout_json: {e}. Use cad_example('partida_direta') como molde e tente de novo.");
            }
            if e.starts_with("CURTO") {
                return format!("Corrija o curto de fase: {e}. Depois chame cad_design de novo.");
            }
            if e.contains("solto") {
                return format!("Ligue o pino solto: {e}. Depois chame cad_design de novo.");
            }
            if e.starts_with("sem testes") || e.starts_with("teste") {
                return format!("Ajuste os testes ou o circuito: {e}. Depois chame cad_design de novo.");
            }
            return format!("Corrija: {e}. Depois chame cad_design de novo.");
        }
        "Revise o relatorio do gate.".to_string()
    }

    /// `_relatorio(r, path)`: o JSON de `cad_design`/`cad_gate`. Chaves e ordem como no Python.
    pub fn to_value(&self) -> Value {
        if self.minimo {
            let mut m = Map::new();
            m.insert("ok".into(), json!(false));
            m.insert("path".into(), json!(self.path));
            m.insert("erros".into(), json!(self.erros));
            if let Some(p) = &self.proximo_fixo {
                m.insert("proximo_passo".into(), json!(p));
            }
            return Value::Object(m);
        }
        let mut testes = Map::new();
        testes.insert("ok".into(), json!(self.testes.ok));
        testes.insert("passaram".into(), json!(self.testes.passaram));
        testes.insert("total".into(), json!(self.testes.total));
        testes.insert("falhas".into(), json!(self.testes.falhas));
        if let Some(s) = self.testes.status {
            testes.insert("status".into(), json!(s));
        }
        let mut fios = Map::new();
        fios.insert("ok".into(), json!(self.fios.ok));
        if let Some(n) = self.fios.n {
            fios.insert("n".into(), json!(n));
        }
        fios.insert("atravessam".into(), json!(self.fios.atravessam));
        json!({
            "ok": self.ok,
            "path": self.path,
            "gate": {
                "build": {"ok": self.build.ok, "mensagem": self.build.mensagem},
                "testes": Value::Object(testes),
                "geo": {"curtos": self.geo.curtos_msg, "soltos": self.geo.soltos_msg},
                "fios": Value::Object(fios),
            },
            "avisos": self.avisos,
            "erros": self.erros,
            "proximo_passo": self.proximo_passo(),
        })
    }

    /// JSON no formato de `json.dumps(indent=1, ensure_ascii=False)`.
    pub fn to_json(&self) -> String {
        cade_layout::json_indent1(&self.to_value())
    }
}

// ----------------------------------------------------------------------------- testes (parse)

fn salta_espacos(s: &str) -> &str {
    s.trim_start()
}

/// Casa `\[FALHA\]\s*(?P<nome>.*?):\s*KM=(?P<obtido>\[.*?\])\s*status=(?P<status>\S+)\s*esperado=
/// (?P<esp>\[[^\]]*\]|None)(?P<resto>.*)$` (busca da esquerda, com os mesmos quantificadores preguicosos).
fn casar_falha(ln: &str) -> Option<Map<String, Value>> {
    let mut ini = 0;
    while let Some(off) = ln[ini..].find("[FALHA]") {
        let corpo = salta_espacos(&ln[ini + off + "[FALHA]".len()..]);
        if let Some(m) = casar_apos_tag(corpo) {
            return Some(m);
        }
        ini += off + 1;
    }
    None
}

fn casar_apos_tag(corpo: &str) -> Option<Map<String, Value>> {
    for (ci, c) in corpo.char_indices() {
        if c != ':' {
            continue;
        }
        let nome = &corpo[..ci];
        let Some(r) = salta_espacos(&corpo[ci + 1..]).strip_prefix("KM=") else { continue };
        // obtido = \[.*?\]  (preguicoso: termina no primeiro ']' que deixa o resto casar)
        if !r.starts_with('[') {
            continue;
        }
        for (pi, ch) in r.char_indices() {
            if ch != ']' {
                continue;
            }
            let obtido = &r[..=pi];
            let Some(r2) = salta_espacos(&r[pi + 1..]).strip_prefix("status=") else { continue };
            // status = \S+ (guloso, com retrocesso ate achar \s*esperado=)
            let run_len = r2.find(char::is_whitespace).unwrap_or(r2.len());
            let mut cortes: Vec<usize> = r2[..run_len].char_indices().map(|(i, _)| i).skip(1).collect();
            cortes.push(run_len);
            for &fim in cortes.iter().rev() {
                let status = &r2[..fim];
                let Some(r3) = salta_espacos(&r2[fim..]).strip_prefix("esperado=") else { continue };
                let (esp, resto) = if r3.starts_with('[') {
                    match r3.find(']') {
                        Some(e) => (&r3[..=e], &r3[e + 1..]),
                        None => continue,
                    }
                } else if let Some(resto) = r3.strip_prefix("None") {
                    ("None", resto)
                } else {
                    continue;
                };
                let mut m = Map::new();
                m.insert("nome".into(), json!(nome));
                m.insert("obtido".into(), json!(obtido));
                m.insert("status".into(), json!(status));
                m.insert("esp".into(), json!(esp));
                m.insert("resto".into(), json!(resto));
                return Some(m);
            }
        }
    }
    None
}

/// `_parse_testes(saida)`: `((passaram, total), falhas)`.
pub fn parse_testes(saida: &str) -> ((Option<u64>, Option<u64>), Vec<Value>) {
    let mut falhas = Vec::new();
    for ln in saida.lines() {
        if ln.contains("[FALHA]") {
            let t = ln.trim();
            falhas.push(match casar_falha(t) {
                Some(m) => Value::Object(m),
                None => json!({"nome": t}),
            });
        }
    }
    (resultado(saida), falhas)
}

/// `re.search(r"RESULTADO:\s*(\d+)/(\d+)")`.
fn resultado(saida: &str) -> (Option<u64>, Option<u64>) {
    let mut ini = 0;
    while let Some(off) = saida[ini..].find("RESULTADO:") {
        let r = salta_espacos(&saida[ini + off + "RESULTADO:".len()..]);
        let d1: String = r.chars().take_while(|c| c.is_ascii_digit()).collect();
        if !d1.is_empty() {
            if let Some(r2) = r[d1.len()..].strip_prefix('/') {
                let d2: String = r2.chars().take_while(|c| c.is_ascii_digit()).collect();
                if !d2.is_empty() {
                    return (d1.parse().ok(), d2.parse().ok());
                }
            }
        }
        ini += off + 1;
    }
    (None, None)
}

// ----------------------------------------------------------------------------- gate

/// `build_spec.gate(path, testes, r)` sobre um `.cad` ja gerado (nao reconstroi o arquivo).
/// Preenche vinculos, geo, fios e testes em `r`. `Err` se o conteudo nao e decomponivel em entidades.
///
/// Circuito com CLP segue o gate do ladder (`gate_clp` de `tools/ladder_dsl.py`): o pino B das
/// bobinas ladder (trilho direito aberto, `docs/ladder.md` §4) nao e pino solto, e nao ha
/// `wires_check` (o Python zera `r["fios"]` nesse ramo).
pub fn gate_em(cad: &[u8], casos: &[Value], exec: &dyn ExecutorTestes, r: &mut Relatorio) -> Result<(), String> {
    let texto = latin1::decodificar(cad);
    let ents = crate::geom::entidades_do_cad(&texto)?;
    let clp = crate::geom::tem_clp(&ents);
    let g = geo::analisar_entidades(&Conectividade::de_entidades(&ents));
    let soltos: Vec<String> = g.soltos.into_iter().filter(|s| !(clp && solto_permitido(s))).collect();
    r.geo = GeoRel {
        curtos_msg: g.curtos.iter().map(|c| acionavel_curto(c)).collect(),
        soltos_msg: soltos.iter().map(|s| acionavel_solto(s)).collect(),
        curtos: g.curtos,
        soltos,
    };
    r.erros.extend(r.geo.curtos_msg.clone());
    r.erros.extend(r.geo.soltos_msg.clone());

    let (ev, av) = vinculos::conferir_texto(&texto)?;
    r.erros.extend(ev);
    r.avisos.extend(av);

    match exec.executar(cad, casos) {
        None => {
            r.testes = Testes { status: Some("nao_portado"), ..Default::default() };
            r.erros.push(ERRO_NAO_PORTADO.to_string());
        }
        Some(s) => {
            let teste = s.texto;
            let ((pas, tot), falhas) = parse_testes(&teste);
            let chaves = if casos.is_empty() { vec![] } else { s.chaves_invalidas };
            r.testes = Testes {
                ok: teste.starts_with("PASSOU") && chaves.is_empty(),
                passaram: pas,
                total: tot,
                falhas: falhas.clone(),
                saida: teste.clone(),
                status: None,
            };
            if teste.starts_with("SEM_TESTES") {
                r.erros.push(
                    "sem testes: declare \"testes\" (casos {nome, entradas, inicial, esperado, status}); sem eles o \
                     circuito nao tem prova funcional"
                        .to_string(),
                );
            }
            for f in &falhas {
                r.erros.push(format!("teste falhou: {}", descreve_falha(f)));
            }
            r.erros.extend(chaves);
            if !casos.is_empty() && !teste.starts_with("PASSOU") && falhas.is_empty() {
                r.erros.push(format!("testes: {}", teste.lines().next().unwrap_or("")));
            }
        }
    }

    let w = fios::analisar_texto(&texto)?;
    if clp {
        // gate do ladder nao roda `wires_check` (o Python zera `r["fios"]`)
        r.fios = FiosRel { ok: Some(true), n: Some(0), atravessam: vec![] };
    } else {
        r.fios = FiosRel { ok: Some(w.ruins.is_empty()), n: Some(w.n), atravessam: w.mensagens() };
    }
    if !w.ruins.is_empty() && !clp {
        let primeiros: Vec<&str> = r.fios.atravessam.iter().take(3).map(|s| s.as_str()).collect();
        r.avisos.push(format!(
            "{} trecho(s) de fio atravessam simbolo (estetico): {}",
            w.ruins.len(),
            primeiros.join("; ")
        ));
    }
    Ok(())
}

/// `_solto_permitido` de `tools/ladder_dsl.py`: pino B de bobina ladder (trilho direito
/// aberto, `docs/ladder.md` §4) e por desenho, nao pino solto; 10063: pino D (contagem
/// decrescente, fora do escopo da DSL) fica sem fio, e o pino R sem fio le reset 0.
fn solto_permitido(s: &str) -> bool {
    ["10060", "10061", "10062"].iter().any(|c| s.contains(&format!("({c}).p2@")) || s.contains(&format!("({c}).B@")))
        || s.contains("(10063).p1@")
        || s.contains("(10063).p3@")
}

fn descreve_falha(f: &Value) -> String {
    let g = |k: &str| f.get(k).and_then(|v| v.as_str()).unwrap_or("").to_string();
    if f.get("obtido").is_some() {
        format!("{} -> obtido {} status={}, esperado {}", g("nome"), g("obtido"), g("status"), g("esp"))
    } else {
        g("nome")
    }
}

/// `cad_gate(path, testes_json)`: gate de um `.cad` existente (validate + vinculos + geo + testes + fios).
///
/// `casos` e a lista de casos de teste (`[]` = sem casos). Relatorio com `minimo` se o arquivo
/// nao existe. Nao grava nada.
pub fn gate_arquivo(path: &str, casos: &[Value], exec: &dyn ExecutorTestes) -> Result<Relatorio, String> {
    if !Path::new(path).is_file() {
        return Ok(Relatorio::so_erro(path, format!("arquivo nao existe: {path}")));
    }
    let cad = std::fs::read(path).map_err(|e| format!("erro leitura {path}: {e}"))?;
    gate_bytes(&cad, path, casos, exec)
}

/// Como [`gate_arquivo`], mas sobre bytes ja lidos (`path` so rotula a saida).
pub fn gate_bytes(cad: &[u8], path: &str, casos: &[Value], exec: &dyn ExecutorTestes) -> Result<Relatorio, String> {
    let mut r = Relatorio::vazio(path);
    r.fios.n = None;
    match cade_core::validate(cad) {
        Ok((modo, versao)) => r.build = Build { ok: true, mensagem: format!("OK {path} modo={modo} versao={versao}") },
        Err(e) => {
            let msg = format!("INVALIDO {path}: {e}");
            r.build = Build { ok: false, mensagem: msg.clone() };
            r.erros.push(format!("arquivo invalido: {msg}"));
            return Ok(r);
        }
    }
    gate_em(cad, casos, exec, &mut r)?;
    r.ok = r.testes.ok && r.geo.curtos.is_empty() && r.geo.soltos.is_empty();
    Ok(r)
}

/// Mensagem do `LayoutError` como o `construir` do Python (`KeyError` -> "campo obrigatorio ausente: 'k'").
pub fn mensagem_layout(e: &LayoutError) -> String {
    match e {
        LayoutError::Chave(_) => format!("campo obrigatorio ausente: {e}"),
        _ => e.to_string(),
    }
}

/// `build_spec.construir(spec, out)`: compila (se for DSL), gera o `.cad` em `out` (cria o diretorio
/// pai) e roda o gate completo. `ok` = build ok E testes passam E sem curto/pino solto
/// (fios = aviso estetico, nao bloqueia).
pub fn construir(spec: &Value, out: &str, exec: &dyn ExecutorTestes) -> Relatorio {
    let mut r = Relatorio::vazio(out);
    let norm = match cade_layout::normalizar(spec) {
        Ok(n) => n,
        Err(e) => {
            r.erros.push(format!("layout invalido: {}", mensagem_layout(&e)));
            return r;
        }
    };
    r.titulo = norm.low.get("titulo").and_then(|t| t.as_str()).map(String::from);
    r.n_simbolos = Some(norm.low.get("simbolos").and_then(|s| s.as_array()).map(|a| a.len()).unwrap_or(0));
    r.avisos.extend(lint::lint_layout(norm.layout.as_ref()));

    let saida = match cade_build::construir(&norm.low) {
        Ok(s) => s,
        Err(e) if e.starts_with("ERRO") => {
            r.build = Build { ok: false, mensagem: e.clone() };
            r.erros.push(format!("build: {e}"));
            return r;
        }
        Err(e) => {
            r.erros.push(format!("layout invalido: {e}"));
            return r;
        }
    };
    if let Some(pai) = Path::new(out).parent().filter(|p| !p.as_os_str().is_empty()) {
        let _ = std::fs::create_dir_all(pai);
    }
    if let Err(e) = std::fs::write(out, &saida.bytes) {
        r.erros.push(format!("build: ERRO escrita {out}: {e}"));
        return r;
    }
    let mut res = match cade_core::validate(&saida.bytes) {
        Ok((modo, versao)) => {
            format!("{} entidades -> {out} | OK {out} modo={modo} versao={versao}", saida.n_entidades)
        }
        Err(e) => format!("ERRO ao validar: INVALIDO {out}: {e}"),
    };
    if !saida.curtos.is_empty() {
        res.push_str(" | AVISO curto A==B em: ");
        res.push_str(&saida.curtos.join(", "));
    }
    r.build = Build { ok: !res.contains("AVISO") && !res.contains("ERRO") && res.contains("OK"), mensagem: res.clone() };
    if res.contains("ERRO") {
        r.erros.push(format!("build: {res}"));
    }
    if res.contains("AVISO") {
        r.erros.push(format!(
            "build: {res} — um simbolo ficou com os dois pinos no mesmo no (curto); revise as conexoes do simbolo citado"
        ));
    }
    if res.contains("ERRO") {
        return r;
    }

    let casos: Vec<Value> = norm.testes.as_array().cloned().unwrap_or_default();
    if let Err(e) = gate_em(&saida.bytes, &casos, exec, &mut r) {
        r.erros.push(format!("layout invalido: {e}"));
        return r;
    }
    r.ok = r.build.ok && r.testes.ok && r.geo.curtos.is_empty() && r.geo.soltos.is_empty();
    r
}

/// `cad_design(layout_json, out_path)` a partir do texto JSON. JSON malformado vira relatorio de erro.
pub fn design_texto(layout_json: &str, out: &str, exec: &dyn ExecutorTestes) -> Relatorio {
    match serde_json::from_str::<Value>(layout_json) {
        Ok(spec) => construir(&spec, out, exec),
        Err(e) => {
            let mut r = Relatorio::so_erro(out, format!("layout invalido: JSON malformado: {e}"));
            r.proximo_fixo = Some("Envie um JSON valido (string). Veja cad_example.".to_string());
            r
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_resultado_e_falha_estruturada() {
        let s = "FALHOU 1 de 2\n[FALHA] S1 liga KM1: KM=['KM2'] status=OK esperado=['KM1'] extra\nRESULTADO: 1/2 OK\n";
        let ((p, t), f) = parse_testes(s);
        assert_eq!((p, t), (Some(1), Some(2)));
        assert_eq!(f.len(), 1);
        assert_eq!(f[0]["nome"], "S1 liga KM1");
        assert_eq!(f[0]["obtido"], "['KM2']");
        assert_eq!(f[0]["status"], "OK");
        assert_eq!(f[0]["esp"], "['KM1']");
        assert_eq!(f[0]["resto"], " extra");
    }

    #[test]
    fn falha_ilegivel_guarda_so_o_nome() {
        let (_, f) = parse_testes("[FALHA] algo estranho");
        assert_eq!(f, vec![json!({"nome": "[FALHA] algo estranho"})]);
    }

    #[test]
    fn esperado_none() {
        let (_, f) = parse_testes("[FALHA] x: KM=[] status=OK esperado=None");
        assert_eq!(f[0]["esp"], "None");
        assert_eq!(f[0]["resto"], "");
    }

    #[test]
    fn sem_resultado() {
        assert_eq!(parse_testes("PASSOU").0, (None, None));
    }

    #[test]
    fn nao_portado_nunca_e_verde() {
        let cad = include_bytes!("../../../tests/golden/partida_direta.cad");
        let r = gate_bytes(cad, "x.cad", &[], &NaoPortado).unwrap();
        assert!(!r.ok);
        assert!(r.estatico_ok());
        assert_eq!(r.testes.status, Some("nao_portado"));
        assert_eq!(r.erros.last().map(String::as_str), Some(ERRO_NAO_PORTADO));
        assert!(r.proximo_passo().contains("NAO rodaram"));
        let v = r.to_value();
        assert_eq!(v["gate"]["testes"]["status"], "nao_portado");
        assert_eq!(v["ok"], false);
    }

    struct Fake(&'static str);
    impl ExecutorTestes for Fake {
        fn executar(&self, _: &[u8], _: &[Value]) -> Option<SaidaTestes> {
            Some(SaidaTestes { texto: self.0.to_string(), chaves_invalidas: vec![] })
        }
    }

    #[test]
    fn executor_passou_deixa_o_gate_verde() {
        let cad = include_bytes!("../../../tests/golden/partida_direta.cad");
        let casos = [json!({"nome": "x"})];
        let r = gate_bytes(cad, "x.cad", &casos, &Fake("PASSOU 1/1\nRESULTADO: 1/1 OK")).unwrap();
        assert!(r.ok, "{:?}", r.erros);
        assert_eq!((r.testes.passaram, r.testes.total), (Some(1), Some(1)));
        assert!(r.to_value()["gate"]["testes"].get("status").is_none());
    }

    #[test]
    fn executor_sem_testes_reprova() {
        let cad = include_bytes!("../../../tests/golden/partida_direta.cad");
        let r = gate_bytes(cad, "x.cad", &[], &Fake("SEM_TESTES: nada")).unwrap();
        assert!(!r.ok);
        assert!(r.erros.iter().any(|e| e.starts_with("sem testes")));
    }

    #[test]
    fn arquivo_inexistente_e_relatorio_minimo() {
        let r = gate_arquivo("/nao/existe.cad", &[], &NaoPortado).unwrap();
        assert_eq!(r.to_value(), json!({"ok": false, "path": "/nao/existe.cad", "erros": ["arquivo nao existe: /nao/existe.cad"]}));
    }

    #[test]
    fn arquivo_invalido_nao_roda_gate() {
        let r = gate_bytes(b"lixo", "x.cad", &[], &NaoPortado).unwrap();
        assert!(!r.build.ok);
        assert!(r.erros[0].starts_with("arquivo invalido: INVALIDO x.cad"));
        assert_eq!(r.fios.n, None);
    }

    #[test]
    fn json_malformado() {
        let r = design_texto("{", "x.cad", &NaoPortado);
        assert!(!r.ok);
        assert!(r.erros[0].starts_with("layout invalido: JSON malformado"));
        assert_eq!(r.to_value()["proximo_passo"], "Envie um JSON valido (string). Veja cad_example.");
    }
}
