//! Geometria compartilhada do `.cad`: pinos por classe, rotacao, posicao absoluta e conectividade.
//!
//! API **publica** pensada para ser reutilizada pelo simulador (`cade_sim`): a conectividade do
//! `Circuito` do Python (`netlist_sim.py`) e a MESMA do `geo_check.py` — fio-fio por extremo
//! coincidente, junta 4001/4012 une ao fio cujo segmento a contem, pino so liga a extremo de fio
//! (docs/re-engenharia.md §9.2). Em vez de duplicar, o sim chama [`Conectividade::de_entidades`].
//!
//! ```
//! use cade_check::geom::{Conectividade, entidades_do_cad};
//! # let bytes = include_bytes!(concat!(env!("CARGO_MANIFEST_DIR"), "/../../tests/golden/partida_direta.cad"));
//! # let cad = cade_model::latin1::decodificar(bytes);
//! let ents = entidades_do_cad(&cad).unwrap();
//! let c = Conectividade::de_entidades(&ents);
//! assert!(!c.pinos.is_empty());
//! // pino ligado -> id de rede; duas pontas ligadas pelo mesmo fio -> mesmo id
//! let ligados: Vec<_> = c.pinos.iter().filter_map(|p| c.rede_do_ponto(p.ponto)).collect();
//! assert!(!ligados.is_empty());
//! ```

use cade_model::dados;
use cade_model::{parse_ent, split_all, Entidade};
use serde_json::Value;
use std::collections::{HashMap, HashSet};
use std::sync::OnceLock;

/// Classes que sao fio (`geo_check.WIRE`).
pub const FIO: [&str; 5] = ["4000", "4009", "4010", "4018", "4019"];
/// Classes ignoradas como simbolo com pinos (`geo_check.SKIP`).
pub const SKIP: [&str; 12] = [
    "4000", "4009", "4010", "4018", "4019", "4001", "4002", "4003", "4004", "4012", "8", "20000",
];
/// Fontes que estampam fase por pino (`geo_check.FONTE`).
pub const FONTE: [&str; 10] = ["3000", "3001", "3002", "3003", "3004", "3005", "3006", "3007", "3011", "3012"];

/// Ponto da folha em unidades do `.cad`.
pub type Ponto = (i64, i64);

/// Estampa de fase de um pino de fonte (`geo_check.CHAR`).
pub fn estampa_de(pino: &str) -> Option<&'static str> {
    Some(match pino {
        "L1" | "L" => "1",
        "L2" => "2",
        "L3" => "3",
        "N" => "N",
        "PE" => "P",
        _ => return None,
    })
}

/// Estampa por classe: o transformador `3012` tambem e fonte no app, mas estampa no **secundario**
/// (`p4` = L/topo, `p3` = N/base). Medido em 22/10/2026: com o 3012 sozinho o comando energiza e nao
/// ha curto; com uma `3003` extra no mesmo par de trilhos o app acusa CURTO.
pub fn estampa_de_classe(classe: &str, pino: &str) -> Option<&'static str> {
    if classe == "3012" {
        return match pino {
            "p4" => Some("1"),
            "p3" => Some("N"),
            _ => None,
        };
    }
    estampa_de(pino)
}

/// `_rot(dx, dy, o)`: rotacao/espelho do offset do pino pela orientacao `o` (nums[17]).
pub fn rotacionar(dx: i64, dy: i64, o: i64) -> (i64, i64) {
    match o {
        1 => (-dy, dx),
        2 => (-dx, -dy),
        3 => (dy, -dx),
        4 => (-dx, dy),
        _ => (dx, dy),
    }
}

type PinosClasse = Vec<(String, (i64, i64))>;

fn par(v: &Value) -> Option<(i64, i64)> {
    let a = v.as_array()?;
    Some((a.first()?.as_i64()?, a.get(1)?.as_i64()?))
}

/// `symbol_pins.json` na ORDEM do arquivo (a ordem de `geo_check.pinos_da_classe` define a ordem
/// dos pinos soltos na saida; `cade_model::dados::symbol_pins` ordena por nome, entao nao serve).
fn pins_ordenados() -> &'static HashMap<String, PinosClasse> {
    static V: OnceLock<HashMap<String, PinosClasse>> = OnceLock::new();
    V.get_or_init(|| {
        let raw: Value = serde_json::from_str(dados::SYMBOL_PINS_JSON).expect("symbol_pins.json invalido");
        let mut out = HashMap::new();
        for (cid, e) in raw.as_object().expect("symbol_pins.json: objeto") {
            let mut v: PinosClasse = Vec::new();
            if let Some(p) = e.get("pins").and_then(|p| p.as_object()) {
                for (k, o) in p {
                    if let Some(xy) = par(o) {
                        v.push((k.clone(), xy));
                    }
                }
            }
            for k in ["A", "B"] {
                if let Some(xy) = e.get(k).and_then(par) {
                    if !v.iter().any(|(n, _)| n == k) {
                        v.push((k.to_string(), xy));
                    }
                }
            }
            out.insert(cid.clone(), v);
        }
        out
    })
}

/// `geo_check.pinos_da_classe`: `[(nome, (dx, dy))]` — o binario (`docs/pinos-binario.json`)
/// primeiro; cai no `symbol_pins.json` (nomeados, depois A/B). Classe desconhecida -> vazio.
pub fn pinos_da_classe(cid: &str) -> Vec<(String, (i64, i64))> {
    if let Some(c) = dados::pinos_binario().get("classes").and_then(|c| c.get(cid)) {
        let mut v = Vec::new();
        if let Some(p) = c.get("pins").and_then(|p| p.as_object()) {
            for (k, o) in p {
                if let Some(xy) = par(o) {
                    v.push((k.clone(), xy));
                }
            }
        }
        return v;
    }
    pins_ordenados().get(cid).cloned().unwrap_or_default()
}

/// Inteiro da entidade (`int(p["nums"][i])`); campo ausente/vazio -> 0.
pub fn num(e: &Entidade, i: usize) -> i64 {
    e.nums.get(i).map(|s| s.parse::<i64>().unwrap_or(0)).unwrap_or(0)
}

/// Rotulo para mensagens: primeiro label, ou a classe quando vazio (`(labels or [""])[0] or id`).
pub fn rotulo(e: &Entidade) -> String {
    match e.labels.first() {
        Some(l) if !l.is_empty() => l.clone(),
        _ => e.id.clone(),
    }
}

/// Entidades parseadas do texto latin1 do `.cad` (`split_all` + `parse_ent`, descarta as que nao casam).
pub fn entidades_do_cad(cad_latin1: &str) -> Result<Vec<Entidade>, String> {
    let p = split_all(cad_latin1)?;
    Ok(p.ents.iter().filter_map(|e| parse_ent(e)).collect())
}

/// Trecho de fio.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Fio {
    pub a: Ponto,
    pub b: Ponto,
}

/// Pino de simbolo em coordenada absoluta.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PinoAbs {
    pub rotulo: String,
    pub classe: String,
    pub nome: String,
    pub ponto: Ponto,
}

/// Conectividade por geometria (nets independentes dos gravados no arquivo).
#[derive(Debug, Clone, Default)]
pub struct Conectividade {
    /// Trechos de fio (classes [`FIO`]), na ordem do arquivo.
    pub fios: Vec<Fio>,
    /// Pinos de todos os simbolos (fora de [`SKIP`]), na ordem do arquivo e do catalogo de pinos.
    pub pinos: Vec<PinoAbs>,
    extremos: HashSet<Ponto>,
    indice: HashMap<Ponto, usize>,
    pai: Vec<usize>,
}

impl Conectividade {
    fn id(&mut self, p: Ponto) -> usize {
        if let Some(&i) = self.indice.get(&p) {
            return i;
        }
        let i = self.pai.len();
        self.pai.push(i);
        self.indice.insert(p, i);
        i
    }

    fn raiz(&mut self, mut a: usize) -> usize {
        while self.pai[a] != a {
            self.pai[a] = self.pai[self.pai[a]];
            a = self.pai[a];
        }
        a
    }

    fn unir(&mut self, a: Ponto, b: Ponto) {
        let (ia, ib) = (self.id(a), self.id(b));
        let (ra, rb) = (self.raiz(ia), self.raiz(ib));
        if ra != rb {
            self.pai[rb] = ra;
        }
    }

    /// Constroi a conectividade das entidades (regras de `geo_check.analisar`).
    /// Entidades com 17 numeros ou menos sao ignoradas (como no Python).
    pub fn de_entidades(ents: &[Entidade]) -> Self {
        let mut c = Conectividade::default();
        let ps: Vec<&Entidade> = ents.iter().filter(|p| p.nums.len() > 17).collect();
        for p in &ps {
            if FIO.contains(&p.id.as_str()) {
                let (a, b) = ((num(p, 8), num(p, 9)), (num(p, 10), num(p, 11)));
                c.fios.push(Fio { a, b });
                c.unir(a, b);
            }
        }
        for p in &ps {
            if p.id == "4001" || p.id == "4012" {
                let pt = (num(p, 8), num(p, 9));
                c.id(pt);
                let fios = c.fios.clone();
                for f in fios {
                    let (x1, y1) = (f.a.0.min(f.b.0), f.a.1.min(f.b.1));
                    let (x2, y2) = (f.a.0.max(f.b.0), f.a.1.max(f.b.1));
                    if (y1 == y2 && y2 == pt.1 && x1 <= pt.0 && pt.0 <= x2)
                        || (x1 == x2 && x2 == pt.0 && y1 <= pt.1 && pt.1 <= y2)
                    {
                        c.unir(pt, f.a);
                    }
                }
            }
        }
        c.extremos = c.fios.iter().flat_map(|f| [f.a, f.b]).collect();
        for p in &ps {
            if SKIP.contains(&p.id.as_str()) {
                continue;
            }
            let (x, y) = (num(p, 8), num(p, 9));
            let o = num(p, 17);
            let rot = rotulo(p);
            for (nome, (dx, dy)) in pinos_da_classe(&p.id) {
                let (rx, ry) = rotacionar(dx, dy, o);
                c.pinos.push(PinoAbs { rotulo: rot.clone(), classe: p.id.clone(), nome, ponto: (x + rx, y + ry) });
            }
        }
        c
    }

    /// O ponto e extremo de algum fio? (so ai um pino se liga).
    pub fn e_extremo(&self, p: Ponto) -> bool {
        self.extremos.contains(&p)
    }

    /// Id da rede (componente conexo) de um ponto conhecido; igual para pontos da mesma rede.
    /// `None` se o ponto nao e extremo de fio nem junta. Os ids so valem dentro desta instancia.
    pub fn rede_do_ponto(&self, p: Ponto) -> Option<usize> {
        let mut a = *self.indice.get(&p)?;
        while self.pai[a] != a {
            a = self.pai[a];
        }
        Some(a)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ent(id: &str, rot: &str, nums: &[i64]) -> Entidade {
        let mut n: Vec<String> = vec!["0".into(); 23];
        for (i, v) in nums.iter().enumerate() {
            n[8 + i] = v.to_string();
        }
        Entidade { seq: "0".into(), id: id.into(), labels: vec![rot.into()], nums: n }
    }

    #[test]
    fn rotacao_como_o_python() {
        assert_eq!(rotacionar(3, 5, 0), (3, 5));
        assert_eq!(rotacionar(3, 5, 1), (-5, 3));
        assert_eq!(rotacionar(3, 5, 2), (-3, -5));
        assert_eq!(rotacionar(3, 5, 3), (5, -3));
        assert_eq!(rotacionar(3, 5, 4), (-3, 5));
        assert_eq!(rotacionar(3, 5, 9), (3, 5));
    }

    #[test]
    fn fio_une_extremos_e_junta_une_ao_meio() {
        // fio horizontal (0,0)-(20,0); fio vertical (10,0)-(10,10) so toca no meio via 4001
        let mut ents = vec![ent("4000", "", &[0, 0, 20, 0]), ent("4000", "", &[10, 5, 10, 10])];
        let c0 = Conectividade::de_entidades(&ents);
        assert_ne!(c0.rede_do_ponto((0, 0)), c0.rede_do_ponto((10, 5)));
        ents.push(ent("4001", "", &[10, 0]));
        ents.push(ent("4000", "", &[10, 0, 10, 5]));
        let c = Conectividade::de_entidades(&ents);
        assert_eq!(c.rede_do_ponto((0, 0)), c.rede_do_ponto((10, 10)));
        assert!(c.e_extremo((20, 0)));
        assert!(!c.e_extremo((5, 0)));
    }

    #[test]
    fn pinos_do_binario_vem_antes_do_symbol_pins() {
        let p = pinos_da_classe("1000");
        assert_eq!(p.first().map(|(n, _)| n.as_str()), Some("p1"));
        assert!(pinos_da_classe("classe-inexistente").is_empty());
    }

    #[test]
    fn estampas_de_fase() {
        assert_eq!(estampa_de("PE"), Some("P"));
        assert_eq!(estampa_de("L"), Some("1"));
        assert_eq!(estampa_de("U1"), None);
    }
}
