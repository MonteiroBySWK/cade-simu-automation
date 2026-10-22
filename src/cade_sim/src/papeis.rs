//! Papeis por classe: o que cada simbolo faz na simulacao (docs/re-engenharia.md 11).
//!
//! Tabela em duas camadas, como `tools/netlist_sim.carregar_papeis`:
//! 1. **embutida** (validada no app): contatos NA/NC, bobina, lampada, polos de potencia;
//! 2. **derivada de `docs/classes-papeis.json`** (RE do binario) para as classes que a camada 1 nao
//!    cobre: contatos NA-NC/comutados, botoes, fins de curso, disjuntores, fusiveis, seletores,
//!    contatos temporizados, temporizadores, motores. A camada 1 sempre prevalece.
//!
//! Os pinos do JSON do RE (`13`, `14`, `A1`...) sao mapeados **por ordem** para os `p1..pN` do
//! binario (`docs/pinos-binario.json`), como diz o proprio JSON.

use cade_model::dados;
use serde_json::Value;
use std::collections::HashMap;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Modo {
    Na,
    Nc,
}

/// Modo dos polos multipolares embutidos.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ModoPolos {
    /// conduz quando o comando esta ativo (contator 2001)
    Na,
    Nc,
    /// sempre conduz (rele termico 6007, disjuntores 6009/6010)
    Fechado,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TipoTemp {
    /// retardo na energizacao (9004)
    Ton,
    /// retardo na desenergizacao (9005)
    Tof,
    /// mesmo T nos dois sentidos (9006)
    TonTof,
    /// pisca-pisca: energizado alterna 1/0 a cada T (9007)
    Intermitente,
}

/// Condicao de fechamento de um par de pinos em funcao do `estado` do elemento.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Cond {
    /// conduz quando `estado == n`
    Estado(i64),
    Sempre,
}

/// De onde vem o `estado` de um elemento comandado.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Fonte {
    /// bobina de mesmo rotulo; sem bobina, a entrada externa de mesmo nome (botao, termico, disjuntor...)
    Rotulo,
    /// saida do temporizador de mesmo rotulo (contatos 7004..7015)
    Temporizador,
}

#[derive(Clone, Debug, PartialEq)]
pub enum Papel {
    /// contato de 2 pinos (os 2 primeiros do binario), NA ou NC
    Contato { modo: Modo },
    Bobina,
    Lampada,
    /// contatos de potencia multipolares: pinos de mesmo dx pareados por dy crescente
    Polos { modo: ModoPolos },
    /// contato com temporizador proprio (`tempo` em segundos; `None` = 0 s ou o do caso)
    ContatoTemp { modo: Modo, tipo: TipoTemp, tempo: Option<f64> },
    /// RE: pares de pinos (indices na ordem do binario) com condicao propria
    Chaves { ligacoes: Vec<(usize, usize, Cond)>, fonte: Fonte, polos: bool },
    /// RE: temporizador (carga) 9004/9005/9006/9007; tempo = rotulo 6, unidade = rotulo 5
    Temporizador(TipoTemp),
    /// RE: motor; gira com fases distintas nos pinos de fase
    Motor,
}

#[derive(Clone, Debug)]
pub struct Papeis {
    mapa: HashMap<String, Papel>,
}

impl Papeis {
    pub fn get(&self, cid: &str) -> Option<&Papel> {
        self.mapa.get(cid)
    }

    pub fn insert(&mut self, cid: &str, p: Papel) {
        self.mapa.insert(cid.to_string(), p);
    }

    /// So a camada 1 (equivale a `PAPEIS_EMBUTIDOS` do Python).
    pub fn embutidos() -> Self {
        let mut m = HashMap::new();
        for c in ["8000", "8016", "7000", "10050"] {
            m.insert(c.to_string(), Papel::Contato { modo: Modo::Na });
        }
        for c in ["8001", "8017", "7001", "10051"] {
            m.insert(c.to_string(), Papel::Contato { modo: Modo::Nc });
        }
        for c in ["9000", "10060"] {
            m.insert(c.to_string(), Papel::Bobina);
        }
        m.insert("9008".into(), Papel::Lampada);
        m.insert("2001".into(), Papel::Polos { modo: ModoPolos::Na });
        for c in ["6007", "6009", "6010"] {
            m.insert(c.to_string(), Papel::Polos { modo: ModoPolos::Fechado });
        }
        Papeis { mapa: m }
    }

    /// Camada 1 + camada 2 (derivada de `docs/classes-papeis.json` embutido). A camada 1 prevalece.
    pub fn padrao() -> Self {
        let mut p = Self::embutidos();
        if let Some(obj) = dados::classes_papeis().as_object() {
            for (cid, v) in obj {
                if cid.starts_with('_') || p.mapa.contains_key(cid) {
                    continue;
                }
                if let Some(papel) = derivar(cid, v) {
                    p.mapa.insert(cid.clone(), papel);
                }
            }
        }
        p
    }
}

/// Classes de contator/polos comandados por bobina: o rotulo delas nao e uma "entrada".
const POLOS: [&str; 5] = ["2000", "2001", "2002", "2006", "2008"];

/// Interpreta `fecha_quando` do JSON do RE.
fn cond(s: &str) -> Option<Cond> {
    let s = s.trim();
    if s == "sempre" {
        return Some(Cond::Sempre);
    }
    s.strip_prefix("estado==")?.trim().parse().ok().map(Cond::Estado)
}

fn derivar(cid: &str, v: &Value) -> Option<Papel> {
    let papel = v.get("papel")?.as_str()?;
    match papel {
        "bobina" => return Some(Papel::Bobina),
        "lampada" | "sinalizador" => return Some(Papel::Lampada),
        "motor" => return Some(Papel::Motor),
        "temporizador_ON" => return Some(Papel::Temporizador(TipoTemp::Ton)),
        "temporizador_OFF" => return Some(Papel::Temporizador(TipoTemp::Tof)),
        "temporizador_ON_OFF" => return Some(Papel::Temporizador(TipoTemp::TonTof)),
        "temporizador_intermitente" => return Some(Papel::Temporizador(TipoTemp::Intermitente)),
        _ => {}
    }
    let contatos = v.get("contatos")?.as_array()?;
    let nomes: Vec<&str> = v.get("pinos")?.as_array()?.iter().filter_map(|x| x.as_str()).collect();
    let n_bin = dados::pinos_binario().get("classes")?.get(cid).and_then(|c| c.get("pins")).and_then(|p| p.as_object())?.len();
    let mut ligacoes = Vec::new();
    for c in contatos {
        let par = c.get("pinos")?.as_array()?;
        let (pa, pb) = (par.first()?.as_str()?, par.get(1)?.as_str()?);
        let i = nomes.iter().position(|n| *n == pa)?;
        let j = nomes.iter().position(|n| *n == pb)?;
        if i >= n_bin || j >= n_bin {
            return None;
        }
        ligacoes.push((i, j, cond(c.get("fecha_quando")?.as_str()?)?));
    }
    if ligacoes.is_empty() {
        return None;
    }
    let fonte = if papel.starts_with("contato_temporizado") { Fonte::Temporizador } else { Fonte::Rotulo };
    Some(Papel::Chaves { ligacoes, fonte, polos: POLOS.contains(&cid) || papel == "termico" })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn embutidos_cobrem_o_modelo_validado() {
        let t = Papeis::embutidos();
        for c in ["8000", "8016", "7000", "10050"] {
            assert_eq!(t.get(c), Some(&Papel::Contato { modo: Modo::Na }));
        }
        for c in ["8001", "8017", "7001", "10051"] {
            assert_eq!(t.get(c), Some(&Papel::Contato { modo: Modo::Nc }));
        }
        assert_eq!(t.get("9000"), Some(&Papel::Bobina));
        assert_eq!(t.get("9008"), Some(&Papel::Lampada));
        assert_eq!(t.get("6007"), Some(&Papel::Polos { modo: ModoPolos::Fechado }));
    }

    #[test]
    fn json_do_re_acrescenta_sem_sobrepor() {
        let t = Papeis::padrao();
        // embutido prevalece
        assert_eq!(t.get("8000"), Some(&Papel::Contato { modo: Modo::Na }));
        // NA-NC 7002: 11-12 fecha com estado==0, 13-14 com estado==1 (pinos p1,p3 e p2,p4)
        match t.get("7002") {
            Some(Papel::Chaves { ligacoes, fonte: Fonte::Rotulo, polos: false }) => {
                assert_eq!(ligacoes, &vec![(0, 2, Cond::Estado(0)), (1, 3, Cond::Estado(1))]);
            }
            o => panic!("7002: {o:?}"),
        }
        // comutado 7003: 11-12 (p1,p2) estado==0; 11-14 (p1,p3) estado==1
        match t.get("7003") {
            Some(Papel::Chaves { ligacoes, .. }) => assert_eq!(ligacoes, &vec![(0, 1, Cond::Estado(0)), (0, 2, Cond::Estado(1))]),
            o => panic!("7003: {o:?}"),
        }
        // contato temporizado 7004 le a saida do temporizador
        assert!(matches!(t.get("7004"), Some(Papel::Chaves { fonte: Fonte::Temporizador, .. })));
        assert_eq!(t.get("9004"), Some(&Papel::Temporizador(TipoTemp::Ton)));
        assert_eq!(t.get("9005"), Some(&Papel::Temporizador(TipoTemp::Tof)));
        assert_eq!(t.get("9006"), Some(&Papel::Temporizador(TipoTemp::TonTof)));
        assert_eq!(t.get("9007"), Some(&Papel::Temporizador(TipoTemp::Intermitente)));
        assert_eq!(t.get("1000"), Some(&Papel::Motor));
        // disjuntor: conduz com estado==1 (inicia aberto); fusivel: estado==0 (inicia integro)
        assert!(matches!(t.get("6000"), Some(Papel::Chaves { ligacoes, .. }) if ligacoes == &vec![(0, 1, Cond::Estado(1))]));
        assert!(matches!(t.get("5000"), Some(Papel::Chaves { ligacoes, .. }) if ligacoes == &vec![(0, 1, Cond::Estado(0))]));
        // pulso (9015): ainda sem modelo
        assert!(t.get("9015").is_none());
    }
}
