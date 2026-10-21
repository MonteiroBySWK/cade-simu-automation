//! Rede serie-paralelo recursiva (comando v2): arvore, medidas, posicionamento e desenho das redes
//! eletricas. Port literal de `tools/layout.py` (secao "Rede serie-paralelo RECURSIVA").

use crate::{dim, pin_off, t_de, val, Layout, R};
use cade_model::dados;
use cade_model::pyfmt::{self, fdiv};
use serde_json::Value;
use std::collections::{BTreeSet, HashMap};

pub const GN: i64 = 10;
pub const RUNG_GAP: i64 = 30;
pub const CHUNK_GAP: i64 = 44;
pub const MARGEM_X: i64 = 12;
pub const SPINE_L: i64 = 8;
pub const SPINE_R: i64 = 14;
pub const ROWGAP: i64 = 10;
pub const GRADE: i64 = 6;
pub const GAP: i64 = 20;

/// Constantes dependentes da folha / estimativa de largura (`SHEET_X`, `_ROWW`).
#[derive(Debug, Clone, Copy)]
pub struct Env {
    pub sheet_x: i64,
    pub sheet_y: i64,
    /// `_ROWW[0]` ja resolvido: `util` se >= 120, senao `None`.
    pub roww: Option<i64>,
}

impl Env {
    /// `_rowmax()`.
    pub fn rowmax(&self) -> i64 {
        let cheia = self.sheet_x - MARGEM_X - 14 - 30 - SPINE_L - SPINE_R;
        self.roww.unwrap_or(cheia)
    }
}

#[derive(Debug, Clone)]
pub struct Leaf {
    pub sid: String,
    pub cl: String,
    pub rot: String,
    pub pa: (i64, i64),
    pub pb: (i64, i64),
    pub na: String,
    pub nb: String,
    pub w: i64,
    pub h: i64,
}

#[derive(Debug, Clone)]
pub enum No {
    Leaf(Leaf),
    Serie(Vec<No>),
    Par(Vec<No>),
}

/// `_folha`.
fn folha(t: &Value) -> R<No> {
    let (sid, cl, rot) = t_de(t)?;
    let info = dados::symbol_pins().get(&cl).ok_or_else(|| {
        val(format!("{}: classe {} sem geometria de pinos (tools/symbol_pins.json)", sid, cl))
    })?;
    let nomeados = &info.pins;
    let (na, nb, pa, pb);
    if !nomeados.is_empty() {
        let chaves: BTreeSet<&str> = nomeados.keys().map(|s| s.as_str()).collect();
        let so_p: BTreeSet<&str> = ["p1", "p2"].into_iter().collect();
        let permitidas: BTreeSet<&str> = ["A", "B", "p1", "p2"].into_iter().collect();
        if chaves == so_p {
            na = "p1";
            nb = "p2";
        } else if chaves.is_subset(&permitidas) && chaves.contains("A") && chaves.contains("B") {
            na = "A";
            nb = "B";
        } else {
            let nomes: Vec<&str> = chaves.iter().copied().collect();
            return Err(val(format!(
                "{} (classe {}) tem {} terminais ({}); a rede de comando aceita so simbolos de 2 terminais (A/B)",
                sid,
                cl,
                nomeados.len(),
                pyfmt::repr_lista(&nomes)
            )));
        }
        pa = nomeados[na];
        pb = nomeados[nb];
    } else if let (Some(a), Some(b)) = (info.a, info.b) {
        na = "A";
        nb = "B";
        pa = a;
        pb = b;
    } else {
        return Err(val(format!("{} (classe {}) sem terminais A/B conhecidos", sid, cl)));
    }
    if pb[1] <= pa[1] {
        return Err(val(format!(
            "{} (classe {}): terminais na mesma altura (A=[{}, {}], B=[{}, {}]); a rede de comando precisa de \
             simbolo vertical (A em cima, B embaixo)",
            sid, cl, pa[0], pa[1], pb[0], pb[1]
        )));
    }
    let (w, h) = dim(&cl);
    Ok(No::Leaf(Leaf {
        sid,
        cl,
        rot,
        pa: (pa[0], pa[1]),
        pb: (pb[0], pb[1]),
        na: na.to_string(),
        nb: nb.to_string(),
        w,
        h,
    }))
}

/// `_expr`: JSON -> arvore.
pub fn expr(e: &Value) -> R<No> {
    match e {
        Value::Object(m) => {
            let chaves: Vec<&str> = ["serie", "paralelo"].into_iter().filter(|k| m.contains_key(*k)).collect();
            if chaves.len() != 1 || m.keys().any(|k| k != "serie" && k != "paralelo") {
                return Err(val(format!(
                    "expressao invalida {}: use exatamente uma chave 'serie' ou 'paralelo'",
                    pyfmt::repr(e)
                )));
            }
            let serie = chaves[0] == "serie";
            let itens = match &m[chaves[0]] {
                Value::Array(a) if !a.is_empty() => a,
                _ => return Err(val(format!("'{}' precisa de uma lista nao vazia", chaves[0]))),
            };
            let mut kids: Vec<No> = Vec::new();
            for it in itens {
                let k = expr(it)?;
                match (k, serie) {
                    (No::Serie(ks), true) => kids.extend(ks),
                    (No::Par(ks), false) => kids.extend(ks),
                    (k, _) => kids.push(k),
                }
            }
            if kids.len() == 1 {
                Ok(kids.remove(0))
            } else if serie {
                Ok(No::Serie(kids))
            } else {
                Ok(No::Par(kids))
            }
        }
        Value::Array(a) => {
            if (2..=3).contains(&a.len()) && a.iter().all(|v| v.is_string()) {
                folha(e)
            } else {
                let mut m = serde_json::Map::new();
                m.insert("serie".into(), Value::Array(a.clone()));
                expr(&Value::Object(m))
            }
        }
        other => Err(val(format!("expressao invalida: {}", pyfmt::repr(other)))),
    }
}

/// Resultado de `_par_layout`.
pub struct ParLay {
    pub ms: Vec<(i64, i64, i64)>,
    pub offs: Vec<i64>,
    pub center: i64,
    pub total: i64,
}

fn par_layout(kids: &[No], env: &Env) -> ParLay {
    let ms: Vec<(i64, i64, i64)> = kids.iter().map(|k| med(k, env)).collect();
    let mut offs = Vec::new();
    let mut pos = 0;
    for &(lw, rw, _h) in &ms {
        offs.push(pos + lw);
        pos += -fdiv(-(lw + rw + GAP), GRADE) * GRADE;
    }
    let total = pos - GAP;
    let center = (offs[0] + offs[offs.len() - 1]).div_euclid(2);
    ParLay { ms, offs, center, total }
}

/// `_par_rows`: faixas contiguas `[ini, fim)` de ramos.
fn par_rows(kids: &[No], env: &Env) -> Vec<(usize, usize)> {
    let mut rows = Vec::new();
    let mut ini = 0;
    for i in 0..kids.len() {
        if i > ini && par_layout(&kids[ini..=i], env).total > env.rowmax() {
            rows.push((ini, i));
            ini = i;
        }
    }
    rows.push((ini, kids.len()));
    rows
}

pub struct ParInfo {
    pub rows: Vec<(usize, usize)>,
    pub lays: Vec<ParLay>,
    pub lw: i64,
    pub rw: i64,
    pub h: i64,
}

pub fn par_info(kids: &[No], env: &Env) -> ParInfo {
    let rows = par_rows(kids, env);
    let lays: Vec<ParLay> = rows.iter().map(|&(a, b)| par_layout(&kids[a..b], env)).collect();
    let hs: Vec<i64> = lays.iter().map(|l| l.ms.iter().map(|m| m.2).max().unwrap()).collect();
    if rows.len() == 1 {
        let (center, total) = (lays[0].center, lays[0].total);
        return ParInfo { rows, lays, lw: center, rw: total - center, h: hs[0] };
    }
    let wmax = lays.iter().map(|l| l.total).max().unwrap();
    let axis = lays[0].center;
    let h = hs.iter().sum::<i64>() + ROWGAP * (rows.len() as i64 - 1);
    ParInfo { rows, lays, lw: axis + SPINE_L, rw: wmax - axis + SPINE_R, h }
}

/// `_med`: (lw, rw, H).
pub fn med(no: &No, env: &Env) -> (i64, i64, i64) {
    match no {
        No::Leaf(l) => {
            let xs = [0, l.w, l.pa.0, l.pb.0];
            let mn = *xs.iter().min().unwrap();
            let mx = *xs.iter().max().unwrap();
            (l.pa.0 - mn, mx - l.pa.0, GN + (l.h - l.pa.1).max(l.pb.1 - l.pa.1) + GN)
        }
        No::Serie(kids) => {
            let ms: Vec<_> = kids.iter().map(|k| med(k, env)).collect();
            (
                ms.iter().map(|m| m.0).max().unwrap(),
                ms.iter().map(|m| m.1).max().unwrap(),
                ms.iter().map(|m| m.2).sum(),
            )
        }
        No::Par(kids) => {
            let pi = par_info(kids, env);
            (pi.lw, pi.rw, pi.h)
        }
    }
}

fn primeira(no: &No) -> &Leaf {
    match no {
        No::Leaf(l) => l,
        No::Serie(k) | No::Par(k) => primeira(&k[0]),
    }
}

fn ultima(no: &No) -> &Leaf {
    match no {
        No::Leaf(l) => l,
        No::Serie(k) | No::Par(k) => ultima(&k[k.len() - 1]),
    }
}

pub fn folhas<'a>(no: &'a No, out: &mut Vec<&'a Leaf>) {
    match no {
        No::Leaf(l) => out.push(l),
        No::Serie(k) | No::Par(k) => k.iter().for_each(|x| folhas(x, out)),
    }
}

#[derive(Clone, PartialEq, Eq, Hash, Debug)]
enum Tok {
    P(String, char),
    N(usize),
    R(&'static str),
}

impl Tok {
    /// `str(tupla)` do Python (usado como chave de ordenacao).
    fn py_str(&self) -> String {
        match self {
            Tok::P(s, ab) => format!("('p', {}, '{}')", pyfmt::repr_str(s), ab),
            Tok::N(n) => format!("('n', {})", n),
            Tok::R(n) => format!("('r', '{}')", n),
        }
    }
}

/// `_UF` com ordem de insercao preservada (`list(uf.p)`).
#[derive(Default)]
struct Uf {
    idx: HashMap<Tok, usize>,
    toks: Vec<Tok>,
    pai: Vec<usize>,
}

impl Uf {
    fn id(&mut self, t: &Tok) -> usize {
        if let Some(&i) = self.idx.get(t) {
            return i;
        }
        let i = self.toks.len();
        self.toks.push(t.clone());
        self.pai.push(i);
        self.idx.insert(t.clone(), i);
        i
    }
    fn find(&mut self, t: &Tok) -> usize {
        let mut a = self.id(t);
        while self.pai[a] != a {
            self.pai[a] = self.pai[self.pai[a]];
            a = self.pai[a];
        }
        a
    }
    fn union(&mut self, a: &Tok, b: &Tok) {
        let ra = self.find(a);
        let rb = self.find(b);
        if ra != rb {
            self.pai[rb] = ra;
        }
    }
    fn raiz_de(&mut self, i: usize) -> usize {
        let mut a = i;
        while self.pai[a] != a {
            self.pai[a] = self.pai[self.pai[a]];
            a = self.pai[a];
        }
        a
    }
}

fn walk(no: &No, i: &Tok, o: &Tok, uf: &mut Uf, fresh: &mut usize) {
    match no {
        No::Leaf(l) => {
            uf.union(&Tok::P(l.sid.clone(), 'A'), i);
            uf.union(&Tok::P(l.sid.clone(), 'B'), o);
        }
        No::Serie(kids) => {
            let mut toks = vec![i.clone()];
            for _ in 0..kids.len() - 1 {
                toks.push(Tok::N(*fresh));
                *fresh += 1;
            }
            toks.push(o.clone());
            for (k, kid) in kids.iter().enumerate() {
                walk(kid, &toks[k], &toks[k + 1], uf, fresh);
            }
        }
        No::Par(kids) => {
            for kid in kids {
                walk(kid, i, o, uf, fresh);
            }
        }
    }
}

/// `pp[(id, 'A'|'B')] = (x, y, nivel, coluna)`.
type PP = (i64, i64, i64, usize);

#[derive(Default)]
struct Pp {
    pins: HashMap<(String, char), PP>,
    /// `pp["__sp"]`: (`in`/`out`, x, ref)
    sp: Vec<(&'static str, i64, (String, char))>,
}

fn colocar(l: &mut Layout, no: &No, ax: i64, yi: i64, yo: i64, pp: &mut Pp, ch: usize, env: &Env) -> R<()> {
    match no {
        No::Leaf(f) => {
            let x = ax - f.pa.0;
            let y = yi + GN - f.pa.1;
            l.sym(&f.sid, &f.cl, &f.rot, x, y)?;
            pp.pins.insert((f.sid.clone(), 'A'), (ax, yi + GN, yi, ch));
            pp.pins.insert((f.sid.clone(), 'B'), (x + f.pb.0, y + f.pb.1, yo, ch));
        }
        No::Serie(kids) => {
            let mut cur = yi;
            for (i, k) in kids.iter().enumerate() {
                let ko = if i == kids.len() - 1 { yo } else { cur + med(k, env).2 };
                colocar(l, k, ax, cur, ko, pp, ch, env)?;
                cur = ko;
            }
        }
        No::Par(kids) => {
            let pi = par_info(kids, env);
            if pi.rows.len() == 1 {
                let left = ax - pi.lays[0].center;
                let offs = pi.lays[0].offs.clone();
                for (k, off) in kids.iter().zip(offs) {
                    colocar(l, k, left + off, yi, yo, pp, ch, env)?;
                }
                return Ok(());
            }
            let left0 = ax - pi.lays[0].center;
            let wmax = pi.lays.iter().map(|x| x.total).max().unwrap();
            let mut yr = yi;
            for (r, (&(a, b), lay)) in pi.rows.iter().zip(pi.lays.iter()).enumerate() {
                let ult = r == pi.rows.len() - 1;
                let yo_r = if ult { yo } else { yr + lay.ms.iter().map(|m| m.2).max().unwrap() };
                for (k, off) in kids[a..b].iter().zip(lay.offs.iter()) {
                    colocar(l, k, left0 + off, yr, yo_r, pp, ch, env)?;
                }
                yr = yo_r + ROWGAP;
            }
            let (a0, b0) = pi.rows[0];
            pp.sp.push(("in", left0 - SPINE_L, (primeira(&kids[a0]).sid.clone(), 'A')));
            pp.sp.push(("out", left0 + wmax + SPINE_R, (ultima(&kids[b0 - 1]).sid.clone(), 'B')));
        }
    }
    Ok(())
}

/// `_conexo`: todos os `pts` no mesmo componente formado por `segs`?
fn conexo(segs: &[((i64, i64), (i64, i64))], pts: &[(i64, i64)]) -> bool {
    let mut idx: HashMap<(i64, i64), usize> = HashMap::new();
    let mut pai: Vec<usize> = Vec::new();
    let id = |p: (i64, i64), idx: &mut HashMap<(i64, i64), usize>, pai: &mut Vec<usize>| -> usize {
        *idx.entry(p).or_insert_with(|| {
            pai.push(pai.len());
            pai.len() - 1
        })
    };
    fn find(pai: &mut [usize], mut a: usize) -> usize {
        while pai[a] != a {
            pai[a] = pai[pai[a]];
            a = pai[a];
        }
        a
    }
    for &(a, b) in segs {
        let (ia, ib) = (id(a, &mut idx, &mut pai), id(b, &mut idx, &mut pai));
        let (ra, rb) = (find(&mut pai, ia), find(&mut pai, ib));
        if ra != rb {
            pai[rb] = ra;
        }
    }
    let mut raizes = BTreeSet::new();
    for &p in pts {
        let i = id(p, &mut idx, &mut pai);
        raizes.insert(find(&mut pai, i));
    }
    raizes.len() == 1
}

fn redes(
    l: &mut Layout,
    uf: &mut Uf,
    pp: &Pp,
    nomes: &HashMap<&'static str, String>,
    bordas: &[i64],
    folhas: &HashMap<String, Leaf>,
) -> R<()> {
    let mut grupos: HashMap<usize, Vec<Tok>> = HashMap::new();
    let todos: Vec<Tok> = uf.toks.clone();
    for t in &todos {
        let i = uf.id(t);
        let r = uf.raiz_de(i);
        grupos.entry(r).or_default().push(t.clone());
    }
    let mut raizes: Vec<usize> = grupos.keys().copied().collect();
    raizes.sort_by_key(|&r| uf.toks[r].py_str());
    for root in raizes {
        let toks = &grupos[&root];
        let mut trilhos: Vec<&'static str> = toks
            .iter()
            .filter_map(|t| if let Tok::R(n) = t { Some(*n) } else { None })
            .collect();
        trilhos.sort();
        trilhos.dedup();
        let pins: Vec<(String, char)> = toks
            .iter()
            .filter_map(|t| if let Tok::P(s, ab) = t { Some((s.clone(), *ab)) } else { None })
            .collect();
        let sps: Vec<(&str, i64)> = pp
            .sp
            .iter()
            .filter(|(_, _, r)| pins.contains(r))
            .map(|(k, x, _)| (*k, *x))
            .collect();
        if trilhos.len() > 1 {
            return Err(val("degrau em curto: os trilhos 'de' e 'para' ficaram no mesmo no".into()));
        }
        let mut segs: Vec<((i64, i64), (i64, i64))> = Vec::new();
        let mut seg = |l: &mut Layout, x1: i64, y1: i64, x2: i64, y2: i64| {
            if (x1, y1) != (x2, y2) {
                l.fio(x1, y1, x2, y2);
                segs.push(((x1, y1), (x2, y2)));
            }
        };
        if !trilhos.is_empty() {
            let lado_a = trilhos[0] == "de";
            let mut ord = pins.clone();
            ord.sort();
            let dados: Vec<(String, PP)> = ord.iter().map(|(s, ab)| (s.clone(), pp.pins[&(s.clone(), *ab)])).collect();
            let niveis: BTreeSet<i64> = dados.iter().map(|d| d.1 .2).collect();
            let nome_trilho = nomes[trilhos[0]].clone();
            if niveis.len() == 1 {
                for (sid, ab) in &ord {
                    let f = &folhas[sid];
                    l.con((sid, if *ab == 'A' { &f.na } else { &f.nb }), (&nome_trilho, "rail"));
                }
                continue;
            }
            let term = if lado_a { *niveis.iter().next().unwrap() } else { *niveis.iter().next_back().unwrap() };
            let kind = if lado_a { "in" } else { "out" };
            let xs_sp: Vec<i64> = sps.iter().filter(|(k, _)| *k == kind).map(|(_, x)| *x).collect();
            if xs_sp.is_empty() {
                return Err(val("no do trilho em varios niveis sem espinha (bug do motor)".into()));
            }
            let xsp = xs_sp[0];
            let termpins: Vec<&(String, PP)> = dados.iter().filter(|(_, q)| q.2 == term).collect();
            for (s, _) in &termpins {
                let f = &folhas[s];
                l.con((s, if lado_a { &f.na } else { &f.nb }), (&nome_trilho, "rail"));
            }
            // min/max com desempate pelo primeiro (como o Python)
            let mut refq = termpins[0].1;
            for (_, q) in termpins.iter().skip(1) {
                if (lado_a && q.0 < refq.0) || (!lado_a && q.0 > refq.0) {
                    refq = *q;
                }
            }
            let ye = if lado_a { refq.1 - 7 } else { refq.1 + 7 };
            let outros: BTreeSet<i64> = dados.iter().map(|(_, q)| q.2).filter(|&n| n != term).collect();
            for &lv in &outros {
                let ps: Vec<PP> = dados.iter().map(|(_, q)| *q).filter(|q| q.2 == lv).collect();
                let mut xs: BTreeSet<i64> = ps.iter().map(|q| q.0).collect();
                xs.insert(xsp);
                let xs: Vec<i64> = xs.into_iter().collect();
                for w in xs.windows(2) {
                    seg(l, w[0], lv, w[1], lv);
                }
                for q in &ps {
                    seg(l, q.0, q.1, q.0, lv);
                }
            }
            let mut ys: BTreeSet<i64> = outros.clone();
            ys.insert(ye);
            let ys: Vec<i64> = ys.into_iter().collect();
            for w in ys.windows(2) {
                seg(l, xsp, w[0], xsp, w[1]);
            }
            seg(l, xsp, ye, refq.0, ye);
            continue;
        }
        let ups: Vec<PP> = pins.iter().filter(|(_, ab)| *ab == 'B').map(|(s, ab)| pp.pins[&(s.clone(), *ab)]).collect();
        let lows: Vec<PP> = pins.iter().filter(|(_, ab)| *ab == 'A').map(|(s, ab)| pp.pins[&(s.clone(), *ab)]).collect();
        if ups.is_empty() || lows.is_empty() {
            return Err(val("no sem origem ou sem destino na rede (expressao incompleta)".into()));
        }
        let lb: BTreeSet<i64> = ups.iter().map(|u| u.2).collect();
        let la: BTreeSet<i64> = lows.iter().map(|d| d.2).collect();
        if sps.is_empty() && lb.len() == 1 && la.len() == 1 {
            let lb = *lb.iter().next().unwrap();
            let la = *la.iter().next().unwrap();
            if la == lb {
                if ups.len() == 1 && lows.len() == 1 && ups[0].0 == lows[0].0 {
                    l.fio(ups[0].0, ups[0].1, lows[0].0, lows[0].1);
                    continue;
                }
                let xs: BTreeSet<i64> = ups.iter().chain(lows.iter()).map(|p| p.0).collect();
                let xs: Vec<i64> = xs.into_iter().collect();
                for w in xs.windows(2) {
                    l.fio(w[0], lb, w[1], lb);
                }
                for u in &ups {
                    l.fio(u.0, u.1, u.0, lb);
                }
                for d in &lows {
                    l.fio(d.0, lb, d.0, d.1);
                }
            } else if la < lb {
                let xm = bordas[ups[0].3] + 18;
                let mut xu: BTreeSet<i64> = ups.iter().map(|u| u.0).collect();
                xu.insert(xm);
                let xu: Vec<i64> = xu.into_iter().collect();
                for w in xu.windows(2) {
                    l.fio(w[0], lb, w[1], lb);
                }
                for u in &ups {
                    l.fio(u.0, u.1, u.0, lb);
                }
                l.fio(xm, lb, xm, la);
                let mut xl: BTreeSet<i64> = lows.iter().map(|d| d.0).collect();
                xl.insert(xm);
                let xl: Vec<i64> = xl.into_iter().collect();
                for w in xl.windows(2) {
                    l.fio(w[0], la, w[1], la);
                }
                for d in &lows {
                    l.fio(d.0, la, d.0, d.1);
                }
            } else {
                return Err(val("nivel de entrada abaixo do de saida (rede invalida)".into()));
            }
            continue;
        }
        // varios niveis (paralelo largo em linhas): um barramento por nivel + espinhas
        let allp: Vec<PP> = ups.iter().chain(lows.iter()).copied().collect();
        let mut sp_lv: Vec<(i64, Vec<i64>)> = Vec::new();
        for (k, x) in &sps {
            let lv: BTreeSet<i64> = if *k == "out" { ups.iter().map(|u| u.2).collect() } else { lows.iter().map(|d| d.2).collect() };
            sp_lv.push((*x, lv.into_iter().collect()));
        }
        let niveis_all: BTreeSet<i64> = allp.iter().map(|q| q.2).collect();
        for &lv in &niveis_all {
            let ps: Vec<PP> = allp.iter().copied().filter(|q| q.2 == lv).collect();
            let mut xs: BTreeSet<i64> = ps.iter().map(|q| q.0).collect();
            for (x, ls) in &sp_lv {
                if ls.contains(&lv) {
                    xs.insert(*x);
                }
            }
            let xs: Vec<i64> = xs.into_iter().collect();
            for w in xs.windows(2) {
                seg(l, w[0], lv, w[1], lv);
            }
            for q in &ps {
                seg(l, q.0, q.1, q.0, lv);
            }
        }
        for (x, ls) in &sp_lv {
            for w in ls.windows(2) {
                seg(l, *x, w[0], *x, w[1]);
            }
        }
        let pts: Vec<(i64, i64)> = allp.iter().map(|q| (q.0, q.1)).collect();
        if !conexo(&segs, &pts) {
            return Err(val("rede em varios niveis ficou desconexa (bug do motor)".into()));
        }
    }
    Ok(())
}

/// `_degrau`: posiciona um degrau (1+ colunas) e desenha suas redes. -> x direito.
pub fn degrau(l: &mut Layout, chunks: &[No], x_left: i64, yi: i64, de_nome: &str, para_nome: &str, env: &Env) -> R<i64> {
    let mut uf = Uf::default();
    let mut fresh = 0usize;
    let mut toks = vec![Tok::R("de")];
    for _ in 0..chunks.len() - 1 {
        toks.push(Tok::N(fresh));
        fresh += 1;
    }
    toks.push(Tok::R("para"));
    let mut pp = Pp::default();
    let mut bordas: Vec<i64> = Vec::new();
    let mut fol: HashMap<String, Leaf> = HashMap::new();
    let mut cur = x_left;
    for (j, no) in chunks.iter().enumerate() {
        let (lw, rw, h) = med(no, env);
        walk(no, &toks[j], &toks[j + 1], &mut uf, &mut fresh);
        colocar(l, no, cur + lw, yi, yi + h, &mut pp, j, env)?;
        let mut fs = Vec::new();
        folhas(no, &mut fs);
        for f in fs {
            fol.insert(f.sid.clone(), f.clone());
        }
        cur += lw + rw;
        bordas.push(cur);
        cur += CHUNK_GAP;
    }
    let nomes: HashMap<&'static str, String> =
        [("de", de_nome.to_string()), ("para", para_nome.to_string())].into_iter().collect();
    redes(l, &mut uf, &pp, &nomes, &bordas, &fol)?;
    Ok(*bordas.last().unwrap())
}

/// `_quebrar`: serie alta demais -> colunas (serpentina).
pub fn quebrar(no: &No, hlim: i64, env: &Env) -> R<Vec<No>> {
    if med(no, env).2 <= hlim {
        return Ok(vec![no.clone()]);
    }
    let kids = match no {
        No::Serie(k) => k,
        _ => {
            return Err(val(format!(
                "grupo paralelo com altura {} > {} (limite da folha); nao ha como quebrar em colunas dentro de um paralelo",
                med(no, env).2,
                hlim
            )))
        }
    };
    let hs: Vec<i64> = kids.iter().map(|k| med(k, env).2).collect();
    for &hk in &hs {
        if hk > hlim {
            return Err(val(format!("elemento aninhado alto demais ({} > {}); simplifique a rede", hk, hlim)));
        }
    }
    let total: i64 = hs.iter().sum();
    let ncols = -fdiv(-total, hlim);
    let mut chunks: Option<Vec<Vec<No>>> = None;
    let mut cap = -fdiv(-total, ncols);
    while cap <= hlim {
        let mut cur: Vec<Vec<No>> = Vec::new();
        let mut atual: Vec<No> = Vec::new();
        let mut h = 0;
        for (k, &hk) in kids.iter().zip(&hs) {
            if !atual.is_empty() && h + hk > cap {
                cur.push(std::mem::take(&mut atual));
                h = 0;
            }
            atual.push(k.clone());
            h += hk;
        }
        cur.push(atual);
        if (cur.len() as i64) <= ncols {
            chunks = Some(cur);
            break;
        }
        cap += 5;
    }
    let chunks = match chunks {
        Some(c) => c,
        None => {
            let mut chunks: Vec<Vec<No>> = Vec::new();
            let mut atual: Vec<No> = Vec::new();
            let mut h = 0;
            for (k, &hk) in kids.iter().zip(&hs) {
                if !atual.is_empty() && h + hk > hlim {
                    chunks.push(std::mem::take(&mut atual));
                    h = 0;
                }
                atual.push(k.clone());
                h += hk;
            }
            chunks.push(atual);
            chunks
        }
    };
    Ok(chunks
        .into_iter()
        .map(|mut c| if c.len() == 1 { c.remove(0) } else { No::Serie(c) })
        .collect())
}

/// `ctx.pin_off` reexportado para `fonte_comando`.
pub fn pin_x(cl: &str, pino: &str) -> R<i64> {
    Ok(pin_off(cl, pino)?[0])
}
