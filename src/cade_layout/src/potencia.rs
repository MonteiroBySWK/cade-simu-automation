//! Grupos de potencia (`_potencia`, `_potencia_mono`, `_estagio`, `_tops_bots`, `_pot_largura`):
//! estagios em cascata, contatores em paralelo (trilhos auxiliares `<id>_e1..`/`<id>_s1..`),
//! inversao de fases (`ordem`), `polos: 4` (o 4o polo comuta o neutro, com bypass do N nos
//! estagios de 3 polos) e `tipo: "monofasico"` (Q 2 polos -> 2x2002 -> motor 1008).

use crate::{dim, get, lista, pin_off, req, str_or, t_de, val, width, Layout, Rail, GAP, PHASE_DX, R};
use cade_model::dados;
use cade_model::pyfmt::{repr_lista, str_de, verdadeiro};
use serde_json::Value;
use std::collections::HashMap;

/// Membro de um estagio: (id, classe, rotulo, ordem de fases).
type Membro = (String, String, String, Option<Vec<String>>);

/// `_estagio`: `[id,cls,rot]` | `[id,cls,rot,{"ordem":[..]}]` | `{"paralelo":[item,..]}`.
fn estagio(c: &Value) -> R<Vec<Membro>> {
    if let Value::Object(_) = c {
        let mut out = Vec::new();
        let itens = req(c, "paralelo")?;
        for m in itens.as_array().ok_or_else(|| crate::tipo("'paralelo' deve ser lista".into()))? {
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
                    ordem = Some(o.iter().map(str_de).collect());
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
    if pins.contains_key("1") {
        return (sel(&["1", "3", "5", "7"]), sel(&["2", "4", "6", "8"]), None);
    }
    if classe == "1008" {
        // motor monofasico (doador: U1=p1, V1=p2, PE=p3, U2=p4, V2=p5)
        return (vec!["p1".into(), "p2".into()], vec!["p4".into(), "p5".into()], Some("p3".into()));
    }
    if classe == "2002" || classe == "6004" {
        // contator/disjuntor 4 polos (nomes p1..p8 do binario)
        return (
            vec!["p1".into(), "p2".into(), "p3".into(), "p4".into()],
            vec!["p5".into(), "p6".into(), "p7".into(), "p8".into()],
            None,
        );
    }
    (sel(&["1", "3", "5"]), sel(&["2", "4", "6"]), None)
}

/// `_classes_colunas`: classes citadas nas colunas de um grupo de potencia (um nivel; inclui paralelo).
fn classes_colunas(pw: &Value) -> Vec<String> {
    let mut out = Vec::new();
    for c in lista(pw.get("colunas")) {
        match c {
            Value::Object(_) => {
                for m in lista(c.get("paralelo")) {
                    if let Some(a) = m.as_array() {
                        if a.len() > 1 {
                            out.push(str_de(&a[1]));
                        }
                    }
                }
            }
            Value::Array(a) if a.len() > 1 => out.push(str_de(&a[1])),
            _ => {}
        }
    }
    out
}

/// `pw.get("id")` como o Python imprimiria (`None` quando ausente).
fn id_bruto(pw: &Value) -> String {
    match pw.get("id") {
        Some(v) => str_de(v),
        None => "None".to_string(),
    }
}

/// `_pot_largura`: largura estimada de um grupo de potencia (reserva na faixa 0).
pub(crate) fn largura(pw: &Value) -> R<i64> {
    let mut nf = match lista(pw.get("fases")).len() {
        0 => 3,
        n => n as i64,
    };
    if matches!(get(pw, "polos"), Some(Value::Number(n)) if n.as_f64() == Some(4.0)) {
        nf += 1;
    }
    if get(pw, "tipo").and_then(|v| v.as_str()) == Some("monofasico") {
        nf = 2;
    }
    let mut mx = 0;
    for c in lista(pw.get("colunas")) {
        let est = estagio(c)?;
        let soma: i64 = est.iter().map(|(_, cl, _, _)| width(cl).max(PHASE_DX * (nf - 1) + 1) + GAP).sum();
        mx = mx.max(soma - GAP);
    }
    Ok(mx)
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

fn erro_polos(pw: &Value, raw: &Value) -> crate::LayoutError {
    val(format!("potencia '{}': 'polos' vale 3 ou 4 (recebido {})", id_bruto(pw), cade_model::pyfmt::repr(raw)))
}

/// `pw["polos"]` (padrao 3); so numero 3 ou 4 vale, como o `in (3, 4)` do Python.
fn polos_de(pw: &Value) -> R<i64> {
    let raw = get(pw, "polos").cloned().unwrap_or(Value::from(3));
    match &raw {
        Value::Number(n) => {
            let f = n.as_f64().unwrap_or(f64::NAN);
            if f == 3.0 || f == 4.0 {
                Ok(f as i64)
            } else {
                Err(erro_polos(pw, &raw))
            }
        }
        _ => Err(erro_polos(pw, &raw)),
    }
}

pub(crate) fn potencia(l: &mut Layout, pw: &Value, x: i64, y0: i64, src_x: &mut Vec<i64>) -> R<i64> {
    if get(pw, "tipo").and_then(|v| v.as_str()) == Some("monofasico") {
        return potencia_mono(l, pw, x, y0);
    }
    let fases: Vec<String> = req(pw, "fases")?
        .as_array()
        .ok_or_else(|| crate::tipo("'fases' deve ser lista".into()))?
        .iter()
        .map(str_de)
        .collect();
    let neutro = str_or(pw, "neutro", "N");
    let polos = polos_de(pw)?;
    let linhas: Vec<String> =
        fases.iter().cloned().chain(if polos == 4 { Some(neutro.clone()) } else { None }).collect();
    if polos == 4 && !classes_colunas(pw).iter().any(|c| c == "6004" || c == "2002") {
        return Err(val(format!(
            "potencia '{}': 'polos: 4' pede disjuntor 6004 e contatores 2002 (o 4o polo comuta o neutro)",
            id_bruto(pw)
        )));
    }
    let mut estagios = Vec::new();
    for c in req(pw, "colunas")?.as_array().ok_or_else(|| crate::tipo("'colunas' deve ser lista".into()))? {
        estagios.push(estagio(c)?);
    }
    let nf = linhas.len();
    let pid = str_or(pw, "id", "P");
    let mut src: Vec<(String, String)> = linhas.iter().map(|f| (f.clone(), "rail".to_string())).collect();
    let mut src_y: i64 = 0;
    let mut src_direto = false;
    let mut y = y0;
    let mut xend = x;

    // `ordem` (nomes de linha na ordem dos pinos de entrada) -> indices em `linhas`.
    let ordem_fi = |ordem: &Option<Vec<String>>| -> R<Vec<usize>> {
        match ordem {
            None => Ok((0..nf).collect()),
            Some(o) => o
                .iter()
                .map(|nm| {
                    linhas.iter().position(|x| x == nm).ok_or_else(|| {
                        val(format!(
                            "potencia '{}': 'ordem' {} fora das linhas {}",
                            pid,
                            repr_lista(o),
                            repr_lista(&linhas)
                        ))
                    })
                })
                .collect(),
        }
    };

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
            for (sid, cl, _, _) in est.iter() {
                let (top, _, _) = tops_bots(cl);
                if top.len() != nf {
                    return Err(val(format!(
                        "{} ({}) em paralelo tem {} pinos de entrada != {} linhas (paralelo exige todos os polos)",
                        sid,
                        cl,
                        top.len(),
                        nf
                    )));
                }
            }
            let ry: Vec<i64> = (0..nf).map(|i| src_y + 11 + 6 * i as i64).collect();
            let pxs = src_x.clone();
            let mut tops: HashMap<usize, Vec<i64>> = HashMap::new();
            for (mi, (_sid, cl, _rot, ordem)) in est.iter().enumerate() {
                let (top, _, _) = tops_bots(cl);
                for (pi, fi) in ordem_fi(ordem)?.iter().enumerate() {
                    let off = pin_off(cl, pino_i(&top, pi)?)?;
                    tops.entry(*fi).or_default().push(xs_m[mi] + off[0]);
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
            if top.len() != nf || (bot.len() != top.len() && !bot.is_empty()) {
                if ["1002", "1008", "1010"].contains(&cl.as_str()) {
                    return Err(val(format!(
                        "{} ({}) e motor MONOFASICO (U1/V1/U2/V2): a DSL `potencia` trifasica so monta 3 fases. \
                         Para reversao monofasica use o grupo `tipo: \"monofasico\"` (disjuntor 2 polos + \
                         2 contatores 2002 + motor 1008). Ver docs/bibliografia/automacao-industrial.md",
                        sid, cl
                    )));
                }
                if bot.is_empty() {
                    // motor terminal: consome as linhas que tem; a extra morre aqui
                } else if !(polos == 4 && n == 1 && top.len() == nf - 1 && bot.len() == top.len()) {
                    return Err(val(format!(
                        "{} ({}) tem {} pinos de entrada != {} linhas (paralelo exige todos os polos; bypass so \
                         vale em estagio simples de 3 polos com `polos: 4`)",
                        sid,
                        cl,
                        top.len(),
                        nf
                    )));
                }
                // bypass: ex. termico 6007 com polos:4 — o N passa direto
            }
            l.sym(sid, cl, rot, xs_m[mi], y)?;
            for (pi, fi) in ordem_fi(ordem)?.iter().enumerate().take(top.len()) {
                let s = &src[*fi];
                l.con((s.0.as_str(), s.1.as_str()), (sid.as_str(), top[pi].as_str()));
            }
            if let Some(pe) = pe {
                let alvo = match get(pw, "pe") {
                    Some(v) => str_de(v),
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
            let m = ult_bots[0].2.len();
            let fis_in: Vec<usize> = ordem_fi(&est[0].3)?.into_iter().take(m).collect();
            let resto: Vec<usize> = (0..nf).filter(|fi| !fis_in.contains(fi)).collect();
            let mut novo_src = Vec::new();
            let mut novo_x = Vec::new();
            for i in 0..nf {
                if i < m {
                    novo_src.push((sid.clone(), pino_i(&bots, i)?.clone()));
                    novo_x.push(xs_m[0] + pin_off(&est[0].1, pino_i(&bots, i)?)?[0]);
                } else {
                    // bypass: a linha passa direto
                    novo_src.push(src[resto[i - m]].clone());
                    novo_x.push(if src_direto && resto[i - m] < src_x.len() {
                        src_x[resto[i - m]]
                    } else {
                        xs_m[0] + PHASE_DX * resto[i - m] as i64
                    });
                }
            }
            src = novo_src;
            src_direto = true;
            *src_x = novo_x;
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

/// `_potencia_mono`: reversao monofasica (fonte L/N -> disjuntor 2 polos -> 2 contatores 2002
/// em paralelo -> motor 1008). O 1o contator e a ligacao de referencia (U1/V1 no L, U2/V2 no N);
/// o 2o cruza o enrolamento auxiliar (V1<->V2 nas saidas p6/p8).
fn potencia_mono(l: &mut Layout, pw: &Value, x: i64, y0: i64) -> R<i64> {
    let pid = str_or(pw, "id", "P");
    if !get(pw, "fase").map(verdadeiro).unwrap_or(false) {
        return Err(val(format!("potencia '{}': tipo monofasico exige 'fase' (ex.: 'L1') e 'neutro'", pid)));
    }
    let fase = str_de(&get(pw, "fase").cloned().unwrap_or(Value::Null));
    let neu = str_or(pw, "neutro", "N");
    let pe_v = get(pw, "pe").cloned().unwrap_or(Value::Null);
    let pe_trilho = str_de(&pe_v);
    if !verdadeiro(&pe_v) || pe_trilho == neu {
        return Err(val(format!(
            "potencia '{}': tipo monofasico exige 'pe' em trilho proprio (PE nunca no neutro)",
            pid
        )));
    }
    let cols = lista(pw.get("colunas"));
    if cols.len() != 3 || cols[0].as_array().is_none() || cols[1].as_object().is_none() || cols[2].as_array().is_none()
    {
        return Err(val(format!(
            "potencia '{}': tipo monofasico exige colunas [disjuntor, {{paralelo: [KM1, KM2]}}, motor]",
            pid
        )));
    }
    let (qid, qcl, qrot) = t_de(&cols[0])?;
    let par: Vec<(String, String, String)> =
        lista(cols[1].get("paralelo")).iter().map(t_de).collect::<R<Vec<_>>>()?;
    if par.len() != 2 {
        return Err(val(format!("potencia '{}': reversao monofasica exige 2 contatores em paralelo", pid)));
    }
    let (qtop, qbot, _) = tops_bots(&qcl);
    if qtop.len() != 2 || qbot.len() != 2 {
        return Err(val(format!(
            "{} ({}) nao e disjuntor de 2 polos (topo {}, base {})",
            qid,
            qcl,
            repr_lista(&qtop),
            repr_lista(&qbot)
        )));
    }
    for (sid, cl, _) in &par {
        let (top, bot, _) = tops_bots(cl);
        if top.len() != 4 || bot.len() != 4 {
            return Err(val(format!("{} ({}) nao tem 4 polos (reversao monofasica usa 2002)", sid, cl)));
        }
    }
    let (mid, mcl, mrot) = t_de(&cols[2])?;
    let (mtop, mbot, mpe) = tops_bots(&mcl);
    if mcl != "1008" || mtop.len() != 2 || mbot.len() != 2 || mpe.is_none() {
        return Err(val(format!("{} ({}) nao e motor monofasico 1008 (U1/V1/PE/U2/V2)", mid, mcl)));
    }
    let mpe = mpe.unwrap();

    // --- disjuntor: L/N -> L'/N' ---
    l.sym(&qid, &qcl, &qrot, x, y0)?;
    l.con((fase.as_str(), "rail"), (qid.as_str(), qtop[0].as_str()));
    l.con((neu.as_str(), "rail"), (qid.as_str(), qtop[1].as_str()));
    let yb = y0 + pin_off(&qcl, &qbot[0])?[1];
    let xq = x + width(&qcl);
    let mut y = yb + 11;
    // --- contatores lado a lado, entradas retas (L' nos pinos 1-2, N' nos 3-4) ---
    let mut xs_m = Vec::new();
    let mut xc = x;
    for (_, cl, _) in &par {
        xs_m.push(xc);
        xc += width(cl) + GAP;
    }
    let tops: Vec<Vec<String>> = par.iter().map(|(_, cl, _)| tops_bots(cl).0).collect();
    let bots: Vec<Vec<String>> = par.iter().map(|(_, cl, _)| tops_bots(cl).1).collect();
    let ent = mk_rails(
        l,
        &pid,
        "e",
        &[y, y + 6],
        &[
            vec![
                xq,
                xs_m[0] + pin_off(&par[0].1, &tops[0][0])?[0],
                xs_m[1] + pin_off(&par[1].1, &tops[1][0])?[0],
            ],
            vec![
                xq,
                xs_m[0] + pin_off(&par[0].1, &tops[0][2])?[0],
                xs_m[1] + pin_off(&par[1].1, &tops[1][2])?[0],
            ],
        ],
    );
    l.con((qid.as_str(), qbot[0].as_str()), (ent[0].as_str(), "rail"));
    l.con((qid.as_str(), qbot[1].as_str()), (ent[1].as_str(), "rail"));
    y += 10;
    for (mi, (sid, cl, rot)) in par.iter().enumerate() {
        l.sym(sid, cl, rot, xs_m[mi], y)?;
        for pi in [0, 1] {
            l.con((ent[0].as_str(), "rail"), (sid.as_str(), tops[mi][pi].as_str()));
        }
        for pi in [2, 3] {
            l.con((ent[1].as_str(), "rail"), (sid.as_str(), tops[mi][pi].as_str()));
        }
    }
    let yb = y + pin_off(&par[0].1, &bots[0][0])?[1];
    let ry: Vec<i64> = (0..4).map(|i| yb + 11 + 6 * i).collect();
    // saidas: s1=U1, s2=V1, s3=U2, s4=V2; KM2 cruza V1/V2 (p6->s4, p8->s2)
    let saidas = [((0, 0), (1, 0)), ((0, 1), (1, 3)), ((0, 2), (1, 2)), ((0, 3), (1, 1))];
    let pinos_motor = [&mtop[0], &mtop[1], &mbot[0], &mbot[1]];
    let mut xs = Vec::new();
    for (k, (a, b)) in saidas.iter().enumerate() {
        xs.push(vec![
            xs_m[a.0] + pin_off(&par[a.0].1, &bots[a.0][a.1])?[0],
            xs_m[b.0] + pin_off(&par[b.0].1, &bots[b.0][b.1])?[0],
            xs_m[0] + pin_off(&mcl, pinos_motor[k])?[0],
        ]);
    }
    let sai = mk_rails(l, &pid, "s", &ry, &xs);
    for ((a, b), nm) in saidas.iter().zip(sai.iter()) {
        l.con((par[a.0].0.as_str(), bots[a.0][a.1].as_str()), (nm.as_str(), "rail"));
        l.con((par[b.0].0.as_str(), bots[b.0][b.1].as_str()), (nm.as_str(), "rail"));
    }
    // --- motor alinhado ao 1o contator ---
    let ym = ry[3] + 10;
    l.sym(&mid, &mcl, &mrot, xs_m[0], ym)?;
    for (nm, pino) in sai.iter().zip(pinos_motor.iter()) {
        l.con((nm.as_str(), "rail"), (mid.as_str(), pino.as_str()));
    }
    l.con((mid.as_str(), mpe.as_str()), (pe_trilho.as_str(), "rail"));
    Ok((xc - GAP).max(xs_m[0] + width(&mcl)))
}
