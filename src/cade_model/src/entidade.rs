//! Port de `tools/dissect.py`: `split_entities`, `split_all`, `parse_ent`.
//!
//! Tudo opera sobre `&str` ja decodificado de latin1. Os casamentos so olham caracteres ASCII,
//! entao fatiar nas posicoes de `#`/`*` e sempre seguro.

/// Entidade decomposta (`parse_ent`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Entidade {
    pub seq: String,
    pub id: String,
    pub labels: Vec<String>,
    pub nums: Vec<String>,
}

impl Entidade {
    /// Serializa como o `cad_build`: `*seq*id#labels...#*nums...` (sem o `#` separador final).
    pub fn serializar(&self, seq: &str) -> String {
        format!("*{}*{}#{}#*{}", seq, self.id, self.labels.join("#"), self.nums.join("*"))
    }
}

/// Resultado de `split_entities` / `split_all`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Particao {
    pub header: String,
    pub ents: Vec<String>,
    pub footer: String,
}

fn digitos(b: &[u8], mut i: usize) -> (usize, usize) {
    let ini = i;
    while i < b.len() && b[i].is_ascii_digit() {
        i += 1;
    }
    (ini, i)
}

/// `\d+\*-?\d+#` a partir de `i`; devolve o indice logo apos o `#`.
fn prefixo_ent(b: &[u8], i: usize) -> Option<usize> {
    let (a, mut j) = digitos(b, i);
    if j == a || j >= b.len() || b[j] != b'*' {
        return None;
    }
    j += 1;
    if j < b.len() && b[j] == b'-' {
        j += 1;
    }
    let (a2, j2) = digitos(b, j);
    if j2 == a2 || j2 >= b.len() || b[j2] != b'#' {
        return None;
    }
    Some(j2 + 1)
}

/// `#(?=\*\d+\*-?\d+#)` em `b[i]`.
fn inicio_ent(b: &[u8], i: usize) -> bool {
    b[i] == b'#' && i + 1 < b.len() && b[i + 1] == b'*' && prefixo_ent(b, i + 2).is_some()
}

/// Python `rest[:-1]` / `rest[-1:]` (usado quando nao ha `$$$`).
fn corta_ultimo(s: &str) -> (&str, &str) {
    match s.char_indices().last() {
        Some((i, _)) => (&s[..i], &s[i..]),
        None => ("", ""),
    }
}

/// `prefixo_ent` sem o `#` inicial: `*` ja consumido, `i` aponta para o 1o digito.
fn prefixo_ent_sem_hash(b: &[u8], i: usize) -> Option<usize> {
    if b.get(i) != Some(&b'*') {
        return None;
    }
    prefixo_ent(b, i + 1)
}

/// Fim da 1a entidade quando colada (`_desgruda` do Python em `tools/dissect.py`):
/// `#((?:\*-?\d+){4,})#([^#*]*)(?=\*\d+\*-?\d+#)`. Quando a string final da entidade nao e
/// vazia (IP do CPU 10206, texto da classe 8), a proxima entidade vem colada sem `#`:
/// `...*31*32#192.128.0.1*26*10204#...`. Devolve o indice onde a 2a entidade comeca
/// (`m.end()` do Python), ou `None` se `b[i..]` nao casa (com `b[i] == b'#'`).
fn fim_grudada(b: &[u8], i: usize) -> Option<usize> {
    let mut j = i + 1;
    let mut n = 0;
    loop {
        if b.get(j) != Some(&b'*') {
            break;
        }
        j += 1;
        if b.get(j) == Some(&b'-') {
            j += 1;
        }
        let k = j;
        while j < b.len() && b[j].is_ascii_digit() {
            j += 1;
        }
        if j == k {
            return None;
        }
        n += 1;
    }
    if n < 4 || b.get(j) != Some(&b'#') {
        return None;
    }
    j += 1;
    while j < b.len() && b[j] != b'#' && b[j] != b'*' {
        j += 1;
    }
    if prefixo_ent_sem_hash(b, j).is_some() { Some(j) } else { None }
}

/// `_desgruda` do Python: separa entidades coladas pela string final nao vazia.
fn desgrudar(e: &str) -> Vec<String> {
    let b = e.as_bytes();
    let mut out = Vec::new();
    let mut ini = 0;
    let mut i = 0;
    while i < b.len() {
        if b[i] == b'#' {
            if let Some(fim) = fim_grudada(b, i) {
                out.push(e[ini..fim].to_string());
                ini = fim;
                i = fim;
                continue;
            }
        }
        i += 1;
    }
    out.push(e[ini..].to_string());
    out
}

/// `split_entities`: header ate o 1o `#` que antecede `*N*ID#`, entidades, footer a partir de `$$$`.
pub fn split_entities(d: &str) -> Result<Particao, String> {
    let b = d.as_bytes();
    let m = (0..b.len())
        .find(|&i| inicio_ent(b, i))
        .ok_or_else(|| "nenhuma entidade encontrada (padrao `#*N*ID#` ausente)".to_string())?;
    let header = &d[..m + 1];
    let rest = &d[m + 1..];
    let (body, footer) = match rest.find("$$$") {
        Some(f) => (&rest[..f], &rest[f..]),
        None => corta_ultimo(rest),
    };
    let bb = body.as_bytes();
    let mut ents = Vec::new();
    let mut prev = 0;
    for i in 0..bb.len() {
        if inicio_ent(bb, i) {
            ents.extend(desgrudar(&body[prev..i]));
            prev = i + 1;
        }
    }
    ents.extend(desgrudar(&body[prev..]));
    Ok(Particao { header: header.to_string(), ents, footer: footer.to_string() })
}

/// `split_all`: como `split_entities`, mas a entidade 0 (colada ao `CADe_SIMU*`) entra em `ents`.
pub fn split_all(d: &str) -> Result<Particao, String> {
    let mut p = split_entities(d)?;
    const PRE: &str = "CADe_SIMU*";
    if let Some(rest) = p.header.strip_prefix(PRE) {
        // ^CADe_SIMU\*(\d+\*-?\d+#.*)#$
        if let Some(fim) = prefixo_ent(rest.as_bytes(), 0) {
            if rest.len() > fim && rest.ends_with('#') {
                let g1 = &rest[..rest.len() - 1];
                p.ents.insert(0, format!("*{}", g1));
                p.header = PRE.to_string();
            }
        }
    }
    Ok(p)
}

/// `(\*-?\d+)+` por inteiro.
fn bloco_nums(p: &str) -> bool {
    let b = p.as_bytes();
    let mut i = 0;
    let mut grupos = 0;
    while i < b.len() {
        if b[i] != b'*' {
            return false;
        }
        i += 1;
        if i < b.len() && b[i] == b'-' {
            i += 1;
        }
        let (a, j) = digitos(b, i);
        if j == a {
            return false;
        }
        i = j;
        grupos += 1;
    }
    grupos > 0
}

/// `parse_ent`: `*seq*id#labels...#*nums` -> [`Entidade`]; `None` se nao casa `\*(\d+)\*(-?\d+)#`.
pub fn parse_ent(e: &str) -> Option<Entidade> {
    let b = e.as_bytes();
    if b.first() != Some(&b'*') {
        return None;
    }
    let (a, j) = digitos(b, 1);
    if j == a || j >= b.len() || b[j] != b'*' {
        return None;
    }
    let seq = &e[a..j];
    let mut k = j + 1;
    let ini_id = k;
    if k < b.len() && b[k] == b'-' {
        k += 1;
    }
    let (a2, j2) = digitos(b, k);
    if j2 == a2 || j2 >= b.len() || b[j2] != b'#' {
        return None;
    }
    let id = &e[ini_id..j2];
    let tail = &e[j2 + 1..];
    let parts: Vec<&str> = tail.split('#').collect();
    for (i, p) in parts.iter().enumerate() {
        if p.starts_with('*') && bloco_nums(p) {
            return Some(Entidade {
                seq: seq.to_string(),
                id: id.to_string(),
                labels: parts[..i].iter().map(|s| s.to_string()).collect(),
                nums: p[1..].split('*').map(|s| s.to_string()).collect(),
            });
        }
    }
    Some(Entidade {
        seq: seq.to_string(),
        id: id.to_string(),
        labels: parts.iter().map(|s| s.to_string()).collect(),
        nums: vec![],
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    const MINI: &str = "CADe_SIMU*0*3004#-X#########*0*0*0*0*0*0*0*0*93*45*0*0*-9*-12*3*18*0*7*0*1*0*0*0#*1*4000##########*0*0*0*0*0*0*0*0*93*45*423*45*0*0*0*0*0*0*0*0*0*1*0#$$$*0*1&&&";

    #[test]
    fn split_all_traz_entidade_zero() {
        let p = split_all(MINI).unwrap();
        assert_eq!(p.header, "CADe_SIMU*");
        assert_eq!(p.ents.len(), 2);
        assert!(p.footer.starts_with("$$$"));
        let e0 = parse_ent(&p.ents[0]).unwrap();
        assert_eq!((e0.seq.as_str(), e0.id.as_str()), ("0", "3004"));
        assert_eq!(e0.labels[0], "-X");
        assert_eq!(e0.nums.len(), 23);
        assert_eq!(e0.nums[8], "93");
        let e1 = parse_ent(&p.ents[1]).unwrap();
        assert_eq!(e1.id, "4000");
        assert_eq!(e1.nums[10], "423");
    }

    #[test]
    fn split_entities_nao_inclui_a_zero() {
        let p = split_entities(MINI).unwrap();
        assert_eq!(p.ents.len(), 1);
        assert!(p.header.starts_with("CADe_SIMU*0*3004#"));
    }

    #[test]
    fn parse_ent_rejeita_lixo() {
        assert!(parse_ent("lixo").is_none());
        assert!(parse_ent("*1*x#").is_none());
    }

    #[test]
    fn bloco_nums_valida() {
        assert!(bloco_nums("*0*-12*3"));
        assert!(!bloco_nums("*0*a"));
        assert!(!bloco_nums(""));
    }

    #[test]
    fn desgruda_entidade_com_string_final() {
        // IP do 10206 cola a proxima entidade sem `#` (tools/dissect.py `_desgruda`)
        let d = "CADe_SIMU*0*3004#-X#*0*0*0*0*93*45#*49*10206#-CLP#*0*0*0*0*196*45*0*0*0#192.128.0.1*50*4000##*0*0*0*0*196*18*196*45*0#$$$*0*1&&&";
        let p = split_entities(d).unwrap();
        assert_eq!(p.ents.len(), 2, "{:?}", p.ents);
        let cpu = parse_ent(&p.ents[0]).unwrap();
        assert_eq!(cpu.id, "10206");
        let fio = parse_ent(&p.ents[1]).unwrap();
        assert_eq!((fio.seq.as_str(), fio.id.as_str()), ("50", "4000"));
        assert_eq!(fio.nums[4], "196");
    }

    #[test]
    fn desgruda_nao_quebra_entidade_normal() {
        // bloco de nums no fim, sem string colada: nada para separar
        let p = split_entities(MINI).unwrap();
        assert_eq!(p.ents.len(), 1);
        let q = split_all(MINI).unwrap();
        assert_eq!(q.ents.len(), 2);
    }
}
