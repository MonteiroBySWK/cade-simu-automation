#!/usr/bin/env python3
"""Harness de avaliacao: PONTUA .cad produzidos por um agente contra casos em linguagem natural.

NAO chama nenhum LLM: o agente (Claude/outro) gera `<caso>.cad` por fora (MCP/skill) e este
script so mede. Caso = tools/eval/casos/<id>.json (enunciado PT-BR, restricoes, obrigatorios, testes).

Criterios (peso): abre/valida (10) | geometria: sem curto de fase e sem pino solto (25) |
testes funcionais do caso (35, proporcional) | fios nao atravessam simbolo (10) |
itens obrigatorios: classes/rotulos (20). Caso sem testes -> pesos renormalizados.

Uso:
  python3 tools/eval/run_eval.py --golden                  # baseline: roda tools/examples/<golden>.layout.json
  python3 tools/eval/run_eval.py CASO ARQ.cad              # CASO = id ou caminho do .json
  python3 tools/eval/run_eval.py --dir saidas/             # saidas/<id_do_caso>.cad para cada caso
  (qualquer modo aceita --json para saida estruturada; exit 1 se algum score < --min, default 100 no --golden)
"""
import argparse
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
CASOS = HERE / "casos"
EXEMPLOS = TOOLS / "examples"
CLI = ROOT / "src" / "cade_cli" / "target" / "debug" / "cade_cli"
PESOS = {"abre": 10, "geometria": 25, "testes": 35, "fios": 10, "obrigatorios": 20}


def carregar_caso(ref):
    p = Path(ref)
    if not p.is_file():
        p = CASOS / (Path(ref).stem + ".json")
    if not p.is_file():
        raise FileNotFoundError(f"caso nao encontrado: {ref} (casos: {[c.stem for c in sorted(CASOS.glob('*.json'))]})")
    return json.loads(p.read_text())


def todos_os_casos():
    return [json.loads(p.read_text()) for p in sorted(CASOS.glob("*.json"))]


def _norm(rot):
    return (rot or "").strip().lstrip("-").upper()


def _validar(path):
    r = subprocess.run([str(CLI), "validate", str(path)], capture_output=True, text=True, timeout=60)
    return r.returncode == 0, (r.stdout.strip() or r.stderr.strip())


def _simbolos(path):
    from dissect import parse_ent, split_entities
    d = Path(path).read_bytes().decode("latin1")
    _, ents, _ = split_entities(d)
    out = []
    for e in ents:
        p = parse_ent(e)
        if p and not (p["id"].startswith("40") and len(p["id"]) == 4) and p["id"] not in ("8", "20000"):
            out.append((p["id"], _norm((p["labels"] or [""])[0])))
    return out


def testes_funcionais(path, casos):
    """-> (passaram, total, detalhes). Chave inexistente no circuito = teste reprovado (nao vacuo)."""
    import netlist_sim as ns
    c = ns.Circuito(str(path))
    ok, det = 0, []
    for cs in casos:
        ruim = ns.chaves_invalidas(c, cs)
        if ruim:
            det.append(f"{cs.get('nome')}: chave(s) inexistente(s) no circuito {[f'{k} ({cp})' for cp, k in ruim]} "
                       f"(entradas {sorted(c.entradas)}, bobinas {sorted(c.bobinas)}, lampadas {sorted(c.lampadas)})")
            continue
        cond, e = ns.executar_caso(c, cs)
        ok += cond
        if not cond:
            det.append(f"{cs.get('nome')}: obtido bobinas={e['bobinas']} lampadas={e['lampadas']} status={e['status']}, "
                       f"esperado {cs.get('esperado')} lampadas={cs.get('esperado_lampadas')} status={cs.get('status')}")
    return ok, len(casos), det


def obrigatorios(path, spec):
    """-> (frac, faltas). Conta classes (min), 'uma_de' (grupos) e rotulos presentes."""
    sims = _simbolos(path)
    cont = Counter(c for c, _ in sims)
    rots = {r for _, r in sims}
    itens, faltas = 0, []
    for cl, n in (spec.get("classes") or {}).items():
        itens += 1
        if cont[cl] < n:
            faltas.append(f"classe {cl}: {cont[cl]} < {n}")
    for grupo in spec.get("uma_de") or []:
        itens += 1
        if not any(cont[c] for c in grupo):
            faltas.append(f"nenhuma das classes {grupo}")
    for r in spec.get("rotulos") or []:
        itens += 1
        if _norm(r) not in rots:
            faltas.append(f"rotulo {r} ausente")
    return ((itens - len(faltas)) / itens if itens else 1.0), faltas


def pontuar(cad, caso):
    """Pontua UM .cad contra UM caso. Retorna dict com criterios, total (0-100) e detalhes."""
    import geo_check
    import wires_check
    r = {"caso": caso["id"], "cad": str(cad), "criterios": {}, "detalhes": {}, "total": 0.0}
    if not Path(cad).is_file():
        r["detalhes"]["abre"] = ["arquivo inexistente"]
        r["criterios"] = {k: 0.0 for k in PESOS}
        return r
    ok, msg = _validar(cad)
    r["criterios"]["abre"] = 1.0 if ok else 0.0
    if not ok:
        r["detalhes"]["abre"] = [msg]
        r["criterios"].update({k: 0.0 for k in PESOS if k != "abre"})
        return r
    res = geo_check.analisar(str(cad))
    curtos, soltos = res[0], res[1]
    r["criterios"]["geometria"] = 1.0 if not (curtos or soltos) else 0.0
    if curtos or soltos:
        r["detalhes"]["geometria"] = [f"CURTO {c}" for c in curtos] + [f"SOLTO {s}" for s in soltos]
    if caso.get("testes"):
        a, b, det = testes_funcionais(cad, caso["testes"])
        r["criterios"]["testes"] = a / b
        r["detalhes"]["testes"] = [f"{a}/{b} passaram"] + det
    else:
        r["criterios"]["testes"] = None          # n/a
    _, ruins = wires_check.analisar(str(cad))
    r["criterios"]["fios"] = 1.0 if not ruins else 0.0
    if ruins:
        r["detalhes"]["fios"] = [f"{n}: {a}->{b}" for n, a, b in ruins[:5]]
    frac, faltas = obrigatorios(cad, caso.get("obrigatorios") or {})
    r["criterios"]["obrigatorios"] = frac
    if faltas:
        r["detalhes"]["obrigatorios"] = faltas
    aplicaveis = {k: v for k, v in r["criterios"].items() if v is not None}
    peso_total = sum(PESOS[k] for k in aplicaveis)
    r["total"] = round(100.0 * sum(PESOS[k] * v for k, v in aplicaveis.items()) / peso_total, 1)
    return r


def construir_golden(caso, destino):
    """Gera o .cad do layout de exemplo `caso['golden']` (None se nao existe)."""
    g = caso.get("golden")
    if not g:
        return None
    f = EXEMPLOS / f"{g}.layout.json"
    if not f.is_file():
        return None
    import build_spec
    spec = json.loads(f.read_text())
    out = Path(destino) / f"{caso['id']}.cad"
    r = build_spec.construir(spec, str(out))
    return str(out) if r["build"]["ok"] else None


def tabela(resultados):
    cols = ["abre", "geometria", "testes", "fios", "obrigatorios"]
    print(f"{'caso':30} {'total':>6}  " + "  ".join(f"{c[:6]:>6}" for c in cols))
    for r in resultados:
        if r.get("pulado"):
            print(f"{r['caso']:30} {'-':>6}  ({r['pulado']})")
            continue
        cel = []
        for c in cols:
            v = r["criterios"].get(c)
            cel.append(f"{'n/a':>6}" if v is None else f"{v * 100:6.0f}")
        print(f"{r['caso']:30} {r['total']:6.1f}  " + "  ".join(cel))
    validos = [r for r in resultados if not r.get("pulado")]
    if validos:
        print(f"{'MEDIA':30} {sum(r['total'] for r in validos) / len(validos):6.1f}  ({len(validos)} caso(s))")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("caso", nargs="?")
    ap.add_argument("cad", nargs="?")
    ap.add_argument("--golden", action="store_true", help="roda os layouts de exemplo como baseline")
    ap.add_argument("--dir", help="pasta com <id_do_caso>.cad")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--min", type=float, default=None, help="score minimo por caso (exit 1 se abaixo)")
    a = ap.parse_args(argv)
    res = []
    if a.golden:
        with tempfile.TemporaryDirectory() as t:
            for caso in todos_os_casos():
                cad = construir_golden(caso, t)
                if cad is None:
                    motivo = "sem golden" if not caso.get("golden") else f"golden '{caso['golden']}' ausente em tools/examples"
                    res.append({"caso": caso["id"], "pulado": motivo, "total": 0.0, "criterios": {}})
                    continue
                res.append(pontuar(cad, caso))
        minimo = 100.0 if a.min is None else a.min
    elif a.dir:
        for caso in todos_os_casos():
            res.append(pontuar(Path(a.dir) / f"{caso['id']}.cad", caso))
        minimo = a.min
    elif a.caso and a.cad:
        res.append(pontuar(a.cad, carregar_caso(a.caso)))
        minimo = a.min
    else:
        ap.print_help()
        return 2
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        tabela(res)
        for r in res:
            for crit, linhas in r.get("detalhes", {}).items():
                for ln in linhas:
                    print(f"  [{r['caso']}] {crit}: {ln}")
    if minimo is not None and any((not r.get("pulado")) and r["total"] < minimo for r in res):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
