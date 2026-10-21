//! Formatacao no estilo Python (`repr`, `int()`), para manter mensagens de erro identicas ao oraculo.

use serde_json::Value;

/// `repr(str)` do Python.
pub fn repr_str(s: &str) -> String {
    let aspas = if s.contains('\'') && !s.contains('"') { '"' } else { '\'' };
    let mut o = String::new();
    o.push(aspas);
    for c in s.chars() {
        match c {
            '\\' => o.push_str("\\\\"),
            '\n' => o.push_str("\\n"),
            '\r' => o.push_str("\\r"),
            '\t' => o.push_str("\\t"),
            c if c == aspas => {
                o.push('\\');
                o.push(c);
            }
            c if (c as u32) < 0x20 || c as u32 == 0x7f => o.push_str(&format!("\\x{:02x}", c as u32)),
            c => o.push(c),
        }
    }
    o.push(aspas);
    o
}

/// `repr()` de um valor JSON como o Python imprimiria o objeto carregado por `json.loads`.
pub fn repr(v: &Value) -> String {
    match v {
        Value::Null => "None".into(),
        Value::Bool(true) => "True".into(),
        Value::Bool(false) => "False".into(),
        Value::Number(n) => {
            if let Some(f) = n.as_f64().filter(|_| n.is_f64()) {
                if f.fract() == 0.0 && f.abs() < 1e16 {
                    format!("{:.1}", f)
                } else {
                    format!("{}", f)
                }
            } else {
                n.to_string()
            }
        }
        Value::String(s) => repr_str(s),
        Value::Array(a) => format!("[{}]", a.iter().map(repr).collect::<Vec<_>>().join(", ")),
        Value::Object(m) => format!(
            "{{{}}}",
            m.iter().map(|(k, v)| format!("{}: {}", repr_str(k), repr(v))).collect::<Vec<_>>().join(", ")
        ),
    }
}

/// `repr(list[str])`.
pub fn repr_lista<S: AsRef<str>>(v: &[S]) -> String {
    format!("[{}]", v.iter().map(|s| repr_str(s.as_ref())).collect::<Vec<_>>().join(", "))
}

/// Truthiness do Python para valores JSON.
pub fn verdadeiro(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().map(|f| f != 0.0).unwrap_or(true),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
    }
}

/// `str(valor)` para escalares (usado em chaves como `str(s.get("id") ...)`).
pub fn str_de(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        other => repr(other),
    }
}

/// `int(valor)` do Python para JSON: inteiro, float (trunca), bool ou string numerica.
pub fn int(v: &Value) -> Result<i64, String> {
    match v {
        Value::Number(n) => n
            .as_i64()
            .or_else(|| n.as_f64().map(|f| f.trunc() as i64))
            .ok_or_else(|| format!("int() invalido: {}", n)),
        Value::Bool(b) => Ok(*b as i64),
        Value::String(s) => s
            .trim()
            .parse::<i64>()
            .map_err(|_| format!("invalid literal for int() with base 10: {}", repr_str(s))),
        other => Err(format!("int() argument must be a string or a number, not '{}'", tipo(other))),
    }
}

/// Nome do tipo Python de um valor JSON.
pub fn tipo(v: &Value) -> &'static str {
    match v {
        Value::Null => "NoneType",
        Value::Bool(_) => "bool",
        Value::Number(n) => {
            if n.is_f64() {
                "float"
            } else {
                "int"
            }
        }
        Value::String(_) => "str",
        Value::Array(_) => "list",
        Value::Object(_) => "dict",
    }
}

/// Divisao inteira com piso (`//` do Python).
pub fn fdiv(a: i64, b: i64) -> i64 {
    a.div_euclid(b) - if b < 0 && a.rem_euclid(b) != 0 { 1 } else { 0 }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn repr_como_python() {
        assert_eq!(repr(&json!({"serie": [["K", "9000"]], "paralelo": []})), "{'serie': [['K', '9000']], 'paralelo': []}");
        assert_eq!(repr_str("it's"), "\"it's\"");
        assert_eq!(repr(&json!(null)), "None");
    }

    #[test]
    fn divisao_com_piso() {
        assert_eq!(fdiv(7, 2), 3);
        assert_eq!(fdiv(-7, 2), -4);
        assert_eq!(fdiv(-6, 2), -3);
        assert_eq!(fdiv(7, -2), -4);
    }
}
