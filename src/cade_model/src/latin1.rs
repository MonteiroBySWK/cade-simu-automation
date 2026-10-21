//! latin1 <-> `String` (1 byte = 1 `char`), como `bytes.decode("latin1")` / `str.encode("latin1")`.

/// `bytes.decode("latin1")`.
pub fn decodificar(bytes: &[u8]) -> String {
    bytes.iter().map(|&b| b as char).collect()
}

/// `str.encode("latin1")`: erro se algum `char` > U+00FF (o Python levanta `UnicodeEncodeError`).
pub fn codificar(s: &str) -> Result<Vec<u8>, String> {
    s.chars()
        .enumerate()
        .map(|(i, c)| {
            u8::try_from(c as u32).map_err(|_| {
                format!(
                    "'latin-1' codec can't encode character '\\u{:04x}' in position {}: ordinal not in range(256)",
                    c as u32, i
                )
            })
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ida_e_volta() {
        let raw: Vec<u8> = (0..=255).collect();
        assert_eq!(codificar(&decodificar(&raw)).unwrap(), raw);
    }

    #[test]
    fn rejeita_fora_de_latin1() {
        assert!(codificar("a\u{20ac}").is_err());
    }
}
