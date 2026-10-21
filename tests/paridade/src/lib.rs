//! Crate-suporte dos testes de paridade (ver `tests/paridade.rs` e `docs/rust-port.md`).
//!
//! Os goldens ficam em `tests/golden/` e sao gerados pelo ORACULO Python (`tests/golden/gerar.py`).

use std::path::PathBuf;

/// Diretorio `tests/golden` do workspace.
pub fn golden_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("golden")
}

/// Raiz do repositorio.
pub fn raiz() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..")
}

/// Descreve a primeira diferenca entre dois blobs (para mensagens de falha legiveis).
pub fn primeira_diferenca(a: &[u8], b: &[u8]) -> String {
    let n = a.len().min(b.len());
    let pos = (0..n).find(|&i| a[i] != b[i]).unwrap_or(n);
    let ctx = |x: &[u8]| String::from_utf8_lossy(&x[pos.saturating_sub(40)..(pos + 40).min(x.len())]).into_owned();
    format!(
        "diferem no byte {} (rust {}b, python {}b)\n  rust  : ...{}...\n  python: ...{}...",
        pos,
        a.len(),
        b.len(),
        ctx(a),
        ctx(b)
    )
}
