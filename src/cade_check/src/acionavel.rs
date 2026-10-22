//! Port de `build_spec.acionavel_solto` / `acionavel_curto`: transforma a saida crua do `geo_check`
//! em mensagens que dizem o que fazer.

const FONTES: [&str; 9] = ["3000", "3001", "3003", "3004", "3005", "3006", "3007", "3011", "3012"];

/// `_PINO_SOLTO`: `^(?P<rot>.*)\((?P<classe>\d+)\)\.(?P<pino>[^@]+)@\((?P<x>-?\d+), (?P<y>-?\d+)\)$`.
fn casar_solto(s: &str) -> Option<(&str, &str, &str, &str, &str)> {
    let s = s.strip_suffix(')')?;
    let arroba = s.rfind("@(")?;
    let (esq, coords) = (&s[..arroba], &s[arroba + 2..]);
    let (x, y) = coords.split_once(", ")?;
    let inteiro = |t: &str| {
        let d = t.strip_prefix('-').unwrap_or(t);
        !d.is_empty() && d.bytes().all(|b| b.is_ascii_digit())
    };
    if !inteiro(x) || !inteiro(y) {
        return None;
    }
    // esq = "<rot>(<classe>).<pino>"; o pino nao contem '@' e o rotulo e guloso ("(.*)\(")
    let mut cand = None;
    for (i, _) in esq.match_indices('(') {
        let resto = &esq[i + 1..];
        let Some(fim) = resto.find(')') else { continue };
        let classe = &resto[..fim];
        let apos = &resto[fim + 1..];
        if !classe.is_empty() && classe.bytes().all(|b| b.is_ascii_digit()) {
            if let Some(pino) = apos.strip_prefix('.') {
                if !pino.is_empty() && !pino.contains('@') {
                    cand = Some((&esq[..i], classe, pino)); // ultimo '(' valido vence (rot guloso)
                }
            }
        }
    }
    let (rot, classe, pino) = cand?;
    Some((rot, classe, pino, x, y))
}

/// `acionavel_solto("-X(3007).L3@(30, 20)")` -> mensagem com o que fazer.
pub fn acionavel_solto(s: &str) -> String {
    let Some((rot, cid, pino, x, y)) = casar_solto(s) else {
        return format!("pino solto: {}", s);
    };
    if FONTES.contains(&cid) {
        return format!(
            "pino {pino} da fonte {rot} ({cid}) solto em ({x},{y}): ligue-o ao trilho {pino} (fontes: \
             {{\"pinos\":{{\"{pino}\":\"{pino}\"}}}}; cada pino da fonte vai a um trilho)"
        );
    }
    if cid == "1000" {
        return format!(
            "pino {pino} do motor {rot} solto em ({x},{y}): ligue TODOS os terminais (U1/V1/W1 as fases, PE ao \
             trilho PE) — use potencia.colunas com fases e \"pe\":\"PE\""
        );
    }
    format!(
        "pino {pino} de {rot} ({cid}) solto em ({x},{y}): nenhum fio termina nesse ponto; ligue o pino (conexao \
         de/para) ou remova o simbolo"
    )
}

/// `acionavel_curto("1+N na mesma net: ...")` -> mensagem.
pub fn acionavel_curto(c: &str) -> String {
    let dica = if c.contains('N') && c.contains('P') {
        " — PE ligado ao neutro: crie trilho PE separado (\"pe\":\"PE\")"
    } else if c.contains('1') || c.contains('2') || c.contains('3') {
        " — duas fases no mesmo no: confira trilhos L1/L2/L3 e a coluna de cada fase"
    } else {
        ""
    };
    format!("CURTO {}{}", c, dica)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn solto_de_fonte() {
        assert_eq!(
            acionavel_solto("-X(3007).L3@(30, 20)"),
            "pino L3 da fonte -X (3007) solto em (30,20): ligue-o ao trilho L3 (fontes: {\"pinos\":{\"L3\":\"L3\"}}; \
             cada pino da fonte vai a um trilho)"
        );
    }

    #[test]
    fn solto_de_motor_e_generico() {
        assert!(acionavel_solto("-M1(1000).PE@(-1, 2)").starts_with("pino PE do motor -M1 solto em (-1,2)"));
        assert!(acionavel_solto("-H1(9008).p2@(90, 52)").contains("nenhum fio termina nesse ponto"));
    }

    #[test]
    fn solto_ilegivel_vira_pino_solto() {
        assert_eq!(acionavel_solto("lixo"), "pino solto: lixo");
    }

    #[test]
    fn curto_com_dica() {
        assert!(acionavel_curto("N+P na mesma net: -X.N, -X.PE").ends_with("(\"pe\":\"PE\")"));
        assert!(acionavel_curto("1+2 na mesma net: -X.L1, -X.L2").contains("duas fases"));
        assert_eq!(acionavel_curto("A+B"), "CURTO A+B");
    }
}
