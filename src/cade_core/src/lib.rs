//! cade_core v0.1 — parser/serializer round-trip byte-fiel para `.cad`.
//!
//! Estratégia Fase 2: tokenização preservadora sobre bytes (latin1).
//! O `.cad` é texto ISO-8859 sem newlines; `*` separa campos.
//! `parse` valida header e fatia em tokens `*`; `emit` rejunta com `*`,
//! garantindo round-trip byte-idêntico. `$$$`/`&&&` ficam dentro dos
//! tokens — nunca normalizados.

/// Documento `.cad` em forma tokenizada (bytes brutos, latin1).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CadFile {
    /// Tokens obtidos por split em `*` (byte 0x2A). Rejuntar com `*` = original.
    pub tokens: Vec<Vec<u8>>,
    /// Modo (`CADe_SIMU*<modo>*...`), ex: 0.
    pub modo: Vec<u8>,
    /// Versão + resto do segundo campo (ex: `3005#220V#########`).
    pub versao_campo: Vec<u8>,
}

/// Erro de parse/validação (String simples em v0.1).
pub type CadResult<T> = Result<T, String>;

/// Faz parse de bytes `.cad` sem normalizar nada.
pub fn parse(data: &[u8]) -> CadResult<CadFile> {
    const MAGIC: &[u8] = b"CADe_SIMU*";
    if !data.starts_with(MAGIC) {
        return Err("header inválido: esperado `CADe_SIMU*`".to_string());
    }
    if !data.windows(3).any(|w| w == b"$$$") {
        return Err("seção `$$$` ausente (arquivo truncado?)".to_string());
    }
    let tokens: Vec<Vec<u8>> = data.split(|b| *b == b'*').map(|t| t.to_vec()).collect();
    if tokens.len() < 3 {
        return Err("poucos campos `*` no header".to_string());
    }
    // tokens[0] = "CADe_SIMU", tokens[1] = modo, tokens[2] = versao+cabecalho
    let modo = tokens[1].clone();
    let versao_campo = tokens[2].clone();
    Ok(CadFile {
        tokens,
        modo,
        versao_campo,
    })
}

/// Serializa de volta para bytes — rejunta tokens com `*`, byte-idêntico.
pub fn emit(doc: &CadFile) -> Vec<u8> {
    doc.tokens.join(&b'*')
}

/// Atalho: valida sem alocar estrutura além do necessário.
pub fn validate(data: &[u8]) -> CadResult<(String, String)> {
    let doc = parse(data)?;
    let modo = String::from_utf8_lossy(&doc.modo).into_owned();
    let versao = String::from_utf8_lossy(&doc.versao_campo)
        .split('#')
        .next()
        .unwrap_or("")
        .to_string();
    Ok((modo, versao))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    fn corpus_dir() -> PathBuf {
        let mut d = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        d.pop(); // src/cade_core -> src
        d.pop(); // src -> root
        d.push("corpus");
        d
    }

    #[test]
    fn roundtrip_corpus_byte_identico() {
        let dir = corpus_dir();
        let mut files = std::fs::read_dir(&dir)
            .expect("corpus/ ausente")
            .map(|e| e.unwrap().path())
            .filter(|p| p.extension().map(|e| e == "cad").unwrap_or(false))
            .collect::<Vec<_>>();
        assert!(!files.is_empty(), "nenhum .cad no corpus");
        files.sort();
        for f in files {
            let raw = std::fs::read(&f).unwrap();
            let doc = parse(&raw).unwrap_or_else(|e| panic!("{}: {}", f.display(), e));
            let out = emit(&doc);
            assert_eq!(raw, out, "round-trip divergiu em {}", f.display());
        }
    }

    #[test]
    fn rejeita_header_invalido() {
        assert!(parse(b"lixo").is_err());
    }

    #[test]
    fn rejeita_sem_dollar() {
        assert!(parse(b"CADe_SIMU*0*3000#X").is_err());
    }

    #[test]
    fn preserva_coordenadas_negativas() {
        let raw = b"CADe_SIMU*0*3000#-X#*0*-12*-9$$$";
        let doc = parse(raw).unwrap();
        assert_eq!(emit(&doc), raw);
    }
}
