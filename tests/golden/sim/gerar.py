#!/usr/bin/env python3
"""Goldens de PARIDADE do motor de simulacao Rust x oraculo Python (`tools/netlist_sim.py`).

Para cada um dos 11 exemplos de `tools/examples/*.layout.json` (o `.cad` e o de `tests/golden/<n>.cad`,
byte-identico ao do Rust) grava `tests/golden/sim/<n>.sim.json` com:
  - os casos declarados em `testes` do exemplo + o veredito do Python;
  - uma varredura de entradas (vazio, cada uma, pares, todas) x bobinas iniciais (nenhuma, cada, todas)
    com o `estado()` completo do Python (status, bobinas, lampadas, temporizadores, curtos).
Tambem grava `timers.sim.json`: temporizadores ON/OFF-delay (papel `contato_temp` por override) sobre
`partida_sinalizacao.cad`, com `avanca`/`passos`.

Uso: python3 tests/golden/sim/gerar.py   (so quando o ORACULO mudar de proposito)
"""
import itertools
import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ROOT = AQUI.parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import netlist_sim as ns  # noqa: E402

EX = ROOT / "tools" / "examples"
GOLD = AQUI.parent


def estado_json(e):
    return {k: e[k] for k in ("status", "bobinas", "lampadas", "temporizadores", "curtos")}


def varredura(c):
    ents = list(c.entradas)
    combos = [()] + [(a,) for a in ents] + list(itertools.combinations(ents, 2)) + ([tuple(ents)] if len(ents) > 2 else [])
    bobs = sorted(c.bobinas)
    iniciais = [[]] + [[b] for b in bobs] + ([bobs] if len(bobs) > 1 else [])
    out = []
    for combo in combos:
        for ini in iniciais:
            ent = {k: True for k in combo}
            out.append({"entradas": ent, "inicial": ini, "estado": estado_json(c.estado(ent, ini))})
    return out


def dump(obj, path):
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def main():
    nomes = sorted(f.name[: -len(".layout.json")] for f in EX.glob("*.layout.json"))
    for nome in nomes:
        spec = json.loads((EX / f"{nome}.layout.json").read_text(encoding="utf-8"))
        c = ns.Circuito(str(GOLD / f"{nome}.cad"))
        declarados = []
        for cs in spec.get("testes", []):
            cond, e = ns.executar_caso(c, cs)
            declarados.append({"caso": cs, "aprovado": bool(cond), "estado": estado_json(e)})
        dados = {"circuito": nome, "fonte": "oraculo_python", "entradas": c.entradas, "bobinas": sorted(c.bobinas),
                 "lampadas": sorted(c.lampadas), "soltos": c.soltos, "declarados": declarados, "varredura": varredura(c)}
        dump(dados, AQUI / f"{nome}.sim.json")
        print(f"{nome}: {len(declarados)} declarados, {len(dados['varredura'])} varredura")

    # temporizadores: contato 8016 (NA 97-98 do termico) vira ON-delay 5 s / OFF-delay 3 s
    cad = GOLD / "partida_sinalizacao.cad"
    casos_ton = [
        {"entradas": {"RT1": True}, "avanca": 0}, {"entradas": {"RT1": True}, "avanca": 4.9},
        {"entradas": {"RT1": True}, "avanca": 5}, {"entradas": {}, "avanca": 100},
        {"entradas": {"RT1": True}, "avanca": 2, "tempos": {"RT1": 2}},
    ]
    seq_ton = [{"entradas": {"RT1": True}, "avanca": 3}, {"entradas": {}, "avanca": 1},
               {"entradas": {"RT1": True}, "avanca": 3}, {"entradas": {"RT1": True}, "avanca": 2}]
    seq_tof = [{"entradas": {"RT1": True}, "avanca": 0}, {"entradas": {}, "avanca": 2}, {"entradas": {}, "avanca": 1}]
    out = {"circuito": "partida_sinalizacao", "fonte": "oraculo_python", "grupos": []}
    for tipo, tempo, casos, seq in (("ton", 5, casos_ton, seq_ton), ("tof", 3, [{"entradas": {"RT1": True}, "avanca": 0}], seq_tof)):
        papeis = ns.carregar_papeis()
        override = {"papel": "contato_temp", "modo": "NA", "tipo": tipo, "tempo": tempo}
        papeis["8016"] = dict(override)
        c = ns.Circuito(str(cad), papeis=papeis)
        g = {"override": {"8016": override}, "casos": [], "sequencia": []}
        for cs in casos:
            e = c.estado(cs["entradas"], None, cs.get("avanca", 0), cs.get("tempos"))
            g["casos"].append({"caso": cs, "estado": estado_json(e)})
        st = c.novo_estado()
        for p in seq:
            e = c.avancar(st, p["entradas"], p["avanca"])
            g["sequencia"].append({"passo": p, "estado": estado_json(e)})
        out["grupos"].append(g)
    dump(out, AQUI / "timers.sim.json")
    print("timers.sim.json")


if __name__ == "__main__":
    main()
