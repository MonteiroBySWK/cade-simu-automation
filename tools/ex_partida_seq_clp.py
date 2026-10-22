#!/usr/bin/env python3
"""Exercicio: partida sequencial de 3 motores trifasicos com CLP (ladder do proprio CADe_SIMU).

S1 liga: M3 parte na hora, M2 apos 2 s, M1 apos mais 2 s. S0 desliga os tres; o termico de
qualquer motor tambem derruba os tres.

Uso: tools/.venv-mcp/bin/python tools/ex_partida_seq_clp.py out/partida_seq_clp.cad
Precisa de CADE_ACERVO (biblioteca de simbolos; ver README).

Ladder (enderecos casam por rotulo, como bobina<->contato):
  R1  I0.1 I0.3 I0.4 I0.5 (I0.2 || B3:1) -> B3:1        selo geral
  R2  B3:1 -> Q0.3 (CM3)  e  T1(2 s) -> T4:0
  R3  T4:0 Q0.3 -> Q0.2 (CM2)  e  T2(2 s) -> T4:1
  R4  T4:1 Q0.2 -> Q0.1 (CM1)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cade_mcp  # noqa: E402

TEMPO = "20"   # unidade '3' = x0,1 s no dialogo do temporizador -> 2,0 s (no Wine roda ~1,5x mais lento)

S, W = [], []   # simbolos, fios


def sym(classe, x, y, rotulo=None, id=None, rotulos=None):
    d = {"classe": classe, "x": x, "y": y}
    if rotulo is not None:
        d["rotulo"] = rotulo
    if id:
        d["id"] = id
    if rotulos:
        d["rotulos"] = rotulos
    S.append(d)


def poly(*pts):
    """Fio por vertices; extremos exatos (so une fio com fio por extremo)."""
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        if (x1, y1) != (x2, y2):
            W.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2})


# ---- bloco do CLP (geometria do exemplo "Acionamento intercalado CLP") -------------------
sym("3011", 36, 60, "-X")
sym("10206", 36, 87, "-CLP")
for x in (36, 42, 48):                       # L, N, PE da fonte direto no CLP
    poly((x, 60), (x, 87))
ENT = [("I0.1", "8001", "-S0", 72), ("I0.2", "8000", "-S1", 90), ("I0.3", "8017", "-RT1", 108),
       ("I0.4", "8017", "-RT2", 126), ("I0.5", "8017", "-RT3", 144)]
poly((54, 87), (54, 60), *[(e[3], 60) for e in ENT])     # saida de comum do CLP -> barra das entradas
for end, cls, rot, x in ENT:
    sym("10204", x, 87, end)
    sym(cls, x, 66, rot)
    poly((x, 60), (x, 66))
    poly((x, 78), (x, 87))
SAI = [("Q0.1", "-CM1", 42), ("Q0.2", "-CM2", 66), ("Q0.3", "-CM3", 90)]
for end, km, x in SAI:
    sym("10205", x, 111, end)
    sym("9000", x, 144, km)
    poly((x, 135), (x, 144))
    poly((x, 156), (x, 162))
poly((60, 87), (60, 81), (24, 81), (24, 162), (42, 162), (66, 162), (90, 162))   # comum das bobinas


# ---- ladder -------------------------------------------------------------------------------
def tempo(id_, x, y):
    sym("10066", x, y, id_, rotulos=[None, None, None, None, "3", TEMPO])


# trilho A (R1, R2)
sym("3008", 30, 177, "24V")
poly((30, 177), (30, 189), (30, 228))
# R1: I0.1 I0.3 I0.4 I0.5 (I0.2 || B3:1) -> B3:1
xs = [(39, "I0.1"), (60, "I0.3"), (81, "I0.4"), (102, "I0.5")]
prev = (30, 189)
for x, end in xs:
    sym("10050", x, 189, end)
    poly(prev, (x, 189))
    prev = (x + 12, 189)
poly(prev, (117, 189), (123, 189))
sym("10050", 123, 189, "I0.2")
sym("10050", 123, 207, "B3:1")
poly((117, 189), (117, 207), (123, 207))
poly((135, 189), (144, 189), (156, 189))
poly((135, 207), (144, 207), (144, 189))
sym("10060", 156, 189, "B3:1")
# R2: B3:1 -> Q0.3 e T1 -> T4:0
sym("10050", 39, 228, "B3:1")
poly((30, 228), (39, 228))
poly((51, 228), (60, 228), (66, 228))
sym("10060", 66, 228, "Q0.3")
poly((60, 228), (60, 240), (66, 240))
tempo("T1", 66, 240)
poly((81, 246), (87, 246))
sym("10060", 87, 246, "T4:0")

# trilho B (R3, R4)
sym("3008", 252, 177, "24V")
poly((252, 177), (252, 189), (252, 240))
# R3: T4:0 Q0.3 -> Q0.2 e T2 -> T4:1   (M2 so parte com M3 ligado)
sym("10050", 261, 189, "T4:0")
sym("10050", 279, 189, "Q0.3")
poly((252, 189), (261, 189))
poly((273, 189), (279, 189))
poly((291, 189), (300, 189), (306, 189))
sym("10060", 306, 189, "Q0.2")
poly((300, 189), (300, 201), (306, 201))
tempo("T2", 306, 201)
poly((321, 207), (327, 207))
sym("10060", 327, 207, "T4:1")
# R4: T4:1 Q0.2 -> Q0.1   (M1 so parte com M2 ligado)
sym("10050", 261, 240, "T4:1")
sym("10050", 279, 240, "Q0.2")
poly((252, 240), (261, 240))
poly((273, 240), (279, 240))
poly((291, 240), (306, 240))
sym("10060", 306, 240, "Q0.1")

# ---- potencia: termico + contator + motor por coluna, direto nos trilhos --------------------
RAILS = [{"nome": "L1", "y": 14, "x0": 246, "x1": 432}, {"nome": "L2", "y": 20, "x0": 246, "x1": 432},
         {"nome": "L3", "y": 26, "x0": 246, "x1": 432}, {"nome": "PE", "y": 150, "x0": 246, "x1": 432}]
sym("3005", 252, 40, "-X", id="X1")
CON = [{"de": ["X1", f], "para": [f, "rail"]} for f in ("L1", "L2", "L3", "PE")]
for n, x in ((1, 300), (2, 348), (3, 396)):
    f, k, m = f"F{n}", f"K{n}", f"M{n}"
    sym("6007", x, 40, f"-RT{n}", id=f)
    sym("2001", x, 75, f"-CM{n}", id=k)
    sym("1000", x, 110, f"-M{n}", id=m)
    for fase, a, b in (("L1", "1", "2"), ("L2", "3", "4"), ("L3", "5", "6")):
        CON.append({"de": [fase, "rail"], "para": [f, a]})
        CON.append({"de": [f, b], "para": [k, a]})
        CON.append({"de": [k, b], "para": [m, {"1": "U1", "3": "V1", "5": "W1"}[a]]})
    CON.append({"de": [m, "PE"], "para": ["PE", "rail"]})


TXT = [{"texto": "Aluno: Sérgio Murilo de Andrade Castelhano Filho", "x": 30, "y": 268, "altura": 8}]


def juncoes():
    """Pontinho 4001 onde 3+ extremos de fio/pino se encontram (so cosmetico, mas o app o usa em T)."""
    cont = {}
    for w in W:
        for p in ((w["x1"], w["y1"]), (w["x2"], w["y2"])):
            cont[p] = cont.get(p, 0) + 1
    return [{"x1": x, "y1": y, "x2": x, "y2": y, "classe": "4001"} for (x, y), c in cont.items() if c >= 3]


def main(out):
    W.extend(juncoes())
    msg = cade_mcp.cad_build("PARTIDA SEQUENCIAL 3 MOTORES - CLP", json.dumps(S), json.dumps(W), out,
                             auto_net=True, conexoes_json=json.dumps(CON), rails_json=json.dumps(RAILS), textos_json=json.dumps(TXT))
    print(msg)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out/partida_seq_clp.cad")
