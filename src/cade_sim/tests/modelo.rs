//! Semantica do motor alem do que o Python cobre: contatos NA-NC / comutados, temporizadores
//! 9004/9005/9006 com contatos 7004.., disjuntor/fusivel, motor, curto. Os circuitos sao montados
//! com `cade_build` (spec baixa) — a mesma rota do gerador; nada de `.cad` escrito a mao.

use cade_sim::{entradas_de_json, Circuito, EstadoSim, Papeis, Status};
use serde_json::{json, Value};

/// Fonte monofasica -X (3003) nos trilhos L1/N + `simbolos` + `conexoes` [(id, pino), (id, pino)].
fn montar(simbolos: Value, conexoes: &[((&str, &str), (&str, &str))], troca_temp: Option<(&str, &str)>) -> Circuito {
    montar_com_fios(simbolos, conexoes, &[], troca_temp)
}

/// Como [`montar`], com fios manuais `[x1, y1, x2, y2]` (pinos que o roteador nao alcanca, ex. 7007.p3).
fn montar_com_fios(simbolos: Value, conexoes: &[((&str, &str), (&str, &str))], fios: &[[i64; 4]], troca_temp: Option<(&str, &str)>) -> Circuito {
    let mut sims = vec![json!({"classe": "3003", "x": 20, "y": 10, "rotulo": "-X", "id": "X"})];
    sims.extend(simbolos.as_array().unwrap().iter().cloned());
    let mut con = vec![
        json!({"de": ["X", "L"], "para": ["L1", "rail"]}),
        json!({"de": ["X", "N"], "para": ["N", "rail"]}),
    ];
    for ((a, pa), (b, pb)) in conexoes {
        let ponta = |id: &str, pino: &str| if id == "L1" || id == "N" { json!([id, "rail"]) } else { json!([id, pino]) };
        con.push(json!({"de": ponta(a, pa), "para": ponta(b, pb)}));
    }
    let spec = json!({
        "titulo": "T",
        "rails": [{"nome": "L1", "y": 14, "x0": 10, "x1": 220}, {"nome": "N", "y": 250, "x0": 10, "x1": 220}],
        "simbolos": sims,
        "conexoes": con,
        "fios": fios.iter().map(|f| json!({"x1": f[0], "y1": f[1], "x2": f[2], "y2": f[3]})).collect::<Vec<_>>(),
    });
    let saida = cade_build::construir(&spec).unwrap_or_else(|e| panic!("{e}"));
    let mut bytes = saida.bytes;
    if let Some((unidade, tempo)) = troca_temp {
        // temporizador-carga: rotulo 5 = unidade, rotulo 6 = tempo (docs/re-engenharia.md 11.4)
        let txt = String::from_utf8(bytes).unwrap();
        let i = txt.find("#A1#A2#").expect("temporizador nao encontrado no .cad") + "#A1#A2#".len();
        let resto: Vec<&str> = txt[i..].splitn(3, '#').collect();
        bytes = format!("{}{}#{}#{}", &txt[..i], unidade, tempo, resto[2]).into_bytes();
    }
    let c = Circuito::de_bytes(&bytes, Papeis::padrao()).unwrap();
    assert!(c.soltos.is_empty(), "pinos soltos: {:?}", c.soltos);
    c
}

fn est(c: &Circuito, ent: Value, avanca: f64) -> EstadoSim {
    c.estado(&entradas_de_json(&ent), &[], avanca, None)
}

#[test]
fn on_delay_9004_com_contato_7004_por_rotulo() {
    // S1 energiza KT1 (9004, 5 x 1 s); o contato 7004 de mesmo rotulo acende H1 depois do tempo
    let c = montar(
        json!([
            {"classe": "8000", "x": 40, "y": 40, "rotulo": "-S1", "id": "S1"},
            {"classe": "9004", "x": 40, "y": 100, "rotulo": "-KT1", "id": "KT1"},
            {"classe": "7004", "x": 120, "y": 40, "rotulo": "-KT1", "id": "KA"},
            {"classe": "9008", "x": 120, "y": 100, "rotulo": "-H1", "id": "H1"}
        ]),
        &[
            (("L1", "A"), ("S1", "A")),
            (("S1", "B"), ("KT1", "A")),
            (("KT1", "B"), ("N", "B")),
            (("L1", "A"), ("KA", "A")),
            (("KA", "B"), ("H1", "A")),
            (("H1", "B"), ("N", "B")),
        ],
        None,
    );
    assert_eq!(c.entradas, ["S1"], "o contato 7004 le o temporizador, nao e entrada");
    assert!(c.bobinas.contains_key("KT1"));
    let e = est(&c, json!({}), 10.0);
    assert!(e.bobinas.is_empty() && e.lampadas.is_empty());
    let e = est(&c, json!({"S1": true}), 0.0);
    assert_eq!(e.bobinas, ["KT1"], "a carga energiza na hora");
    assert!(e.lampadas.is_empty(), "mas o contato temporizado ainda esta aberto");
    assert_eq!(e.temporizadores[0].tipo, "ton");
    assert_eq!(e.temporizadores[0].tempo, 5.0);
    assert!(est(&c, json!({"S1": true}), 4.9).lampadas.is_empty());
    let e = est(&c, json!({"S1": true}), 5.0);
    assert_eq!(e.lampadas, ["H1"]);
    assert!(e.temporizadores[0].saida);
    // reset imediato ao desenergizar
    let mut st = c.novo_estado(&[], None);
    c.avancar(&mut st, &entradas_de_json(&json!({"S1": true})), 3.0);
    let e = c.avancar(&mut st, &entradas_de_json(&json!({})), 1.0);
    assert_eq!(e.temporizadores[0].decorrido, 0.0);
    assert!(c.avancar(&mut st, &entradas_de_json(&json!({"S1": true})), 3.0).lampadas.is_empty());
    assert_eq!(c.avancar(&mut st, &entradas_de_json(&json!({"S1": true})), 2.0).lampadas, ["H1"]);
}

#[test]
fn unidade_e_tempo_vem_dos_rotulos_5_e_6() {
    // unidade '3' = x1 tick (0,1 s); tempo 15 -> 1,5 s  (acervo: `T1##IN#Q#3#15`)
    let sims = json!([
        {"classe": "8000", "x": 40, "y": 40, "rotulo": "-S1", "id": "S1"},
        {"classe": "9004", "x": 40, "y": 100, "rotulo": "-KT1", "id": "KT1"}
    ]);
    let con = [(("L1", "A"), ("S1", "A")), (("S1", "B"), ("KT1", "A")), (("KT1", "B"), ("N", "B"))];
    let t = |u, tempo| {
        let c = montar(sims.clone(), &con, Some((u, tempo)));
        est(&c, json!({"S1": true}), 0.0).temporizadores[0].tempo
    };
    assert_eq!(t("3", "15"), 1.5);
    assert_eq!(t("0", "2"), 2.0); // x10 ticks = 1 s
    assert_eq!(t("1", "2"), 20.0); // x100 ticks = 10 s
    assert_eq!(t("2", "1"), 100.0); // x1000 ticks = 100 s
    assert_eq!(t("0", "0.5"), 0.0, "atoi: fracao vira 0 (comuta no 1o tick)");
}

/// S1 energiza o temporizador `classe_t` (rotulo -KT); o contato temporizado `classe_c` (rotulo -KT)
/// alimenta H1. `unidade/tempo` ajustam os rotulos 5/6 do temporizador.
fn com_temporizador(classe_t: &str, classe_c: &str, unidade: &str, tempo: &str) -> Circuito {
    montar(
        json!([
            {"classe": "8000", "x": 40, "y": 40, "rotulo": "-S1", "id": "S1"},
            {"classe": classe_t, "x": 40, "y": 100, "rotulo": "-KT", "id": "KT"},
            {"classe": classe_c, "x": 120, "y": 40, "rotulo": "-KT", "id": "KA"},
            {"classe": "9008", "x": 120, "y": 100, "rotulo": "-H1", "id": "H1"}
        ]),
        &[
            (("L1", "A"), ("S1", "A")),
            (("S1", "B"), ("KT", "A")),
            (("KT", "B"), ("N", "B")),
            (("L1", "A"), ("KA", "A")),
            (("KA", "B"), ("H1", "A")),
            (("H1", "B"), ("N", "B")),
        ],
        Some((unidade, tempo)),
    )
}

#[test]
fn off_delay_9005_segura_o_contato_nc_7009_aberto_depois_de_soltar() {
    // NC temporizado: lampada acesa em repouso; energizar abre na hora; ao soltar, so volta apos 3 s
    let c = com_temporizador("9005", "7009", "0", "3");
    let mut st = c.novo_estado(&[], None);
    let on = entradas_de_json(&json!({"S1": true}));
    let off = entradas_de_json(&json!({}));
    assert_eq!(c.avancar(&mut st, &off, 5.0).lampadas, ["H1"], "repouso: NC fechado");
    assert!(c.avancar(&mut st, &on, 0.0).lampadas.is_empty(), "abre na hora");
    assert!(c.avancar(&mut st, &off, 2.0).lampadas.is_empty(), "segura 3 s");
    assert_eq!(c.avancar(&mut st, &off, 1.0).lampadas, ["H1"], "fecha aos 3 s");
    // reenergizar recarrega T
    c.avancar(&mut st, &on, 0.0);
    c.avancar(&mut st, &off, 2.5);
    c.avancar(&mut st, &on, 0.0);
    assert!(c.avancar(&mut st, &off, 2.5).lampadas.is_empty());
    assert_eq!(c.avancar(&mut st, &off, 0.5).lampadas, ["H1"]);
}

#[test]
fn on_off_delay_9006_atrasa_nos_dois_sentidos() {
    let c = com_temporizador("9006", "7013", "0", "2");
    let mut st = c.novo_estado(&[], None);
    let on = entradas_de_json(&json!({"S1": true}));
    let off = entradas_de_json(&json!({}));
    assert_eq!(c.avancar(&mut st, &off, 1.0).lampadas, ["H1"], "NC fechado em repouso");
    assert_eq!(c.avancar(&mut st, &on, 1.9).lampadas, ["H1"], "ainda contando");
    assert!(c.avancar(&mut st, &on, 0.1).lampadas.is_empty(), "2 s: saida liga, NC abre");
    assert!(c.avancar(&mut st, &off, 1.9).lampadas.is_empty());
    assert_eq!(c.avancar(&mut st, &off, 0.1).lampadas, ["H1"], "2 s depois de soltar: volta");
    // soltou antes de completar o ON: a saida nunca ligou
    c.avancar(&mut st, &on, 1.0);
    assert_eq!(c.avancar(&mut st, &off, 5.0).lampadas, ["H1"]);
}

#[test]
fn contato_temporizado_comutado_7007_troca_de_via_no_tempo() {
    // 55 comum (p1), 56 NF (p2) -> H1, 58 NA (p3) -> H2
    // o roteador so alcanca A (p1) e B (p2) da 7007; p3 (96,52) desce por fio manual ate H2.A (96,130)
    let c = montar_com_fios(
        json!([
            {"classe": "8000", "x": 30, "y": 40, "rotulo": "-S1", "id": "S1"},
            {"classe": "9004", "x": 30, "y": 100, "rotulo": "-KT1", "id": "KT1"},
            {"classe": "7007", "x": 90, "y": 40, "rotulo": "-KT1", "id": "KA"},
            {"classe": "9008", "x": 90, "y": 80, "rotulo": "-H1", "id": "H1"},
            {"classe": "9008", "x": 96, "y": 130, "rotulo": "-H2", "id": "H2"}
        ]),
        &[
            (("L1", "A"), ("S1", "A")),
            (("S1", "B"), ("KT1", "A")),
            (("KT1", "B"), ("N", "B")),
            (("L1", "A"), ("KA", "A")),
            (("KA", "B"), ("H1", "A")),
            (("H1", "B"), ("N", "B")),
            (("H2", "B"), ("N", "B")),
        ],
        &[[96, 52, 96, 130]],
        None,
    );
    assert_eq!(est(&c, json!({}), 0.0).lampadas, ["H1"]);
    assert_eq!(est(&c, json!({"S1": true}), 4.9).lampadas, ["H1"]);
    assert_eq!(est(&c, json!({"S1": true}), 5.0).lampadas, ["H2"]);
}

#[test]
fn contato_na_nc_7002_instantaneo() {
    // S1 -> KM1 (9000); 7002: p1-p3 (11-12) NF -> H1, p2-p4 (13-14) NA -> H2
    let c = montar(
        json!([
            {"classe": "8000", "x": 30, "y": 40, "rotulo": "-S1", "id": "S1"},
            {"classe": "9000", "x": 30, "y": 100, "rotulo": "-KM1", "id": "KM1"},
            {"classe": "7002", "x": 80, "y": 40, "rotulo": "-KM1", "id": "K2"},
            {"classe": "9008", "x": 80, "y": 120, "rotulo": "-H1", "id": "H1"},
            {"classe": "9008", "x": 120, "y": 120, "rotulo": "-H2", "id": "H2"}
        ]),
        &[
            (("L1", "A"), ("S1", "A")),
            (("S1", "B"), ("KM1", "A")),
            (("KM1", "B"), ("N", "B")),
            (("L1", "A"), ("K2", "p1")),
            (("L1", "A"), ("K2", "p2")),
            (("K2", "p3"), ("H1", "A")),
            (("K2", "p4"), ("H2", "A")),
            (("H1", "B"), ("N", "B")),
            (("H2", "B"), ("N", "B")),
        ],
        None,
    );
    assert_eq!(est(&c, json!({}), 0.0).lampadas, ["H1"], "repouso: NF fechado");
    let e = est(&c, json!({"S1": true}), 0.0);
    assert_eq!(e.bobinas, ["KM1"]);
    assert_eq!(e.lampadas, ["H2"], "energizado: NA fecha, NF abre");
    assert_eq!(e.status, Status::Ok);
}

#[test]
fn interruptor_inicia_aberto_e_fusivel_inicia_integro() {
    // 2007 (interruptor, estado==1 conduz) e 5000 (fusivel, estado==0 conduz): estado inicial 0 (RE 11.3/11.5)
    let c = montar(
        json!([
            {"classe": "2007", "x": 40, "y": 40, "rotulo": "-Q1", "id": "Q1"},
            {"classe": "9008", "x": 40, "y": 100, "rotulo": "-H1", "id": "H1"},
            {"classe": "5000", "x": 100, "y": 40, "rotulo": "-F1", "id": "F1"},
            {"classe": "9008", "x": 100, "y": 100, "rotulo": "-H2", "id": "H2"}
        ]),
        &[
            (("L1", "A"), ("Q1", "A")),
            (("Q1", "B"), ("H1", "A")),
            (("H1", "B"), ("N", "B")),
            (("L1", "A"), ("F1", "A")),
            (("F1", "B"), ("H2", "A")),
            (("H2", "B"), ("N", "B")),
        ],
        None,
    );
    assert_eq!(c.entradas, ["F1", "Q1"]);
    assert_eq!(est(&c, json!({}), 0.0).lampadas, ["H2"], "interruptor aberto, fusivel integro");
    assert_eq!(est(&c, json!({"Q1": true}), 0.0).lampadas, ["H1", "H2"], "fechar o interruptor liga H1");
    assert_eq!(est(&c, json!({"Q1": true, "F1": true}), 0.0).lampadas, ["H1"], "fusivel queimado abre H2");
}

#[test]
fn curto_fase_neutro_por_contato_fechado() {
    let c = montar(
        json!([{"classe": "8000", "x": 40, "y": 40, "rotulo": "-S1", "id": "S1"}]),
        &[(("L1", "A"), ("S1", "A")), (("S1", "B"), ("N", "B"))],
        None,
    );
    assert_eq!(est(&c, json!({}), 0.0).status, Status::Ok);
    let e = est(&c, json!({"S1": true}), 0.0);
    assert_eq!(e.status, Status::Curto);
    assert_eq!(e.curtos, ["1+N"]);
}

#[test]
fn motor_gira_com_fases_distintas() {
    let c = Circuito::abrir(concat!(env!("CARGO_MANIFEST_DIR"), "/../../tests/golden/partida_direta.cad")).unwrap();
    assert_eq!(c.rotulos_motores(), ["M1"]);
    assert!(est(&c, json!({}), 0.0).motores.is_empty());
    assert_eq!(est(&c, json!({"S1": true}), 0.0).motores, ["M1"]);
    assert!(est(&c, json!({"S1": true, "RT1": true}), 0.0).motores.is_empty(), "termico aberto");
    assert_eq!(est(&c, json!({}), 0.0).status, Status::Ok);
}
