//! `Circuito`: netlist por geometria + motor de relaxacao (paridade com `tools/netlist_sim.py`).
//!
//! Modelo (docs/re-engenharia.md 9 e 11): cada fonte estampa um "char de fase" por pino; elemento
//! fechado une as duas redes; duas estampas diferentes na mesma rede = CURTO; bobina/lampada/
//! temporizador energizam quando os dois pinos veem estampas diferentes (exceto PE); a logica
//! (selo, intertravamento) e relaxada ate o ponto fixo (OK / RACE / INSTAVEL).

use crate::papeis::{Cond, Fonte, Modo, ModoPolos, Papel, Papeis, TipoTemp};
use cade_check::geom::{entidades_do_cad, estampa_de_classe, num, pinos_da_classe, rotacionar, Conectividade, FONTE, SKIP};
use cade_model::{dados, latin1};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap};

/// Union-find sobre redes (ids inteiros).
#[derive(Default)]
struct Uf {
    pai: HashMap<u32, u32>,
}

impl Uf {
    fn find(&mut self, x: u32) -> u32 {
        let mut a = *self.pai.entry(x).or_insert(x);
        while self.pai[&a] != a {
            let p = self.pai[&a];
            let pp = self.pai[&p];
            self.pai.insert(a, pp);
            a = pp;
        }
        a
    }

    fn union(&mut self, a: u32, b: u32) {
        let (ra, rb) = (self.find(a), self.find(b));
        if ra != rb {
            self.pai.insert(rb, ra);
        }
    }
}

/// Entradas externas: rotulo -> estado (0/1; seletor de 3 posicoes usa 0..2).
pub type Entradas = BTreeMap<String, i64>;

/// Converte o objeto JSON dos casos (`{"S1": true}`) em [`Entradas`].
pub fn entradas_de_json(v: &Value) -> Entradas {
    let mut e = Entradas::new();
    if let Some(o) = v.as_object() {
        for (k, x) in o {
            let n = match x {
                Value::Bool(b) => *b as i64,
                Value::Number(n) => n.as_i64().unwrap_or(0),
                _ => 0,
            };
            e.insert(k.clone(), n);
        }
    }
    e
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Status {
    Ok,
    Race,
    Instavel,
    Curto,
}

impl Status {
    pub fn as_str(self) -> &'static str {
        match self {
            Status::Ok => "OK",
            Status::Race => "RACE",
            Status::Instavel => "INSTAVEL",
            Status::Curto => "CURTO",
        }
    }
}

/// Estado observavel de um temporizador.
#[derive(Clone, Debug, PartialEq)]
pub struct InfoTimer {
    pub id: String,
    pub tipo: &'static str,
    pub tempo: f64,
    pub decorrido: f64,
    pub saida: bool,
}

/// Resultado de [`Circuito::avancar`] / [`Circuito::estado`] (= `estado()` do Python + motores).
#[derive(Clone, Debug, PartialEq)]
pub struct EstadoSim {
    pub status: Status,
    pub bobinas: Vec<String>,
    pub lampadas: Vec<String>,
    pub motores: Vec<String>,
    pub temporizadores: Vec<InfoTimer>,
    pub curtos: Vec<String>,
}

impl EstadoSim {
    pub fn to_json(&self) -> Value {
        let mut tim = serde_json::Map::new();
        for t in &self.temporizadores {
            tim.insert(
                t.id.clone(),
                json!({"tipo": t.tipo, "tempo": t.tempo, "decorrido": t.decorrido, "saida": t.saida}),
            );
        }
        json!({
            "status": self.status.as_str(),
            "bobinas": self.bobinas,
            "lampadas": self.lampadas,
            "motores": self.motores,
            "temporizadores": Value::Object(tim),
            "curtos": self.curtos,
        })
    }

    pub fn temporizadores_on(&self) -> BTreeSet<String> {
        self.temporizadores.iter().filter(|t| t.saida).map(|t| t.id.clone()).collect()
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum FonteEstado {
    Rotulo,
    /// saida do temporizador de mesmo rotulo (contatos 7004..; e 7000..7003/polos sob 9007)
    PorRotulo,
    /// temporizador proprio do contato (`Papel::ContatoTemp`)
    Embutido(usize),
}

#[derive(Clone, Debug)]
struct Chave {
    chave: String,
    ligs: Vec<(u32, u32, Cond)>,
    fonte: FonteEstado,
    polos: bool,
}

#[derive(Clone, Debug)]
struct Timer {
    id: String,
    chave: String,
    tipo: TipoTemp,
    tempo: f64,
}

#[derive(Clone, Debug)]
struct Motor {
    chave: String,
    fases: Vec<u32>,
}

/// Estado persistente entre passos (bobinas, saidas e tempo decorrido dos temporizadores).
#[derive(Clone, Debug)]
pub struct Persistente {
    coil: BTreeMap<String, bool>,
    tm: Vec<bool>,
    el: Vec<f64>,
    tempos: Vec<f64>,
}

struct Aval {
    coil: BTreeMap<String, bool>,
    lamp: BTreeSet<String>,
    motores: BTreeSet<String>,
    curtos: Vec<String>,
}

pub struct Circuito {
    chaves: Vec<Chave>,
    bob: Vec<(String, u32, u32)>,
    lamp: Vec<(String, u32, u32)>,
    motores: Vec<Motor>,
    timers: Vec<Timer>,
    timer_por_rotulo: HashMap<String, usize>,
    /// rotulos com temporizador intermitente (9007): contatos/polos de mesmo rotulo seguem `tm`
    intermitentes: BTreeSet<String>,
    fixos: Vec<(u32, char)>,
    /// bobinas (e temporizadores) por rotulo; 1a ocorrencia
    pub bobinas: BTreeMap<String, (u32, u32)>,
    pub lampadas: BTreeMap<String, (u32, u32)>,
    /// rotulos acionaveis de fora (botoes, termicos, disjuntores...), ordenados
    pub entradas: Vec<String>,
    /// pinos de papel funcional sem fio no ponto
    pub soltos: Vec<String>,
    pub legado: bool,
    pub supply: Option<u32>,
    pub ret: Option<u32>,
}

fn nome(rot: &str) -> String {
    rot.trim_start_matches('-').trim().to_string()
}

/// `atoi` do C: prefixo inteiro (com sinal), senao 0 (por isso "0.5" vira 0).
fn atoi(s: &str) -> i64 {
    let s = s.trim_start();
    let (sinal, resto) = match s.strip_prefix('-') {
        Some(r) => (-1, r),
        None => (1, s.strip_prefix('+').unwrap_or(s)),
    };
    let dig: String = resto.chars().take_while(|c| c.is_ascii_digit()).collect();
    sinal * dig.parse::<i64>().unwrap_or(0)
}

/// Tempo do temporizador-carga em segundos: `atoi(rotulo 6) x mult(rotulo 5)` ticks de 100 ms.
fn tempo_do_temporizador(labels: &[String]) -> f64 {
    let unidade = labels.get(4).map(|s| s.as_str()).unwrap_or("");
    let mult = match unidade {
        "3" => 1,
        "0" => 10,
        "1" => 100,
        "2" => 1000,
        _ => 1,
    };
    let ticks = atoi(labels.get(5).map(|s| s.as_str()).unwrap_or("")) * mult;
    ticks.max(0) as f64 / 10.0
}

fn pares_polos(offs: &[(String, (i64, i64))], pinos: &HashMap<String, u32>) -> Vec<(u32, u32)> {
    let mut col: BTreeMap<i64, Vec<(i64, &str)>> = BTreeMap::new();
    for (n, (dx, dy)) in offs {
        if pinos.contains_key(n) {
            col.entry(*dx).or_default().push((*dy, n.as_str()));
        }
    }
    let mut out = Vec::new();
    for (_, mut v) in col {
        v.sort();
        let ordem: Vec<u32> = v.iter().map(|(_, n)| pinos[*n]).collect();
        let mut i = 0;
        while i + 1 < ordem.len() {
            out.push((ordem[i], ordem[i + 1]));
            i += 2;
        }
    }
    out
}

fn nomes_re(cid: &str) -> Vec<String> {
    dados::classes_papeis()
        .get(cid)
        .and_then(|v| v.get("pinos"))
        .and_then(|p| p.as_array())
        .map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect())
        .unwrap_or_default()
}

impl Circuito {
    /// Le um `.cad` do disco com a tabela de papeis padrao.
    pub fn abrir(path: &str) -> Result<Self, String> {
        let raw = std::fs::read(path).map_err(|e| format!("erro leitura {path}: {e}"))?;
        Self::de_bytes(&raw, Papeis::padrao())
    }

    pub fn de_bytes(raw: &[u8], papeis: Papeis) -> Result<Self, String> {
        let d = latin1::decodificar(raw);
        let ents = entidades_do_cad(&d)?;
        // geometria compartilhada com o gate (cade_check::geom): fio-fio por extremo, juncao 4001/4012
        let geo = Conectividade::de_entidades(&ents);
        let ps: Vec<_> = ents.iter().filter(|p| p.nums.len() > 17).collect();

        let mut ids: HashMap<usize, u32> = HashMap::new();
        let mut fresh: u32 = 100_000;
        let mut c = Circuito {
            chaves: vec![],
            bob: vec![],
            lamp: vec![],
            motores: vec![],
            timers: vec![],
            timer_por_rotulo: HashMap::new(),
            intermitentes: BTreeSet::new(),
            fixos: vec![],
            bobinas: BTreeMap::new(),
            lampadas: BTreeMap::new(),
            entradas: vec![],
            soltos: vec![],
            legado: false,
            supply: None,
            ret: None,
        };

        for p in &ps {
            let cid = p.id.as_str();
            if SKIP.contains(&cid) {
                continue;
            }
            let (x, y, o) = (num(p, 8), num(p, 9), num(p, 17));
            let rot = p.labels.first().cloned().unwrap_or_default();
            let chave = {
                let n = nome(&rot);
                if n.is_empty() { cid.to_string() } else { n }
            };
            let papel = papeis.get(cid).cloned();
            let offs = pinos_da_classe(cid);
            // nome -> (rede, ligado)
            let mut pinos: HashMap<String, (u32, bool)> = HashMap::new();
            for (nm, (dx, dy)) in &offs {
                let (rx, ry) = rotacionar(*dx, *dy, o);
                let pt = (x + rx, y + ry);
                if let Some(r) = geo.rede_do_ponto(pt).filter(|_| geo.e_extremo(pt)) {
                    let n = ids.len() as u32 + 1;
                    let id = *ids.entry(r).or_insert(n);
                    pinos.insert(nm.clone(), (id, true));
                } else {
                    fresh += 1;
                    pinos.insert(nm.clone(), (fresh, false));
                }
            }
            if FONTE.contains(&cid) {
                for (nm, (no, lig)) in offs.iter().filter_map(|(n, _)| pinos.get(n).map(|v| (n, v))) {
                    if *lig {
                        if let Some(ch) = estampa_de_classe(&cid, nm).and_then(|e| e.chars().next()) {
                            c.fixos.push((*no, ch));
                        }
                    }
                }
                continue;
            }
            let Some(papel) = papel else { continue };
            let rotulo_msg = if rot.is_empty() { cid } else { rot.as_str() };
            let net = |i: usize| -> Option<(u32, bool, &str)> {
                let (nm, _) = offs.get(i)?;
                let (n, l) = pinos.get(nm)?;
                Some((*n, *l, nm.as_str()))
            };
            // os dois primeiros pinos (modelo embutido); registra soltos
            let dois = |c: &mut Circuito| -> Option<(u32, u32)> {
                let (a, la, na) = net(0)?;
                let (b, lb, nb) = net(1)?;
                if !la {
                    c.soltos.push(format!("{rotulo_msg}({cid}).{na}"));
                }
                if !lb {
                    c.soltos.push(format!("{rotulo_msg}({cid}).{nb}"));
                }
                Some((a, b))
            };
            match papel {
                Papel::Bobina => {
                    if let Some((a, b)) = dois(&mut c) {
                        c.bob.push((chave.clone(), a, b));
                        c.bobinas.entry(chave).or_insert((a, b));
                    }
                }
                Papel::Lampada => {
                    if let Some((a, b)) = dois(&mut c) {
                        c.lamp.push((chave.clone(), a, b));
                        c.lampadas.entry(chave).or_insert((a, b));
                    }
                }
                Papel::Contato { modo } => {
                    if let Some((a, b)) = dois(&mut c) {
                        let cond = if modo == Modo::Nc { Cond::Estado(0) } else { Cond::Estado(1) };
                        c.chaves.push(Chave { chave, ligs: vec![(a, b, cond)], fonte: FonteEstado::Rotulo, polos: false });
                    }
                }
                Papel::ContatoTemp { modo, tipo, tempo } => {
                    if let Some((a, b)) = dois(&mut c) {
                        let cond = if modo == Modo::Nc { Cond::Estado(0) } else { Cond::Estado(1) };
                        c.timers.push(Timer { id: String::new(), chave: chave.clone(), tipo, tempo: tempo.unwrap_or(0.0) });
                        let idx = c.timers.len() - 1;
                        c.chaves.push(Chave { chave, ligs: vec![(a, b, cond)], fonte: FonteEstado::Embutido(idx), polos: false });
                    }
                }
                Papel::Temporizador(tipo) => {
                    if let Some((a, b)) = dois(&mut c) {
                        c.bob.push((chave.clone(), a, b));
                        c.bobinas.entry(chave.clone()).or_insert((a, b));
                        c.timers.push(Timer { id: String::new(), chave, tipo, tempo: tempo_do_temporizador(&p.labels) });
                    }
                }
                Papel::Polos { modo } => {
                    let ligs = pares_polos(&offs, &pinos.iter().map(|(k, v)| (k.clone(), v.0)).collect())
                        .into_iter()
                        .map(|(a, b)| {
                            let cond = match modo {
                                ModoPolos::Fechado => Cond::Sempre,
                                ModoPolos::Na => Cond::Estado(1),
                                ModoPolos::Nc => Cond::Estado(0),
                            };
                            (a, b, cond)
                        })
                        .collect();
                    c.chaves.push(Chave { chave, ligs, fonte: FonteEstado::Rotulo, polos: true });
                }
                Papel::Chaves { ligacoes, fonte, polos } => {
                    let mut ligs = Vec::new();
                    let mut ok = true;
                    for (i, j, cond) in &ligacoes {
                        match (net(*i), net(*j)) {
                            (Some((a, la, na)), Some((b, lb, nb))) => {
                                for (l, n) in [(la, na), (lb, nb)] {
                                    let msg = format!("{rotulo_msg}({cid}).{n}");
                                    if !l && !polos && !c.soltos.contains(&msg) {
                                        c.soltos.push(msg);
                                    }
                                }
                                ligs.push((a, b, *cond));
                            }
                            _ => ok = false,
                        }
                    }
                    if ok {
                        let f = if fonte == Fonte::Temporizador { FonteEstado::PorRotulo } else { FonteEstado::Rotulo };
                        c.chaves.push(Chave { chave, ligs, fonte: f, polos });
                    }
                }
                Papel::Motor => {
                    let re = nomes_re(cid);
                    let mut fases = Vec::new();
                    for (i, (nm, _)) in offs.iter().enumerate() {
                        if re.get(i).map(|s| s.as_str()) == Some("PE") {
                            continue;
                        }
                        if let Some((n, true)) = pinos.get(nm).copied() {
                            fases.push(n);
                        }
                    }
                    c.motores.push(Motor { chave, fases });
                }
            }
        }

        // ids unicos para temporizadores (estado de tempo e por instancia)
        let mut total: HashMap<String, usize> = HashMap::new();
        for t in &c.timers {
            *total.entry(t.chave.clone()).or_default() += 1;
        }
        let mut vistos: HashMap<String, usize> = HashMap::new();
        for t in c.timers.iter_mut() {
            let v = vistos.entry(t.chave.clone()).or_default();
            *v += 1;
            t.id = if total[&t.chave] == 1 { t.chave.clone() } else { format!("{}#{}", t.chave, v) };
        }
        for (i, t) in c.timers.iter().enumerate() {
            c.timer_por_rotulo.entry(t.chave.clone()).or_insert(i);
        }
        // 9007 intermitente (RE 11.4, FUN_00632a20): o estado alterna e e copiado a polos e a
        // 7000..7015 de mesmo rotulo — ou seja, ate o contato "instantaneo" pisca. Como no
        // oraculo Python, todo contato/polo de fonte Rotulo cujo rotulo tem 9007 segue `tm`.
        // AMBIGUO: o RE nao diz o que vale se o mesmo rotulo tiver bobina 9000 e 9007 juntos;
        // aqui o 9007 prevalece (o rotulo entra em `intermitentes`).
        for t in &c.timers {
            if t.tipo == TipoTemp::Intermitente {
                c.intermitentes.insert(t.chave.clone());
            }
        }
        let mut ent: BTreeSet<String> = BTreeSet::new();
        for k in c.chaves.iter().filter(|k| !k.polos) {
            if !c.bobinas.contains_key(&k.chave) {
                ent.insert(k.chave.clone());
            }
        }
        // contatos temporizados por rotulo apontam para temporizadores, nao para entradas
        for k in c.chaves.iter().filter(|k| k.fonte == FonteEstado::PorRotulo) {
            if c.timer_por_rotulo.contains_key(&k.chave) {
                ent.remove(&k.chave);
            }
        }
        c.entradas = ent.into_iter().collect();

        // fonte / retorno
        c.legado = c.fixos.is_empty();
        if c.legado {
            // ladder / sem fonte: 1o contato = fase, retorno = B comum das bobinas
            let primeiro = c.chaves.iter().find(|k| !k.polos).and_then(|k| k.ligs.first()).map(|l| l.0);
            c.supply = primeiro;
            let mut cont: Vec<(u32, usize)> = Vec::new();
            for (_, _, b) in &c.bob {
                match cont.iter_mut().find(|(n, _)| n == b) {
                    Some(e) => e.1 += 1,
                    None => cont.push((*b, 1)),
                }
            }
            let mut melhor: Option<(u32, usize)> = None;
            for &(n, k) in &cont {
                if melhor.is_none_or(|(_, m)| k > m) {
                    melhor = Some((n, k));
                }
            }
            c.ret = melhor.map(|m| m.0);
            if let Some(s) = c.supply {
                c.fixos.push((s, '1'));
            }
            if let Some(r) = c.ret {
                c.fixos.push((r, 'N'));
            }
        } else {
            c.supply = ['1', '2', '3'].iter().find_map(|ch| c.fixos.iter().find(|(_, x)| x == ch).map(|(n, _)| *n));
            c.ret = c.fixos.iter().find(|(_, x)| *x == 'N').map(|(n, _)| *n);
        }
        Ok(c)
    }

    // --- avaliacao combinacional ----------------------------------------------------------------

    fn controle(&self, chave: &str, ent: &Entradas, coil: &BTreeMap<String, bool>) -> i64 {
        if self.bobinas.contains_key(chave) {
            coil.get(chave).copied().unwrap_or(false) as i64
        } else {
            ent.get(chave).copied().unwrap_or(0)
        }
    }

    fn estado_da_chave(&self, k: &Chave, ent: &Entradas, coil: &BTreeMap<String, bool>, tm: &[bool]) -> i64 {
        match k.fonte {
            FonteEstado::Rotulo => {
                if self.intermitentes.contains(&k.chave) {
                    self.timer_por_rotulo.get(&k.chave).map(|&i| tm[i] as i64).unwrap_or(0)
                } else {
                    self.controle(&k.chave, ent, coil)
                }
            }
            FonteEstado::PorRotulo => self.timer_por_rotulo.get(&k.chave).map(|&i| tm[i] as i64).unwrap_or(0),
            FonteEstado::Embutido(i) => tm[i] as i64,
        }
    }

    /// Uma passada: une redes por elementos fechados, estampa fases, energiza cargas.
    fn avaliar(&self, ent: &Entradas, coil: &BTreeMap<String, bool>, tm: &[bool]) -> Aval {
        let mut uf = Uf::default();
        for k in &self.chaves {
            let estado = self.estado_da_chave(k, ent, coil, tm);
            for &(a, b, cond) in &k.ligs {
                let fecha = match cond {
                    Cond::Sempre => true,
                    Cond::Estado(n) => estado == n,
                };
                if fecha {
                    uf.union(a, b);
                }
            }
        }
        let mut chars: HashMap<u32, BTreeSet<char>> = HashMap::new();
        for &(no, ch) in &self.fixos {
            chars.entry(uf.find(no)).or_default().insert(ch);
        }
        let vistos = |uf: &mut Uf, n: u32| -> BTreeSet<char> {
            let mut s = chars.get(&uf.find(n)).cloned().unwrap_or_default();
            s.remove(&'P');
            s
        };
        let energizado = |uf: &mut Uf, a: u32, b: u32| -> bool {
            let (sa, sb) = (vistos(uf, a), vistos(uf, b));
            !sa.is_empty() && !sb.is_empty() && sa != sb
        };
        let mut novo: BTreeMap<String, bool> = self.bobinas.keys().map(|k| (k.clone(), false)).collect();
        for (k, a, b) in &self.bob {
            if energizado(&mut uf, *a, *b) {
                novo.insert(k.clone(), true);
            }
        }
        let mut lamp = BTreeSet::new();
        for (k, a, b) in &self.lamp {
            if energizado(&mut uf, *a, *b) {
                lamp.insert(k.clone());
            }
        }
        // motor: gira quando dois pinos de fase veem estampas (sem PE) diferentes
        let mut motores = BTreeSet::new();
        for m in &self.motores {
            let sets: Vec<BTreeSet<char>> = m.fases.iter().map(|&n| vistos(&mut uf, n)).collect();
            let gira = sets.iter().enumerate().any(|(i, a)| !a.is_empty() && sets[i + 1..].iter().any(|b| !b.is_empty() && a != b));
            if gira {
                motores.insert(m.chave.clone());
            }
        }
        let mut curtos: Vec<String> = chars
            .values()
            .filter(|s| s.len() > 1)
            .map(|s| s.iter().map(|c| c.to_string()).collect::<Vec<_>>().join("+"))
            .collect();
        curtos.sort();
        Aval { coil: novo, lamp, motores, curtos }
    }

    /// Relaxa a logica ate o ponto fixo (selo/intertravamento).
    fn assentar(&self, ent: &Entradas, mut coil: BTreeMap<String, bool>, tm: &[bool]) -> (Status, Aval) {
        let mut vistos: BTreeSet<Vec<String>> = BTreeSet::new();
        let mut ult = Aval { coil: coil.clone(), lamp: BTreeSet::new(), motores: BTreeSet::new(), curtos: vec![] };
        for _ in 0..40 {
            let a = self.avaliar(ent, &coil, tm);
            if a.coil == coil {
                let st = if a.curtos.is_empty() { Status::Ok } else { Status::Curto };
                return (st, a);
            }
            let assin: Vec<String> = a.coil.iter().filter(|(_, v)| **v).map(|(k, _)| k.clone()).collect();
            if !vistos.insert(assin) {
                return (Status::Race, a);
            }
            coil = a.coil.clone();
            ult = a;
        }
        ult.coil = coil;
        (Status::Instavel, ult)
    }

    // --- tempo (ON/OFF-delay) -------------------------------------------------------------------

    fn ativos(&self, ent: &Entradas, coil: &BTreeMap<String, bool>) -> Vec<bool> {
        self.timers.iter().map(|t| self.controle(&t.chave, ent, coil) != 0).collect()
    }

    /// Avanca `dt` nos temporizadores; True se alguma saida mudou.
    fn passo_tempo(&self, st: &mut Persistente, ativo: &[bool], dt: f64) -> bool {
        let mut mudou = false;
        for (i, t) in self.timers.iter().enumerate() {
            let a = ativo[i];
            let tempo = st.tempos[i];
            let novo = match t.tipo {
                TipoTemp::Ton => {
                    if !a {
                        st.el[i] = 0.0;
                        false
                    } else {
                        st.el[i] += dt;
                        st.el[i] >= tempo - 1e-9
                    }
                }
                TipoTemp::Tof => {
                    if a {
                        st.el[i] = 0.0;
                        true
                    } else if st.tm[i] {
                        st.el[i] += dt;
                        st.el[i] < tempo - 1e-9
                    } else {
                        false
                    }
                }
                TipoTemp::TonTof => {
                    if a {
                        if st.tm[i] {
                            st.el[i] = 0.0;
                            true
                        } else {
                            st.el[i] += dt;
                            st.el[i] >= tempo - 1e-9
                        }
                    } else if st.tm[i] {
                        st.el[i] += dt;
                        st.el[i] < tempo - 1e-9
                    } else {
                        st.el[i] = 0.0;
                        false
                    }
                }
                TipoTemp::Intermitente => {
                    if !a {
                        st.el[i] = 0.0;
                        false
                    } else if tempo <= 1e-9 {
                        // T=0: sem periodo definido; como o oraculo, alterna a cada passo com dt>0
                        st.el[i] = 0.0;
                        if dt > 0.0 { !st.tm[i] } else { st.tm[i] }
                    } else {
                        st.el[i] += dt;
                        let mut n = st.tm[i];
                        while st.el[i] >= tempo - 1e-9 {
                            st.el[i] -= tempo;
                            n = !n;
                        }
                        n
                    }
                }
            };
            if novo != st.tm[i] {
                st.tm[i] = novo;
                mudou = true;
            }
        }
        mudou
    }

    /// Menor tempo ate alguma saida mudar (None se nenhuma esta correndo).
    fn proximo_evento(&self, st: &Persistente, ativo: &[bool]) -> Option<f64> {
        let mut r: Option<f64> = None;
        for (i, t) in self.timers.iter().enumerate() {
            let corre = match t.tipo {
                TipoTemp::Ton => ativo[i] && !st.tm[i],
                TipoTemp::Tof => !ativo[i] && st.tm[i],
                TipoTemp::TonTof => (ativo[i] && !st.tm[i]) || (!ativo[i] && st.tm[i]),
                TipoTemp::Intermitente => ativo[i],
            };
            if corre {
                let falta = (st.tempos[i] - st.el[i]).max(0.0);
                r = Some(r.map_or(falta, |x| x.min(falta)));
            }
        }
        r
    }

    /// Estado persistente inicial: `inicial` = bobinas/temporizadores ja energizados.
    pub fn novo_estado(&self, inicial: &[String], tempos: Option<&BTreeMap<String, f64>>) -> Persistente {
        let ini: BTreeSet<&str> = inicial.iter().map(|s| s.as_str()).collect();
        let coil = self.bobinas.keys().map(|k| (k.clone(), ini.contains(k.as_str()))).collect();
        let tempos_v: Vec<f64> = self
            .timers
            .iter()
            .map(|t| tempos.and_then(|m| m.get(&t.id).or_else(|| m.get(&t.chave))).copied().unwrap_or(t.tempo))
            .collect();
        let tm: Vec<bool> = self.timers.iter().map(|t| ini.contains(t.id.as_str()) || ini.contains(t.chave.as_str())).collect();
        let el = self
            .timers
            .iter()
            .enumerate()
            .map(|(i, t)| if tm[i] && matches!(t.tipo, TipoTemp::Ton) { tempos_v[i] } else { 0.0 })
            .collect();
        Persistente { coil, tm, el, tempos: tempos_v }
    }

    /// Aplica `ent` constante por `avanca` s sobre `st` (mutado).
    pub fn avancar(&self, st: &mut Persistente, ent: &Entradas, avanca: f64) -> EstadoSim {
        let (mut status, mut aval) = self.assentar(ent, st.coil.clone(), &st.tm);
        let mut restante = avanca;
        for _ in 0..200 {
            if self.timers.is_empty() || matches!(status, Status::Race | Status::Instavel) {
                break;
            }
            let ativo = self.ativos(ent, &aval.coil);
            if self.passo_tempo(st, &ativo, 0.0) {
                (status, aval) = self.assentar(ent, aval.coil.clone(), &st.tm);
                continue;
            }
            if restante <= 1e-9 {
                break;
            }
            let ev = self.proximo_evento(st, &ativo);
            let dt = ev.map_or(restante, |e| restante.min(e));
            if dt <= 0.0 {
                break;
            }
            let mudou = self.passo_tempo(st, &ativo, dt);
            restante -= dt;
            if mudou {
                (status, aval) = self.assentar(ent, aval.coil.clone(), &st.tm);
            }
        }
        st.coil = aval.coil.clone();
        EstadoSim {
            status,
            bobinas: aval.coil.iter().filter(|(_, v)| **v).map(|(k, _)| k.clone()).collect(),
            lampadas: aval.lamp.into_iter().collect(),
            motores: aval.motores.into_iter().collect(),
            temporizadores: self
                .timers
                .iter()
                .enumerate()
                .map(|(i, t)| InfoTimer {
                    id: t.id.clone(),
                    tipo: match t.tipo {
                        TipoTemp::Ton => "ton",
                        TipoTemp::Tof => "tof",
                        TipoTemp::TonTof => "tonof",
                        TipoTemp::Intermitente => "intermitente",
                    },
                    tempo: st.tempos[i],
                    decorrido: (st.el[i] * 1e6).round() / 1e6,
                    saida: st.tm[i],
                })
                .collect(),
            curtos: aval.curtos,
        }
    }

    // --- API publica ----------------------------------------------------------------------------

    /// `estado()` do Python: um passo a partir do estado inicial.
    pub fn estado(&self, ent: &Entradas, inicial: &[String], avanca: f64, tempos: Option<&BTreeMap<String, f64>>) -> EstadoSim {
        let mut st = self.novo_estado(inicial, tempos);
        self.avancar(&mut st, ent, avanca)
    }

    /// `resolve()` do Python: `(status, bobinas)`.
    pub fn resolve(&self, ent: &Entradas, inicial: &[String]) -> (Status, BTreeSet<String>) {
        let e = self.estado(ent, inicial, 0.0, None);
        (e.status, e.bobinas.into_iter().collect())
    }

    /// Ids dos temporizadores (contatos temporizados e temporizadores-carga).
    pub fn ids_temporizadores(&self) -> Vec<String> {
        self.timers.iter().map(|t| t.id.clone()).collect()
    }

    /// Chaves de temporizadores (rotulos), para validar `inicial`.
    pub fn chaves_temporizadores(&self) -> Vec<String> {
        self.timers.iter().map(|t| t.chave.clone()).collect()
    }

    /// Motores do desenho (rotulos).
    pub fn rotulos_motores(&self) -> Vec<String> {
        let mut v: Vec<String> = self.motores.iter().map(|m| m.chave.clone()).collect();
        v.sort();
        v.dedup();
        v
    }
}
