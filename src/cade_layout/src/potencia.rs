//! Grupos de potencia (`_potencia`, `_estagio`, `_tops_bots`, `_pot_largura`): estagios em cascata,
//! contatores em paralelo (trilhos auxiliares `<id>_e1..`/`<id>_s1..`) e inversao de fases (`ordem`).

use crate::{dim, get, int_of, lista, pin_off, req, str_or, t_de, tipo, val, width, Layout, Rail, GAP, PHASE_DX, R};
use cade_model::dados;
use cade_model::pyfmt;
use serde_json::Value;
use std::collections::HashMap;

/// Membro de um estagio: (id, classe, rotulo, ordem de fases).
type Membro = (String, String, String, Option<Vec<String>>);

/// `_estagio`: `[id,cls,rot]` | `[id,cls,rot,{"ordem":[..]}]` | `{"paralelo":[item,..]}`.
fn estagio(c: &Value) -> R<Vec<Membro>> {
    if let Value::Object(_) = c {
        let mut out = Vec::new();
        let itens = req(c, "paralelo")?;
        for m in itens.as_array().ok_or_else(|| tipo("'paralelo' deve ser lista".into()))? {
            out.extend(estagio(m)?);
        }
        return Ok(out);
    }
    let (sid, cl, rot) = t_de(c)?;
    let mut ordem = None;
    if let Some(a) = c.as_array() {
        if a.len() > 3 {
            if let Value::Object(_) = &a[3] {
                if let Some(o) = get(&a[3], "ordem").and_then(|v| v.as_array()).filter(|o| !o.is_empty()) {
                    ordem = Some(o.iter().map(pyfmt::str_de).collect());
                }
            }
        }
    }
    Ok(vec![(sid, cl, rot, ordem)])
}

/// `_tops_bots`: (pinos de topo, pinos de base, PE) por fase.
fn tops_bots(classe: &str) -> (Vec<String>, Vec<String>, Option<String>) {
    let vazio = Default::default();
    let pins = dados::symbol_pins().get(classe).map(|i| &i.pins).unwrap_or(&vazio);
    let sel = |ns: &[&str]| -> Vec<String> { ns.iter().filter(|p| pins.contains_key(**p)).map(|p| p.to_string()).collect() };
    if pins.contains_key("U1") {
        return (sel(&["U1", "V1", "W1"]), vec![], if pins.contains_key("PE") { Some("PE".into()) } else { None });
    }
    (sel(&["1", "3", "5"]), sel(&["2", "4", "6"]), None)
}

/// `_pot_largura`: largura estimada de um grupo de potencia.
pub(crate) fn largura(pw: &Value) -> R<i64> {
    let nf = match lista(pw.get("fases")).len() {
        0 => 3,
        n => n as i64,
    };
    let mut mx = 0;
    for c in lista(pw.get("colunas")) {
        let est = estagio(c)?;
        let soma: i64 = est.iter().map(|(_, cl, _, _)| width(cl).max(PHASE_DX * (nf - 1) + 1) + GAP).sum();
        mx = mx.max(soma - GAP);
    }
    Ok(mx)
}

fn idx_fase(fases: &[String], f: &str) -> R<usize> {
    fases
        .iter()
        .position(|x| x == f)
        .ok_or_else(|| val(format!("{} is not in list", pyfmt::repr_str(f))))
}

fn pino_i(v: &[String], i: usize) -> R<&String> {
    v.get(i).ok_or_else(|| val("list index out of range".into()))
}

fn mk_rails(l: &mut Layout, pid: &str, prefixo: &str, ys: &[i64], xs_por_fase: &[Vec<i64>]) -> Vec<String> {
    let mut nomes = Vec::new();
    for (i, yy) in ys.iter().enumerate() {
        let nm = format!("{}_{}{}", pid, prefixo, i + 1);
        let xs = &xs_por_fase[i];
        l.rails.push(Rail { nome: nm.clone(), y: *yy, x0: *xs.iter().min().unwrap(), x1: *xs.iter().max().unwrap() });
        nomes.push(nm);
    }
    nomes
}

pub(crate) fn potencia(l: &mut Layout, pw: &Value, x: i64, y0: i64) -> R<i64> {
    let fases: Vec<String> = req(pw, "fases")?
        .as_array()
        .ok_or_else(|| tipo("'fases' deve ser lista".into()))?
        .iter()
        .map(pyfmt::str_de)
        .collect();
    let neutro = str_or(pw, "neutro", "N");
    let mut estagios = Vec::new();
    for c in req(pw, "colunas")?.as_array().ok_or_else(|| tipo("'colunas' deve ser lista".into()))? {
        estagios.push(estagio(c)?);
    }
    let nf = fases.len();
    let pid = str_or(pw, "id", "P");
    let mut src: Vec<(String, String)> = fases.iter().map(|f| (f.clone(), "rail".to_string())).collect();
    let mut src_y: i64 = 0;
    let mut src_direto = false;
    let mut src_x: Vec<i64> = Vec::new();
    let mut y = y0;
    let mut xend = x;
    let _ = int_of;

    for est in &estagios {
        let n = est.len();
        // --- posicao dos membros ---
        let mut xs_m = Vec::new();
        let mut xc = x;
        for (_, cl, _, _) in est {
            xs_m.push(xc);
            xc += width(cl).max(PHASE_DX * (nf as i64 - 1) + 1) + GAP;
        }
        // --- trilhos de entrada se >1 membro vem de pinos de um simbolo ---
        if n > 1 && src_direto {
            let ry: Vec<i64> = (0..nf).map(|i| src_y + 11 + 6 * i as i64).collect();
            let pxs = src_x.clone();
            let mut tops: HashMap<usize, Vec<i64>> = HashMap::new();
            for (mi, (_sid, cl, _rot, ordem)) in est.iter().enumerate() {
                let (top, _, _) = tops_bots(cl);
                for pi in 0..nf {
                    let fi = match ordem {
                        Some(o) => idx_fase(&fases, o.get(pi).ok_or_else(|| val("list index out of range".into()))?)?,
                        None => pi,
                    };
                    let off = pin_off(cl, pino_i(&top, pi)?)?;
                    tops.entry(fi).or_default().push(xs_m[mi] + off[0]);
                }
            }
            let xs: Vec<Vec<i64>> = (0..nf)
                .map(|i| {
                    let mut v = vec![pxs[i]];
                    v.extend(tops.get(&i).cloned().unwrap_or_default());
                    v
                })
                .collect();
            let nomes = mk_rails(l, &pid, "e", &ry, &xs);
            for i in 0..nf {
                l.con((src[i].0.as_str(), src[i].1.as_str()), (nomes[i].as_str(), "rail"));
            }
            src = nomes.iter().map(|nm| (nm.clone(), "rail".to_string())).collect();
            y = ry[nf - 1] + 10;
        }
        // --- coloca membros ---
        let mut ult_bots: Vec<(String, String, Vec<String>)> = Vec::new();
        for (mi, (sid, cl, rot, ordem)) in est.iter().enumerate() {
            let (top, bot, pe) = tops_bots(cl);
            if top.len() < nf {
                return Err(val(format!("{} ({}) tem {} pinos de topo < {} fases", sid, cl, top.len(), nf)));
            }
            l.sym(sid, cl, rot, xs_m[mi], y)?;
            for pi in 0..nf {
                let fi = match ordem {
                    Some(o) => idx_fase(&fases, o.get(pi).ok_or_else(|| val("list index out of range".into()))?)?,
                    None => pi,
                };
                let s = &src[fi];
                l.con((s.0.as_str(), s.1.as_str()), (sid.as_str(), top[pi].as_str()));
            }
            if let Some(pe) = pe {
                let alvo = match get(pw, "pe") {
                    Some(v) => pyfmt::str_de(v),
                    None => neutro.clone(),
                };
                l.con((sid.as_str(), pe.as_str()), (alvo.as_str(), "rail"));
            }
            ult_bots.push((sid.clone(), cl.clone(), bot));
            xend = xend.max(xs_m[mi] + width(cl).max(PHASE_DX * (nf as i64 - 1) + 1));
        }
        let h = est.iter().map(|(_, cl, _, _)| dim(cl).1).max().unwrap();
        let bots = ult_bots[0].2.clone();
        if bots.is_empty() {
            break; // motor: fim da cascata
        }
        // --- saida do estagio ---
        let yb = y + pin_off(&est[0].1, &bots[0])?[1];
        if n == 1 {
            let sid = &est[0].0;
            let mut s = Vec::new();
            for i in 0..nf {
                s.push((sid.clone(), pino_i(&bots, i)?.clone()));
            }
            src = s;
            src_direto = true;
            src_x = (0..nf)
                .map(|i| Ok(xs_m[0] + pin_off(&est[0].1, pino_i(&bots, i)?)?[0]))
                .collect::<R<Vec<i64>>>()?;
            src_y = yb;
            y += h + 20;
        } else {
            let ry: Vec<i64> = (0..nf).map(|i| yb + 11 + 6 * i as i64).collect();
            let mut xs: Vec<Vec<i64>> = Vec::new();
            for i in 0..nf {
                let mut v = Vec::new();
                for (mi, (_s, cl, b)) in ult_bots.iter().enumerate() {
                    v.push(xs_m[mi] + pin_off(cl, pino_i(b, i)?)?[0]);
                }
                xs.push(v);
            }
            // o proximo estagio (alinhado ao 1o membro) tambem toca o trilho
            for (i, v) in xs.iter_mut().enumerate() {
                v.push(xs_m[0] + PHASE_DX * i as i64);
            }
            let nomes = mk_rails(l, &pid, "s", &ry, &xs);
            for (sid, _cl, b) in &ult_bots {
                for i in 0..nf {
                    l.con((sid.as_str(), pino_i(b, i)?.as_str()), (nomes[i].as_str(), "rail"));
                }
            }
            src = nomes.iter().map(|nm| (nm.clone(), "rail".to_string())).collect();
            src_direto = false;
            y = ry[nf - 1] + 10;
        }
    }
    Ok(xend)
}
