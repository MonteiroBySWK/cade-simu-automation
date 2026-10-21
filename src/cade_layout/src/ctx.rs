//! `_Ctx` + `_comando_rede` + `_fonte_comando` do Python: estado compartilhado (trilhos, faixas,
//! amarracoes) e o comando v2. `Motor` e dono do `Layout` em construcao.

use crate::rede::{self, degrau, expr, med, quebrar, No, CHUNK_GAP, GN, MARGEM_X, RUNG_GAP};
use crate::{dim, eh_rede, get, pin_off, req, str_or, truthy, val, width, Env, Layout, Rail, R};
use cade_model::pyfmt;
use serde_json::Value;
use std::collections::HashMap;

pub(crate) const FORA: i64 = -1_000_000;

pub(crate) struct Prep {
    pub rungs: Vec<Vec<No>>,
    pub yi: i64,
}

pub(crate) struct Motor {
    pub l: Layout,
    /// nome -> indice em `l.rails` (ordem de insercao = `ctx.R`)
    rmap: Vec<(String, usize)>,
    pub x0: i64,
    pub x1: i64,
    prep: HashMap<usize, Prep>,
    pub top0: i64,
    nties: usize,
    /// (j, nome_anterior, nome_novo, y_ant, y_novo)
    right_ties: Vec<(usize, String, String, i64, i64)>,
    c_nomes: Option<(String, String)>,
    pub env: Env,
}

fn max_py(v: &[i64]) -> i64 {
    *v.iter().max().expect("max de lista vazia")
}

impl Motor {
    pub fn new(l: Layout, rails: &[(String, i64)], x0: i64, x1: i64, env: Env) -> Motor {
        let mut m = Motor {
            l,
            rmap: vec![],
            x0,
            x1,
            prep: HashMap::new(),
            top0: 0,
            nties: 0,
            right_ties: vec![],
            c_nomes: None,
            env,
        };
        for (n, y) in rails {
            m.novo_trilho(n, *y, x0, x1);
        }
        m
    }

    fn novo_trilho(&mut self, nome: &str, y: i64, xa: i64, xb: i64) {
        self.l.rails.push(Rail { nome: nome.to_string(), y, x0: xa, x1: xb });
        let idx = self.l.rails.len() - 1;
        match self.rmap.iter_mut().find(|(n, _)| n == nome) {
            Some(e) => e.1 = idx,
            None => self.rmap.push((nome.to_string(), idx)),
        }
    }

    fn ix(&self, nome: &str) -> Option<usize> {
        self.rmap.iter().find(|(n, _)| n == nome).map(|(_, i)| *i)
    }

    fn r(&mut self, nome: &str) -> &mut Rail {
        let i = self.ix(nome).unwrap_or_else(|| panic!("trilho {} inexistente", nome));
        &mut self.l.rails[i]
    }

    fn y(&self, nome: &str) -> i64 {
        self.l.rails[self.ix(nome).expect("trilho")].y
    }

    pub fn tem_trilho(&self, nome: &str) -> bool {
        self.ix(nome).is_some()
    }
    pub fn y_de(&self, nome: &str) -> i64 {
        self.y(nome)
    }
    pub fn rail_y(&self, nome: &str) -> Option<i64> {
        self.ix(nome).map(|i| self.l.rails[i].y)
    }
    pub fn rails_y(&self) -> Vec<i64> {
        self.rmap.iter().map(|(_, i)| self.l.rails[*i].y).collect()
    }

    fn set_y(&mut self, nome: &str, y: i64) {
        self.r(nome).y = y;
    }

    fn nomes_ordenados(&self) -> Vec<String> {
        let mut n: Vec<String> = self.rmap.iter().map(|(n, _)| n.clone()).collect();
        n.sort();
        n
    }

    // ---- preparacao: mede as redes, cria C*, desloca trilhos de baixo ----
    pub fn preparar_comando(&mut self, blocos: &[Value], tc: Option<&Value>) -> R<()> {
        let mut auto: Vec<String> = Vec::new();
        if let Some(tc) = tc {
            let nomes: Vec<String> = match get(tc, "nomes") {
                Some(Value::Array(a)) if !a.is_empty() => a.iter().map(pyfmt::str_de).collect(),
                _ => vec!["C1".into(), "C2".into()],
            };
            if nomes.len() != 2 {
                return Err(val("trilhos_comando.nomes: exatamente 2 trilhos [topo, base]".into()));
            }
            if !(truthy(tc.get("transformador")) || truthy(tc.get("fonte"))) {
                return Err(val(
                    "trilhos_comando sem 'transformador' nem 'fonte': o par de trilhos ficaria sem alimentacao".into(),
                ));
            }
            self.c_nomes = Some((nomes[0].clone(), nomes[1].clone()));
            if !self.tem_trilho(&nomes[0]) {
                let y = self.top0 + if truthy(tc.get("transformador")) { 30 } else { 14 };
                let x0 = self.x0;
                self.novo_trilho(&nomes[0], y, x0, x0);
            }
            if !self.tem_trilho(&nomes[1]) {
                let x0 = self.x0;
                self.novo_trilho(&nomes[1], FORA, x0, x0);
                auto.push(nomes[1].clone());
            }
        }
        let sheet_y = self.env.sheet_y;
        for (bi, blk) in blocos.iter().enumerate() {
            if !eh_rede(blk) {
                continue;
            }
            for k in ["de", "para"] {
                let nome = blk.get(k).map(pyfmt::str_de);
                if !nome.as_deref().map(|n| self.tem_trilho(n)).unwrap_or(false) {
                    return Err(val(format!(
                        "comando '{}': '{}'='{}' nao e um trilho (trilhos: {})",
                        blk.get("id").map(pyfmt::str_de).unwrap_or_else(|| "None".into()),
                        k,
                        nome.unwrap_or_else(|| "None".into()),
                        pyfmt::repr_lista(&self.nomes_ordenados())
                    )));
                }
            }
            let id_txt = blk.get("id").map(pyfmt::str_de).unwrap_or_else(|| "None".into());
            if blk.get("serie").is_some() || blk.get("ramos").is_some() {
                return Err(val(format!(
                    "comando '{}': misture 'rede'/'rungs' com 'serie'/'ramos' no mesmo bloco nao e permitido \
                     (use blocos separados)",
                    id_txt
                )));
            }
            let fontes: Vec<Value> = if let Some(r) = blk.get("rede") {
                vec![r.clone()]
            } else {
                let a = get(blk, "rungs").filter(|v| pyfmt::verdadeiro(v)).or_else(|| get(blk, "degraus"));
                match a {
                    Some(Value::Array(a)) if !a.is_empty() => a.clone(),
                    _ => {
                        return Err(val(format!(
                            "comando '{}': 'rungs' precisa de uma lista nao vazia de redes",
                            id_txt
                        )))
                    }
                }
            };
            let mut arvores = Vec::new();
            for r in &fontes {
                arvores.push(expr(r)?);
            }
            let de = pyfmt::str_de(&blk["de"]);
            let para = pyfmt::str_de(&blk["para"]);
            let ystart = if self.y(&de) > -100_000 { self.top0.max(self.y(&de) + 14) } else { self.top0 };
            let yi = ystart - GN;
            let base_y = if auto.contains(&para) { None } else { Some(self.y(&para)) };
            let lowest = max_py(&self.rails_y());
            let extra = base_y.map(|b| lowest - b).unwrap_or(0);
            let hlim = (sheet_y - 8 - extra) - yi;
            let mut rungs = Vec::new();
            let mut hmax = 0;
            for t in &arvores {
                let chunks = quebrar(t, hlim, &self.env)?;
                let h = chunks.iter().map(|c| med(c, &self.env).2).max().unwrap();
                rungs.push(chunks);
                hmax = hmax.max(h);
            }
            let need = yi + hmax;
            if auto.contains(&para) {
                if need > self.y(&para) {
                    self.set_y(&para, need);
                }
            } else if need > self.y(&para) {
                let y0 = self.y(&para);
                let delta = need - y0;
                let nomes: Vec<String> = self.rmap.iter().map(|(n, _)| n.clone()).collect();
                for n in nomes {
                    let yy = self.y(&n);
                    if yy >= y0 {
                        self.set_y(&n, yy + delta);
                    }
                }
            }
            self.prep.insert(bi, Prep { rungs, yi });
        }
        for nome in &auto {
            if self.y(nome) < -100_000 {
                let c1 = self.c_nomes.as_ref().unwrap().0.clone();
                let y = self.y(&c1) + 40;
                self.set_y(nome, y);
            }
        }
        let nomes: Vec<String> = self.rmap.iter().map(|(n, _)| n.clone()).collect();
        for n in nomes {
            let y = self.y(&n);
            if y > self.env.sheet_y {
                return Err(val(format!("trilho {} em y={} fora da folha (max {})", n, y, self.env.sheet_y)));
            }
        }
        Ok(())
    }

    fn y_livre(&self) -> i64 {
        let mut ys = self.rails_y();
        for s in &self.l.simbolos {
            ys.push(s.y + dim(&s.classe).1);
        }
        for f in &self.l.fios {
            ys.push(f.y1);
            ys.push(f.y2);
        }
        max_py(&ys) + 16
    }

    /// Amarra as faixas: `para` pela direita (x depois de tudo); `de` ja amarrado pela esquerda.
    pub fn fechar(&mut self) -> R<()> {
        if self.right_ties.is_empty() {
            return Ok(());
        }
        let mut xs = vec![self.x1];
        for s in &self.l.simbolos {
            xs.push(s.x + width(&s.classe));
        }
        for (n, i) in &self.rmap {
            if !self.right_ties.iter().any(|(_, a, b, _, _)| n == a || n == b) {
                xs.push(self.l.rails[*i].x1);
            }
        }
        for f in &self.l.fios {
            xs.push(f.x1);
            xs.push(f.x2);
        }
        let base = max_py(&xs);
        let ties = self.right_ties.clone();
        for (j, a, b, ya, yb) in ties {
            let xr = base + 6 + 5 * j as i64;
            if xr > self.env.sheet_x {
                return Err(val("amarracao das faixas fora da folha".into()));
            }
            for nome in [&a, &b] {
                let r = self.r(nome);
                r.x1 = r.x1.max(xr);
            }
            self.l.fio(xr, ya, xr, yb);
        }
        Ok(())
    }

    /// `_fonte_comando`: transformador 3012 e/ou fonte 3003 do par de trilhos de comando. -> x final.
    pub fn fonte_comando(&mut self, tc: &Value, x: i64, top0: i64) -> R<i64> {
        let (c1, c2) = self.c_nomes.clone().expect("c_nomes");
        let mut xmax = x;
        let mut xi = x;
        let mut x_c1: Vec<i64> = vec![];
        let mut x_c2: Vec<i64> = vec![];
        if let Some(tr) = get(tc, "transformador").filter(|v| pyfmt::verdadeiro(v)) {
            let cl = str_or(tr, "classe", "3012");
            let tid = str_or(tr, "id", "T1");
            let prim: Vec<String> = match get(tr, "primario") {
                Some(Value::Array(a)) if !a.is_empty() => a.iter().map(pyfmt::str_de).collect(),
                _ => vec!["L1".into(), "L2".into()],
            };
            if prim.len() != 2 || prim.iter().any(|p| !self.tem_trilho(p)) {
                return Err(val(format!(
                    "transformador.primario deve ter 2 trilhos existentes (trilhos: {})",
                    pyfmt::repr_lista(&self.nomes_ordenados())
                )));
            }
            self.l.sym(&tid, &cl, &str_or(tr, "rotulo", "-T1"), xi, top0)?;
            self.l.con((tid.as_str(), "p1"), (prim[0].as_str(), "rail"));
            self.l.con((tid.as_str(), "p2"), (prim[1].as_str(), "rail"));
            self.l.con((tid.as_str(), "p4"), (c1.as_str(), "rail"));
            self.l.con((tid.as_str(), "p3"), (c2.as_str(), "rail"));
            x_c1.push(xi + pin_off(&cl, "p4")?[0]);
            x_c2.push(xi + pin_off(&cl, "p3")?[0]);
            xmax = xi + width(&cl);
            xi = xmax + 12;
        }
        if let Some(fo) = get(tc, "fonte").filter(|v| pyfmt::verdadeiro(v)) {
            let cl = str_or(fo, "classe", "3003");
            let fid = str_or(fo, "id", "X2");
            self.l.sym(&fid, &cl, &str_or(fo, "rotulo", "-X2"), xi, top0)?;
            let mapa: Vec<(String, String)> = match get(fo, "pinos") {
                Some(Value::Object(m)) if !m.is_empty() => {
                    m.iter().map(|(k, v)| (k.clone(), pyfmt::str_de(v))).collect()
                }
                _ => vec![("L".into(), c2.clone()), ("N".into(), c1.clone())],
            };
            for (pino, tri) in mapa {
                if tri != c1 && tri != c2 {
                    return Err(val(format!(
                        "fonte.pinos: '{}' nao e trilho de comando ({}/{})",
                        tri, c1, c2
                    )));
                }
                self.l.con((fid.as_str(), pino.as_str()), (tri.as_str(), "rail"));
                let px = xi + pin_off(&cl, &pino)?[0];
                if tri == c1 {
                    x_c1.push(px);
                } else {
                    x_c2.push(px);
                }
            }
            xmax = xmax.max(xi + width(&cl));
        }
        if x_c1.is_empty() || x_c2.is_empty() {
            return Err(val("trilhos_comando: os dois trilhos precisam de alimentacao".into()));
        }
        let m1 = *x_c1.iter().min().unwrap();
        let m2 = *x_c2.iter().min().unwrap();
        {
            let r = self.r(&c1);
            r.x0 = m1;
            r.x1 = m1;
        }
        {
            let r = self.r(&c2);
            r.x0 = m2;
            r.x1 = m2;
        }
        Ok(xmax)
    }

    /// `_comando_rede`: degraus da rede serie-paralelo; devolve o x final da faixa 0.
    pub fn comando_rede(&mut self, bi: usize, blk: &Value, x: i64, reserva: i64) -> R<i64> {
        let env = self.env;
        let pr = self.prep.remove(&bi).expect("prep");
        let de = pyfmt::str_de(req(blk, "de")?);
        let para = pyfmt::str_de(req(blk, "para")?);
        let bid = match get(blk, "id") {
            Some(v) if pyfmt::verdadeiro(v) => pyfmt::str_de(v),
            _ => "c".to_string(),
        };
        let rungs = &pr.rungs;
        let larg = |r: &Vec<No>| -> i64 {
            r.iter().map(|c| {
                let m = med(c, &env);
                m.0 + m.1
            }).sum::<i64>()
                + CHUNK_GAP * (r.len() as i64 - 1)
        };
        let xmax = env.sheet_x - MARGEM_X;
        let x_faixa = self.x0 + 5;
        let lim0 = xmax - reserva - 40;
        let mut faixas: Vec<Vec<(usize, i64)>> = vec![vec![]];
        let mut cur = x;
        let mut k = 0usize;
        for (ri, r) in rungs.iter().enumerate() {
            let w = larg(r);
            let lim = if k == 0 { lim0 } else { xmax - 14 };
            if cur + w > lim {
                if k >= 1 && faixas[k].is_empty() {
                    return Err(val(format!(
                        "degrau com largura {} nao cabe nem sozinho numa faixa (max {})",
                        w,
                        lim - x_faixa
                    )));
                }
                faixas.push(vec![]);
                k += 1;
                cur = x_faixa;
                if cur + w > xmax - 14 {
                    return Err(val(format!("degrau com largura {} nao cabe na folha ({})", w, env.sheet_x)));
                }
            }
            faixas[k].push((ri, cur));
            cur += w + RUNG_GAP;
        }
        let mut xend0 = x;
        let mut nomes_prev = (de.clone(), para.clone());
        let mut j: Option<usize> = None;
        for (k, items) in faixas.iter().enumerate() {
            if items.is_empty() {
                continue;
            }
            let (de_k, para_k, yi);
            if k == 0 {
                de_k = de.clone();
                para_k = para.clone();
                yi = pr.yi;
            } else {
                let hk = items
                    .iter()
                    .map(|(ri, _)| rungs[*ri].iter().map(|c| med(c, &env).2).max().unwrap())
                    .max()
                    .unwrap();
                let y_top = self.y_livre();
                yi = y_top + 14 - GN;
                let y_para = yi + hk;
                if y_para > env.sheet_y - 4 {
                    return Err(val(format!(
                        "faixa extra nao cabe na folha (y={} > {}); reduza a rede ou use 'rungs' em menos degraus",
                        y_para, env.sheet_y
                    )));
                }
                de_k = format!("{}~{}{}", de, bid, k);
                para_k = format!("{}~{}{}", para, bid, k);
                let jj = match j {
                    Some(v) => v,
                    None => {
                        let v = self.nties;
                        self.nties += 1;
                        j = Some(v);
                        v
                    }
                };
                let xt = self.x0 - 6 - 5 * jj as i64;
                if xt < 12 {
                    return Err(val(
                        "blocos com faixas demais: sem espaco para as amarracoes na margem esquerda".into(),
                    ));
                }
                let x0 = self.x0;
                self.novo_trilho(&de_k, y_top, xt, x0);
                self.novo_trilho(&para_k, y_para, x0, x0);
                let ya = self.y(&nomes_prev.0);
                {
                    let r = self.r(&nomes_prev.0);
                    r.x0 = r.x0.min(xt);
                }
                self.l.fio(xt, ya, xt, y_top);
                let y_prev_para = self.y(&nomes_prev.1);
                self.right_ties.push((jj, nomes_prev.1.clone(), para_k.clone(), y_prev_para, y_para));
                nomes_prev = (de_k.clone(), para_k.clone());
            }
            for (ri, xl) in items {
                let xr = degrau(&mut self.l, &rungs[*ri], *xl, yi, &de_k, &para_k, &env)?;
                if k == 0 {
                    xend0 = xend0.max(xr);
                }
                for n in [&de_k, &para_k] {
                    let r = self.r(n);
                    r.x1 = r.x1.max(xr + 6);
                }
            }
        }
        let _ = rede::GAP;
        Ok(xend0)
    }
}
