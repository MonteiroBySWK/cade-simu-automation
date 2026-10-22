//! Port de `cade_mcp._assign_nets` e `_shorts`.

use crate::roteador::Ent;
use cade_model::dados::ClassePins;
use std::collections::HashMap;

type Pt = (i64, i64);

#[derive(Default)]
struct Uf {
    idx: HashMap<Pt, usize>,
    pai: Vec<usize>,
}

impl Uf {
    fn id(&mut self, p: Pt) -> usize {
        if let Some(&i) = self.idx.get(&p) {
            return i;
        }
        let i = self.pai.len();
        self.pai.push(i);
        self.idx.insert(p, i);
        i
    }
    fn find(&mut self, mut a: usize) -> usize {
        while self.pai[a] != a {
            self.pai[a] = self.pai[self.pai[a]];
            a = self.pai[a];
        }
        a
    }
    fn union(&mut self, a: Pt, b: Pt) {
        let (ia, ib) = (self.id(a), self.id(b));
        let (ra, rb) = (self.find(ia), self.find(ib));
        if ra != rb {
            self.pai[rb] = ra;
        }
    }
}

fn num(e: &Ent, i: usize) -> Result<i64, String> {
    e.nums
        .get(i)
        .ok_or_else(|| "list index out of range".to_string())?
        .parse::<i64>()
        .map_err(|_| format!("invalid literal for int() with base 10: {}", cade_model::pyfmt::repr_str(&e.nums[i])))
}

#[derive(Clone, Copy, PartialEq)]
enum Tag {
    Fio,
    A,
    B,
}

const IDS_FIO: [&str; 3] = ["4018", "4009", "4001"];

fn pin_pts(e: &Ent, pins: &HashMap<String, ClassePins>) -> Result<Vec<(Tag, Pt)>, String> {
    if e.id == "4000" || IDS_FIO.contains(&e.id.as_str()) {
        return Ok(vec![(Tag::Fio, (num(e, 8)?, num(e, 9)?)), (Tag::Fio, (num(e, 10)?, num(e, 11)?))]);
    }
    let (x, y) = (num(e, 8)?, num(e, 9)?);
    let mut out = vec![];
    if let Some(m) = pins.get(&e.id) {
        if let Some(a) = m.a {
            out.push((Tag::A, (x + a[0], y + a[1])));
        }
        if let Some(b) = m.b {
            out.push((Tag::B, (x + b[0], y + b[1])));
        }
    }
    Ok(out)
}

/// Calcula NETs por geometria e escreve `nums[21]`/`nums[22]` (A/B, ou net do fio).
pub fn assign_nets(ents: &mut [Ent], pins: &HashMap<String, ClassePins>) -> Result<(), String> {
    let mut uf = Uf::default();
    let mut ordem: Vec<Pt> = Vec::new(); // bycoord, na ordem de insercao
    let mut vistos: HashMap<Pt, ()> = HashMap::new();
    for e in ents.iter() {
        for (_, pt) in pin_pts(e, pins)? {
            if vistos.insert(pt, ()).is_none() {
                ordem.push(pt);
            }
            uf.id(pt);
        }
    }
    for e in ents.iter() {
        if e.id == "4000" {
            uf.union((num(e, 8)?, num(e, 9)?), (num(e, 10)?, num(e, 11)?));
        }
    }
    let mut raizes: HashMap<usize, i64> = HashMap::new();
    let mut nxt = 20;
    for &pt in &ordem {
        let i = uf.id(pt);
        let r = uf.find(i);
        raizes.entry(r).or_insert_with(|| {
            nxt += 1;
            nxt
        });
    }
    for e in ents.iter_mut() {
        let pts = pin_pts(e, pins)?;
        if e.id == "4000" {
            let i = uf.id((num(e, 8)?, num(e, 9)?));
            let r = uf.find(i);
            let net = raizes[&r];
            if e.nums.len() > 21 {
                e.nums[21] = net.to_string();
            }
            continue;
        }
        for (tag, pt) in pts {
            let i = uf.id(pt);
            let r = uf.find(i);
            let net = raizes[&r];
            let idx = if tag == Tag::A { 21 } else { 22 };
            if e.nums.len() > idx {
                e.nums[idx] = net.to_string();
            }
        }
    }
    Ok(())
}

/// Simbolos com o mesmo net em A e B (curto). Retorna os rotulos (ou ids).
///
/// 2002/6004 (`_SEM_PAR_AB` do Python): A/B do binario sao dois pinos vizinhos do TOPO (p1/p2),
/// nao um polo; com entradas em paralelo (reversao mono/4 polos) vao ao mesmo trilho por desenho.
pub fn shorts(ents: &[Ent]) -> Vec<String> {
    let mut bad = vec![];
    for e in ents {
        if ["4000", "4018", "4009", "4001", "2002", "6004"].contains(&e.id.as_str()) {
            continue;
        }
        let n = &e.nums;
        if n.len() > 22 && n[21] == n[22] && n[21] != "0" && !n[21].is_empty() {
            let lab = e.labels.first().cloned().unwrap_or_else(|| e.id.clone());
            bad.push(if lab.is_empty() { e.id.clone() } else { lab });
        }
    }
    bad
}
