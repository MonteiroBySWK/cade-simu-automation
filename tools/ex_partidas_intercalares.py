#!/usr/bin/env python3
"""Exercicio: partida intercalada de 2 motores com CLP (ladder), termicos, sinalizacao e intertravamento.

Recriado do zero a partir do enunciado (o Pratica5_Part_Intercalada.cad original nao estava disponivel).
Sequencia: LIGA (B1) -> M1; 5 s depois M2 tambem; mais 5 s e M1 desliga (fica so M2). DESLIGA (B0),
EMERGENCIA ou qualquer termico (RT1/RT2) derrubam os dois; religar exige novo LIGA.

Uso: tools/.venv-mcp/bin/python tools/ex_partidas_intercalares.py out/partidas_intercalares.cad
Precisa de CADE_ACERVO (biblioteca de simbolos; ver README).

I/O:  I0.1 B0 DESLIGA (NF)  I0.2 B1 LIGA (NA)  I0.3 EMERGENCIA (NF)  I0.4 RT1_OK  I0.5 RT2_OK (NF 95-96)
      Q0.1 C1  Q0.2 C2  Q0.3 marcha (memoria)  Q0.4 H1  Q0.5 H2;  H3/H4 direto no NA 97-98 de RT1/RT2.
Ladder (enderecos casam por rotulo, como bobina<->contato):
  R1  I0.1 I0.3 I0.4 I0.5 (I0.2 || Q0.3) -> Q0.3       marcha + PERMISSAO = RT1_OK E RT2_OK
  R2  Q0.3 -> T1(5 s) -> T4:0   e   Q0.3 /T4:1 -> Q0.1 (C1)
  R3  T4:0 -> T2(5 s) -> T4:1   e   T4:0 -> Q0.2 (C2)
  R4  Q0.1 -> Q0.4 (H1)      R5  Q0.2 -> Q0.5 (H2)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cade_mcp  # noqa: E402

TEMPO = "50"   # unidade '3' = x0,1 s no dialogo do temporizador -> 5,0 s (no Wine roda ~1,5x mais lento)

S, W, T = [], [], []   # simbolos, fios, textos


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


def txt(s, x, y, altura=3):
    T.append({"texto": s, "x": x, "y": y, "altura": altura})


def lamp(x, y, rotulo, cor):
    sym("9008", x, y, rotulo, rotulos=[None, None, None, None, cor])   # cor: 0 verde, 1 vermelho


VERDE, VERMELHO = "0", "1"

# ---- bloco do CLP (geometria do exemplo "Acionamento intercalado CLP") -------------------
txt('CIRCUITO DE COMANDO "CLP"', 30, 26, 4)
txt("PAINEL DE COMANDOS", 72, 40, 4)
sym("3011", 36, 60, "-X")
sym("10206", 36, 87, "-CLP")
for x in (36, 42, 48):                       # L, N, PE da fonte direto no CLP
    poly((x, 60), (x, 87))
ENT = [("I0.1", "8001", "B0", 72, "DESLIGA"), ("I0.2", "8000", "B1", 96, "LIGA"),
       ("I0.3", "8001", "EMERG", 120, "EMERGÊNCIA"),   # 8005 (cogumelo) nao abre o contato na simulacao do app
       ("I0.4", "8017", "RT1", 144, "RT1 95-96"), ("I0.5", "8017", "RT2", 168, "RT2 95-96")]
ALM = [("RT1", 198, "H3", "SOBRECARGA M1", 166), ("RT2", 216, "H4", "SOBRECARGA M2", 172)]
barra = [e[3] for e in ENT] + [a[1] for a in ALM]
poly((54, 87), (54, 60), *[(x, 60) for x in barra])     # saida de comum do CLP -> barra das entradas
for end, cls, rot, x, nome in ENT:
    sym("10204", x, 87, end)
    sym(cls, x, 66, rot)
    poly((x, 60), (x, 66))
    poly((x, 78), (x, 87))
    txt(nome, x - 8, 52)
SAI = [("Q0.1", "9000", "C1", 42), ("Q0.2", "9000", "C2", 66), ("Q0.4", "9008", "H1", 90), ("Q0.5", "9008", "H2", 114)]
for end, cls, rot, x in SAI:
    sym("10205", x, 111, end)
    if cls == "9008":
        lamp(x, 144, rot, VERDE)
    else:
        sym(cls, x, 144, rot)
    poly((x, 135), (x, 144))
    poly((x, 156), (x, 162))
txt("H1 M1 EM FUNCIONAMENTO", 78, 166)
txt("H2 M2 EM FUNCIONAMENTO", 102, 172)
# H3/H4: contato NA 97-98 do termico (mesmo rotulo do 6007) em serie com o piloto vermelho
for rt, x, h, nome, ty in ALM:
    sym("8016", x, 66, rt)
    poly((x, 60), (x, 66))
    poly((x, 78), (x, 144))
    lamp(x, 144, h, VERMELHO)
    poly((x, 156), (x, 162))
    txt(f"{h} {nome}", x - 10, ty)
retorno = [x for *_, x in SAI] + [a[1] for a in ALM]
poly((60, 87), (60, 81), (24, 81), (24, 162), *[(x, 162) for x in retorno])   # comum das cargas


# ---- ladder -------------------------------------------------------------------------------
def tempo(id_, x, y):
    sym("10066", x, y, id_, rotulos=[None, None, None, None, "3", TEMPO])


txt('CIRCUITO LINGUAGEM "LADDER"', 60, 186, 4)
txt("PERMISSÃO = RT1_OK E RT2_OK (I0.4 . I0.5)", 168, 203)
# trilho A (R1, R2, R3)
sym("3008", 30, 195, "24V")
poly((30, 195), (30, 207), (30, 237), (30, 267))
# R1: I0.1 I0.3 I0.4 I0.5 (I0.2 || Q0.3) -> Q0.3
prev = (30, 207)
for x, end in ((39, "I0.1"), (60, "I0.3"), (81, "I0.4"), (102, "I0.5")):
    sym("10050", x, 207, end)
    poly(prev, (x, 207))
    prev = (x + 12, 207)
poly(prev, (117, 207), (123, 207))
sym("10050", 123, 207, "I0.2")
sym("10050", 123, 219, "Q0.3")
poly((117, 207), (117, 219), (123, 219))
poly((135, 207), (144, 207), (156, 207))
poly((135, 219), (144, 219), (144, 207))
sym("10060", 156, 207, "Q0.3")
# R2: Q0.3 -> T1 -> T4:0  e  Q0.3 /T4:1 -> Q0.1
sym("10050", 39, 237, "Q0.3")
poly((30, 237), (39, 237))
poly((51, 237), (57, 237), (66, 237))
sym("10051", 66, 237, "T4:1")
poly((78, 237), (96, 237))
sym("10060", 96, 237, "Q0.1")
poly((57, 237), (57, 249), (63, 249))
tempo("-T1", 63, 249)
poly((78, 255), (84, 255))
sym("10060", 84, 255, "T4:0")
# R3: T4:0 -> T2 -> T4:1  e  T4:0 -> Q0.2
sym("10050", 39, 267, "T4:0")
poly((30, 267), (39, 267))
poly((51, 267), (57, 267), (96, 267))
sym("10060", 96, 267, "Q0.2")
poly((57, 267), (57, 279), (63, 279))
tempo("-T2", 63, 279)
poly((78, 285), (84, 285))
sym("10060", 84, 285, "T4:1")

# trilho B (R4, R5): pilotos de funcionamento seguem a saida do contator
sym("3008", 252, 195, "24V")
poly((252, 195), (252, 207), (252, 225))
for y, q, h in ((207, "Q0.1", "Q0.4"), (225, "Q0.2", "Q0.5")):
    sym("10050", 261, y, q)
    poly((252, y), (261, y))
    poly((273, y), (288, y))
    sym("10060", 288, y, h)

# ---- potencia: X1 -> DJ1 -> trilhos L1/L2/L3; termico + contator + motor por coluna ----------
txt('CIRCUITO DE POTÊNCIA "MOTORES"', 300, 6, 4)
RAILS = [{"nome": "L1", "y": 66, "x0": 252, "x1": 420}, {"nome": "L2", "y": 72, "x0": 252, "x1": 420},
         {"nome": "L3", "y": 78, "x0": 252, "x1": 420}, {"nome": "PE", "y": 178, "x0": 252, "x1": 420}]
sym("3005", 258, 26, "-X", id="X1")
sym("6009", 258, 40, "DJ1", id="DJ1")
CON = [{"de": ["X1", "L1"], "para": ["DJ1", "1"]}, {"de": ["X1", "L2"], "para": ["DJ1", "3"]},
       {"de": ["X1", "L3"], "para": ["DJ1", "5"]}, {"de": ["X1", "PE"], "para": ["PE", "rail"]},
       {"de": ["DJ1", "2"], "para": ["L1", "rail"]}, {"de": ["DJ1", "4"], "para": ["L2", "rail"]},
       {"de": ["DJ1", "6"], "para": ["L3", "rail"]}]
for n, x in ((1, 312), (2, 372)):
    f, k, m = f"F{n}", f"K{n}", f"M{n}"
    sym("6007", x, 92, f"RT{n}", id=f)
    sym("2001", x, 120, f"C{n}", id=k)
    sym("1000", x, 152, f"M{n}", id=m)
    for fase, a, b in (("L1", "1", "2"), ("L2", "3", "4"), ("L3", "5", "6")):
        CON.append({"de": [fase, "rail"], "para": [f, a]})
        CON.append({"de": [f, b], "para": [k, a]})
        CON.append({"de": [k, b], "para": [m, {"1": "U1", "3": "V1", "5": "W1"}[a]]})
    CON.append({"de": [m, "PE"], "para": ["PE", "rail"]})

# ---- tabela de E/S, legenda e identificacao ----------------------------------------------------
LINHAS = ["TABELA DE ENTRADAS E SAÍDAS",
          "I0.1  B0 DESLIGA (NF)", "I0.2  B1 LIGA (NA)", "I0.3  EMERGÊNCIA (NF)",
          "I0.4  RT1_OK - térmico M1 (NF 95-96)", "I0.5  RT2_OK - térmico M2 (NF 95-96)",
          "Q0.1  C1 - contator M1      Q0.2  C2 - contator M2", "Q0.3  marcha (memória da sequência)",
          "Q0.4  H1 M1 EM FUNCIONAMENTO (verde)", "Q0.5  H2 M2 EM FUNCIONAMENTO (verde)",
          "H3/H4 SOBRECARGA M1/M2 (vermelho) - NA 97-98",
          "LEGENDA: DJ1 disjuntor  RT relé térmico  C contator",
          "B botoeira  H sinaleiro  T temporizador (TON)",
          "SEQUÊNCIA: LIGA -> M1;  5 s -> M2;  +5 s -> M1 desliga"]
for i, s in enumerate(LINHAS):
    txt(s, 312, 196 + 6 * i)
txt("Aluno: Sérgio Murilo de Andrade Castelhano Filho", 150, 292, 4)


def juncoes():
    """Pontinho 4001 onde 3+ extremos de fio/pino se encontram (so cosmetico, mas o app o usa em T)."""
    cont = {}
    for w in W:
        for p in ((w["x1"], w["y1"]), (w["x2"], w["y2"])):
            cont[p] = cont.get(p, 0) + 1
    return [{"x1": x, "y1": y, "x2": x, "y2": y, "classe": "4001"} for (x, y), c in cont.items() if c >= 3]


def main(out):
    W.extend(juncoes())
    msg = cade_mcp.cad_build("PARTIDAS INTERCALARES - CLP", json.dumps(S), json.dumps(W), out,
                             auto_net=True, conexoes_json=json.dumps(CON), rails_json=json.dumps(RAILS),
                             textos_json=json.dumps(T))
    print(msg)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out/partidas_intercalares.cad")
