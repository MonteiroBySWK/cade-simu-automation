//! Simulador GEOMETRICO de circuitos com CLP modular + ladder (paridade com `tools/clp_sim.py`).
//!
//! Modelo geometrico de `docs/ladder.md` §3.2: le o `.cad` (nada vem da DSL) e roda a mesma ordem de
//! avaliacao do modelo logico (`tools/ladder_dsl.py`): um tick de 100 ms, avaliacao sincrona.
//!
//! - conectividade por GEOMETRIA (extremo a extremo; nets gravados ignorados), reaproveitada de
//!   `cade_check::geom`;
//! - potenciais por "char": fontes 3000..3011 (L1->1, L2->2, L3->3, N->N, PE->P), 3008 -> '+',
//!   3009 -> '-', CPU 10206 alimentada (fase+N ou 2 fases em L/N) -> '+' em p3 e '-' em p4,
//!   saida 10205 com bit 1 -> '+';
//! - contatos eletricos conduzem nos dois sentidos; contatos ladder (10050 NA / 10051 NF) so de A para B;
//! - um tick: rede fisica (com os contatores do tick anterior e as entradas do caso) + ladder com os
//!   bits do tick anterior; bobinas 10060/10061/10062, TON 10066, TOF 10067, CTU 10063,
//!   bordas 10052/10053; disjuntores/termico alternam,
//!   botoeiras sao momentaneas (soltas quando nao citadas).
//!
//! Textos de `teste_casos`/`executar_caso`/`chaves_invalidas` sao IDENTICOS aos do Python
//! (o gate compara a saida).

use cade_check::geom::{
    entidades_do_cad, num, pinos_da_classe, rotacionar, Conectividade, FONTE, SKIP,
};
use cade_model::dados;
use cade_model::latin1;
use cade_model::pyfmt::{repr, repr_lista};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};

// Classes do `tem_clp` do Python (`tools/clp_sim.py`): CPU/entradas/saidas, fonte do trilho,
// bobinas ladder, TON/TOF/CTU, contatos ladder e bordas. Qualquer uma delas escolhe este simulador.
pub const CLASSES_CLP: [&str; 14] = [
    "10206", "10204", "10205", "3008", "10060", "10061", "10062", "10066", "10067", "10063", "10050",
    "10051", "10052", "10053",
];

const LADDER_NA: &str = "10050";
const LADDER_NF: &str = "10051";
const LADDER_SUBIDA: &str = "10052";
const LADDER_DESCIDA: &str = "10053";
const OUT_C: &str = "10060";
const SET_C: &str = "10061";
const RST_C: &str = "10062";
const TON_C: &str = "10066";
const TOF_C: &str = "10067";
const CTU_C: &str = "10063";
const CPU: &str = "10206";
const ENTRADA: &str = "10204";
const SAIDA: &str = "10205";
const FONTE_MAIS: &str = "3008";
const FONTE_MENOS: &str = "3009";
const BOTAO_NA: &str = "8000";
const BOTAO_NF: &str = "8001";
const AUX: [&str; 2] = ["7000", "7001"];
const DISJUNTOR: [&str; 4] = ["6002", "6003", "6009", "6010"];
const TERMICO: &str = "6007";
const POLO_CONTATOR: &str = "2001";
const BOBINA: &str = "9000";
const LAMPADA: &str = "9008";
// Radio do dialogo do TON: 0,1 s / 1 s / 10 s / x60 s, em ticks.
const BASE_TICKS: [(&str, i64); 4] = [("3", 1), ("0", 10), ("1", 100), ("2", 1000)];
pub const MAX_TICKS: usize = 2000;
const FASES: [char; 4] = ['1', '2', '3', 'N'];

fn tem(ss: &[&str], cid: &str) -> bool {
    ss.contains(&cid)
}

// `tem_clp` do Python: True se o .cad tem CPU/entradas/saidas de CLP ou elementos ladder.
pub fn tem_clp(cad: &[u8]) -> bool {
    let d = latin1::decodificar(cad);
    let Ok(ents) = entidades_do_cad(&d) else {
        return false;
    };
    ents.iter().any(|e| CLASSES_CLP.contains(&e.id.as_str()))
}

fn nome_fisico(rot: &str) -> String {
    rot.trim_start_matches('-').trim().to_string()
}

// Preset do contador em pulsos a partir dos labels gravados ([op,'','R','C','D','Q',preset,preset]).
fn ctu_preset(labels: &[String]) -> i64 {
    let mut lab: Vec<String> = labels.to_vec();
    while lab.len() < 8 {
        lab.push(String::new());
    }
    lab[6]
        .replace(',', ".")
        .trim()
        .parse::<f64>()
        .unwrap_or(0.0)
        .max(1.0) as i64
}
// Preset do TON/TOF em ticks a partir dos labels gravados ([op,'','IN','Q',base,tempo]).
fn ton_ticks(labels: &[String]) -> i64 {
    let mut lab: Vec<String> = labels.to_vec();
    while lab.len() < 6 {
        lab.push(String::new());
    }
    let n: f64 = lab[5].replace(',', ".").trim().parse().unwrap_or(0.0);
    let base = BASE_TICKS
        .iter()
        .find(|(b, _)| *b == lab[4].trim())
        .map(|(_, m)| *m)
        .unwrap_or(10);
    ((n * base as f64).round() as i64).max(1)
}

/// `carregar_papeis` do Python reduzido ao que o ladder usa: papel `contato` (NA/NC).
/// Embutidos primeiro (validados no app); o JSON do RE so acrescenta (`contato` via alias).
fn contato_nc(cid: &str) -> Option<bool> {
    if tem(&["8000", "8016", "7000", "10050"], cid) {
        return Some(false);
    }
    if tem(&["8001", "8017", "7001", "10051"], cid) {
        return Some(true);
    }
    let v = dados::classes_papeis().get(cid)?;
    let bruto = v.get("papel").or_else(|| v.get("role"))?.as_str()?;
    let papel = bruto.trim().to_lowercase();
    let (papel_n, modo_alias): (String, Option<String>) = match papel.as_str() {
        "na" | "no" | "contato_na" => ("contato".into(), Some("NA".into())),
        "nc" | "nf" | "contato_nc" => ("contato".into(), Some("NC".into())),
        _ => (papel.clone(), None),
    };
    if papel_n != "contato" {
        return None;
    }
    let modo = v
        .get("modo")
        .and_then(|m| m.as_str())
        .map(|m| m.to_uppercase().replace("NF", "NC").replace("NO", "NA"))
        .or(modo_alias);
    Some(modo.as_deref() == Some("NC"))
}

/// Assinatura de um estado para detectar regime/ciclo (`_assin` do Python).
type Assinatura = (
    Vec<(String, bool)>,
    Vec<(String, bool)>,
    Vec<i64>,
    Vec<(String, bool)>,
    Vec<i64>,
    Vec<bool>,
);

/// Um passo do historico: (nome, falhas, resultado).
type PassoHist = (String, Vec<String>, Resumo);

/// Pino por nome: (rede, ligado a extremo de fio).
type Pinos = HashMap<String, (u32, bool)>;

/// Entidade bruta: (classe, rotulo, labels, pinos).
type Bruto = (String, String, Vec<String>, Pinos);

/// Union-find sobre redes (ids inteiros).
#[derive(Default)]
struct Uf {
    pai: HashMap<u32, u32>,
}

impl Uf {
    fn raiz(&mut self, x: u32) -> u32 {
        let mut a = *self.pai.entry(x).or_insert(x);
        while self.pai[&a] != a {
            let p = self.pai[&a];
            let pp = self.pai[&p];
            self.pai.insert(a, pp);
            a = pp;
        }
        a
    }

    fn unir(&mut self, a: u32, b: u32) {
        let (ra, rb) = (self.raiz(a), self.raiz(b));
        if ra != rb {
            self.pai.insert(rb, ra);
        }
    }
}

#[derive(Clone, Debug)]
struct Cpu {
    l: u32,
    n: u32,
    mais: u32,
    menos: u32,
}

#[derive(Clone, Debug)]
struct ContatoLadder {
    na: bool,
    /// None = por nivel; Some(true) = borda de subida, Some(false) = borda de descida.
    flanco: Option<bool>,
    op: String,
    a: u32,
    b: u32,
}

#[derive(Clone, Debug)]
struct BobLadder {
    tipo: char, // 'O' = OUT, 'S' = SET, 'R' = RST
    op: String,
    a: u32,
    b: u32,
    b_ligado: bool,
}

#[derive(Clone, Debug)]
struct Ton {
    op: String,
    a: u32,
    b: u32,
    t: i64,
    idx: usize,
    /// 'O' = TON (retardo na ligacao), 'F' = TOF (retardo no desligamento).
    kind: char,
}

#[derive(Clone, Debug)]
struct Contador {
    op: String,
    c: u32, // CU (conta na borda de subida)
    r: u32, // reset (nivel: '+' zera)
    q: u32, // Q (estampa '+' com contagem >= preset)
    preset: i64,
    idx: usize,
}

#[derive(Clone, Debug)]
struct Contato {
    nc: bool,
    chave: String,
    a: u32,
    b: u32,
    por_bobina: bool,
}

#[derive(Clone, Debug)]
struct Polo {
    chave: String,
    tipo: char, // 'p' = passa (termico), 'd' = disjuntor, 'c' = contator
    pares: Vec<(u32, u32)>,
}

/// Estado do simulador: bits (por operando), fisicos (bobinas 9000), acumuladores dos
/// temporizadores, imagem anterior dos bits (bordas), contagens e CUs anteriores (contadores).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Estado {
    pub bits: BTreeMap<String, bool>,
    pub prev: BTreeMap<String, bool>,
    pub fis: BTreeMap<String, bool>,
    pub acc: Vec<i64>,
    pub cnt: Vec<i64>,
    pub cnt_v: Vec<bool>,
}

/// Info de um tick (lampadas, curtos, CPU alimentada, SET+RST juntos).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct InfoTick {
    pub lampadas: Vec<String>,
    pub curtos: Vec<String>,
    pub cpu: bool,
    pub indefinido: Vec<String>,
}

/// Resumo de `rodar`/`regime` (`_resumo` do Python).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Resumo {
    pub status: String,
    pub bobinas: Vec<String>,
    pub lampadas: Vec<String>,
    pub bits: BTreeMap<String, bool>,
    pub curtos: Vec<String>,
    pub cpu: bool,
    pub ticks: Option<i64>,
}

pub struct CircuitoClp {
    fixos: Vec<(u32, char)>,
    cpus: Vec<Cpu>,
    ent_clp: Vec<(String, u32)>,
    sai_clp: Vec<(String, u32)>,
    ladder: Vec<ContatoLadder>,
    bob_ladder: Vec<BobLadder>,
    tons: Vec<Ton>,
    contadores: Vec<Contador>,
    contatos: Vec<Contato>,
    polos: Vec<Polo>,
    bobinas: BTreeMap<String, Vec<(u32, u32)>>,
    lampadas: BTreeMap<String, Vec<(u32, u32)>>,
    /// Rotulos acionaveis de fora (botoes, disjuntores, termicos...), ordenados.
    pub entradas: Vec<String>,
    alternaveis: HashSet<String>,
    /// Todos os operandos do ladder (I/Q/M/T...), ordenados.
    pub operandos: Vec<String>,
}

/// Estampa de fase de um pino de fonte (`CHAR` de `tools/geo_check.py`).
fn char_fonte(pino: &str) -> Option<char> {
    Some(match pino {
        "L1" | "L" | "p4" => '1',
        "L2" => '2',
        "L3" => '3',
        "N" | "p3" => 'N',
        "PE" => 'P',
        _ => return None,
    })
}

/// Polos de um multipolar: pinos de mesmo dx pareados por dy crescente (1-2, 3-4, 5-6).
fn pares_polos(cid: &str, pinos: &HashMap<String, (u32, bool)>) -> Vec<(u32, u32)> {
    let mut col: BTreeMap<i64, Vec<(i64, String)>> = BTreeMap::new();
    for (nome, (dx, dy)) in pinos_da_classe(cid) {
        if pinos.contains_key(&nome) {
            col.entry(dx).or_default().push((dy, nome));
        }
    }
    let mut out = Vec::new();
    for (_, mut v) in col {
        v.sort();
        let ordem: Vec<u32> = v.iter().map(|(_, n)| pinos[n].0).collect();
        let mut i = 0;
        while i + 1 < ordem.len() {
            out.push((ordem[i], ordem[i + 1]));
            i += 2;
        }
    }
    out
}

impl CircuitoClp {
    pub fn de_bytes(cad: &[u8]) -> Result<Self, String> {
        let d = latin1::decodificar(cad);
        let ents = entidades_do_cad(&d)?;
        let ps: Vec<_> = ents.iter().filter(|p| p.nums.len() > 17).collect();
        let geo = Conectividade::de_entidades(&ents);
        let mut prox: u32 = 1_000_000;
        let mut no = |pt: (i64, i64)| -> (u32, bool) {
            match geo.rede_do_ponto(pt).filter(|_| geo.e_extremo(pt)) {
                Some(r) => (r as u32, true),
                None => {
                    prox += 1;
                    (prox, false)
                }
            }
        };

        // brutos para `nomes_bob` (as bobinas precedem os contatos que as seguem)
        let mut brutos: Vec<Bruto> = Vec::new();
        for p in &ps {
            let cid = p.id.as_str();
            if SKIP.contains(&cid) {
                continue;
            }
            let (x, y, o) = (num(p, 8), num(p, 9), num(p, 17));
            let rot = p.labels.first().cloned().unwrap_or_default();
            let mut pin = HashMap::new();
            for (pnome, (dx, dy)) in pinos_da_classe(cid) {
                let (rx, ry) = rotacionar(dx, dy, o);
                pin.insert(pnome, no((x + rx, y + ry)));
            }
            brutos.push((cid.to_string(), rot, p.labels.clone(), pin));
        }
        let nomes_bob: HashSet<String> = brutos
            .iter()
            .filter(|(cid, _, _, _)| cid == BOBINA)
            .map(|(_, r, _, _)| nome_fisico(r))
            .collect();

        let mut fixos = Vec::new();
        let mut cpus = Vec::new();
        let mut ent_clp = Vec::new();
        let mut sai_clp = Vec::new();
        let mut ladder = Vec::new();
        let mut bob_ladder = Vec::new();
        let mut tons = Vec::new();
        let mut contadores = Vec::new();
        let mut contatos = Vec::new();
        let mut polos = Vec::new();
        let mut bobinas: BTreeMap<String, Vec<(u32, u32)>> = BTreeMap::new();
        let mut lampadas: BTreeMap<String, Vec<(u32, u32)>> = BTreeMap::new();
        let mut disjuntores = HashSet::new();
        let mut termicos = HashSet::new();
        let mut botoes = HashSet::new();
        for (cid, rot, labels, pin) in &brutos {
            let cid = cid.as_str();
            let n: HashMap<&str, u32> = pin.iter().map(|(k, v)| (k.as_str(), v.0)).collect();
            let chave = {
                let f = nome_fisico(rot);
                if f.is_empty() {
                    cid.to_string()
                } else {
                    f
                }
            };
            if FONTE.contains(&cid) {
                for (pnome, (v, lig)) in pin {
                    if *lig {
                        if let Some(ch) = char_fonte(pnome) {
                            fixos.push((*v, ch));
                        }
                    }
                }
            } else if cid == FONTE_MAIS {
                for (v, lig) in pin.values() {
                    if *lig {
                        fixos.push((*v, '+'));
                    }
                }
            } else if cid == FONTE_MENOS {
                for (v, lig) in pin.values() {
                    if *lig {
                        fixos.push((*v, '-'));
                    }
                }
            } else if cid == CPU {
                cpus.push(Cpu {
                    l: n["p1"],
                    n: n["p2"],
                    mais: n["p3"],
                    menos: n["p4"],
                });
            } else if cid == ENTRADA {
                ent_clp.push((rot.trim().to_string(), n["p1"]));
            } else if cid == SAIDA {
                sai_clp.push((rot.trim().to_string(), n["p1"]));
            } else if cid == LADDER_NA || cid == LADDER_NF || cid == LADDER_SUBIDA || cid == LADDER_DESCIDA {
                ladder.push(ContatoLadder {
                    na: cid == LADDER_NA,
                    flanco: if cid == LADDER_SUBIDA {
                        Some(true)
                    } else if cid == LADDER_DESCIDA {
                        Some(false)
                    } else {
                        None
                    },
                    op: rot.trim().to_string(),
                    a: n["p1"],
                    b: n["p2"],
                });
            } else if cid == OUT_C || cid == SET_C || cid == RST_C {
                let tipo = if cid == OUT_C {
                    'O'
                } else if cid == SET_C {
                    'S'
                } else {
                    'R'
                };
                bob_ladder.push(BobLadder {
                    tipo,
                    op: rot.trim().to_string(),
                    a: n["p1"],
                    b: n["p2"],
                    b_ligado: pin["p2"].1,
                });
            } else if cid == TON_C || cid == TOF_C {
                let idx = tons.len();
                tons.push(Ton {
                    op: rot.trim().to_string(),
                    a: n["p1"],
                    b: n["p2"],
                    t: ton_ticks(labels),
                    idx,
                    kind: if cid == TOF_C { 'F' } else { 'O' },
                });
            } else if cid == CTU_C {
                let idx = contadores.len();
                contadores.push(Contador {
                    op: rot.trim().to_string(),
                    c: n["p2"],
                    r: n["p1"],
                    q: n["p4"],
                    preset: ctu_preset(labels),
                    idx,
                });
            } else if cid == BOBINA || cid == LAMPADA {
                (if cid == BOBINA {
                    &mut bobinas
                } else {
                    &mut lampadas
                })
                .entry(chave)
                .or_default()
                .push((n["p1"], n["p2"]));
            } else if tem(&DISJUNTOR, cid) || cid == TERMICO || cid == POLO_CONTATOR {
                let tipo = if tem(&DISJUNTOR, cid) {
                    'd'
                } else if cid == TERMICO {
                    'p'
                } else {
                    'c'
                };
                if tipo == 'd' {
                    disjuntores.insert(chave.clone());
                } else if tipo == 'p' {
                    termicos.insert(chave.clone());
                }
                polos.push(Polo {
                    chave,
                    tipo,
                    pares: pares_polos(cid, pin),
                });
            } else {
                let Some(nc) = contato_nc(cid) else { continue };
                if !n.contains_key("p1") || !n.contains_key("p2") {
                    continue;
                }
                if cid == BOTAO_NA || cid == BOTAO_NF {
                    botoes.insert(chave.clone());
                }
                let por_bobina = tem(&AUX, cid)
                    || (nomes_bob.contains(&chave) && cid != BOTAO_NA && cid != BOTAO_NF);
                contatos.push(Contato {
                    nc,
                    chave,
                    a: n["p1"],
                    b: n["p2"],
                    por_bobina,
                });
            }
        }
        // entradas validas: botoes, disjuntores, termicos e contatos que nao seguem bobina
        let mut entradas: BTreeSet<String> = botoes.iter().cloned().collect();
        entradas.extend(disjuntores.iter().cloned());
        entradas.extend(termicos.iter().cloned());
        for c in &contatos {
            if !nomes_bob.contains(&c.chave) {
                entradas.insert(c.chave.clone());
            }
        }
        let alternaveis: HashSet<String> = disjuntores
            .union(&termicos)
            .filter(|k| !botoes.contains(*k))
            .cloned()
            .collect();
        let mut operandos: BTreeSet<String> = BTreeSet::new();
        operandos.extend(ent_clp.iter().map(|(o, _)| o.clone()));
        operandos.extend(sai_clp.iter().map(|(o, _)| o.clone()));
        operandos.extend(ladder.iter().map(|c| c.op.clone()));
        operandos.extend(bob_ladder.iter().map(|b| b.op.clone()));
        operandos.extend(tons.iter().map(|t| t.op.clone()));
        operandos.extend(contadores.iter().map(|t| t.op.clone()));
        Ok(CircuitoClp {
            fixos,
            cpus,
            ent_clp,
            sai_clp,
            ladder,
            bob_ladder,
            tons,
            contadores,
            contatos,
            polos,
            bobinas,
            lampadas,
            entradas: entradas.into_iter().collect(),
            alternaveis,
            operandos: operandos.into_iter().collect(),
        })
    }

    // ------------------------------------------------------------- estado
    /// Bobinas fisicas 9000 (para mensagens de chave invalida).
    pub fn bobinas_fisicas(&self) -> Vec<String> {
        self.bobinas.keys().cloned().collect()
    }

    /// Lampadas fisicas 9008 (para mensagens de chave invalida).
    pub fn lampadas_fisicas(&self) -> Vec<String> {
        self.lampadas.keys().cloned().collect()
    }

    pub fn estado_zero(&self, inicial: &[String]) -> Estado {
        let ini: HashSet<&str> = inicial.iter().map(|s| s.as_str()).collect();
        let bits: BTreeMap<String, bool> = self
            .operandos
            .iter()
            .map(|o| (o.clone(), ini.contains(o.as_str())))
            .collect();
        Estado {
            prev: bits.clone(),
            bits,
            fis: self
                .bobinas
                .keys()
                .map(|k| (k.clone(), ini.contains(k.as_str())))
                .collect(),
            acc: vec![0; self.tons.len()],
            cnt: vec![0; self.contadores.len()],
            cnt_v: vec![false; self.contadores.len()],
        }
    }

    fn contato_fechado(
        &self,
        c: &Contato,
        ent: &BTreeMap<String, bool>,
        fis: &BTreeMap<String, bool>,
    ) -> bool {
        let ativo = if c.por_bobina {
            fis.get(&c.chave).copied().unwrap_or(false)
        } else {
            ent.get(&c.chave).copied().unwrap_or(false)
        };
        if c.nc {
            !ativo
        } else {
            ativo
        }
    }

    fn rede(&self, ent: &BTreeMap<String, bool>, fis: &BTreeMap<String, bool>) -> Uf {
        let mut uf = Uf::default();
        for c in &self.contatos {
            if self.contato_fechado(c, ent, fis) {
                uf.unir(c.a, c.b);
            }
        }
        for pl in &self.polos {
            let ok = pl.tipo == 'p'
                || (pl.tipo == 'd' && ent.get(&pl.chave).copied().unwrap_or(false))
                || (pl.tipo == 'c' && fis.get(&pl.chave).copied().unwrap_or(false));
            if ok {
                for (a, b) in &pl.pares {
                    uf.unir(*a, *b);
                }
            }
        }
        uf
    }

    /// Um tick de 100 ms: do estado do tick anterior (+ entradas) ao novo, tudo sincrono.
    pub fn tick(&self, est: &Estado, ent: &BTreeMap<String, bool>) -> (Estado, InfoTick) {
        let mut uf = self.rede(ent, &est.fis);
        let mut chars: HashMap<u32, BTreeSet<char>> = HashMap::new();
        for (no, ch) in &self.fixos {
            chars.entry(uf.raiz(*no)).or_default().insert(*ch);
        }
        let fases: BTreeSet<char> = FASES.into_iter().collect();
        let mut cpu_on = false;
        for c in &self.cpus {
            let sl: BTreeSet<char> = chars
                .get(&uf.raiz(c.l))
                .cloned()
                .unwrap_or_default()
                .intersection(&fases)
                .copied()
                .collect();
            let sn: BTreeSet<char> = chars
                .get(&uf.raiz(c.n))
                .cloned()
                .unwrap_or_default()
                .intersection(&fases)
                .copied()
                .collect();
            if !sl.is_empty() && !sn.is_empty() && sl != sn {
                cpu_on = true;
                chars.entry(uf.raiz(c.mais)).or_default().insert('+');
                chars.entry(uf.raiz(c.menos)).or_default().insert('-');
            }
        }
        for (op, no) in &self.sai_clp {
            if est.bits.get(op).copied().unwrap_or(false) {
                chars.entry(uf.raiz(*no)).or_default().insert('+');
            }
        }
        let energ = |uf: &mut Uf, chars: &HashMap<u32, BTreeSet<char>>, a: u32, b: u32| -> bool {
            let sa: BTreeSet<char> = chars
                .get(&uf.raiz(a))
                .cloned()
                .unwrap_or_default()
                .into_iter()
                .filter(|c| *c != 'P')
                .collect();
            let sb: BTreeSet<char> = chars
                .get(&uf.raiz(b))
                .cloned()
                .unwrap_or_default()
                .into_iter()
                .filter(|c| *c != 'P')
                .collect();
            !sa.is_empty() && !sb.is_empty() && sa != sb
        };
        let mut novo_fis = BTreeMap::new();
        for (k, v) in &self.bobinas {
            novo_fis.insert(
                k.clone(),
                v.iter().any(|(a, b)| energ(&mut uf, &chars, *a, *b)),
            );
        }
        let lamp: Vec<String> = self
            .lampadas
            .keys()
            .filter(|k| {
                self.lampadas[*k]
                    .iter()
                    .any(|(a, b)| energ(&mut uf, &chars, *a, *b))
            })
            .cloned()
            .collect();
        let mut curtos: Vec<String> = chars
            .values()
            .filter(|s| {
                s.iter().filter(|c| **c != 'P').count() > 1
                    || (s.contains(&'P') && s.iter().any(|c| ['1', '2', '3', '+', '-'].contains(c)))
            })
            .map(|s| {
                let mut v: Vec<char> = s.iter().copied().collect();
                v.sort();
                v.into_iter()
                    .map(|c| c.to_string())
                    .collect::<Vec<_>>()
                    .join("+")
            })
            .collect();
        curtos.sort();
        let mut nb = est.bits.clone();
        for (op, no) in &self.ent_clp {
            nb.insert(
                op.clone(),
                chars.get(&uf.raiz(*no)).is_some_and(|s| s.contains(&'+')),
            );
        }
        // ladder: '+' direcional a partir das nets com '+' (contatos com os bits do tick anterior)
        let mut mais: HashSet<u32> = chars
            .iter()
            .filter(|(_, s)| s.contains(&'+'))
            .map(|(r, _)| *r)
            .collect();
        loop {
            let mut mudou = false;
            for c in &self.ladder {
                let bit = est.bits.get(&c.op).copied().unwrap_or(false);
                let anterior = est.prev.get(&c.op).copied().unwrap_or(false);
                let fech = match c.flanco {
                    None => {
                        if c.na {
                            bit
                        } else {
                            !bit
                        }
                    }
                    Some(sobe) => (bit == sobe) && (anterior != sobe),
                };
                if fech && mais.contains(&uf.raiz(c.a)) && !mais.contains(&uf.raiz(c.b)) {
                    mais.insert(uf.raiz(c.b));
                    mudou = true;
                }
            }
            for t in &self.tons {
                let ligado = if t.kind == 'F' {
                    mais.contains(&uf.raiz(t.a)) || est.acc[t.idx] > 0
                } else {
                    est.acc[t.idx] >= t.t
                };
                if ligado && !mais.contains(&uf.raiz(t.b)) {
                    mais.insert(uf.raiz(t.b));
                    mudou = true;
                }
            }
            for t in &self.contadores {
                let cu = mais.contains(&uf.raiz(t.c));
                let prev_cu = est.cnt_v.get(t.idx).copied().unwrap_or(false);
                let novo = if mais.contains(&uf.raiz(t.r)) {
                    0
                } else {
                    (est.cnt[t.idx] + i64::from(cu && !prev_cu)).min(99999)
                };
                if novo >= t.preset && !mais.contains(&uf.raiz(t.q)) {
                    mais.insert(uf.raiz(t.q));
                    mudou = true;
                }
            }
            if !mudou {
                break;
            }
        }
        let menos: HashSet<u32> = chars
            .iter()
            .filter(|(_, s)| s.contains(&'-'))
            .map(|(r, _)| *r)
            .collect();
        let mut sets = BTreeSet::new();
        let mut rsts = BTreeSet::new();
        let mut outs: BTreeMap<String, bool> = BTreeMap::new();
        for b in &self.bob_ladder {
            let v = mais.contains(&uf.raiz(b.a)) && (!b.b_ligado || menos.contains(&uf.raiz(b.b)));
            if b.tipo == 'O' {
                outs.insert(b.op.clone(), outs.get(&b.op).copied().unwrap_or(false) || v);
            } else if v {
                (if b.tipo == 'S' { &mut sets } else { &mut rsts }).insert(b.op.clone());
            }
        }
        for (op, v) in &outs {
            nb.insert(op.clone(), *v);
        }
        for op in &sets {
            nb.insert(op.clone(), true);
        }
        for op in &rsts {
            nb.insert(op.clone(), false);
        }
        let mut nacc = est.acc.clone();
        for t in &self.tons {
            nacc[t.idx] = if mais.contains(&uf.raiz(t.a)) {
                if t.kind == 'F' { t.t } else { (est.acc[t.idx] + 1).min(t.t) }
            } else if t.kind == 'F' {
                (est.acc[t.idx] - 1).max(0)
            } else {
                0
            };
        }
        for t in &self.tons {
            nb.insert(t.op.clone(), false);
        }
        for t in &self.tons {
            // bit do timer: TON acc >= T; TOF IN ou acc > 0 (mesmo label em varios: OU)
            let ligado = if t.kind == 'F' {
                mais.contains(&uf.raiz(t.a)) || est.acc[t.idx] > 0
            } else {
                nacc[t.idx] >= t.t
            };
            if ligado {
                nb.insert(t.op.clone(), true);
            }
        }
        let mut ncnt = est.cnt.clone();
        let mut ncnt_v = est.cnt_v.clone();
        ncnt.resize(self.contadores.len(), 0);
        ncnt_v.resize(self.contadores.len(), false);
        for t in &self.contadores {
            let cu = mais.contains(&uf.raiz(t.c));
            let anterior = est.cnt_v.get(t.idx).copied().unwrap_or(false);
            ncnt[t.idx] = if mais.contains(&uf.raiz(t.r)) {
                0
            } else {
                (est.cnt.get(t.idx).copied().unwrap_or(0) + i64::from(cu && !anterior)).min(99999)
            };
            ncnt_v[t.idx] = cu;
            nb.insert(t.op.clone(), ncnt[t.idx] >= t.preset);
        }
        (
            Estado {
                bits: nb,
                prev: est.bits.clone(),
                fis: novo_fis,
                acc: nacc,
                cnt: ncnt,
                cnt_v: ncnt_v,
            },
            InfoTick {
                lampadas: lamp,
                curtos,
                cpu: cpu_on,
                indefinido: sets.intersection(&rsts).cloned().collect(),
            },
        )
    }

    fn assin(est: &Estado) -> Assinatura {
        (
            est.bits.iter().map(|(k, v)| (k.clone(), *v)).collect(),
            est.fis.iter().map(|(k, v)| (k.clone(), *v)).collect(),
            est.acc.clone(),
            est.prev.iter().map(|(k, v)| (k.clone(), *v)).collect(),
            est.cnt.clone(),
            est.cnt_v.clone(),
        )
    }

    fn resumo(&self, est: &Estado, info: &InfoTick, status: &str, ticks: Option<i64>) -> Resumo {
        Resumo {
            status: status.to_string(),
            bobinas: est
                .fis
                .iter()
                .filter(|(_, v)| **v)
                .map(|(k, _)| k.clone())
                .collect(),
            lampadas: info.lampadas.clone(),
            bits: est.bits.clone(),
            curtos: info.curtos.clone(),
            cpu: info.cpu,
            ticks,
        }
    }

    /// Exatamente `ticks` ticks (0 = so le o estado atual).
    pub fn rodar(
        &self,
        ent: &BTreeMap<String, bool>,
        ticks: i64,
        est: Option<Estado>,
    ) -> (Estado, Resumo) {
        let mut est = est.unwrap_or_else(|| self.estado_zero(&[]));
        let mut indef = BTreeSet::new();
        let (_, mut info) = self.tick(&est, ent);
        for _ in 0..ticks.max(0) {
            let (novo, info2) = self.tick(&est, ent);
            est = novo;
            indef.extend(info2.indefinido.iter().cloned());
            info = info2;
        }
        let st = if !info.curtos.is_empty() {
            "CURTO"
        } else if !indef.is_empty() {
            "INDEFINIDO"
        } else {
            "OK"
        };
        let r = self.resumo(&est, &info, st, Some(ticks));
        (est, r)
    }

    /// Roda ate (bits, fisico, acc) ficarem iguais por 2 ticks seguidos. Ciclo -> OSCILA.
    pub fn regime(
        &self,
        ent: &BTreeMap<String, bool>,
        est: Option<Estado>,
        max_ticks: usize,
    ) -> (Estado, Resumo) {
        let mut est = est.unwrap_or_else(|| self.estado_zero(&[]));
        let mut vistos: HashSet<Assinatura> = HashSet::new();
        vistos.insert(Self::assin(&est));
        let (mut estavel, mut indef) = (0, BTreeSet::new());
        let mut info = InfoTick {
            lampadas: vec![],
            curtos: vec![],
            cpu: false,
            indefinido: vec![],
        };
        for i in 1..=max_ticks.max(1) {
            let (novo, info2) = self.tick(&est, ent);
            indef.extend(info2.indefinido.iter().cloned());
            let mesmo = Self::assin(&novo) == Self::assin(&est);
            est = novo;
            info = info2;
            if mesmo {
                estavel += 1;
                if estavel >= 2 {
                    let st = if !info.curtos.is_empty() {
                        "CURTO"
                    } else if !indef.is_empty() {
                        "INDEFINIDO"
                    } else {
                        "OK"
                    };
                    let r = self.resumo(&est, &info, st, Some(i as i64));
                    return (est, r);
                }
                continue;
            }
            estavel = 0;
            let a = Self::assin(&est);
            if vistos.contains(&a) {
                let r = self.resumo(&est, &info, "OSCILA", Some(i as i64));
                return (est, r);
            }
            vistos.insert(a);
        }
        let r = self.resumo(&est, &info, "OSCILA", Some(max_ticks as i64));
        (est, r)
    }

    /// t=0 (`docs/ladder.md` §3.1): bits = inicial + entradas com o hardware em repouso
    /// (botoes soltos, disjuntores/termicos como no 1o passo); fisicos = saidas avaliadas
    /// com esses bits.
    pub fn imagem_inicial(&self, caso: &Value) -> Estado {
        let ini: HashSet<String> = caso
            .get("inicial")
            .and_then(|v| v.as_array())
            .map(|a| {
                a.iter()
                    .filter_map(|s| s.as_str())
                    .map(String::from)
                    .collect()
            })
            .unwrap_or_default();
        let mut est = self.estado_zero(&ini.iter().cloned().collect::<Vec<_>>());
        let primeira = primeira_entrada(caso);
        let ent: BTreeMap<String, bool> = primeira
            .into_iter()
            .filter(|(k, _)| self.alternaveis.contains(k))
            .collect();
        let (e1, _) = self.tick(&est, &ent);
        for (op, _) in &self.ent_clp {
            est.bits.insert(
                op.clone(),
                ini.contains(op) || e1.bits.get(op).copied().unwrap_or(false),
            );
        }
        let (e2, _) = self.tick(&est, &ent);
        for k in self.bobinas.keys().cloned().collect::<Vec<_>>() {
            let v = ini.contains(&k) || e2.fis.get(&k).copied().unwrap_or(false);
            est.fis.insert(k, v);
        }
        est.prev = est.bits.clone();
        for t in &self.tons {
            if ini.contains(&t.op) {
                est.acc[t.idx] = t.t;
            }
        }
        for t in &self.contadores {
            if ini.contains(&t.op) {
                if let Some(c) = est.cnt.get_mut(t.idx) {
                    *c = t.preset;
                }
            }
        }
        est
    }

    /// Saidas 10205 com bit 1 no estado assentado (para a conformidade).
    pub fn saidas_energizadas(&self, est: &Estado) -> Vec<String> {
        let mut v: Vec<String> = self
            .sai_clp
            .iter()
            .filter(|(op, _)| est.bits.get(op).copied().unwrap_or(false))
            .map(|(op, _)| op.clone())
            .collect();
        v.sort();
        v.dedup();
        v
    }
}

// --------------------------------------------------------------------------- casos

/// `primeira_entrada` do Python: entradas do 1o passo (ou do caso).
fn primeira_entrada(caso: &Value) -> BTreeMap<String, bool> {
    let seq = caso
        .get("sequencia")
        .or_else(|| caso.get("passos"))
        .and_then(|v| v.as_array());
    let fonte = seq
        .and_then(|s| s.first())
        .and_then(|p| p.get("entradas"))
        .or_else(|| caso.get("entradas"));
    entradas_bool(fonte.unwrap_or(&Value::Null))
}

fn entradas_bool(v: &Value) -> BTreeMap<String, bool> {
    let mut e = BTreeMap::new();
    if let Some(o) = v.as_object() {
        for (k, x) in o {
            e.insert(
                k.clone(),
                match x {
                    Value::Bool(b) => *b,
                    Value::Number(n) => n.as_f64().unwrap_or(0.0) != 0.0,
                    _ => false,
                },
            );
        }
    }
    e
}

fn lista_str(v: Option<&Value>) -> Vec<String> {
    v.and_then(|x| x.as_array())
        .map(|a| {
            a.iter()
                .filter_map(|s| s.as_str())
                .map(String::from)
                .collect()
        })
        .unwrap_or_default()
}

fn ticks_do_passo(p: &Value) -> Option<i64> {
    if let Some(n) = p.get("ticks").and_then(|v| v.as_i64()) {
        return Some(n);
    }
    if let Some(n) = p.get("ticks").and_then(|v| v.as_f64()) {
        return Some(n as i64);
    }
    p.get("tempo_s")
        .and_then(|v| v.as_f64())
        .map(|s| (s * 10.0).round() as i64)
}

/// Falhas (lista de strings) de um passo/caso contra o resultado `r` (`confere` do Python).
pub fn confere(p: &Value, r: &Resumo) -> Vec<String> {
    let mut falhas = Vec::new();
    if let Some(status) = p.get("status").and_then(|s| s.as_str()) {
        if r.status != status {
            falhas.push(format!("status {} != {status}", r.status));
        }
    }
    if let Some(esp) = p.get("esperado").and_then(|v| v.as_array()) {
        let mut quero: Vec<String> = esp
            .iter()
            .filter_map(|s| s.as_str())
            .map(nome_fisico)
            .collect();
        quero.sort();
        if r.bobinas != quero {
            falhas.push(format!(
                "bobinas {} != {}",
                repr_lista(&r.bobinas),
                repr_lista(&quero)
            ));
        }
    }
    if let Some(esp) = p.get("esperado_lampadas").and_then(|v| v.as_array()) {
        let mut quero: Vec<String> = esp
            .iter()
            .filter_map(|s| s.as_str())
            .map(nome_fisico)
            .collect();
        quero.sort();
        if r.lampadas != quero {
            falhas.push(format!(
                "lampadas {} != {}",
                repr_lista(&r.lampadas),
                repr_lista(&quero)
            ));
        }
    }
    if let Some(obj) = p.get("esperado_bits").and_then(|v| v.as_object()) {
        for (op, v) in obj {
            let tem = r.bits.get(op).copied().unwrap_or(false);
            let quero = matches!(v, Value::Bool(true))
                || v.as_i64().is_some_and(|n| n != 0)
                || v.as_f64().is_some_and(|f| f != 0.0);
            if tem != quero {
                falhas.push(format!("bit {op}={} (esperado {})", tem as u8, quero as u8));
            }
        }
    }
    falhas
}

/// Executa um caso (simples ou com `sequencia`) -> (falhas, resultado final, historico).
/// `sim` e o que tem `imagem_inicial`/`rodar`/`regime` (aqui, `&CircuitoClp`).
pub fn executar_caso(sim: &CircuitoClp, caso: &Value) -> (Vec<String>, Resumo, Vec<PassoHist>) {
    let mut est = sim.imagem_inicial(caso);
    let seq = caso
        .get("sequencia")
        .or_else(|| caso.get("passos"))
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    let mut hist = Vec::new();
    if !seq.is_empty() {
        let mut r = None;
        for (i, p) in seq.iter().enumerate() {
            let ent = entradas_bool(p.get("entradas").unwrap_or(&Value::Null));
            let (e2, r2) = match ticks_do_passo(p) {
                Some(n) => sim.rodar(&ent, n, Some(est)),
                None => sim.regime(&ent, Some(est), MAX_TICKS),
            };
            est = e2;
            let nome = p
                .get("nome")
                .and_then(|s| s.as_str())
                .unwrap_or(&format!("passo {}", i + 1))
                .to_string();
            let fs = confere(p, &r2);
            hist.push((nome, fs, r2.clone()));
            r = Some(r2);
        }
        let r = r.expect("sequencia nao vazia");
        let mut falhas: Vec<String> = Vec::new();
        for (nm, fs, _) in &hist {
            for f in fs {
                falhas.push(format!("{nm}: {f}"));
            }
        }
        if let Some(status) = caso.get("status").and_then(|s| s.as_str()) {
            for (nm, _, rr) in &hist {
                if rr.status != status {
                    falhas.push(format!("{nm}: status {} != {status}", rr.status));
                }
            }
        }
        return (falhas, r, hist);
    }
    let n = ticks_do_passo(caso);
    let ent = entradas_bool(caso.get("entradas").unwrap_or(&Value::Null));
    let (_, r) = match n {
        Some(t) => sim.rodar(&ent, t, Some(est)),
        None => sim.regime(&ent, Some(est), MAX_TICKS),
    };
    (confere(caso, &r), r, hist)
}

/// Chaves citadas pelo caso que nao existem no circuito (`chaves_invalidas` do Python).
pub fn chaves_invalidas(c: &CircuitoClp, caso: &Value) -> Vec<(String, String)> {
    let validas_ini: BTreeSet<String> = c
        .operandos
        .iter()
        .cloned()
        .chain(c.bobinas.keys().cloned())
        .collect();
    let esp_bob: BTreeSet<String> = c.bobinas.keys().cloned().collect();
    let esp_lamp: BTreeSet<String> = c.lampadas.keys().cloned().collect();
    let esp_bits: BTreeSet<String> = c.operandos.iter().cloned().collect();
    let seq = caso
        .get("sequencia")
        .or_else(|| caso.get("passos"))
        .and_then(|v| v.as_array());
    let mut blocos: Vec<&Value> = vec![caso];
    if let Some(s) = seq {
        blocos.extend(s.iter());
    }
    let mut ruim = Vec::new();
    for b in blocos {
        if let Some(o) = b.get("entradas").and_then(|e| e.as_object()) {
            for k in o.keys() {
                if !c.entradas.contains(k) {
                    ruim.push(("entradas".to_string(), k.clone()));
                }
            }
        }
        for k in lista_str(b.get("inicial")) {
            if !validas_ini.contains(&k) {
                ruim.push(("inicial".to_string(), k));
            }
        }
        for k in lista_str(b.get("esperado")) {
            if !esp_bob.contains(&nome_fisico(&k)) {
                ruim.push(("esperado".to_string(), k));
            }
        }
        for k in lista_str(b.get("esperado_lampadas")) {
            if !esp_lamp.contains(&nome_fisico(&k)) {
                ruim.push(("esperado_lampadas".to_string(), k));
            }
        }
        if let Some(o) = b.get("esperado_bits").and_then(|e| e.as_object()) {
            for k in o.keys() {
                if !esp_bits.contains(k) {
                    ruim.push(("esperado_bits".to_string(), k.clone()));
                }
            }
        }
    }
    ruim
}

/// Roda os casos e devolve (aprovado, texto) no formato de `clp_sim.teste_casos`.
pub fn teste_casos(sim: &CircuitoClp, casos: &[Value]) -> (bool, String) {
    let mut s = String::new();
    let mut ok = 0;
    for cs in casos {
        let (falhas, r, hist) = executar_caso(sim, cs);
        if falhas.is_empty() {
            ok += 1;
        }
        let on: Vec<String> = r
            .bits
            .iter()
            .filter(|(_, v)| **v)
            .map(|(k, _)| k.clone())
            .collect();
        let nome = cs.get("nome").and_then(|x| x.as_str()).unwrap_or("?");
        let esperado = if hist.is_empty() {
            repr(cs.get("esperado").unwrap_or(&Value::Null))
        } else {
            "(sequencia)".to_string()
        };
        s.push_str(&format!(
            "  [{}] {nome}: KM={} status={} esperado={esperado} lampadas={} bits1={}",
            if falhas.is_empty() { "OK " } else { "FALHA" },
            repr_lista(&r.bobinas),
            r.status,
            repr_lista(&r.lampadas),
            repr_lista(&on)
        ));
        if !falhas.is_empty() {
            s.push_str(&format!(" -- {}", falhas.join("; ")));
        }
        s.push('\n');
        for (nm, fs, rr) in &hist {
            s.push_str(&format!(
                "      - {nm}: KM={} lampadas={} ticks={}",
                repr_lista(&rr.bobinas),
                repr_lista(&rr.lampadas),
                rr.ticks.unwrap_or(0)
            ));
            if !fs.is_empty() {
                s.push_str(&format!(" -- {}", fs.join("; ")));
            }
            s.push('\n');
        }
    }
    s.push_str(&format!("RESULTADO: {ok}/{len} OK\n", len = casos.len()));
    (!casos.is_empty() && ok == casos.len(), s)
}
