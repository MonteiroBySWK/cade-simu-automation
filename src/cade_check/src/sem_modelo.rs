//! Port de `build_spec.conferir_classes_sem_modelo` / `conferir_classes_em_spec` (A11):
//! recusa com erro claro as classes sem modelo de simulacao (em vez de um falso verde).
//!
//! Duas portas de entrada, como no Python:
//! - [`conferir_em_spec`]: sobre a spec ainda nao compilada (layout topologico OU spec baixa),
//!   usada por [`crate::gate::construir`] antes de compilar;
//! - [`conferir_entidades`]: sobre as entidades de um `.cad`, usada por
//!   [`crate::gate::gate_em`] antes de geo/vinculos.
//!
//! Erro no conjunto curado (pneumatica, grafcet, 9007/9015, ladder sem modelo, sensor 3+ fios,
//! PLC fora de 10204/10205/10206, 6015/6017); aviso para `papel: "outro"` (exceto fios/juncao).

use cade_model::Entidade;
use serde_json::Value;
use std::collections::HashSet;

/// Instrucoes ladder ainda sem modelo (o gate simula as do texto de [`SUPORTADOS`]).
const LADDER_SEM_MODELO: [&str; 6] = ["10064", "10065", "10068", "10069", "10075", "10081"];
/// Temporizadores ainda sem modelo.
const TEMP_SEM_MODELO: [&str; 2] = ["9007", "9015"];
/// Protecoes ainda sem modelo.
const PROT_SEM_MODELO: [&str; 2] = ["6015", "6017"];
/// Unicos PLCs simulados.
const PLC_MODELADO: [&str; 3] = ["10204", "10205", "10206"];
/// Fio/juncao: geometria pura, sem aviso.
const FIOS_SEM_AVISO: [&str; 6] = ["4000", "4001", "4009", "4010", "4018", "4019"];

/// O que o gate simula (texto de `build_spec._SUPORTADOS`, parte de toda mensagem A11).
pub const SUPORTADOS: &str = "contatos 8000/8001/8016/8017, auxiliares 7000/7001, bobinas 9000/9001/9002/9014, \
     sinalizacao 9008/9009..9013/8101/8103, polos 2000/2001/2002/2006/2008, protecao 6007/6009/6010, \
     temporizadores 9004/9005/9006 + contatos 7004..7015, motores, ladder \
     10050/10051/10052/10053/10060/10061/10062/10066/10067, contador 10063, CLP 10204/10205/10206, fontes 3000..3012";

fn papel_de(info: Option<&Value>) -> &str {
    info.and_then(|c| c.get("papel")).and_then(|v| v.as_str()).unwrap_or("")
}

fn pinos_de(info: Option<&Value>) -> usize {
    info.and_then(|c| c.get("pinos")).and_then(|v| v.as_array()).map(|a| a.len()).unwrap_or(0)
}

fn nome_de(_cid: &str, info: Option<&Value>) -> String {
    match info.and_then(|c| c.get("nome")).and_then(|v| v.as_str()).filter(|s| !s.is_empty()) {
        Some(n) => n.to_string(),
        None => "sem nome no catalogo".to_string(),
    }
}

/// `(erro?, motivo)` da classe (`_motivo_sem_modelo`): `None` = classe modelada.
fn motivo(cid: &str, papel: &str, n_pinos: usize) -> Option<(bool, String)> {
    let n: i64 = cid.parse().ok()?;
    if (10500..=10599).contains(&n) {
        return Some((true, "pneumatica (faixa 10500-10599) nao tem modelo (sem pinos no binario)".to_string()));
    }
    if (10100..=10199).contains(&n) {
        return Some((true, "GRAFCET (faixa 10100-10199) nao tem modelo (sem pinos no binario)".to_string()));
    }
    if TEMP_SEM_MODELO.contains(&cid) {
        return Some((
            true,
            format!("temporizador {cid} ainda sem modelo (use 9004/9005/9006 + contatos 7004..7015)"),
        ));
    }
    if LADDER_SEM_MODELO.contains(&cid) {
        return Some((
            true,
            format!(
                "instrucao ladder {cid} ainda sem modelo (use 10050/10051/10052/10053, 10060/10061/10062, TON 10066, \
                 TOF 10067 ou CTU 10063)"
            ),
        ));
    }
    if papel.starts_with("sensor") && n_pinos >= 3 {
        return Some((
            true,
            "sensor 3 fios (PNP/NPN) ainda sem modelo: precisa de alimentacao + saida (use botoeira 8000/8001 como \
             placeholder da deteccao)"
                .to_string(),
        ));
    }
    if (papel == "plc" || (10200..=10299).contains(&n)) && !PLC_MODELADO.contains(&cid) {
        return Some((
            true,
            "CLP com imagem sem modelo: so CPU 10206 + I/O 10204/10205 sao simulados (troque por eles ou desenhe a \
             logica em rele)"
                .to_string(),
        ));
    }
    if PROT_SEM_MODELO.contains(&cid) {
        return Some((
            true,
            "protecao sem modelo (use disjuntor 6002/6003/6009/6010, termico 6007 ou fusivel 5000..5004)".to_string(),
        ));
    }
    if papel == "outro" && !FIOS_SEM_AVISO.contains(&cid) {
        return Some((
            false,
            "sem modelo: ignorada nos testes; confira o comportamento no app (Play) antes de entregar".to_string(),
        ));
    }
    None
}

/// `_msg_sem_modelo(cid, nome, motivo)`.
fn mensagem(cid: &str, nome: &str, motivo: &str) -> String {
    format!(
        "classe {cid} ({nome}) sem modelo de simulacao: {motivo}. O gate simula: {SUPORTADOS}. Alternativas: \
         simplificar para componentes suportados, montar com cad_build validando por fora, ou pedir suporte a classe"
    )
}

fn avaliar(cid: &str, cat: &Value, erros: &mut Vec<String>, avisos: &mut Vec<String>) {
    let info = cat.get(cid);
    let Some((erro, motivo)) = motivo(cid, papel_de(info), pinos_de(info)) else { return };
    let m = mensagem(cid, &nome_de(cid, info), &motivo);
    if erro {
        erros.push(m);
    } else {
        avisos.push(m);
    }
}

/// `conferir_classes_sem_modelo`: classes do `.cad` sem modelo funcional.
/// Erro no conjunto curado, aviso no resto. Ordem de primeira aparicao, sem repetir.
pub fn conferir_entidades(ps: &[Entidade]) -> (Vec<String>, Vec<String>) {
    let cat = cade_model::dados::classes_papeis();
    let mut vistos = HashSet::new();
    let (mut erros, mut avisos) = (Vec::new(), Vec::new());
    for p in ps {
        if !vistos.insert(p.id.clone()) {
            continue;
        }
        avaliar(&p.id, cat, &mut erros, &mut avisos);
    }
    (erros, avisos)
}

/// Todas as classes citadas numa spec (layout topologico OU spec baixa), sem repetir
/// (`_classes_da_spec`): valores de `"classe"` e itens `[id, classe, ...]`.
fn classes_da_spec(spec: &Value) -> Vec<String> {
    fn ver(cid: &str, achadas: &mut Vec<String>) {
        if !cid.is_empty() && cid.bytes().all(|b| b.is_ascii_digit()) && !achadas.iter().any(|c| c == cid) {
            achadas.push(cid.to_string());
        }
    }
    fn varrer(o: &Value, achadas: &mut Vec<String>) {
        match o {
            Value::Object(m) => {
                for (k, v) in m {
                    if k == "classe" {
                        if let Some(s) = v.as_str() {
                            ver(s, achadas);
                        }
                    } else {
                        varrer(v, achadas);
                    }
                }
            }
            Value::Array(a) => {
                if a.len() >= 2 && a[0].as_str().is_some() {
                    if let Some(s) = a[1].as_str() {
                        ver(s, achadas);
                    }
                }
                for v in a {
                    varrer(v, achadas);
                }
            }
            _ => {}
        }
    }
    let mut achadas = Vec::new();
    if spec.is_object() {
        varrer(spec, &mut achadas);
    }
    achadas
}

/// `conferir_classes_em_spec`: A11 sobre a spec ainda nao compilada (pega 10500 etc. mesmo sem
/// geometria). So vale para objeto (como o `isinstance(spec, dict)` do Python).
pub fn conferir_em_spec(spec: &Value) -> (Vec<String>, Vec<String>) {
    let cat = cade_model::dados::classes_papeis();
    let (mut erros, mut avisos) = (Vec::new(), Vec::new());
    for cid in classes_da_spec(spec) {
        avaliar(&cid, cat, &mut erros, &mut avisos);
    }
    (erros, avisos)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn faixas_e_protecao_sao_erro() {
        let (e, _) = conferir_em_spec(&json!({"layout": {"potencia": [{"colunas": [["Q", "6017", "-Q"]]}]}}));
        assert_eq!(e.len(), 1);
        assert!(e[0].starts_with("classe 6017 (Interruptor automático) sem modelo de simulacao: protecao sem modelo"));
        assert!(e[0].contains("O gate simula: contatos 8000/8001"));
        let (e, _) = conferir_em_spec(&json!({"simbolos": [{"classe": "10501"}]}));
        assert!(e[0].contains("pneumatica"));
        let (e, _) = conferir_em_spec(&json!({"simbolos": [{"classe": "10150"}]}));
        assert!(e[0].contains("GRAFCET"));
    }

    #[test]
    fn outro_vira_aviso_e_fio_nao() {
        let (_, a) = conferir_em_spec(&json!({"simbolos": [{"classe": "7018"}]}));
        assert_eq!(a.len(), 1);
        assert!(a[0].contains("sem modelo: ignorada nos testes"));
        let (_, a) = conferir_em_spec(&json!({"simbolos": [{"classe": "4000"}, {"classe": "4001"}]}));
        assert!(a.is_empty());
    }

    #[test]
    fn modeladas_passam() {
        for c in ["8000", "9000", "2002", "6004", "1008", "6007", "10204", "10206", "10050", "10063"] {
            let (e, a) = conferir_em_spec(&json!({"simbolos": [{"classe": c}]}));
            assert!(e.is_empty() && a.is_empty(), "{c}: {e:?} {a:?}");
        }
    }

    #[test]
    fn sem_repetir_e_sem_nome_no_catalogo() {
        let (e, _) = conferir_em_spec(&json!({"simbolos": [{"classe": "6015"}, {"classe": "6015"}]}));
        assert_eq!(e.len(), 1);
        let (e, _) = conferir_em_spec(&json!({"layout": {"comando": [{"serie": [["K", "10599", "-K"]]}]}}));
        assert!(e[0].contains("(sem nome no catalogo)") && e[0].contains("pneumatica"));
    }
}
