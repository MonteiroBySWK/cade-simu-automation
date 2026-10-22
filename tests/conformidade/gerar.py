#!/usr/bin/env python3
"""Gera os casos de CONFORMIDADE provisorios a partir do oraculo Python (`tools/netlist_sim.py`).

Para cada exemplo de `tools/examples/*.layout.json` cria `tests/conformidade/<caso>/`:
  circuito.cad      copia de `tests/golden/<caso>.cad` (byte-identico ao do Rust)
  cenario.json      sequencia de acoes (pressionar/soltar/alternar/esperar/reiniciar)
  golden_app.json   estado apos CADA acao, com `"fonte": "oraculo_python"`

Formato completo e como regravar com o app real: `docs/conformidade.md`. O gravador do app
(`docker/wine-golden/`, `tools/app_sim.py`) sobrescreve `golden_app.json` com `"fonte": "app"`;
este script **nunca** sobrescreve um golden cuja fonte seja `app` (use --forcar para isso).

Uso: python3 tests/conformidade/gerar.py [--forcar]
"""
import itertools
import json
import shutil
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ROOT = AQUI.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import netlist_sim as ns  # noqa: E402

EX = ROOT / "tools" / "examples"
GOLD = ROOT / "tests" / "golden"
ESPERA_MS = 300          # > 1 tick do app (100 ms): deixa a relaxacao assentar antes de observar
TRAVAM = ("RT", "Q", "F")   # entradas que o app trava ao clicar (termico, disjuntor): alternar


ESP = [{"acao": "esperar", "ms": ESPERA_MS}]
BASE = [{"acao": "reiniciar"}] + ESP


def trava(k):
    return k.startswith(TRAVAM)


def liga(k):
    return [{"acao": "alternar" if trava(k) else "pressionar", "alvo": k}]


def solta(k):
    return [] if trava(k) else [{"acao": "soltar", "alvo": k}]


def destrava(k):
    return [{"acao": "alternar", "alvo": k}] + ESP if trava(k) else []


def blocos_de(c):
    """Cenarios canonicos: cada entrada sozinha (testa selo) e pares (segura uma, aperta a outra)."""
    ents = list(c.entradas)
    out = [BASE + liga(k) + ESP + solta(k) + ESP + destrava(k) for k in ents]
    for a, b in itertools.permutations(ents, 2):
        out.append(BASE + liga(a) + ESP + liga(b) + ESP + solta(b) + ESP + solta(a) + ESP + destrava(a) + destrava(b))
    return out


def acoes_de(c):
    """Concatena so os blocos sem RACE/INSTAVEL (o app nao tem resultado definido para corrida)."""
    return BASE + [a for b in blocos_de(c) if simular(c, b) is not None for a in b]


def simular(c, acoes):
    """Roda as acoes no oraculo com estado persistente. -> lista de passos ou None se ha RACE/INSTAVEL."""
    ent, t_ms, st, passos = {}, 0, c.novo_estado(), []
    for i, a in enumerate(acoes):
        dt = 0.0
        if a["acao"] in ("pressionar", "soltar", "alternar"):
            k = a["alvo"]
            ent[k] = {"pressionar": True, "soltar": False, "alternar": not ent.get(k, False)}[a["acao"]]
        elif a["acao"] == "esperar":
            dt, t_ms = a["ms"] / 1000.0, t_ms + a["ms"]
        elif a["acao"] == "reiniciar":
            ent, st = {}, c.novo_estado()
        e = c.avancar(st, ent, dt)
        if e["status"] in ("RACE", "INSTAVEL"):
            return None
        passos.append({"i": i, "t_ms": t_ms, "bobinas": sorted(e["bobinas"]), "lampadas": sorted(e["lampadas"]),
                       "saidas_clp": [], "temporizadores": sorted(k for k, t in e["temporizadores"].items() if t["saida"]),
                       "curto": e["status"] == "CURTO"})
    return passos


def main(forcar=False):
    nomes = sorted(f.name[: -len(".layout.json")] for f in EX.glob("*.layout.json"))
    for nome in nomes:
        d = AQUI / nome
        d.mkdir(exist_ok=True)
        shutil.copyfile(GOLD / f"{nome}.cad", d / "circuito.cad")
        c = ns.Circuito(str(d / "circuito.cad"))
        acoes = acoes_de(c)
        passos = simular(c, acoes)
        assert passos is not None, nome
        cen = {"versao": 1, "descricao": f"{nome}: cada entrada sozinha e pares (segura uma, aperta a outra); "
                                         f"espera de {ESPERA_MS} ms entre as acoes", "acoes": acoes}
        (d / "cenario.json").write_text(json.dumps(cen, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        gold = d / "golden_app.json"
        if gold.is_file() and not forcar:
            try:
                if json.loads(gold.read_text(encoding="utf-8")).get("fonte") == "app":
                    print(f"{nome}: golden do APP preservado")
                    continue
            except ValueError:
                pass
        g = {"versao": 1, "fonte": "oraculo_python", "passos": passos}
        gold.write_text(json.dumps(g, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"{nome}: {len(acoes)} acoes")


if __name__ == "__main__":
    main("--forcar" in sys.argv)
