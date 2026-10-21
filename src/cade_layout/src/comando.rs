//! Forma legada do comando (`serie` + `ramos`, fileiras horizontais): `_comando` do Python.

use crate::{dim, get, lista, req, t_de, truthy, val, width, Layout, R, GAP, ROW_PITCH};
use cade_model::pyfmt::{self, fdiv};
use serde_json::Value;

type Sl = (&'static str, (String, String, String));

pub(crate) fn comando(l: &mut Layout, blk: &Value, x: i64, y0: i64, y_baixo: i64) -> R<i64> {
    let de = pyfmt::str_de(req(blk, "de")?);
    let para = pyfmt::str_de(req(blk, "para")?);
    let mut ser = Vec::new();
    for s in lista(blk.get("serie")) {
        ser.push(t_de(s)?);
    }
    let ramos = lista(blk.get("ramos"));
    let xcol = x;
    let mut y = y0;
    let head: (String, String);
    let y_ramos;
    let mut xend;
    if !ser.is_empty() {
        let mut cur: Option<(String, String)> = None;
        for (sid, cl, rot) in &ser {
            l.sym(sid, cl, rot, xcol, y)?;
            let de_con = match &cur {
                None => (de.clone(), "rail".to_string()),
                Some(c) => c.clone(),
            };
            l.con(de_con, (sid.as_str(), "A"));
            cur = Some((sid.clone(), "B".to_string()));
            y += dim(cl).1 + 20;
        }
        head = cur.unwrap();
        let ult_cl = &ser[ser.len() - 1].1;
        let y_ult = y - 20 - dim(ult_cl).1;
        let h_ult = dim(ult_cl).1;
        y_ramos = y_ult + h_ult + 50;
        xend = xcol + ser.iter().map(|(_, c, _)| width(c)).max().unwrap();
    } else {
        head = (de.clone(), "rail".to_string());
        y_ramos = y0;
        xend = xcol;
    }

    // slots por ramo
    let mut plano: Vec<Vec<Sl>> = Vec::new();
    for r in ramos {
        let mut sl: Vec<Sl> = Vec::new();
        if truthy(r.get("via")) {
            sl.push(("via", t_de(r.get("via").unwrap())?));
        }
        if truthy(r.get("selo")) {
            sl.push(("selo", t_de(r.get("selo").unwrap())?));
        }
        for s in lista(r.get("serie")) {
            sl.push(("serie", t_de(s)?));
        }
        sl.push(("carga", t_de(req(r, "carga")?)?));
        if truthy(r.get("indica")) {
            sl.push(("indica", t_de(r.get("indica").unwrap())?));
        }
        plano.push(sl);
    }
    let nslots = plano.iter().map(|s| s.len()).max().unwrap_or(0);
    let wmax: Vec<i64> = (0..nslots)
        .map(|i| plano.iter().filter(|s| i < s.len()).map(|s| width(&s[i].1 .1)).max().unwrap_or(0))
        .collect();
    let mut xs = Vec::new();
    let mut xc = xcol;
    for w in &wmax {
        xs.push(xc);
        xc += w + GAP;
    }
    let n = ramos.len() as i64;
    let mut pitch = ROW_PITCH;
    if n > 1 {
        let disp = (y_baixo - 20) - y_ramos - 15;
        pitch = ROW_PITCH.min(fdiv(disp, n - 1));
        if pitch < 28 {
            return Err(val("ramos de comando nao cabem na folha".into()));
        }
    }
    for (k, sl) in plano.iter().enumerate() {
        let yy = y_ramos + k as i64 * pitch;
        let mut cur = head.clone();
        let mut via: Option<String> = None;
        let mut carga_par: Option<String> = None;
        for (i, (papel, (sid, cl, rot))) in sl.iter().enumerate() {
            l.sym(sid, cl, rot, xs[i], yy)?;
            match *papel {
                "via" => {
                    l.con(cur.clone(), (sid.as_str(), "A"));
                    via = Some(sid.clone());
                    cur = (sid.clone(), "B".into());
                }
                "selo" => {
                    let v = via.clone().unwrap_or_default();
                    l.con((v.as_str(), "A"), (sid.as_str(), "A"));
                    l.con((v.as_str(), "B"), (sid.as_str(), "B"));
                }
                "serie" => {
                    l.con(cur.clone(), (sid.as_str(), "A"));
                    cur = (sid.clone(), "B".into());
                }
                "carga" => {
                    l.con(cur.clone(), (sid.as_str(), "A"));
                    carga_par = Some(sid.clone());
                    cur = (sid.clone(), "B".into());
                    l.con((sid.as_str(), "B"), (para.as_str(), "rail"));
                }
                _ => {
                    let c = carga_par.clone().unwrap_or_default();
                    l.con((c.as_str(), "A"), (sid.as_str(), "A"));
                    l.con((c.as_str(), "B"), (sid.as_str(), "B"));
                }
            }
        }
        let ult = &sl[sl.len() - 1];
        xend = xend.max(xs[sl.len() - 1] + width(&ult.1 .1));
    }
    let _ = get;
    Ok(xend)
}
