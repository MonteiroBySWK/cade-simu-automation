#!/usr/bin/env python3
"""Harness de avaliacao: PONTUA .cad produzidos por um agente contra casos em linguagem natural.

NAO chama nenhum LLM: o agente (Claude/outro) gera `<caso>.cad` por fora (MCP/skill) e este
script so mede. Caso = tools/eval/casos/<id>.json (enunciado PT-BR, restricoes, obrigatorios, testes).

Criterios (peso): abre/valida (10) | geometria: sem curto de fase e sem pino solto (25) |
testes funcionais do caso (35, proporcional) | fios nao atravessam simbolo (10) |
itens obrigatorios: classes/rotulos (20). Caso sem testes -> pesos renormalizados.

Ladder (`dsl: ladder/1`, em casos/ladder/): testes via clp_sim (ticks/sequencia/
esperado_bits), geometria com a excecao do trilho direito aberto (pino B das
bobinas 10060/10061/10062 sem fio, docs/ladder.md §4) + checagem da folha
segura (455x305, tools/sheet.json) + vinculos por rotulo; obrigatorios inclui
`operandos` (presentes nos rotulos das celulas 10050/10051/10060/10061/10062/
10204/10205); fios conta 1.0 (o gate de ladder nao aplica wires_check).

Uso:
  python3 tools/eval/run_eval.py --golden                  # baseline: roda tools/examples/<golden>.layout.json
                                                           # (.ladder.json p/ casos ladder) em casos/ + casos/ladder/
  python3 tools/eval/run_eval.py CASO ARQ.cad              # CASO = id ou caminho do .json (vale heldout/)
  python3 tools/eval/run_eval.py --dir saidas/             # saidas/<id_do_caso>.cad para cada caso de casos/
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
LADDER_DIR = CASOS / "ladder"
HELDOUT = HERE / "heldout"
EXEMPLOS = TOOLS / "examples"
sys.path.insert(0, str(ROOT / "tools"))
import cade_config  # noqa: E402
CLI = cade_config.cli_path()
PESOS = {"abre": 10, "geometria": 25, "testes": 35, "fios": 10, "obrigatorios": 20}
LADDER_DSL = "ladder/1"
OPERANDO_CLASSES = {"10050", "10051", "10060", "10061", "10062", "10066", "10204", "10205"}
FOLHA_X, FOLHA_Y = 455, 305


def eh_ladder(caso):
    return caso.get("dsl") == LADDER_DSL


def _pastas_de_caso():
    return [CASOS, LADDER_DIR, HELDOUT]


def carregar_caso(ref):
    p = Path(ref)
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    for base in _pastas_de_caso():
        q = base / (Path(ref).stem + ".json")
        if q.is_file():
            return json.loads(q.read_text(encoding="utf-8"))
    vistos = sorted(c.stem for b in _pastas_de_caso() for c in b.glob("*.json"))
    raise FileNotFoundError(f"caso nao encontrado: {ref} (casos: {vistos})")


def todos_os_casos():
    """Casos com golden (casos/ + casos/ladder/). heldout/ fica de fora (sem golden)."""
    fs = sorted(CASOS.glob("*.json")) + sorted(LADDER_DIR.glob("*.json"))
    return [json.loads(p.read_text(encoding="utf-8")) for p in fs]


def _norm(rot):
    return (rot or "").strip().lstrip("-").upper()


def _validar(path):
    r = subprocess.run([str(CLI), "validate", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    return r.returncode == 0, (r.stdout.strip() or r.stderr.strip())


def _simbolos(path):
    from dissect import parse_ent, split_all
    d = Path(path).read_bytes().decode("latin1")
    _, ents, _ = split_all(d)  # split_all: nao perde a 1a entidade (split_entities some com 3007/3011)
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


def testes_funcionais_ladder(path, casos):
    """-> (passaram, total, detalhes). Mesmo contrato de testes_funcionais, via clp_sim
    (sequencia/ticks/tempo_s, inicial com operandos, esperado_bits, OSCILA/INDEFINIDO)."""
    import clp_sim as cs
    c = cs.CircuitoCLP(str(path))
    ok, det = 0, []
    for t in casos:
        ruim = cs.chaves_invalidas(c, t)
        if ruim:
            det.append(f"{t.get('nome')}: chave(s) inexistente(s) no circuito {[f'{k} ({cp})' for cp, k in ruim]} "
                       f"(entradas {sorted(c.entradas)}, operandos {sorted(c.operandos)}, "
                       f"bobinas {sorted(c.bobinas)}, lampadas {sorted(c.lampadas)})")
            continue
        falhas, r, _ = cs.executar_caso(c, t)
        if not falhas:
            ok += 1
        else:
            det.append(f"{t.get('nome')}: {'; '.join(falhas)} "
                       f"(bobinas={r['bobinas']} lampadas={r['lampadas']} status={r['status']} bits1="
                       f"{sorted(k for k, v in r['bits'].items() if v)})")
    return ok, len(casos), det


def _operandos_presentes(path):
    """Rotulos das celulas ladder/CLP (10050/10051 bobinas e portas de CLP)."""
    return {r for cid, r in _simbolos(path) if cid in OPERANDO_CLASSES}


def obrigatorios(path, spec):
    """-> (frac, faltas). Conta classes (min), 'uma_de' (grupos), rotulos e operandos (ladder) presentes."""
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
    if spec.get("operandos"):
        ops = _operandos_presentes(path)
        for o in spec["operandos"]:
            itens += 1
            if _norm(o) not in ops:
                faltas.append(f"operando {o} ausente nas celulas ladder/CLP")
    return ((itens - len(faltas)) / itens if itens else 1.0), faltas


def extremos_da_folha(path):
    """(xmax, ymax) do desenho: fios pelos extremos, simbolos por posicao + dimensao."""
    from dissect import parse_ent, split_all
    try:
        dims = json.loads((TOOLS / "symbol_dims.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dims = {}
    d = Path(path).read_bytes().decode("latin1")
    _, ents, _ = split_all(d)
    mx = my = 0
    for e in ents:
        p = parse_ent(e)
        if not p or len(p["nums"]) < 12:
            continue
        try:
            x, y = int(p["nums"][8]), int(p["nums"][9])
        except (ValueError, IndexError):
            continue
        if p["id"].startswith("40") and len(p["id"]) == 4:
            try:
                mx = max(mx, x, int(p["nums"][10]))
                my = max(my, y, int(p["nums"][11]))
            except (ValueError, IndexError):
                pass
        elif p["id"] not in ("8", "20000"):
            w, h = dims.get(p["id"], [21, 15])[:2]
            mx, my = max(mx, x + w), max(my, y + h)
    return mx, my


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
    if eh_ladder(caso):
        import ladder_dsl
        soltos = [s for s in soltos if not ladder_dsl._solto_permitido(s)]
        import build_spec
        ev, _ = build_spec.conferir_vinculos(str(cad))
        mx, my = extremos_da_folha(str(cad))
        fora = None
        if mx > FOLHA_X or my > FOLHA_Y:
            fora = f"desenho ate ({mx},{my}) passa da folha segura ({FOLHA_X},{FOLHA_Y})"
        r["criterios"]["geometria"] = 1.0 if not (curtos or soltos or ev or fora) else 0.0
        msgs = [f"CURTO {c}" for c in curtos] + [f"SOLTO {s}" for s in soltos] + ev
        if fora:
            msgs.append(fora)
        if msgs:
            r["detalhes"]["geometria"] = msgs
    else:
        r["criterios"]["geometria"] = 1.0 if not (curtos or soltos) else 0.0
        if curtos or soltos:
            r["detalhes"]["geometria"] = [f"CURTO {c}" for c in curtos] + [f"SOLTO {s}" for s in soltos]
    if caso.get("testes"):
        if eh_ladder(caso):
            a, b, det = testes_funcionais_ladder(cad, caso["testes"])
        else:
            a, b, det = testes_funcionais(cad, caso["testes"])
        r["criterios"]["testes"] = a / b
        r["detalhes"]["testes"] = [f"{a}/{b} passaram"] + det
    else:
        r["criterios"]["testes"] = None          # n/a
    if eh_ladder(caso):
        r["criterios"]["fios"] = 1.0     # gate de ladder nao aplica wires_check (trilho/derivacoes)
        r["detalhes"]["fios"] = ["n/a em ladder"]
    else:
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
    """Gera o .cad do layout de exemplo `caso['golden']` (None se nao existe).
    Golden ladder (`*.ladder`) compila pela ladder_dsl; os demais pela build_spec."""
    g = caso.get("golden")
    if not g:
        return None
    if g.endswith(".ladder"):
        f = EXEMPLOS / f"{g}.json"
        if not f.is_file():
            return None
        import ladder_dsl
        spec = json.loads(f.read_text(encoding="utf-8"))
        out = Path(destino) / f"{caso['id']}.cad"
        r = ladder_dsl.construir(spec, str(out))
        return str(out) if r["ok"] else None
    f = EXEMPLOS / f"{g}.layout.json"
    if not f.is_file():
        return None
    import build_spec
    spec = json.loads(f.read_text(encoding="utf-8"))
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
                    motivo = "sem golden" if not caso.get("golden") else f"golden '{caso['golden']}' ausente ou com falha em tools/examples"
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
