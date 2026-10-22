#!/usr/bin/env python3
"""Goldens do `cade_check` (gate estatico): o Python e o ORACULO.

Para cada caso grava, em tests/golden/check/, `<nome>.design.json` (layout -> build_spec.construir) ou
`<nome>.gate.json` (.cad existente -> build_spec.gate) com a parte ESTATICA do gate:
  entrada, tipo, titulo, n_simbolos, build{ok,mensagem}, geo{curtos,soltos,curtos_msg,soltos_msg},
  fios{ok,n,atravessam}, avisos, erros (sem os de teste), estatico_ok
A parte funcional (cad_test / conferir_chaves_de_teste) e neutralizada de proposito: o simulador Rust
(`cade_sim`) e outra fase; aqui so comparamos o que nao depende dele. Caminhos de saida viram `{OUT}`/`{PATH}`.

Fixtures defeituosas (geradas aqui, com o Python): 3004 por fase + PE no neutro, pino solto, termico com
rotulo diferente do contato, fio atravessando simbolo.

Uso: python3 tests/golden/check/gerar.py   (exige `cargo build`: o Python chama target/debug/cade)
"""
import copy
import json
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
GOLDEN = AQUI.parent
ROOT = GOLDEN.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import build_spec  # noqa: E402
import cade_mcp  # noqa: E402

# neutraliza a parte funcional (depende do simulador, que o cade_check nao tem)
cade_mcp.cad_test = lambda path, casos="[]": "SEM_TESTES"
build_spec.conferir_chaves_de_teste = lambda path, testes: []

PREFIXOS_TESTE = ("teste ", "sem testes", "testes:")


def rel(p):
    return str(Path(p).resolve().relative_to(ROOT))


def estatico(r, entrada, tipo, troca):
    """Recorta a parte estatica de `r` (dict de construir/gate) no formato do golden."""
    def sub(s):
        for a, b in troca:
            s = s.replace(a, b)
        return s
    geo = r["geo"]
    out = {
        "entrada": entrada, "tipo": tipo,
        "titulo": r.get("titulo"), "n_simbolos": r.get("n_simbolos"),
        "build": {"ok": r["build"]["ok"], "mensagem": sub(r["build"]["mensagem"])},
        "geo": {k: geo.get(k, []) for k in ("curtos", "soltos", "curtos_msg", "soltos_msg")},
        "fios": r["fios"],
        "avisos": [sub(a) for a in r["avisos"]],
        "erros": [sub(e) for e in r["erros"] if not e.startswith(PREFIXOS_TESTE)],
    }
    out["estatico_ok"] = bool(out["build"]["ok"] and not out["geo"]["curtos"] and not out["geo"]["soltos"])
    return out


def caso_design(spec, entrada, tmp):
    out = tmp / "saida.cad"
    r = build_spec.construir(copy.deepcopy(spec), str(out))
    return estatico(r, entrada, "design", [(str(out), "{OUT}")])


def caso_gate(path, entrada):
    code, saida = cade_mcp._run("validate", str(path))
    r = {"testes": {}, "geo": {}, "fios": {}, "avisos": [], "erros": [], "_teste_raw": "",
         "build": {"ok": code == 0, "mensagem": saida}}
    if code != 0:
        r["erros"].append(f"arquivo invalido: {saida}")
        r["geo"], r["fios"] = {}, {"ok": None, "n": 0, "atravessam": []}
    else:
        build_spec.gate(str(path), [], r)
    return estatico(r, entrada, "gate", [(str(path), "{PATH}")])


def grava(nome, sufixo, obj):
    (AQUI / f"{nome}.{sufixo}.json").write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def le(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- fixtures defeituosas
def fixtures():
    base = le(ROOT / "tools" / "examples" / "partida_direta.layout.json")
    out = {}

    # 1) legado: uma 3004 por fase e PE do motor no neutro (curto N x PE + fases soltas)
    d = copy.deepcopy(base)
    l = d["layout"] if "layout" in d else d
    l["fontes"] = [{"classe": "3004", "id": "X1", "rotulo": "-X", "fases": ["L1", "L2", "L3"], "neutro": "N"}]
    l["trilhos"].pop("PE", None)
    for g in l["potencia"]:
        g.pop("pe", None)
    out["defeito_3004x3_pe_no_n"] = ("layout", d)

    # 1b) curto de fase (pinos da 3007: PE e L2 ligados aos trilhos errados)
    d = copy.deepcopy(base)
    l = d["layout"] if "layout" in d else d
    l["fontes"][0]["pinos"] = {"L1": "L1", "L2": "L1", "L3": "L3", "N": "N", "PE": "N"}
    out["defeito_curto_pe_n_e_fases"] = ("layout", d)

    # 2) termico 6007 com rotulo diferente do contato 8017 (-RT1): no app o termico nunca dispara
    d = copy.deepcopy(base)
    l = d["layout"] if "layout" in d else d
    for g in l["potencia"]:
        for c in g["colunas"]:
            if isinstance(c, list) and c[1] == "6007":
                c[2] = "-RTX"
    out["defeito_termico_rotulo"] = ("layout", d)

    # 3) pino solto: H1 sem ligacao no pino B
    out["defeito_pino_solto"] = ("baixa", {
        "titulo": "SOLTO",
        "simbolos": [{"classe": "8000", "x": 40, "y": 40, "rotulo": "-S1", "id": "S1"},
                     {"classe": "9000", "x": 40, "y": 100, "rotulo": "-KM1", "id": "KM1"},
                     {"classe": "9008", "x": 90, "y": 40, "rotulo": "-H1", "id": "H1"}],
        "conexoes": [{"de": ["S1", "B"], "para": ["KM1", "A"]}, {"de": ["S1", "A"], "para": ["H1", "A"]}]})

    # 4) fio manual atravessando o corpo de um simbolo
    out["defeito_fio_atravessa"] = ("baixa", {
        "titulo": "ATRAVESSA",
        "simbolos": [{"classe": "8000", "x": 40, "y": 40, "rotulo": "-S1", "id": "S1"},
                     {"classe": "9000", "x": 40, "y": 100, "rotulo": "-KM1", "id": "KM1"}],
        "conexoes": [{"de": ["S1", "B"], "para": ["KM1", "A"]}],
        "fios": [{"x1": 20, "y1": 110, "x2": 120, "y2": 110}]})
    return out


def main():
    for f in AQUI.iterdir():
        if f.is_file() and f.name != "gerar.py":
            f.unlink()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # 1) design: todos os layouts do golden (validos e de erro)
        for f in sorted(GOLDEN.glob("*.layout.json")):
            nome = f.name[:-len(".layout.json")]
            grava(nome, "design", caso_design(le(f), rel(f), tmp))
            print("design", nome)
        # 2) fixtures: grava entrada + .cad e os dois tipos de caso
        for nome, (tipo, spec) in fixtures().items():
            if tipo == "layout":
                (AQUI / f"{nome}.layout.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False) + "\n",
                                                          encoding="utf-8")
                grava(nome, "design", caso_design(spec, rel(AQUI / f"{nome}.layout.json"), tmp))
                low, _t, _l = build_spec.normalizar(spec)
            else:
                (AQUI / f"{nome}.baixa.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False) + "\n",
                                                         encoding="utf-8")
                low = spec
            res = cade_mcp.cad_build(titulo=low.get("titulo", "NOVO"), simbolos_json=json.dumps(low["simbolos"]),
                                     conexoes_json=json.dumps(low.get("conexoes", [])),
                                     fios_json=json.dumps(low.get("fios", [])),
                                     rails_json=json.dumps(low.get("rails", [])), out_path=str(AQUI / f"{nome}.cad"))
            assert "ERRO" not in res, (nome, res)
            print("fixture", nome)
        # 3) gate de .cad: goldens do build, corpus e fixtures
        cads = sorted(GOLDEN.glob("*.cad")) + sorted((ROOT / "corpus").glob("*.cad")) + sorted(AQUI.glob("*.cad"))
        for c in cads:
            grava(c.stem, "gate", caso_gate(c, rel(c)))
            print("gate", c.stem)


if __name__ == "__main__":
    main()
