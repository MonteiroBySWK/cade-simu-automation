//! Port literal de `cade_mcp._rotear` e auxiliares (`_pin_coord`, `_symboxes`, `_cruza`).

use cade_model::dados::{self, ClassePins};
use cade_model::pyfmt::{self, fdiv};
use cade_model::Proto;
use serde_json::Value;
use std::collections::{BTreeSet, HashMap};

/// Entidade em construcao (`{"id","labels","nums"}` do Python).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Ent {
    pub id: String,
    pub labels: Vec<String>,
    pub nums: Vec<String>,
}

impl Ent {
    pub fn serializar(&self, seq: &str) -> String {
        format!("*{}*{}#{}#*{}", seq, self.id, self.labels.join("#"), self.nums.join("*"))
    }
}

type Pt = (i64, i64);
type Caixa = (i64, i64, i64, i64);

struct Sim {
    classe: String,
    x: i64,
    y: i64,
}

fn pins_da(classe: &str) -> Option<&'static ClassePins> {
    dados::symbol_pins().get(classe)
}

/// `_pin_coord`: coordenada do pino (nomeado ou A/B) ou `None`.
fn pin_coord(s: &Sim, pino: &str) -> Option<Pt> {
    let off = pins_da(&s.classe)?.offset(pino)?;
    Some((s.x + off[0], s.y + off[1]))
}

const IDS_FIO: [&str; 6] = ["4000", "4018", "4009", "4001", "8", "4010"];

/// `_symboxes`: corpos dos simbolos (inset 2) para o keep-out.
fn symboxes(ents: &[Ent]) -> Vec<Caixa> {
    let mut out = Vec::new();
    for e in ents {
        if IDS_FIO.contains(&e.id.as_str()) {
            continue;
        }
        let g = |i: usize| e.nums.get(i).and_then(|s| s.parse::<i64>().ok());
        let (Some(x), Some(y), Some(w), Some(h)) = (g(8), g(9), g(14), g(15)) else { continue };
        if w > 4 && h > 4 {
            out.push((x + 2, y + 2, x + w - 2, y + h - 2));
        }
    }
    out
}

/// `_cruza`: o segmento atravessa o corpo de algum simbolo (fora da vizinhanca de `skip`)?
fn cruza(seg: (Pt, Pt), boxes: &[Caixa], skip: &[Pt]) -> bool {
    let ((x1, y1), (x2, y2)) = seg;
    let mut l = (x2 - x1).abs().max((y2 - y1).abs());
    if l == 0 {
        l = 1;
    }
    for i in 0..=l {
        let px = x1 + fdiv((x2 - x1) * i, l);
        let py = y1 + fdiv((y2 - y1) * i, l);
        if skip.iter().any(|&(a, b)| (px - a).abs() <= 4 && (py - b).abs() <= 4) {
            continue;
        }
        if boxes.iter().any(|b| b.0 < px && px < b.2 && b.1 < py && py < b.3) {
            return true;
        }
    }
    false
}

fn emit(ents: &mut Vec<Ent>, wire: &Proto, a: Pt, b: Pt) {
    if a == b {
        return;
    }
    let mut n = wire.nums.clone();
    n[8] = a.0.to_string();
    n[9] = a.1.to_string();
    n[10] = b.0.to_string();
    n[11] = b.1.to_string();
    for k in n.iter_mut().take(8) {
        *k = "0".into();
    }
    ents.push(Ent { id: "4000".into(), labels: wire.labels.clone(), nums: n });
}

struct Rail {
    nome: String,
    y: i64,
    x0: i64,
    x1: i64,
}

/// Par `[id, pino]` de uma conexao.
fn extremo(v: Option<&Value>) -> Option<(String, String)> {
    let a = v?.as_array()?;
    if a.is_empty() || (a.len() == 1) {
        return None;
    }
    Some((pyfmt::str_de(&a[0]), pyfmt::str_de(&a[1])))
}

fn truthy_opt(v: Option<&Value>) -> bool {
    v.map(pyfmt::verdadeiro).unwrap_or(false)
}

/// Liga pinos por nome (e a trilhos), emitindo fios 4000 em `ents`.
pub fn rotear(
    ents: &mut Vec<Ent>,
    simbolos: &[Value],
    conexoes: &[Value],
    wire: &Proto,
    rails: &[Value],
) -> Result<(), String> {
    // trilhos: dict (a chave repetida mantem a 1a posicao e o ultimo valor)
    let mut rail_map: Vec<Rail> = Vec::new();
    for r in rails {
        let get = |k: &str| -> Result<&Value, String> {
            r.get(k).ok_or_else(|| format!("campo obrigatorio ausente: '{}'", k))
        };
        let nome = pyfmt::str_de(get("nome")?);
        let nr = Rail { nome: nome.clone(), y: pyfmt::int(get("y")?)?, x0: pyfmt::int(get("x0")?)?, x1: pyfmt::int(get("x1")?)? };
        match rail_map.iter().position(|q| q.nome == nome) {
            Some(i) => rail_map[i] = nr,
            None => rail_map.push(nr),
        }
    }
    let mut vert: HashMap<String, BTreeSet<i64>> = rail_map
        .iter()
        .map(|r| (r.nome.clone(), BTreeSet::from([r.x0, r.x1])))
        .collect();
    let mut byid: HashMap<String, Sim> = HashMap::new();
    for (i, s) in simbolos.iter().enumerate() {
        let key = match (s.get("id"), s.get("rotulo")) {
            (Some(v), _) if pyfmt::verdadeiro(v) => pyfmt::str_de(v),
            (_, Some(v)) if pyfmt::verdadeiro(v) => pyfmt::str_de(v),
            _ => format!("#{}", i),
        };
        let classe = pyfmt::str_de(s.get("classe").ok_or("campo obrigatorio ausente: 'classe'")?);
        let x = pyfmt::int(s.get("x").ok_or("campo obrigatorio ausente: 'x'")?)?;
        let y = pyfmt::int(s.get("y").ok_or("campo obrigatorio ausente: 'y'")?)?;
        byid.insert(key, Sim { classe, x, y });
    }
    let idx_rail = |rm: &Vec<Rail>, n: &str| rm.iter().position(|r| r.nome == n);

    for (idx, c) in conexoes.iter().enumerate() {
        let erro = || format!("ERRO conexão inválida: {}", pyfmt::repr(c));
        let de_v = c.get("de");
        let para_v = c.get("para");
        if !truthy_opt(de_v) || !truthy_opt(para_v) {
            return Err(erro());
        }
        let de = extremo(de_v).ok_or_else(|| "list index out of range".to_string())?;
        let para = extremo(para_v).ok_or_else(|| "list index out of range".to_string())?;
        // 1) ligacao a TRILHO
        let mut feito = false;
        for (lado_v, outro_v) in [(&de, &para), (&para, &de)] {
            let Some(ri) = idx_rail(&rail_map, &lado_v.0) else { continue };
            let Some(s) = byid.get(&outro_v.0) else { continue };
            let Some(p1) = pin_coord(s, &outro_v.1) else {
                return Err(format!("ERRO: sem geometria p/ {}.{}", outro_v.0, outro_v.1));
            };
            let ry = rail_map[ri].y;
            let off = pins_da(&s.classe).and_then(|i| i.offset(&outro_v.1)).unwrap_or([0, 0]);
            let s_esc = if off[1] <= 0 { -1 } else { 1 };
            let e1 = (p1.0, p1.1 + s_esc * 7);
            emit(ents, wire, p1, e1);
            // RETO: coluna do pino livre ate o trilho
            let boxes0 = symboxes(ents);
            if !cruza((e1, (e1.0, ry)), &boxes0, &[p1, e1]) {
                emit(ents, wire, e1, (e1.0, ry));
                vert.get_mut(&lado_v.0).unwrap().insert(e1.0);
                feito = true;
                break;
            }
            let via = match c.get("via") {
                None | Some(Value::Null) => {
                    let boxes = symboxes(ents);
                    let mut xm = e1.0 + 8;
                    for _ in 0..24 {
                        let (lo, hi) = (e1.1.min(ry), e1.1.max(ry));
                        let bate = boxes.iter().any(|b| {
                            b.0 - 2 <= xm && xm <= b.2 + 2 && 2 * (lo - 2) <= b.1 + b.3 && b.1 + b.3 <= 2 * (hi + 2)
                        });
                        if !bate {
                            break;
                        }
                        xm += 6;
                    }
                    xm
                }
                Some(v) => pyfmt::int(v)?,
            };
            emit(ents, wire, e1, (via, e1.1));
            emit(ents, wire, (via, e1.1), (via, ry));
            vert.get_mut(&lado_v.0).unwrap().insert(via);
            feito = true;
            break;
        }
        if feito {
            continue;
        }
        let (Some(s_de), Some(s_para)) = (byid.get(&de.0), byid.get(&para.0)) else {
            return Err(format!("{} (confira os ids)", erro()));
        };
        let (p1, p2) = (pin_coord(s_de, &de.1), pin_coord(s_para, &para.1));
        let (Some(p1), Some(p2)) = (p1, p2) else {
            return Err(format!(
                "ERRO: sem geometria de pino p/ classe {} (ou pino '{}'). Use fios_json manual ou outra classe.",
                s_de.classe, de.1
            ));
        };
        let (x1, y1) = p1;
        let (x2, y2) = p2;
        let topo_y = |cl: &str, pino: &str| pins_da(cl).and_then(|i| i.topo(pino)).map(|o| o[1]).unwrap_or(0);
        let d1 = topo_y(&s_de.classe, &de.1);
        let d2 = topo_y(&s_para.classe, &para.1);
        let s1 = if d1 <= 0 { -1 } else { 1 };
        let s2 = if d2 <= 0 { -1 } else { 1 };
        let g = 7;
        let pts: Vec<Pt> = if x1 == x2 && !cruza((p1, p2), &symboxes(ents), &[p1, p2]) {
            vec![p1, p2]
        } else {
            let a1 = (x1, y1 + s1 * g);
            let b1 = (x2, y2 + s2 * g);
            let mut pts = vec![(x1, y1), a1];
            if s1 == s2 {
                if a1.1 != b1.1 {
                    pts.push((x2, a1.1));
                }
            } else {
                let boxes = symboxes(ents);
                let passo = if x2 >= x1 { 1 } else { -1 };
                let mut xm = x2 + (10 + 3 * (idx as i64 % 4)) * passo;
                let (lo, hi) = (a1.1.min(b1.1), a1.1.max(b1.1));
                for _ in 0..12 {
                    let bate = boxes.iter().any(|b| {
                        b.0 - 2 <= xm && xm <= b.2 + 2 && 2 * (lo - 2) <= b.1 + b.3 && b.1 + b.3 <= 2 * (hi + 2)
                    });
                    if !bate {
                        break;
                    }
                    xm += 6 * passo;
                }
                pts.push((xm, a1.1));
                pts.push((xm, b1.1));
            }
            pts.push(b1);
            pts.push((x2, y2));
            pts
        };
        for w in pts.windows(2) {
            emit(ents, wire, w[0], w[1]);
        }
    }
    // 2) trilhos em segmentos (vertice em cada conexao -> nets fecham)
    for r in &rail_map {
        let xs: Vec<i64> = vert[&r.nome].iter().copied().collect();
        for w in xs.windows(2) {
            emit(ents, wire, (w[0], r.y), (w[1], r.y));
        }
    }
    Ok(())
}
