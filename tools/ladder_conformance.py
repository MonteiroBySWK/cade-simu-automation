#!/usr/bin/env python3
"""Prepara casos de CONFORMIDADE de ladder (motor Rust x app real).

Para cada `tools/examples/<nome>.ladder.json`:
  - gera o `.cad` com `ladder_dsl.construir`;
  - grava `tests/conformidade/ladder_<nome>/circuito.cad`;
  - escreve `cenario.json` com uma sequencia **fisicamente possivel** (um atuador por vez):
    reiniciar -> parte 1 -> solta (selo) -> espera (TON) -> para -> parte 2 -> termico -> rearma -> reiniciar.

A observacao e feita depois de cada acao; o golden e gravado por `tools/golden_app.py` no app
(Wine). O `cade conformidade` compara `saidas_clp` (Q0.x) + bobinas + lampadas + motores.

Uso:
  python3 tools/ladder_conformance.py                 # (re)gera circuito.cad + cenario.json
  python3 tools/ladder_conformance.py --so partida_direta
  python3 tools/ladder_conformance.py --json          # resumo
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
EX = TOOLS / "examples"
DEST = ROOT / "tests" / "conformidade"
ESPERA = 300          # ms entre acoes (>= 3 ticks do app)


def _lab(dev):
    """[id, classe, rotulo] -> rotulo sem '-' (ex.: '-S1' -> 'S1')."""
    if isinstance(dev, str):
        return dev.strip().lstrip("-").upper()
    if isinstance(dev, (list, tuple)) and len(dev) >= 3:
        return str(dev[2]).strip().lstrip("-").upper()
    return ""


def _carga_labels(carga):
    if isinstance(carga, str):
        return [_lab(carga)]
    if isinstance(carga, (list, tuple)):
        if len(carga) == 3 and isinstance(carga[2], str) and not isinstance(carga[0], (list, tuple)):
            return [_lab(carga)]
        return [_lab(c) for c in carga]
    return []


def entradas_do_exemplo(spec):
    """-> dict com listas de rotulos: paradas (NF), partidas (NA), termicos (RT), saidas (Q)."""
    clp = spec["layout"]["clp"]
    paradas, partidas, termicos = [], [], []
    for e in clp.get("entradas", []):
        dev = e.get("dispositivo") or []
        classe = str(dev[1]) if len(dev) > 1 else ""
        rot = _lab(dev)
        if not rot:
            continue
        if classe == "8001" or rot.startswith(("S0", "B0")):
            paradas.append(rot)
        elif classe == "8000":
            partidas.append(rot)
        elif rot.startswith("RT"):
            # so rele termico de verdade; DJ1 (8016 do disjuntor) NAO entra: o gravador ja fecha
            termicos.append(rot)
    saidas = []
    for s in clp.get("saidas", []):
        for lab in _carga_labels(s.get("carga")):
            if lab and lab not in saidas:
                saidas.append(lab)
    return {"paradas": paradas, "partidas": partidas, "termicos": termicos, "saidas": saidas}


def cenario_de(spec):
    """Sequencia canonica: cobre partida, selo, timer, parada, 2a partida, termico e rearme."""
    e = entradas_do_exemplo(spec)
    acoes = [{"acao": "reiniciar"}, {"acao": "esperar", "ms": ESPERA}]
    partidas = e["partidas"] or []
    paradas = e["paradas"] or []
    termicos = e["termicos"] or []

    def aperta(rot):
        acoes.append({"acao": "pressionar", "alvo": rot})
        acoes.append({"acao": "esperar", "ms": ESPERA})
        acoes.append({"acao": "soltar", "alvo": rot})
        acoes.append({"acao": "esperar", "ms": ESPERA})

    if partidas:
        aperta(partidas[0])
        acoes.append({"acao": "esperar", "ms": 1500})          # TON / sequencia
    if len(partidas) > 1:
        # com o primeiro selado, tenta o segundo (intertravamento); depois para e usa o segundo
        aperta(partidas[1])
        acoes.append({"acao": "esperar", "ms": ESPERA})
    if paradas:
        aperta(paradas[0])
        acoes.append({"acao": "esperar", "ms": ESPERA})
    if len(partidas) > 1:
        aperta(partidas[1])
    elif partidas:
        aperta(partidas[0])
    if termicos:
        for rt in termicos[:2]:
            acoes.append({"acao": "alternar", "alvo": rt})
            acoes.append({"acao": "esperar", "ms": ESPERA})
            acoes.append({"acao": "alternar", "alvo": rt})     # rearma
            acoes.append({"acao": "esperar", "ms": ESPERA})
    if partidas:
        aperta(partidas[0])
    acoes.append({"acao": "reiniciar"})
    acoes.append({"acao": "esperar", "ms": ESPERA})
    return {"versao": 1, "tempo": "parede",
            "descricao": f"ladder: partida, selo, timer/sequencia, parada, 2a partida, termico e rearme "
                         f"({', '.join(partidas) or '-'} / {', '.join(paradas) or '-'})",
            "acoes": acoes}


def preparar(nome, forcar=False):
    spec_path = EX / f"{nome}.ladder.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    d = DEST / f"ladder_{nome}"
    d.mkdir(parents=True, exist_ok=True)
    cad = d / "circuito.cad"
    # gera pelo oraculo Python (ladder_dsl) para o .cad ser identico ao do gate
    r = subprocess.run([sys.executable, str(TOOLS / "ladder_dsl.py"), str(spec_path), str(cad)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    if r.returncode != 0 or not cad.is_file():
        raise RuntimeError(f"{nome}: build falhou\n{r.stdout[-800:]}\n{r.stderr[-400:]}")
    cen = cenario_de(spec)
    (d / "cenario.json").write_text(json.dumps(cen, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"caso": d.name, "acoes": len(cen["acoes"]), "cad": str(cad),
            "partidas": entradas_do_exemplo(spec)["partidas"],
            "paradas": entradas_do_exemplo(spec)["paradas"],
            "termicos": entradas_do_exemplo(spec)["termicos"]}


def main(argv):
    ap = argparse.ArgumentParser(description="gera casos de conformidade de ladder")
    ap.add_argument("--so", help="um exemplo (nome sem .ladder.json)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    nomes = [args.so] if args.so else sorted(p.name[: -len(".ladder.json")] for p in EX.glob("*.ladder.json"))
    res = []
    for n in nomes:
        r = preparar(n)
        res.append(r)
        print(f"{r['caso']}: {r['acoes']} acoes | partidas={r['partidas']} paradas={r['paradas']} termicos={r['termicos']}")
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
