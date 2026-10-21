//! `cade_layout` — port de `tools/layout.py`: spec TOPOLOGICA (sem x/y) -> spec "baixa"
//! `{titulo, rails, simbolos, conexoes[, fios]}` consumida por `cade_build`.
//!
//! Inclui: forma legada (`serie`+`ramos`), rede serie-paralelo recursiva (`rede`/`rungs`),
//! serpentina e faixas amarradas, `trilhos_comando` (transformador 3012 / fonte 3003),
//! fontes (3004 por fase ou 3007 multi-terminal), terra e `potencia` (paralelo e `ordem`).
//! Os numeros (GAP, GN, ...) e a ordem de emissao sao identicos ao oraculo Python.

// Port literal do Python: assinaturas largas e indices paralelos sao intencionais (paridade primeiro).
#![allow(clippy::too_many_arguments, clippy::type_complexity, clippy::needless_range_loop)]

mod comando;
mod ctx;
mod potencia;
pub mod rede;

use cade_model::dados;
use cade_model::pyfmt;
use serde_json::{json, Map, Value};
use std::collections::HashSet;
use std::fmt;

pub use rede::Env;

/// Equivalente das excecoes Python que o oraculo levanta.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum LayoutError {
    /// `ValueError(msg)`.
    Valor(String),
    /// `KeyError(chave)`: `str()` = `repr(chave)`.
    Chave(String),
    /// `TypeError(msg)`.
    Tipo(String),
}

impl fmt::Display for LayoutError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            LayoutError::Valor(m) | LayoutError::Tipo(m) => f.write_str(m),
            LayoutError::Chave(k) => f.write_str(&pyfmt::repr_str(k)),
        }
    }
}

impl std::error::Error for LayoutError {}

pub type R<T> = Result<T, LayoutError>;

pub(crate) fn val(m: String) -> LayoutError {
    LayoutError::Valor(m)
}

pub(crate) fn tipo(m: String) -> LayoutError {
    LayoutError::Tipo(m)
}

pub const GAP: i64 = rede::GAP;
pub const PHASE_DX: i64 = 6;
pub const ROW_PITCH: i64 = 60;
pub const FALLBACK_DIM: (i64, i64) = (18, 15);

// ------------------------------------------------------------------ helpers de classe/JSON

/// `dim(classe)`.
pub fn dim(classe: &str) -> (i64, i64) {
    dados::symbol_dims().get(classe).copied().unwrap_or(FALLBACK_DIM)
}

/// `pin_off(classe, pino)`.
pub fn pin_off(classe: &str, pino: &str) -> R<[i64; 2]> {
    dados::symbol_pins()
        .get(classe)
        .and_then(|i| i.offset(pino))
        .ok_or_else(|| val(format!("classe {} sem pino {}", classe, pino)))
}

/// `_width(classe)`: corpo ou o pino mais a direita.
pub fn width(classe: &str) -> i64 {
    let (w, _) = dim(classe);
    let mut m = w;
    if let Some(info) = dados::symbol_pins().get(classe) {
        for o in info.pins.values() {
            m = m.max(o[0]);
        }
        for o in [info.a, info.b].into_iter().flatten() {
            m = m.max(o[0]);
        }
    }
    m
}

pub(crate) fn get<'a>(v: &'a Value, k: &str) -> Option<&'a Value> {
    v.get(k).filter(|x| !x.is_null())
}

pub(crate) fn req<'a>(v: &'a Value, k: &str) -> R<&'a Value> {
    match v {
        Value::Object(m) => m.get(k).ok_or_else(|| LayoutError::Chave(k.to_string())),
        other => Err(tipo(format!("indices de lista devem ser inteiros ou fatias, nao str ({})", pyfmt::tipo(other)))),
    }
}

pub(crate) fn truthy(v: Option<&Value>) -> bool {
    v.map(pyfmt::verdadeiro).unwrap_or(false)
}

/// `d.get(k, padrao)` convertido com `str()`.
pub(crate) fn str_or(v: &Value, k: &str, padrao: &str) -> String {
    match get(v, k) {
        Some(x) => pyfmt::str_de(x),
        None => padrao.to_string(),
    }
}

pub(crate) fn int_of(v: &Value) -> R<i64> {
    pyfmt::int(v).map_err(val)
}

pub(crate) fn lista(v: Option<&Value>) -> &[Value] {
    match v {
        Some(Value::Array(a)) => a,
        _ => &[],
    }
}

/// `_t`: `[id, classe, rotulo?]` -> (id, classe, rotulo).
pub(crate) fn t_de(t: &Value) -> R<(String, String, String)> {
    let a = t
        .as_array()
        .ok_or_else(|| tipo(format!("simbolo invalido: {}", pyfmt::repr(t))))?;
    if a.len() < 2 {
        return Err(val(format!("simbolo invalido: {}", pyfmt::repr(t))));
    }
    Ok((
        pyfmt::str_de(&a[0]),
        pyfmt::str_de(&a[1]),
        if a.len() > 2 { pyfmt::str_de(&a[2]) } else { String::new() },
    ))
}

// ------------------------------------------------------------------ spec baixa

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Rail {
    pub nome: String,
    pub y: i64,
    pub x0: i64,
    pub x1: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Simbolo {
    pub classe: String,
    pub x: i64,
    pub y: i64,
    pub rotulo: String,
    pub id: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Conexao {
    pub de: (String, String),
    pub para: (String, String),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Fio {
    pub x1: i64,
    pub y1: i64,
    pub x2: i64,
    pub y2: i64,
}

/// Spec baixa em construcao (`Layout` do Python); tambem e o resultado de [`compilar`].
#[derive(Debug, Clone)]
pub struct Layout {
    pub titulo: String,
    pub rails: Vec<Rail>,
    pub simbolos: Vec<Simbolo>,
    pub conexoes: Vec<Conexao>,
    pub fios: Vec<Fio>,
    ids: HashSet<String>,
}

pub type Low = Layout;

impl Layout {
    pub fn new(titulo: String) -> Layout {
        Layout { titulo, rails: vec![], simbolos: vec![], conexoes: vec![], fios: vec![], ids: HashSet::new() }
    }

    pub(crate) fn sym(&mut self, id: &str, classe: &str, rotulo: &str, x: i64, y: i64) -> R<()> {
        if !self.ids.insert(id.to_string()) {
            return Err(val(format!("id duplicado: {}", id)));
        }
        self.simbolos.push(Simbolo {
            classe: classe.to_string(),
            x,
            y,
            rotulo: rotulo.to_string(),
            id: id.to_string(),
        });
        Ok(())
    }

    pub(crate) fn con<A, B, C, D>(&mut self, de: (A, B), para: (C, D))
    where
        A: AsRef<str>,
        B: AsRef<str>,
        C: AsRef<str>,
        D: AsRef<str>,
    {
        self.conexoes.push(Conexao {
            de: (de.0.as_ref().to_string(), de.1.as_ref().to_string()),
            para: (para.0.as_ref().to_string(), para.1.as_ref().to_string()),
        });
    }

    /// Segmento reto manual (ignora comprimento zero e duplicatas, inclusive invertidas).
    pub(crate) fn fio(&mut self, x1: i64, y1: i64, x2: i64, y2: i64) {
        if (x1, y1) == (x2, y2) {
            return;
        }
        let f = Fio { x1, y1, x2, y2 };
        let inv = Fio { x1: x2, y1: y2, x2: x1, y2: y1 };
        if !self.fios.contains(&f) && !self.fios.contains(&inv) {
            self.fios.push(f);
        }
    }

    /// JSON da spec baixa na mesma ordem de chaves do Python.
    pub fn to_value(&self) -> Value {
        let mut m = Map::new();
        m.insert("titulo".into(), json!(self.titulo));
        m.insert(
            "rails".into(),
            Value::Array(
                self.rails
                    .iter()
                    .map(|r| json!({"nome": r.nome, "y": r.y, "x0": r.x0, "x1": r.x1}))
                    .collect(),
            ),
        );
        m.insert(
            "simbolos".into(),
            Value::Array(
                self.simbolos
                    .iter()
                    .map(|s| json!({"classe": s.classe, "x": s.x, "y": s.y, "rotulo": s.rotulo, "id": s.id}))
                    .collect(),
            ),
        );
        m.insert(
            "conexoes".into(),
            Value::Array(
                self.conexoes
                    .iter()
                    .map(|c| json!({"de": [c.de.0, c.de.1], "para": [c.para.0, c.para.1]}))
                    .collect(),
            ),
        );
        if !self.fios.is_empty() {
            m.insert(
                "fios".into(),
                Value::Array(
                    self.fios
                        .iter()
                        .map(|f| json!({"x1": f.x1, "y1": f.y1, "x2": f.x2, "y2": f.y2}))
                        .collect(),
                ),
            );
        }
        Value::Object(m)
    }
}

/// `json.dumps(valor, indent=1, ensure_ascii=False)` (formato dos goldens `.spec.json`).
pub fn json_indent1(v: &Value) -> String {
    use serde::Serialize;
    let mut buf = Vec::new();
    let fmt = serde_json::ser::PrettyFormatter::with_indent(b" ");
    let mut ser = serde_json::Serializer::with_formatter(&mut buf, fmt);
    v.serialize(&mut ser).expect("serializar JSON");
    String::from_utf8(buf).expect("utf-8")
}

// ------------------------------------------------------------------ compilar

pub(crate) fn eh_rede(blk: &Value) -> bool {
    ["rede", "rungs", "degraus"].iter().any(|k| blk.get(*k).is_some())
}

/// `_legado_para_rede`: bloco `{serie, ramos}` -> bloco com `rede` equivalente.
fn legado_para_rede(blk: &Value) -> Value {
    let copia = |v: &Value| v.clone();
    let ser: Vec<Value> = lista(blk.get("serie")).iter().map(copia).collect();
    let mut ramos: Vec<Value> = Vec::new();
    for r in lista(blk.get("ramos")) {
        let mut s: Vec<Value> = Vec::new();
        let via = get(r, "via");
        let selo = get(r, "selo");
        if truthy(via) && truthy(selo) {
            s.push(json!({"paralelo": [via.unwrap().clone(), selo.unwrap().clone()]}));
        } else if truthy(via) {
            s.push(via.unwrap().clone());
        }
        s.extend(lista(r.get("serie")).iter().map(copia));
        let carga = r.get("carga").cloned().unwrap_or(Value::Null);
        if truthy(r.get("indica")) {
            s.push(json!({"paralelo": [carga, r.get("indica").unwrap().clone()]}));
        } else {
            s.push(carga);
        }
        ramos.push(json!({"serie": s}));
    }
    let cauda: Vec<Value> = if ramos.is_empty() {
        vec![]
    } else if ramos.len() == 1 {
        vec![ramos.remove(0)]
    } else {
        vec![json!({"paralelo": ramos})]
    };
    let mut novo = Map::new();
    if let Some(m) = blk.as_object() {
        for (k, v) in m {
            if k != "serie" && k != "ramos" {
                novo.insert(k.clone(), v.clone());
            }
        }
    }
    let mut rede: Vec<Value> = ser;
    rede.extend(cauda);
    novo.insert("rede".into(), json!({"serie": rede}));
    Value::Object(novo)
}

/// Compila a spec topologica na spec baixa. Se a forma legada nao couber na folha, traduz os
/// blocos legados para `rede` (que quebra em colunas/faixas) em vez de falhar.
pub fn compilar(spec: &Value) -> R<Low> {
    match compilar_interno(spec) {
        Ok(l) => Ok(l),
        Err(e @ LayoutError::Valor(_)) => {
            let comando = lista(spec.get("comando"));
            let legados: Vec<usize> =
                comando.iter().enumerate().filter(|(_, b)| !eh_rede(b)).map(|(i, _)| i).collect();
            if legados.is_empty() {
                return Err(e);
            }
            let mut alt = spec.clone();
            let novos: Vec<Value> = comando
                .iter()
                .enumerate()
                .map(|(i, b)| if legados.contains(&i) { legado_para_rede(b) } else { b.clone() })
                .collect();
            alt.as_object_mut().expect("spec objeto").insert("comando".into(), Value::Array(novos));
            match compilar_interno(&alt) {
                Ok(l) => Ok(l),
                Err(LayoutError::Valor(_)) => Err(e),
                Err(outro) => Err(outro),
            }
        }
        Err(e) => Err(e),
    }
}

fn compilar_interno(spec: &Value) -> R<Low> {
    let (sheet_x, sheet_y) = dados::folha();
    let titulo = match get(spec, "titulo") {
        Some(t) => pyfmt::str_de(t),
        None => "NOVO".to_string(),
    };
    let tr = req(spec, "trilhos")?
        .as_object()
        .ok_or_else(|| tipo("'trilhos' deve ser um objeto".into()))?;
    let x0 = match tr.get("x0") {
        Some(v) => int_of(v)?,
        None => 25,
    };
    let x1 = match tr.get("x1") {
        Some(v) => int_of(v)?,
        None => 395,
    };
    let mut rails: Vec<(String, i64)> = Vec::new();
    for (k, v) in tr {
        if k == "x0" || k == "x1" {
            continue;
        }
        rails.push((k.clone(), int_of(v)?));
    }
    let mut m = ctx::Motor::new(Layout::new(titulo), &rails, x0, x1, Env { sheet_x, sheet_y, roww: None });
    // trilhos de cima (fases) = metade superior; de baixo (N, PE) = metade inferior.
    let ys: Vec<i64> = rails.iter().map(|r| r.1).collect();
    if ys.is_empty() {
        return Err(val("min() iterable argument is empty".into()));
    }
    let (mn, mx) = (*ys.iter().min().unwrap(), *ys.iter().max().unwrap());
    let meio2 = mn + mx;
    let y_cima = ys.iter().copied().filter(|v| 2 * v <= meio2).max().unwrap_or(mn);
    let top0 = y_cima + 14;
    m.top0 = top0;
    let blocos = lista(spec.get("comando"));
    let tc = get(spec, "trilhos_comando").filter(|v| pyfmt::verdadeiro(v));
    // largura util da faixa 0 para a rede
    let mut est = x0 + 5;
    let fontes = lista(spec.get("fontes"));
    if !fontes.is_empty() {
        let mut ws = vec![0];
        for f in fontes {
            let padrao = if truthy(f.get("pinos")) { "3007" } else { "3004" };
            ws.push(width(&str_or(f, "classe", padrao)));
        }
        est += ws.into_iter().max().unwrap() + 15;
    }
    if let Some(tc) = tc {
        est += (if truthy(tc.get("transformador")) { 15 + 12 } else { 0 })
            + (if truthy(tc.get("fonte")) { 12 } else { 0 })
            + 15;
    }
    let mut reserva_pot = 0;
    for pw in lista(spec.get("potencia")) {
        reserva_pot += potencia::largura(pw)? + GAP;
    }
    let util = sheet_x - rede::MARGEM_X - 40 - reserva_pot - est - rede::SPINE_L - rede::SPINE_R;
    m.env.roww = if util >= 120 { Some(util) } else { None };
    m.preparar_comando(blocos, tc)?;
    // y_baixo (so a forma legada usa)
    let nomes_para = |so_legado: bool| -> Vec<String> {
        blocos
            .iter()
            .filter(|b| !so_legado || !eh_rede(b))
            .filter_map(|b| b.get("para").map(pyfmt::str_de))
            .filter(|p| m.tem_trilho(p))
            .collect()
    };
    let mut para = nomes_para(true);
    if para.is_empty() {
        para = nomes_para(false);
    }
    let y_baixo = if !para.is_empty() {
        m.y_de(&para[0])
    } else {
        let baixo: Vec<i64> = m.rails_y().into_iter().filter(|v| 2 * v > meio2).collect();
        if let Some(b) = baixo.iter().min() {
            *b
        } else {
            m.rails_y().into_iter().max().unwrap()
        }
    };

    let mut cursor = x0 + 5;

    // ---- fontes: coladas aos trilhos, em escada na faixa da esquerda ----
    let mut fx_max = cursor;
    for f in fontes {
        if truthy(f.get("pinos")) {
            let cl = str_or(f, "classe", "3007");
            let id = pyfmt::str_de(req(f, "id")?);
            m.l.sym(&id, &cl, &str_or(f, "rotulo", "-X"), cursor, top0)?;
            if let Some(Value::Object(p)) = f.get("pinos") {
                for (pino, trilho) in p {
                    m.l.con((id.as_str(), pino.as_str()), (pyfmt::str_de(trilho), "rail"));
                }
            }
            fx_max = fx_max.max(cursor + width(&cl));
            continue;
        }
        let fases: Vec<String> = lista(f.get("fases")).iter().map(pyfmt::str_de).collect();
        let fid = pyfmt::str_de(req(f, "id")?);
        for (i, fase) in fases.iter().enumerate() {
            let mut sid = if fases.len() == 1 { fid.clone() } else { format!("{}_{}", fid, fase) };
            if fases.len() > 1 && fid.chars().last().map(|c| c.is_ascii_digit()).unwrap_or(false) {
                let mut cs = fid.chars();
                cs.next_back();
                sid = format!("{}{}", cs.as_str(), i + 1);
            }
            let x = cursor + 8 * i as i64;
            let y = top0 + 8 * i as i64;
            let cl = str_or(f, "classe", "3004");
            m.l.sym(&sid, &cl, &str_or(f, "rotulo", "-X"), x, y)?;
            m.l.con((sid.as_str(), "A"), (fase.as_str(), "rail"));
            m.l.con((sid.as_str(), "B"), (str_or(f, "neutro", "N"), "rail"));
            fx_max = fx_max.max(x + width(&cl));
        }
    }
    if !fontes.is_empty() {
        cursor = fx_max + 15;
    }

    // ---- fonte/transformador do par de trilhos de comando ----
    if let Some(tc) = tc {
        cursor = m.fonte_comando(tc, cursor, top0)? + 15;
    }

    // ---- comando ----
    let reserva = reserva_pot;
    for (i, blk) in blocos.iter().enumerate() {
        if eh_rede(blk) {
            cursor = m.comando_rede(i, blk, cursor, reserva)? + 40;
        } else {
            cursor = comando::comando(&mut m.l, blk, cursor, top0, y_baixo)? + 40;
        }
    }

    // ---- potencia: grupos de N colunas por fase, alinhados ----
    for pw in lista(spec.get("potencia")) {
        cursor = potencia::potencia(&mut m.l, pw, cursor, top0)? + GAP;
    }

    // ---- terra ----
    if let Some(t) = get(spec, "terra").filter(|v| pyfmt::verdadeiro(v)) {
        let cl = str_or(t, "classe", "3002");
        let (_, h) = dim(&cl);
        let neutro = str_or(t, "neutro", "N");
        let ny = m
            .rail_y(&neutro)
            .ok_or_else(|| LayoutError::Chave(neutro.clone()))?;
        let tid = str_or(t, "id", "PE");
        m.l.sym(&tid, &cl, &str_or(t, "rotulo", "TERRA"), x0 + 35, ny - h)?;
        m.l.con((tid.as_str(), "A"), (neutro.as_str(), "rail"));
    }

    m.fechar()?;
    let out = m.l;
    check_folha(&out, sheet_x, sheet_y)?;
    Ok(out)
}

/// `_check_folha`.
fn check_folha(l: &Layout, sx: i64, sy: i64) -> R<()> {
    let mut boxes: Vec<(&str, (i64, i64, i64, i64))> = Vec::new();
    for s in &l.simbolos {
        let (_, h) = dim(&s.classe);
        let w = width(&s.classe);
        let b = (s.x, s.y, s.x + w, s.y + h);
        if b.2 > sx || b.3 > sy {
            return Err(val(format!(
                "{} fora da folha: ({}, {}, {}, {}) (max {}x{})",
                s.id, b.0, b.1, b.2, b.3, sx, sy
            )));
        }
        for (o_id, o) in &boxes {
            if b.0 < o.2 && o.0 < b.2 && b.1 < o.3 && o.1 < b.3 {
                return Err(val(format!("sobreposicao: {} x {}", s.id, o_id)));
            }
        }
        boxes.push((&s.id, b));
    }
    for r in &l.rails {
        if r.y > sy || r.x1 > sx {
            return Err(val(format!(
                "trilho {} fora da folha: y={} x1={} (max {}x{})",
                r.nome, r.y, r.x1, sx, sy
            )));
        }
    }
    for f in &l.fios {
        if f.x1.max(f.x2) > sx || f.y1.max(f.y2) > sy {
            return Err(val(format!(
                "fio fora da folha: {{'x1': {}, 'y1': {}, 'x2': {}, 'y2': {}}}",
                f.x1, f.y1, f.x2, f.y2
            )));
        }
    }
    Ok(())
}

// ------------------------------------------------------------------ normalizar (build_spec)

/// Resultado de [`normalizar`].
#[derive(Debug, Clone)]
pub struct Normalizado {
    /// Spec baixa (JSON).
    pub low: Value,
    pub testes: Value,
    /// Layout topologico de origem (`None` se a entrada ja era spec baixa).
    pub layout: Option<Value>,
}

/// `build_spec.normalizar`: layout topologico OU spec baixa (com/sem a chave `layout`).
pub fn normalizar(spec: &Value) -> R<Normalizado> {
    if !spec.is_object() {
        return Err(val("a spec deve ser um objeto JSON".into()));
    }
    let mut layout_d = get(spec, "layout").cloned();
    let ou = |a: Option<&Value>, b: Option<&Value>| -> Value {
        if truthy(a) {
            a.unwrap().clone()
        } else if truthy(b) {
            b.unwrap().clone()
        } else {
            json!([])
        }
    };
    let mut testes = ou(spec.get("testes"), layout_d.as_ref().and_then(|l| l.get("testes")));
    if layout_d.is_none() && spec.get("simbolos").is_none() && spec.get("trilhos").is_some() {
        layout_d = Some(spec.clone());
        testes = ou(spec.get("testes"), None);
    }
    if let Some(ld) = layout_d {
        let mut low = compilar(&ld)?;
        if truthy(spec.get("titulo")) {
            low.titulo = pyfmt::str_de(spec.get("titulo").unwrap());
        }
        return Ok(Normalizado { low: low.to_value(), testes, layout: Some(ld) });
    }
    if spec.get("simbolos").is_none() {
        return Err(val("spec sem 'layout' (DSL topologica) nem 'simbolos' (spec baixa)".into()));
    }
    Ok(Normalizado { low: spec.clone(), testes, layout: None })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fio_ignora_duplicata_invertida() {
        let mut l = Layout::new("t".into());
        l.fio(1, 1, 5, 1);
        l.fio(5, 1, 1, 1);
        l.fio(2, 2, 2, 2);
        assert_eq!(l.fios.len(), 1);
    }

    #[test]
    fn json_indent1_como_python() {
        let v = json!({"a": [1, 2], "b": {}, "c": []});
        assert_eq!(json_indent1(&v), "{\n \"a\": [\n  1,\n  2\n ],\n \"b\": {},\n \"c\": []\n}");
    }

    #[test]
    fn width_e_dim() {
        assert!(width("2001") >= dim("2001").0);
        assert_eq!(dim("classe_inexistente"), FALLBACK_DIM);
    }

    #[test]
    fn spec_sem_nada_da_erro() {
        let e = normalizar(&json!({"foo": 1})).unwrap_err();
        assert!(e.to_string().contains("spec sem 'layout'"));
    }
}
