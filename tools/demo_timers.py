#!/usr/bin/env python3
"""Exemplos A4 (temporizadores eletricos): gera e valida no modelo Python.

- out/timer_on_9004.cad: 9004 + contato 7004 de mesmo rotulo ligam KM1/H1 apos 1 s.
- out/timer_pisca_9007.cad: 9007 + lampada 9008 piscam a cada 0,5 s enquanto S1 fecha.

Gera via DSL (build_spec, mesma geometria do gate), ajusta label4/5 do temporizador
(unidade/tempo, docs/re-engenharia.md 11.4) e valida com build_spec.gate + netlist_sim.
Nao usa Wine nem o app (a prova no app fica com o operador).
"""
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
OUT = TOOLS.parent / "out"

import build_spec  # noqa: E402
import netlist_sim as ns  # noqa: E402
from dissect import parse_ent, split_all  # noqa: E402


def _base(titulo, comando, testes=()):
    return {"titulo": titulo, "layout": {
        "trilhos": {"L1": 14, "L2": 20, "L3": 26, "N": 282, "x0": 25, "x1": 395, "PE": 291},
        "fontes": [{"id": "X1", "classe": "3007", "rotulo": "-X",
                    "pinos": {"L1": "L1", "L2": "L2", "L3": "L3", "N": "N", "PE": "PE"}}],
        "comando": comando, "testes": list(testes)}}


SPEC_ON = _base("TEMPORIZADOR ON (9004+7004, 1 s)", [
    {"id": "m1", "de": "L1", "para": "N", "serie": [["S1", "8000", "-S1"]],
     "ramos": [{"carga": ["KT1", "9004", "-KT1"]}]},
    {"id": "m2", "de": "L1", "para": "N", "serie": [["T1", "7004", "-KT1"]],
     "ramos": [{"carga": ["KM1", "9000", "-KM1"], "indica": ["H1", "9008", "-H1"]}]},
])
TESTES_ON = [
    {"nome": "antes de 1 s", "entradas": {"S1": True}, "avanca": 0.9,
     "esperado": ["KT1"], "esperado_lampadas": [], "esperado_temporizadores": [], "status": "OK"},
    {"nome": "apos 1 s liga", "entradas": {"S1": True}, "avanca": 1.0,
     "esperado": ["KM1", "KT1"], "esperado_lampadas": ["H1"], "esperado_temporizadores": ["KT1"], "status": "OK"},
    {"nome": "sem S1 nada liga", "entradas": {}, "avanca": 5,
     "esperado": [], "esperado_lampadas": [], "status": "OK"},
]

SPEC_PISCA = _base("TEMPORIZADOR INTERMITENTE (9007+9008, 0,5 s)", [
    {"id": "m1", "de": "L1", "para": "N", "serie": [["S1", "8000", "-S1"]],
     "ramos": [{"carga": ["KT1", "9007", "-KT1"]}]},
    {"id": "m2", "de": "L1", "para": "N", "serie": [["T1", "7004", "-KT1"]],
     "ramos": [{"carga": ["H1", "9008", "-H1"]}]},
])
TESTES_PISCA = [
    {"nome": "repouso apagada", "entradas": {}, "avanca": 0,
     "esperado_lampadas": [], "status": "OK"},
    {"nome": "meio periodo ainda apagada", "entradas": {"S1": True}, "avanca": 0.4,
     "esperado_lampadas": [], "status": "OK"},
    {"nome": "um periodo acesa", "entradas": {"S1": True}, "avanca": 0.5,
     "esperado_lampadas": ["H1"], "status": "OK"},
    {"nome": "dois periodos apagada", "entradas": {"S1": True}, "avanca": 1.0,
     "esperado_lampadas": [], "status": "OK"},
    {"nome": "sem S1 apagada", "entradas": {}, "avanca": 5,
     "esperado_lampadas": [], "status": "OK"},
]


def ajustar_tempo(path, classe, rotulo, unidade, tempo):
    """Reescreve label4/5 (unidade/tempo) do simbolo e devolve os labels novos."""
    raw = Path(path).read_bytes().decode("latin1")
    _, ents, _ = split_all(raw)
    for e in ents:
        p = parse_ent(e)
        if p and p["id"] == classe and (p["labels"] or [""])[0] == rotulo:
            break
    else:
        raise SystemExit(f"simbolo {classe} {rotulo} nao achado em {path}")
    antigos = list(p["labels"]) + [""] * 9
    novos = antigos[:9]
    novos[4], novos[5] = unidade, tempo
    velho, novo = "#" + "#".join(antigos[:len(p["labels"])]) + "#", "#" + "#".join(novos) + "#"
    assert raw.count(velho) == 1, (classe, rotulo)
    Path(path).write_bytes(raw.replace(velho, novo, 1).encode("latin1"))
    return novos


def gerar(spec, testes, path, classe, rotulo, unidade, tempo):
    r = build_spec.construir(dict(spec, testes=[]), str(path))
    assert r["build"]["ok"], r["erros"]
    ajustar_tempo(path, classe, rotulo, unidade, tempo)
    g = build_spec.gate(str(path), testes)
    print(f"{path.name}: build OK, tempo {classe}={tempo}x{unidade} | "
          f"testes {g['testes']['passaram']}/{g['testes']['total']} "
          f"{'GATE: OK' if g['testes']['ok'] and not g['geo']['curtos'] and not g['geo']['soltos'] else 'GATE: REPROVADO'}")
    for e in g["erros"]:
        print("  ERRO:", e)
    return g


def main():
    OUT.mkdir(exist_ok=True)
    p1 = OUT / "timer_on_9004.cad"
    g1 = gerar(SPEC_ON, TESTES_ON, p1, "9004", "-KT1", "0", "1")       # 10 ticks de 100 ms = 1 s
    c = ns.Circuito(str(p1))
    st = c.novo_estado()
    serie = [(0.0, "S1"), (0.9, "S1"), (0.1, "S1"), (0.0, None)]
    t = 0.0
    for dt, ent in serie:
        e = c.avancar(st, {"S1": True} if ent else {}, dt)
        t += dt
        print(f"  t={t:.1f}s KM1={e['bobinas']} H1={e['lampadas']} tm={e['temporizadores']['KT1']}")
    assert g1["testes"]["ok"]

    p2 = OUT / "timer_pisca_9007.cad"
    g2 = gerar(SPEC_PISCA, TESTES_PISCA, p2, "9007", "-KT1", "3", "5")  # 5 ticks de 100 ms = 0,5 s
    c = ns.Circuito(str(p2))
    st = c.novo_estado()
    t = 0.0
    for _ in range(5):
        e = c.avancar(st, {"S1": True}, 0.25)
        t += 0.25
        print(f"  t={t:.2f}s H1={e['lampadas']} tm={e['temporizadores']['KT1']['saida']}")
    e = c.avancar(st, {}, 0.5)
    print(f"  solto H1={e['lampadas']} tm={e['temporizadores']['KT1']['saida']}")
    assert g2["testes"]["ok"]
    print("OK: exemplos gerados e validados no modelo Python")


if __name__ == "__main__":
    main()
