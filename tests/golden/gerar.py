#!/usr/bin/env python3
"""Gera os GOLDENS de paridade Rust x Python (o Python e o ORACULO).

Para cada caso grava em tests/golden/:
  <nome>.layout.json   entrada (copia dos exemplos de tools/examples ou caso extra)
  <nome>.spec.json     spec "baixa" intermediaria (layout.compilar + titulo), json.dumps(indent=1)
  <nome>.cad           .cad do cad_build (byte a byte)
  <nome>.erro.txt      (so casos de erro) mensagem do ValueError de layout.compilar
Casos de spec baixa (<nome>.baixa.json) geram so o .cad.

Uso: python3 tests/golden/gerar.py      (rode so quando o ORACULO Python mudar de proposito)
O teste Rust (tests/paridade) compara o binario `cade` com estes arquivos.
"""
import copy
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import build_spec  # noqa: E402
import cade_mcp  # noqa: E402

TRILHOS = {"L1": 14, "L2": 20, "L3": 26, "N": 282, "x0": 25, "x1": 395, "PE": 291}
FONTE = {"id": "X1", "classe": "3007", "rotulo": "-X",
         "pinos": {"L1": "L1", "L2": "L2", "L3": "L3", "N": "N", "PE": "PE"}}


def mono(rungs, trilhos=None):
    return {"titulo": "T", "trilhos": trilhos or {"L1": 14, "N": 100, "x0": 25, "x1": 395},
            "fontes": [{"id": "X1", "classe": "3003", "pinos": {"L": "L1", "N": "N"}}],
            "comando": [{"id": "c1", "de": "L1", "para": "N", "rungs": rungs}]}


def rung(i):
    return {"serie": [[f"S{i}", "8001", f"-S{i}"],
                      {"paralelo": [[f"B{i}", "8000", f"-B{i}"], [f"s{i}", "7000", f"-K{i}"]]},
                      {"paralelo": [[f"K{i}", "9000", f"-K{i}"], [f"H{i}", "9008", f"-H{i}"]]}]}


def ramos8():
    return [{"via": [f"B{i}", "8000", f"-S{i}"], "selo": [f"s{i}", "7000", f"-K{i}"],
             "carga": [f"K{i}", "9000", f"-K{i}"], "indica": [f"H{i}", "9008", f"-H{i}"]} for i in range(8)]


def legado8():
    return {"titulo": "x", "trilhos": TRILHOS, "fontes": [FONTE],
            "comando": [{"id": "m1", "de": "L1", "para": "N",
                         "serie": [["RT1", "8017", "-RT1"], ["S0", "8001", "-S0"]], "ramos": ramos8()}]}


# casos extras (stress do motor): {nome: layout puro}
EXTRAS = {
    "x_faixas_9_degraus": mono([rung(i) for i in range(9)]),
    "x_serpentina_30": mono([{"serie": [[f"E{i}", "7000", f"-K{i}"] for i in range(30)]
                              + [{"paralelo": [["K", "9000", "-K"], ["H", "9008", "-H"]]}]}]),
    "x_legado_vira_rede": legado8(),
    "x_uma_lampada": mono([{"serie": [["S0", "8000", "-S0"], ["H1", "9008", "-H1"]]}]),
    "x_paralelo_aninhado": mono([{"serie": [
        {"paralelo": [{"serie": [["A", "8000", "-A"], {"paralelo": [["B", "8001", "-B"], ["C", "8001", "-C"]]}]},
                      ["D", "7000", "-D"], ["E", "7001", "-E"]]},
        {"paralelo": [["K", "9000", "-K"], ["H", "9008", "-H"]]}]}]),
}

# casos de ERRO: o texto do ValueError de layout.compilar e o golden
ERROS = {
    "e_nao_cabe_40_degraus": mono([rung(i) for i in range(40)]),
    "e_classe_3_terminais": mono([{"serie": [["Q", "2001", "-KM"], ["K", "9000", "-K"]]}]),
    "e_id_duplicado": mono([{"serie": [["K", "9000", "-K"], ["K", "9000", "-K"]]}]),
    "e_paralelo_vazio": mono([{"paralelo": []}]),
    "e_duas_chaves": mono([{"serie": [["K", "9000", "-K"]], "paralelo": []}]),
    "e_trilho_inexistente": None,
    "e_trilhos_comando_sem_fonte": None,
    "e_paralelo_largo_demais": mono([{"serie": [{"paralelo": [[f"B{i}", "8000", f"-B{i}"] for i in range(60)]},
                                                ["K", "9000", "-K"]]}]),
}
_s = mono([rung(0)])
_s["comando"][0]["para"] = "X"
ERROS["e_trilho_inexistente"] = _s
_s = mono([rung(0)])
_s["trilhos_comando"] = {"nomes": ["C1", "C2"]}
ERROS["e_trilhos_comando_sem_fonte"] = _s

# specs BAIXAS (cad_build direto): exercitam o roteador sem o motor de layout
BAIXAS = {
    "b_roteador_sem_trilho": {
        "titulo": "ROTEADOR",
        "simbolos": [
            {"classe": "8000", "x": 40, "y": 40, "rotulo": "-S1", "id": "S1"},
            {"classe": "9000", "x": 40, "y": 100, "rotulo": "-KM1", "id": "KM1"},
            {"classe": "9008", "x": 90, "y": 40, "rotulo": "-H1", "id": "H1"},
            {"classe": "8001", "x": 140, "y": 90, "rotulo": "-S0", "id": "S0"},
            {"classe": "7000", "x": 140, "y": 20, "rotulo": "-KM1", "id": "K1"},
        ],
        "conexoes": [
            {"de": ["S1", "B"], "para": ["KM1", "A"]},
            {"de": ["S1", "A"], "para": ["H1", "A"]},
            {"de": ["H1", "B"], "para": ["S0", "A"]},
            {"de": ["KM1", "B"], "para": ["S0", "B"]},
            {"de": ["K1", "B"], "para": ["KM1", "A"]},
        ],
    },
    "b_trilhos_via_fios": {
        "titulo": "TRILHOS",
        "rails": [{"nome": "L1", "y": 14, "x0": 25, "x1": 200}, {"nome": "N", "y": 200, "x0": 25, "x1": 200}],
        "simbolos": [
            {"classe": "8000", "x": 40, "y": 40, "rotulo": "-S1", "id": "S1"},
            {"classe": "9000", "x": 40, "y": 110, "rotulo": "-KM1", "id": "KM1"},
            {"classe": "9008", "x": 100, "y": 110, "rotulo": "-H1", "id": "H1"},
        ],
        "conexoes": [
            {"de": ["L1", "rail"], "para": ["S1", "A"]},
            {"de": ["S1", "B"], "para": ["KM1", "A"]},
            {"de": ["KM1", "B"], "para": ["N", "rail"]},
            {"de": ["H1", "A"], "para": ["L1", "rail"], "via": 130},
            {"de": ["N", "rail"], "para": ["H1", "B"]},
        ],
        "fios": [{"x1": 300, "y1": 20, "x2": 300, "y2": 80}],
    },
    "b_motor_e_contator": {
        "titulo": "MOTOR",
        "rails": [{"nome": "L1", "y": 14, "x0": 25, "x1": 120}, {"nome": "L2", "y": 20, "x0": 25, "x1": 120},
                  {"nome": "L3", "y": 26, "x0": 25, "x1": 120}, {"nome": "PE", "y": 250, "x0": 25, "x1": 120}],
        "simbolos": [
            {"classe": "2001", "x": 40, "y": 50, "rotulo": "-KM1", "id": "KM1"},
            {"classe": "1000", "x": 40, "y": 150, "rotulo": "-M1", "id": "M1"},
        ],
        "conexoes": [
            {"de": ["L1", "rail"], "para": ["KM1", "1"]},
            {"de": ["L2", "rail"], "para": ["KM1", "3"]},
            {"de": ["L3", "rail"], "para": ["KM1", "5"]},
            {"de": ["KM1", "2"], "para": ["M1", "U1"]},
            {"de": ["KM1", "4"], "para": ["M1", "V1"]},
            {"de": ["KM1", "6"], "para": ["M1", "W1"]},
            {"de": ["M1", "PE"], "para": ["PE", "rail"]},
        ],
    },
}


def baixa_para_cad(low, out):
    res = cade_mcp.cad_build(titulo=low.get("titulo", "NOVO"), simbolos_json=json.dumps(low["simbolos"]),
                             conexoes_json=json.dumps(low.get("conexoes", [])),
                             fios_json=json.dumps(low.get("fios", [])),
                             rails_json=json.dumps(low.get("rails", [])), out_path=str(out))
    assert "ERRO" not in res, res
    return res


def grava_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    for f in OUT.iterdir():
        if f.is_file() and f.name != "gerar.py":
            f.unlink()
    casos = []
    for f in sorted((ROOT / "tools" / "examples").glob("*.layout.json")):
        nome = f.name[:-len(".layout.json")]
        shutil.copyfile(f, OUT / f.name)
        casos.append((nome, json.loads(f.read_text(encoding="utf-8"))))
    for nome, lay in EXTRAS.items():
        grava_json(OUT / f"{nome}.layout.json", lay)
        casos.append((nome, lay))
    for nome, spec in casos:
        low, _testes, _lay = build_spec.normalizar(spec)
        (OUT / f"{nome}.spec.json").write_text(json.dumps(low, indent=1, ensure_ascii=False), encoding="utf-8")
        baixa_para_cad(low, OUT / f"{nome}.cad")
        print("OK", nome, len(low["simbolos"]), "simbolos")
    for nome, lay in ERROS.items():
        grava_json(OUT / f"{nome}.layout.json", lay)
        try:
            build_spec.normalizar(copy.deepcopy(lay))
        except ValueError as e:
            (OUT / f"{nome}.erro.txt").write_text(str(e), encoding="utf-8")
            print("ERRO esperado", nome, "->", str(e)[:70])
        else:
            raise SystemExit(f"{nome}: deveria falhar")
    for nome, low in BAIXAS.items():
        grava_json(OUT / f"{nome}.baixa.json", low)
        baixa_para_cad(low, OUT / f"{nome}.cad")
        print("OK baixa", nome)


if __name__ == "__main__":
    main()
