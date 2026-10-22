//! Liga o simulador ao gate (`cade gate` / `cade design`): implementa `cade_check::ExecutorTestes`.
//!
//! Reproduz o par `cad_test` + `conferir_chaves_de_teste` do Python: texto `PASSOU/FALHOU/SEM_TESTES`
//! seguido das linhas `[OK ]/[FALHA]` e `RESULTADO: n/m`, e as mensagens de chave inexistente
//! (teste vacuo = falso verde).

use crate::casos::{chaves_invalidas, teste_casos};
use crate::circuito::Circuito;
use cade_check::{ExecutorTestes, SaidaTestes};
use serde_json::Value;

/// Executor de testes funcionais baseado em [`Circuito`].
#[derive(Debug, Clone, Copy, Default)]
pub struct ExecutorSim;

fn lista<S: AsRef<str>>(v: &[S]) -> String {
    cade_model::pyfmt::repr_lista(v)
}

/// `conferir_chaves_de_teste` do Python (`build_spec.py`).
pub fn mensagens_chaves(c: &Circuito, casos: &[Value]) -> Vec<String> {
    let entradas: Vec<&String> = c.entradas.iter().collect();
    let bobinas: Vec<&String> = c.bobinas.keys().collect();
    let lampadas: Vec<&String> = c.lampadas.keys().collect();
    let mut tim = c.ids_temporizadores();
    tim.sort();
    let mut erros = Vec::new();
    for cs in casos {
        let nome = cs.get("nome").and_then(|n| n.as_str()).unwrap_or("?");
        for (campo, k) in chaves_invalidas(c, cs) {
            erros.push(match campo.as_str() {
                "entradas" => format!(
                    "teste '{nome}': entrada '{k}' nao existe no circuito (entradas validas: {}; bobinas: {}). \
                     A chave e o ROTULO do simbolo sem o '-' (ex.: '-S1' -> 'S1').",
                    lista(&entradas),
                    lista(&bobinas)
                ),
                "esperado_lampadas" => format!(
                    "teste '{nome}': '{campo}' cita '{k}', que nao e lampada (lampadas: {}; use o rotulo sem '-', ex.: '-H1' -> 'H1').",
                    lista(&lampadas)
                ),
                "esperado_temporizadores" => {
                    format!("teste '{nome}': '{campo}' cita '{k}', que nao e contato temporizado (temporizadores: {}).", lista(&tim))
                }
                _ => format!("teste '{nome}': '{campo}' cita '{k}', que nao e bobina (bobinas: {}).", lista(&bobinas)),
            });
        }
    }
    erros
}

impl ExecutorTestes for ExecutorSim {
    fn executar(&self, cad: &[u8], casos: &[Value]) -> Option<SaidaTestes> {
        let c = match Circuito::de_bytes(cad, crate::papeis::Papeis::padrao()) {
            Ok(c) => c,
            Err(e) => {
                return Some(SaidaTestes { texto: format!("FALHOU\nERRO ao simular: {e}\n"), chaves_invalidas: vec![] });
            }
        };
        if casos.is_empty() {
            return Some(SaidaTestes {
                texto: "SEM_TESTES: declare casos (chave \"testes\" na spec)".to_string(),
                chaves_invalidas: vec![],
            });
        }
        let r = teste_casos(&c, casos);
        let texto = format!("{}\n{}", if r.aprovado() { "PASSOU" } else { "FALHOU" }, r.texto());
        Some(SaidaTestes { texto, chaves_invalidas: mensagens_chaves(&c, casos) })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn cad() -> Vec<u8> {
        std::fs::read(concat!(env!("CARGO_MANIFEST_DIR"), "/../../tests/golden/partida_direta.cad")).unwrap()
    }

    #[test]
    fn passou_falhou_e_sem_testes() {
        let ok = vec![json!({"nome": "liga", "entradas": {"S1": true}, "esperado": ["KM1"], "status": "OK"})];
        let s = ExecutorSim.executar(&cad(), &ok).unwrap();
        assert!(s.texto.starts_with("PASSOU\n") && s.texto.contains("RESULTADO: 1/1 OK"), "{}", s.texto);
        assert!(s.chaves_invalidas.is_empty());
        let mau = vec![json!({"nome": "liga", "entradas": {"S1": true}, "esperado": []})];
        let s = ExecutorSim.executar(&cad(), &mau).unwrap();
        assert!(s.texto.starts_with("FALHOU\n") && s.texto.contains("[FALHA] liga"), "{}", s.texto);
        let s = ExecutorSim.executar(&cad(), &[]).unwrap();
        assert!(s.texto.starts_with("SEM_TESTES"));
    }

    #[test]
    fn chave_inexistente_vira_mensagem_do_python() {
        let casos = vec![json!({"nome": "x", "entradas": {"FANTASMA": true}, "esperado": ["KM1"]})];
        let s = ExecutorSim.executar(&cad(), &casos).unwrap();
        assert_eq!(s.chaves_invalidas.len(), 1);
        assert!(s.chaves_invalidas[0].starts_with("teste 'x': entrada 'FANTASMA' nao existe no circuito (entradas validas: ['RT1', 'S0', 'S1']"));
    }
}
