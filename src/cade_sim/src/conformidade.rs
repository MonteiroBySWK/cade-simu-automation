//! Conformidade: o motor Rust contra o app real (golden gravado no Wine por `app_sim`).
//!
//! Layout de um caso (`tests/conformidade/<caso>/`):
//!
//! - `circuito.cad` — o desenho;
//! - `cenario.json` — sequencia temporal de acoes:
//!   `{"versao":1,"descricao":"..","acoes":[{"acao":"pressionar","alvo":"S1"},
//!   {"acao":"esperar","ms":500},{"acao":"soltar","alvo":"S1"},{"acao":"alternar","alvo":"RT1"},
//!   {"acao":"reiniciar"}]}` — `pressionar`/`soltar` seguram/largam um botao, `alternar` clica numa
//!   chave que trava (termico, disjuntor), `reiniciar` para e reinicia a simulacao;
//! - `golden_app.json` — estado observado apos CADA acao:
//!   `{"versao":1,"fonte":"app"|"oraculo_python","passos":[{"i":0,"t_ms":0,"bobinas":[..],
//!   "lampadas":[..],"motores":[..],"saidas_clp":[..],"curto":false}, ..]}`.
//!
//! Campos ausentes no golden nao sao comparados (o gravador so precisa registrar o que o app
//! mostra). Conjuntos comparam sem ordem.

use crate::circuito::{Circuito, Entradas, EstadoSim, Status};
use serde_json::{json, Map, Value};
use std::collections::BTreeSet;
use std::fs;
use std::path::Path;

/// Campos de conjunto comparados (golden pode omitir qualquer um).
pub const CAMPOS_CONJUNTO: [&str; 5] = ["bobinas", "lampadas", "motores", "saidas_clp", "temporizadores"];

#[derive(Clone, Debug, PartialEq)]
pub enum Acao {
    Pressionar(String),
    Soltar(String),
    Alternar(String),
    Esperar(u64),
    Reiniciar,
}

impl Acao {
    pub fn de_json(v: &Value) -> Result<Acao, String> {
        let nome = v.get("acao").and_then(|a| a.as_str()).ok_or("acao sem campo `acao`")?;
        let alvo = || v.get("alvo").and_then(|a| a.as_str()).map(String::from).ok_or_else(|| format!("acao `{nome}` sem `alvo`"));
        match nome {
            "pressionar" => Ok(Acao::Pressionar(alvo()?)),
            "soltar" => Ok(Acao::Soltar(alvo()?)),
            "alternar" => Ok(Acao::Alternar(alvo()?)),
            "esperar" => Ok(Acao::Esperar(v.get("ms").and_then(|m| m.as_u64()).ok_or("acao `esperar` sem `ms` inteiro")?)),
            "reiniciar" => Ok(Acao::Reiniciar),
            o => Err(format!("acao desconhecida: {o:?}")),
        }
    }
}

#[derive(Clone, Debug)]
pub struct Cenario {
    pub descricao: String,
    pub acoes: Vec<Acao>,
}

impl Cenario {
    pub fn de_json(v: &Value) -> Result<Cenario, String> {
        let acoes = v.get("acoes").and_then(|a| a.as_array()).ok_or("cenario sem `acoes`")?;
        Ok(Cenario {
            descricao: v.get("descricao").and_then(|d| d.as_str()).unwrap_or("").to_string(),
            acoes: acoes.iter().map(Acao::de_json).collect::<Result<_, _>>()?,
        })
    }
}

/// Estado observado apos uma acao.
#[derive(Clone, Debug, PartialEq)]
pub struct Observacao {
    pub i: usize,
    pub t_ms: u64,
    pub estado: EstadoSim,
    /// saidas do CLP (ladder ainda nao implementado: sempre vazio)
    pub saidas_clp: Vec<String>,
}

impl Observacao {
    pub fn to_json(&self) -> Value {
        json!({
            "i": self.i, "t_ms": self.t_ms,
            "bobinas": self.estado.bobinas, "lampadas": self.estado.lampadas,
            "motores": self.estado.motores, "saidas_clp": self.saidas_clp,
            "temporizadores": self.estado.temporizadores_on().into_iter().collect::<Vec<_>>(),
            "curto": self.estado.status == Status::Curto,
        })
    }
}

/// Executa o cenario no motor. Erro se uma acao cita um rotulo que o desenho nao tem (teste vacuo).
pub fn executar(c: &Circuito, cen: &Cenario) -> Result<Vec<Observacao>, String> {
    let valido = |k: &str| c.entradas.iter().any(|e| e == k) || c.bobinas.contains_key(k);
    let mut ent = Entradas::new();
    let mut st = c.novo_estado(&[], None);
    let mut t_ms = 0u64;
    let mut obs = Vec::new();
    for (i, a) in cen.acoes.iter().enumerate() {
        let mut avanca = 0.0;
        match a {
            Acao::Pressionar(k) | Acao::Soltar(k) | Acao::Alternar(k) => {
                if !valido(k) {
                    return Err(format!("acao {i}: rotulo {k:?} nao existe no circuito (entradas: {:?})", c.entradas));
                }
                match a {
                    Acao::Pressionar(_) => ent.insert(k.clone(), 1),
                    Acao::Soltar(_) => ent.insert(k.clone(), 0),
                    _ => {
                        let v = ent.get(k).copied().unwrap_or(0);
                        ent.insert(k.clone(), (v == 0) as i64)
                    }
                };
            }
            Acao::Esperar(ms) => {
                avanca = *ms as f64 / 1000.0;
                t_ms += ms;
            }
            Acao::Reiniciar => {
                ent.clear();
                st = c.novo_estado(&[], None);
            }
        }
        let estado = c.avancar(&mut st, &ent, avanca);
        obs.push(Observacao { i, t_ms, estado, saidas_clp: vec![] });
    }
    Ok(obs)
}

/// Uma divergencia motor x golden.
#[derive(Clone, Debug, PartialEq)]
pub struct Diff {
    pub passo: usize,
    pub campo: String,
    pub golden: Value,
    pub motor: Value,
}

fn conjunto(v: &Value) -> Option<BTreeSet<String>> {
    v.as_array().map(|a| a.iter().filter_map(|s| s.as_str().map(String::from)).collect())
}

/// Compara observacoes do motor com o golden (so os campos presentes nele).
pub fn comparar(obs: &[Observacao], golden: &Value) -> Vec<Diff> {
    let mut diffs = Vec::new();
    let Some(passos) = golden.get("passos").and_then(|p| p.as_array()) else {
        return vec![Diff { passo: 0, campo: "passos".into(), golden: Value::Null, motor: json!(obs.len()) }];
    };
    if passos.len() != obs.len() {
        diffs.push(Diff { passo: 0, campo: "n_passos".into(), golden: json!(passos.len()), motor: json!(obs.len()) });
    }
    for (g, o) in passos.iter().zip(obs) {
        let mj = o.to_json();
        let passo = g.get("i").and_then(|i| i.as_u64()).map(|i| i as usize).unwrap_or(o.i);
        for campo in CAMPOS_CONJUNTO {
            if let Some(gv) = g.get(campo) {
                if conjunto(gv) != conjunto(&mj[campo]) {
                    diffs.push(Diff { passo, campo: campo.into(), golden: gv.clone(), motor: mj[campo].clone() });
                }
            }
        }
        if let Some(gv) = g.get("curto").and_then(|c| c.as_bool()) {
            if Some(gv) != mj["curto"].as_bool() {
                diffs.push(Diff { passo, campo: "curto".into(), golden: json!(gv), motor: mj["curto"].clone() });
            }
        }
    }
    diffs
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Resultado {
    Ok,
    Divergente,
    /// pasta sem `golden_app.json`
    SemGolden,
    /// erro de leitura/circuito/cenario
    Erro,
}

impl Resultado {
    pub fn as_str(&self) -> &'static str {
        match self {
            Resultado::Ok => "ok",
            Resultado::Divergente => "divergente",
            Resultado::SemGolden => "sem_golden",
            Resultado::Erro => "erro",
        }
    }
}

pub struct RelCaso {
    pub nome: String,
    pub fonte: String,
    pub resultado: Resultado,
    pub passos: usize,
    pub erro: Option<String>,
    pub diffs: Vec<Diff>,
}

pub struct Relatorio {
    pub casos: Vec<RelCaso>,
}

impl Relatorio {
    pub fn n(&self, r: Resultado) -> usize {
        self.casos.iter().filter(|c| c.resultado == r).count()
    }

    /// Aprovado = nenhum caso divergente/erro e ao menos um caso ok.
    pub fn aprovado(&self) -> bool {
        self.n(Resultado::Divergente) == 0 && self.n(Resultado::Erro) == 0 && self.n(Resultado::Ok) > 0
    }

    /// Quantos goldens ainda sao provisorios (nao gravados no app).
    pub fn provisorios(&self) -> usize {
        self.casos.iter().filter(|c| c.resultado != Resultado::SemGolden && c.fonte != "app").count()
    }

    pub fn to_json(&self) -> Value {
        let casos: Vec<Value> = self
            .casos
            .iter()
            .map(|c| {
                let mut m = Map::new();
                m.insert("caso".into(), json!(c.nome));
                m.insert("resultado".into(), json!(c.resultado.as_str()));
                m.insert("fonte".into(), json!(c.fonte));
                m.insert("passos".into(), json!(c.passos));
                if let Some(e) = &c.erro {
                    m.insert("erro".into(), json!(e));
                }
                m.insert(
                    "diffs".into(),
                    Value::Array(c.diffs.iter().map(|d| json!({"passo": d.passo, "campo": d.campo, "golden": d.golden, "motor": d.motor})).collect()),
                );
                Value::Object(m)
            })
            .collect();
        json!({
            "ok": self.n(Resultado::Ok),
            "divergentes": self.n(Resultado::Divergente),
            "erros": self.n(Resultado::Erro),
            "sem_golden": self.n(Resultado::SemGolden),
            "goldens_provisorios": self.provisorios(),
            "aprovado": self.aprovado(),
            "casos": casos,
        })
    }

    pub fn texto(&self) -> String {
        let mut s = String::new();
        for c in &self.casos {
            let tag = match c.resultado {
                Resultado::Ok => "OK        ",
                Resultado::Divergente => "DIVERGENTE",
                Resultado::SemGolden => "SEM GOLDEN",
                Resultado::Erro => "ERRO      ",
            };
            s.push_str(&format!("  [{tag}] {} ({} passos, golden: {})\n", c.nome, c.passos, if c.fonte.is_empty() { "-" } else { &c.fonte }));
            if let Some(e) = &c.erro {
                s.push_str(&format!("      {e}\n"));
            }
            for d in &c.diffs {
                s.push_str(&format!("      passo {} {}: golden={} motor={}\n", d.passo, d.campo, d.golden, d.motor));
            }
        }
        s.push_str(&format!(
            "CONFORMIDADE: {} ok, {} divergente(s), {} erro(s), {} sem golden; {} golden(s) provisorio(s) (fonte != app)\n",
            self.n(Resultado::Ok),
            self.n(Resultado::Divergente),
            self.n(Resultado::Erro),
            self.n(Resultado::SemGolden),
            self.provisorios()
        ));
        s
    }
}

fn le_json(p: &Path) -> Result<Value, String> {
    let t = fs::read_to_string(p).map_err(|e| format!("{}: {e}", p.display()))?;
    serde_json::from_str(&t).map_err(|e| format!("{}: json invalido: {e}", p.display()))
}

/// Roda um caso (pasta com `circuito.cad` + `cenario.json` + `golden_app.json`).
pub fn rodar_caso(dir: &Path) -> RelCaso {
    let nome = dir.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    let mut r = RelCaso { nome, fonte: String::new(), resultado: Resultado::Erro, passos: 0, erro: None, diffs: vec![] };
    let res: Result<(), String> = (|| {
        let c = Circuito::abrir(&dir.join("circuito.cad").to_string_lossy())?;
        let cen = Cenario::de_json(&le_json(&dir.join("cenario.json"))?)?;
        r.passos = cen.acoes.len();
        let obs = executar(&c, &cen)?;
        let gp = dir.join("golden_app.json");
        if !gp.is_file() {
            r.resultado = Resultado::SemGolden;
            return Ok(());
        }
        let g = le_json(&gp)?;
        r.fonte = g.get("fonte").and_then(|f| f.as_str()).unwrap_or("desconhecida").to_string();
        r.diffs = comparar(&obs, &g);
        r.resultado = if r.diffs.is_empty() { Resultado::Ok } else { Resultado::Divergente };
        Ok(())
    })();
    if let Err(e) = res {
        r.erro = Some(e);
        r.resultado = Resultado::Erro;
    }
    r
}

/// Roda todos os casos (subpastas com `circuito.cad`) de `raiz`, em ordem alfabetica.
pub fn rodar(raiz: &Path) -> Result<Relatorio, String> {
    let mut dirs: Vec<_> = fs::read_dir(raiz)
        .map_err(|e| format!("{}: {e}", raiz.display()))?
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.is_dir() && p.join("circuito.cad").is_file())
        .collect();
    dirs.sort();
    Ok(Relatorio { casos: dirs.iter().map(|d| rodar_caso(d)).collect() })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn acao_de_json() {
        let v: Value = serde_json::from_str(r#"{"acao":"esperar","ms":250}"#).unwrap();
        assert_eq!(Acao::de_json(&v).unwrap(), Acao::Esperar(250));
        assert!(Acao::de_json(&json!({"acao":"pressionar"})).is_err());
        assert!(Acao::de_json(&json!({"acao":"dancar"})).is_err());
    }

    #[test]
    fn comparar_ignora_campos_ausentes_e_ordem() {
        let st = EstadoSim {
            status: Status::Ok,
            bobinas: vec!["KM1".into(), "KM2".into()],
            lampadas: vec![],
            motores: vec![],
            temporizadores: vec![],
            curtos: vec![],
        };
        let obs = vec![Observacao { i: 0, t_ms: 0, estado: st, saidas_clp: vec![] }];
        let g = json!({"passos":[{"i":0,"bobinas":["KM2","KM1"]}]});
        assert!(comparar(&obs, &g).is_empty());
        let g = json!({"passos":[{"i":0,"bobinas":["KM1"],"curto":true}]});
        let d = comparar(&obs, &g);
        assert_eq!(d.len(), 2);
        assert_eq!(d[0].campo, "bobinas");
        assert_eq!(d[1].campo, "curto");
        let g = json!({"passos":[]});
        assert_eq!(comparar(&obs, &g)[0].campo, "n_passos");
    }
}
