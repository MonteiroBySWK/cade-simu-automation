#!/usr/bin/env python3
"""DSL `ladder/1` (CLP modular + ladder do CADe_SIMU 4.0): validacao, modelo logico e gerador de .cad.

Contrato: docs/ladder.md (semantica §1-3, geometria §4). Este modulo e o ORACULO Python; o port Rust
segue o mesmo contrato. Tres pecas:

  1. validar(spec)              -> erros/avisos da DSL (V1..V8 do doc, + extensoes abaixo)
  2. ModeloLogico(spec)         -> simulador §3.1 por ticks de 100 ms (mesma API de clp_sim.CircuitoCLP:
                                   imagem_inicial / rodar / regime), usado p/ conferir a DSL contra o .cad
  3. compilar(spec) / construir(spec, out) -> .cad (zonas: hardware do CLP, potencia, ladder) + gate
                                   (clp_sim = modelo GEOMETRICO do .cad, geo_check, conferencia logico x geometrico)

Extensoes sobre o doc (ver docs/ladder.md §2.5):
  - `layout.potencia` = {"tipo":"dj_comum", ...}: UM disjuntor DJ (mesmo rotulo do contato aux 8016 e da
    protecao 6002 da CPU; o app liga/desliga todos juntos) + n colunas [contator 2001 -> (termico 6007) -> motor].
  - elemento inline `["TON", op, {"tempo":n,"base":"1s"}]` DENTRO da logica do degrau (sem bobina de Q), como o
    arquivo-base da Pratica 5: passa '+' de IN para Q quando o acumulador chega ao preset.
  - `clp.saidas[].carga` pode ser lista de cargas EM PARALELO (bobina + lampada de sinalizacao).
  - `textos`: [{"x","y","txt"}] (legenda/tabela de I/O desenhadas no .cad, classe 8).
"""
import json
import re
import sys
from pathlib import Path

T = Path(__file__).resolve().parent
sys.path.insert(0, str(T))
from cadfile import Cad, Ent  # noqa: E402

OPERANDO = re.compile(r"^[A-Za-z\-][A-Za-z0-9._:/\-]{0,14}$")
BASES = {"0.1s": ("3", 1), "1s": ("0", 10), "10s": ("1", 100), "100s": ("2", 1000)}
TIPOS_SAIDA = {"OUT": "10060", "SET": "10061", "RST": "10062"}
PASSO = 21           # contato 12 + fio 9
RAMO = 18            # pitch vertical entre ramos em paralelo
FOLHA_X, FOLHA_Y = 455, 305


class DslErro(ValueError):
    pass


# ======================================================================================== expressao
def _folha(e):
    return isinstance(e, (list, tuple)) and e and isinstance(e[0], str)


def norm(e):
    """-> ('c', 'NA'|'NF', op) | ('ton', op, n, base) | ('serie', [..]) | ('par', [..]). Achata e remove grupos de 1."""
    if _folha(e):
        t = e[0].upper()
        if t in ("NA", "NF"):
            if len(e) != 2:
                raise DslErro(f"contato {e!r}: use [\"NA\"|\"NF\", operando]")
            return ("c", t, str(e[1]))
        if t == "TON":
            o = (e[2] if len(e) > 2 else {}) or {}
            base = str(o.get("base", "1s"))
            if base not in BASES:
                raise DslErro(f"TON {e[1]}: base {base!r} invalida (use {sorted(BASES)})")
            return ("ton", str(e[1]), float(o.get("tempo", 1)), base)
        if t in ("P", "N"):
            raise DslErro(f"contato de flanco {t!r} e reservado em ladder/1")
        raise DslErro(f"tipo de elemento {e[0]!r} desconhecido (NA, NF, TON)")
    if isinstance(e, dict):
        ks = [k for k in ("serie", "paralelo") if k in e]
        if len(ks) != 1:
            raise DslErro(f"bloco {e!r}: use exatamente uma chave 'serie' ou 'paralelo'")
        tipo = "serie" if ks[0] == "serie" else "par"
        kids = [norm(x) for x in e[ks[0]]]
    elif isinstance(e, (list, tuple)):
        tipo, kids = "serie", [norm(x) for x in e]
    else:
        raise DslErro(f"expressao invalida: {e!r}")
    flat = []
    for k in kids:
        flat += k[1] if k[0] == tipo else [k]
    if not flat:
        raise DslErro("grupo vazio")
    return flat[0] if len(flat) == 1 else (tipo, flat)


def operandos_lidos(n):
    if n[0] == "c":
        return {n[2]}
    if n[0] == "ton":
        return set()
    return set().union(*(operandos_lidos(k) for k in n[1]))


def tons_de(n):
    if n[0] == "ton":
        return [n]
    if n[0] == "c":
        return []
    return [t for k in n[1] for t in tons_de(k)]


def linhas(n):
    """Numero de linhas (ramos) ocupadas pelo no."""
    if n[0] in ("c", "ton"):
        return 1
    if n[0] == "serie":
        return max(linhas(k) for k in n[1])
    return sum(linhas(k) for k in n[1])


def _saida(s):
    if isinstance(s, dict):
        raise DslErro("saida {\"paralelo\":[..]} (varias bobinas no mesmo no) e reservada: use um degrau por bobina")
    t = str(s[0]).upper()
    if t == "TON":
        o = (s[2] if len(s) > 2 else {}) or {}
        return ("ton", str(s[1]), o)
    if t not in TIPOS_SAIDA:
        raise DslErro(f"saida {s!r}: use OUT, SET, RST (ou TON com q)")
    return (t, str(s[1]))


def rungs_normalizados(spec):
    """-> [{id, logica(no), saida(tipo, op), comentario}]. TON como saida vira TON inline + OUT(q)."""
    L = (spec.get("layout") or {}).get("ladder") or {}
    out = []
    for i, r in enumerate(L.get("rungs") or L.get("degraus") or []):
        lg = norm(r["logica"])
        sa = _saida(r["saida"])
        if sa[0] == "ton":
            o = sa[2]
            ton = ("ton", sa[1], float(o.get("tempo", 1)), str(o.get("base", "1s")))
            lg = ("serie", (lg[1] if lg[0] == "serie" else [lg]) + [ton])
            sa = ("OUT", str(o.get("q") or sa[1] + ".Q"))
        out.append({"id": r.get("id", f"r{i + 1}"), "logica": lg, "saida": sa, "comentario": r.get("comentario", "")})
    return out


def _achatar_colunas(cols):
    out = []
    for c in cols:
        if isinstance(c, dict):
            for m in c.get("paralelo", []):
                out += _achatar_colunas([m])
        elif isinstance(c, (list, tuple)) and len(c) > 2:
            out.append(c)
    return out


def _chave(rot):
    return (rot or "").lstrip("-").strip()


def _cargas(s):
    c = s["carga"]
    return [c] if (c and isinstance(c[0], str)) else list(c)


# ======================================================================================== validacao
def validar(spec):
    """-> (erros, avisos)."""
    erros, avisos = [], []
    L = spec.get("layout") or {}
    clp = L.get("clp") or {}
    if spec.get("dsl") != "ladder/1":
        erros.append("campo \"dsl\" deve ser \"ladder/1\"")
    if not clp:
        return erros + ["layout.clp ausente"], avisos
    if str(clp.get("classe", "10206")) != "10206":
        erros.append("clp.classe: so \"10206\" em ladder/1")
    try:
        rungs = rungs_normalizados(spec)
    except (DslErro, KeyError, IndexError, TypeError) as e:
        return erros + [f"ladder invalido: {e}"], avisos
    if not rungs:
        erros.append("layout.ladder.rungs vazio")
    ent_ops = [e["operando"] for e in clp.get("entradas", [])]
    sai_ops = [s["operando"] for s in clp.get("saidas", [])]
    rot_fis = set()
    for e in clp.get("entradas", []):
        rot_fis.add(_chave(e["dispositivo"][2]))
        if e.get("serie"):
            erros.append(f"entrada {e['operando']}: 'serie' de entrada e reservado (use um dispositivo)")
    for s in clp.get("saidas", []):
        rot_fis |= {_chave(c[2]) for c in _cargas(s)} | {_chave(c[2]) for c in s.get("serie", [])}
    for op in ent_ops + sai_ops:
        if not OPERANDO.match(op):
            erros.append(f"operando {op!r} invalido (1-15 chars, sem '#' ou '*')")
    for nome, ops in (("entradas", ent_ops), ("saidas", sai_ops)):
        if len(set(ops)) != len(ops):
            erros.append(f"clp.{nome}: operandos repetidos (V5)")
    ids = [r["id"] for r in rungs]
    if len(set(ids)) != len(ids):
        erros.append("ids de degrau repetidos (V5)")
    produzidos, saidas_por_op = set(ent_ops), {}
    for r in rungs:
        t, op = r["saida"]
        saidas_por_op.setdefault(op, []).append(t)
        produzidos.add(op)
        for ton in tons_de(r["logica"]):
            produzidos.add(ton[1])
        if t == "OUT" and not OPERANDO.match(op):
            erros.append(f"degrau {r['id']}: operando de saida {op!r} invalido")
        if len(tons_de(r["logica"])) != len(_tons_topo(r["logica"])):
            erros.append(f"degrau {r['id']}: TON so pode estar na serie principal do degrau (nao dentro de ramo paralelo)")
    for op, ts in saidas_por_op.items():
        if ts.count("OUT") > 1:
            erros.append(f"operando {op}: mais de um OUT (V2)")
        if "OUT" in ts and ({"SET", "RST"} & set(ts)):
            erros.append(f"operando {op}: OUT misturado com SET/RST (V2)")
    for r in rungs:
        for op in operandos_lidos(r["logica"]):
            if op not in produzidos:
                erros.append(f"degrau {r['id']}: operando {op} lido mas nunca produzido (V1: entrada, bobina ou TON)")
    escritos = set(saidas_por_op)
    for op in sai_ops:
        if op not in escritos:
            erros.append(f"clp.saidas: {op} sem bobina no ladder (V3)")
    for op in escritos:
        if op.startswith("Q") and op not in sai_ops and op[1:2].isdigit():
            avisos.append(f"bobina {op} sem saida fisica no clp.saidas (V3)")
    for op in produzidos | set(ent_ops) | set(sai_ops):
        if _chave(op) in rot_fis:
            erros.append(f"operando {op} igual a um rotulo fisico (V4): o app tambem comanda o polo de mesmo rotulo")
    for r in rungs:
        for k in operandos_lidos(r["logica"]):
            pass
    nr = {op for op in ent_ops}
    for e in clp.get("entradas", []):
        d = e["dispositivo"]
        if d[1] == "8001":
            for r in rungs:
                if _usa_nf(r["logica"], e["operando"]):
                    avisos.append(f"V7: contato NF de {e['operando']} com dispositivo NF ({d[2]}): bit 1 em repouso")
                    break
    pot = L.get("potencia")
    if pot is not None and not (isinstance(pot, list) or (isinstance(pot, dict) and pot.get("tipo") == "dj_comum")):
        erros.append("layout.potencia: lista (formato de docs/dsl-layout.md, com trilhos/fontes) ou "
                     "{\"tipo\":\"dj_comum\", ...}")
    if isinstance(pot, list) and not (L.get("trilhos") and L.get("fontes")):
        erros.append("layout.potencia em lista exige layout.trilhos e layout.fontes (como no DSL de layout)")
    return erros, avisos


def _tons_topo(n):
    if n[0] == "ton":
        return [n]
    if n[0] == "serie":
        return [k for k in n[1] if k[0] == "ton"]
    return []


def _usa_nf(n, op):
    if n[0] == "c":
        return n[2] == op and n[1] == "NF"
    if n[0] == "ton":
        return False
    return any(_usa_nf(k, op) for k in n[1])


# ======================================================================================== modelo logico (§3.1)
class ModeloLogico:
    """Mesma API/ordem de avaliacao de clp_sim.CircuitoCLP (§3.1 x §3.2 devem coincidir)."""

    def __init__(self, spec):
        erros, _ = validar(spec)
        if erros:
            raise DslErro("; ".join(erros))
        L = spec["layout"]
        self.clp = L["clp"]
        self.rungs = rungs_normalizados(spec)
        self.entradas_clp = [(e["operando"], e["dispositivo"]) for e in self.clp["entradas"]]
        self.saidas = []          # (op, [cargas], [serie])
        for s in self.clp["saidas"]:
            self.saidas.append((s["operando"], _cargas(s), s.get("serie", [])))
        prot = (self.clp.get("alimentacao") or {}).get("protecao")
        self.protecao = _chave(prot[2]) if prot else None
        pot = L.get("potencia") or {}
        if isinstance(pot, list):                      # formato layout.py: 6007 = termico, 6002/6003/6009/6010 = disjuntor
            itens = [it for g in pot for it in _achatar_colunas(g.get("colunas", []))]
            self.disjuntores = {_chave(it[2]) for it in itens if str(it[1]) in ("6002", "6003", "6009", "6010")}
            self.termicos = {_chave(it[2]) for it in itens if str(it[1]) == "6007"}
        else:
            self.disjuntores = {_chave((pot.get("disjuntor") or ["", "", ""])[2])}
            self.termicos = {_chave(m["termico"]) for m in pot.get("motores", []) if m.get("termico")}
        if self.protecao:
            self.disjuntores.add(self.protecao)
        self.disjuntores.discard("")
        self.botoes = {_chave(e["dispositivo"][2]) for e in self.clp["entradas"] if e["dispositivo"][1] in ("8000", "8001")}
        self.bobinas = {}
        for _, cargas, _ in self.saidas:
            for c in cargas:
                if c[1] == "9000":
                    self.bobinas[_chave(c[2])] = c
        self.lampadas = {_chave(c[2]) for _, cargas, _ in self.saidas for c in cargas if c[1] == "9008"}
        self.tons = []
        for r in self.rungs:
            for t in tons_de(r["logica"]):
                self.tons.append({"op": t[1], "T": max(1, int(round(t[2] * BASES[t[3]][1])))})
        self.operandos = sorted({o for o, _ in self.entradas_clp} | {s[0] for s in self.saidas} |
                                {r["saida"][1] for r in self.rungs} | {t["op"] for t in self.tons} |
                                set().union(*(operandos_lidos(r["logica"]) for r in self.rungs)))
        self.entradas = sorted(self.botoes | self.disjuntores | self.termicos |
                               {_chave(e["dispositivo"][2]) for e in self.clp["entradas"]})
        self.alternaveis = self.disjuntores | self.termicos

    def estado_zero(self, inicial=()):
        ini = set(inicial or ())
        return {"bits": {o: (1 if o in ini else 0) for o in self.operandos},
                "fis": {k: k in ini for k in self.bobinas},
                "acc": [0] * len(self.tons)}

    # --- hardware
    def _cpu_on(self, ent):
        return True if self.protecao is None else bool(ent.get(self.protecao, False))

    @staticmethod
    def _conduz(d, ent):
        k, cls = _chave(d[2]), str(d[1])
        v = bool(ent.get(k, False))
        return (not v) if cls in ("8001", "8017", "7001") else v

    def _eval(self, n, vin, bits, acc, ton_i, nacc):
        if n[0] == "c":
            b = bool(bits.get(n[2]))
            return vin and (b if n[1] == "NA" else not b)
        if n[0] == "ton":
            i = ton_i[0]
            ton_i[0] += 1
            q = acc[i] >= self.tons[i]["T"]
            nacc[i] = min(acc[i] + 1, self.tons[i]["T"]) if vin else 0
            return vin and q
        if n[0] == "serie":
            v = vin
            for k in n[1]:
                v = self._eval(k, v, bits, acc, ton_i, nacc)
            return v
        return any([self._eval(k, vin, bits, acc, ton_i, nacc) for k in n[1]])

    def tick(self, est, ent):
        bits, fis, acc = est["bits"], est["fis"], est["acc"]
        cpu = self._cpu_on(ent)
        nb = dict(bits)
        for op, d in self.entradas_clp:
            nb[op] = 1 if (cpu and self._conduz(d, ent)) else 0
        nacc, ton_i = list(acc), [0]
        sets, rsts, outs = set(), set(), {}
        for r in self.rungs:
            v = self._eval(r["logica"], True, bits, acc, ton_i, nacc)
            t, op = r["saida"]
            if t == "OUT":
                outs[op] = outs.get(op, False) or v
            elif v:
                (sets if t == "SET" else rsts).add(op)
        for op, v in outs.items():
            nb[op] = 1 if v else 0
        for op in sets:
            nb[op] = 1
        for op in rsts:
            nb[op] = 0
        for t in self.tons:
            nb[t["op"]] = 0
        for i, t in enumerate(self.tons):
            if nacc[i] >= t["T"]:
                nb[t["op"]] = 1
        novo_fis, lamp = {k: False for k in self.bobinas}, set()
        for op, cargas, serie in self.saidas:
            if not (cpu and bits.get(op)):
                continue
            if not all(self._conduz_serie(s, fis, ent) for s in serie):
                continue
            for c in cargas:
                if c[1] == "9000":
                    novo_fis[_chave(c[2])] = True
                elif c[1] == "9008":
                    lamp.add(_chave(c[2]))
        return ({"bits": nb, "fis": novo_fis, "acc": nacc},
                {"lampadas": sorted(lamp), "curtos": [], "cpu": cpu, "indefinido": sorted(sets & rsts)})

    def _conduz_serie(self, s, fis, ent):
        k, cls = _chave(s[2]), str(s[1])
        if cls in ("7000", "7001"):
            ativo = bool(fis.get(k, False))
            return (not ativo) if cls == "7001" else ativo
        return self._conduz(s, ent)

    # rodar / regime / imagem_inicial: identicos ao clp_sim (reuso)
    def rodar(self, ent, ticks, est=None):
        import clp_sim
        return clp_sim.CircuitoCLP.rodar(self, ent, ticks, est)

    def regime(self, ent, est=None, max_ticks=2000):
        import clp_sim
        return clp_sim.CircuitoCLP.regime(self, ent, est, max_ticks)

    _assin = staticmethod(lambda est: (tuple(sorted(est["bits"].items())), tuple(sorted(est["fis"].items())), tuple(est["acc"])))

    @staticmethod
    def _resumo(est, info, status, ticks=None):
        import clp_sim
        return clp_sim.CircuitoCLP._resumo(est, info, status, ticks)

    def imagem_inicial(self, caso):
        import clp_sim
        ini = set(caso.get("inicial") or ())
        est = self.estado_zero(ini)
        ent = {k: v for k, v in clp_sim.primeira_entrada(caso).items() if k in self.alternaveis}
        e1, _ = self.tick(est, ent)
        for op, _ in self.entradas_clp:
            est["bits"][op] = 1 if (op in ini or e1["bits"][op]) else 0
        e2, _ = self.tick(est, ent)
        est["fis"] = {k: (k in ini) or e2["fis"][k] for k in est["fis"]}
        for i, t in enumerate(self.tons):
            if t["op"] in ini:
                est["acc"][i] = t["T"]
        return est


# ======================================================================================== desenho (geometria)
_FLAGS = {  # n0..n7 gravados pelo app (base da Pratica 5 / acervo)
    "6002": ["1", "1", "1", "1", "0", "0", "0", "0"], "6003": ["1", "1", "1", "1", "1", "1", "0", "0"],
}
FIO_N = {"L": "4000", "N": "4009", "PE": "4010", "+": "4018", "-": "4019"}


def _lib():
    import cade_mcp
    return cade_mcp._lib()


class Desenho:
    def __init__(self):
        self.cad = Cad([], "")
        _, self.protos, self.footer, _ = _lib()
        self.xmax = self.ymax = 0

    def _toca(self, x, y):
        self.xmax, self.ymax = max(self.xmax, x), max(self.ymax, y)

    def sym(self, cid, x, y, rotulo=None, labels=None, extra=""):
        p = self.protos[str(cid)]
        nums = list(p["nums"])
        nums[8], nums[9] = str(int(x)), str(int(y))
        if cid in _FLAGS:
            nums[:8] = _FLAGS[cid]
        nums[19] = "1"                          # o app grava n19=1 em todo simbolo (base da Pratica 5)
        lab = list(labels) if labels is not None else list(p["labels"])
        if rotulo is not None and lab:
            lab[0] = rotulo
        if len(lab) < 9:
            lab += [""] * (9 - len(lab))
        e = Ent(cid, lab, nums, extra)
        self.cad.adicionar(e)
        self._toca(int(x) + 21, int(y) + 15)
        return e

    def fio(self, x1, y1, x2, y2, cls="+"):
        if (x1, y1) == (x2, y2):
            return
        n = ["0"] * 8 + [str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2))] + ["0"] * 6 + ["2", "0", "0", "0", "0"]
        self.cad.adicionar(Ent(FIO_N.get(cls, cls), [""] * 9, n))
        self._toca(max(x1, x2), max(y1, y2))

    def junc(self, x, y):
        n = ["0"] * 8 + [str(int(x)), str(int(y)), str(int(x)), str(int(y))] + ["0"] * 11
        self.cad.adicionar(Ent("4001", [""] * 9, n))

    def texto(self, x, y, txt):
        w = max(6, int(round(1.9 * len(txt))))
        lab = ["", "", " 0", " 0", " 0", " 0", " 0", " 0", " 0", " 0*0*0*0*0*0*0*0*0*" + f"{x}*{y}*{x + w}*{y + 3}" + "*0" * 11, txt]
        self.cad.adicionar(Ent("8", lab, []))
        self._toca(x + w, y + 3)


# --------------------------------------------------------------------------------------- ladder (zona C)
def _larg(n):
    """Avanco horizontal do no a partir do cursor (inclui o fio de 9 antes de cada elemento)."""
    if n[0] == "c":
        return PASSO
    if n[0] == "ton":
        return 24
    if n[0] == "serie":
        return sum(_larg(k) for k in n[1])
    return 9 + max(_larg(k) for k in n[1])


def _desenha(d, n, x, y, ops):
    """Desenha o no com o cursor (pino/no) em (x,y) na linha principal; devolve (x_fim, y_fim)."""
    if n[0] == "c":
        d.fio(x, y, x + 9, y)
        d.sym("10050" if n[1] == "NA" else "10051", x + 9, y, n[2])
        return x + PASSO, y
    if n[0] == "ton":
        d.fio(x, y, x + 9, y)
        u, nn = BASES[n[3]][0], n[2]
        txt = str(int(nn)) if float(nn).is_integer() else str(nn)
        d.sym("10066", x + 9, y, labels=[n[1], "", "IN", "Q", u, txt, "", "", ""])
        return x + 24, y + 6
    if n[0] == "serie":
        for k in n[1]:
            x, y = _desenha(d, k, x, y, ops)
        return x, y
    # paralelo: no de entrada (x+9,y), ramos empilhados +18, no de saida em x+9+W
    W = max(_larg(k) for k in n[1])
    xe, xs = x + 9, x + 9 + W
    d.fio(x, y, xe, y)
    ys, yy = [], y
    for k in n[1]:
        ys.append(yy)
        yy += RAMO * linhas(k)
    for k, yr in zip(n[1], ys):
        xf, yf = _desenha(d, k, xe, yr, ops)
        if xf < xs:
            d.fio(xf, yf, xs, yr)
    # verticais em segmentos entre ramos (junc 4001 onde >=3 pontas)
    for xv in (xe, xs):
        for a, b in zip(ys, ys[1:]):
            d.fio(xv, a, xv, b)
        d.junc(xv, y)
        for yr in ys[1:-1]:
            d.junc(xv, yr)
    return xs, y


def desenha_ladder(d, rungs, x0, y0, ymax=FOLHA_Y - 12):
    """Colunas de degraus com 3008 proprio; coluna nova se passa de ymax. -> [(xL, y_ini, y_fim)] por coluna."""
    cols, atual, y = [], [], y0 + 15
    for r in rungs:
        h = RAMO * (linhas(r["logica"]) - 1) + 21 + (6 if tons_de(r["logica"]) else 0)
        if atual and y + h > ymax:
            cols.append(atual)
            atual, y = [], y0 + 15
        atual.append((r, y))
        y += h
    if atual:
        cols.append(atual)
    xL, info = x0, []
    for ci, col in enumerate(cols):
        fim_x = []
        for r, y in col:
            xe, ye = _desenha_dry(r["logica"], xL, y)
            fim_x.append(xe)
        xc = max(fim_x) + 9
        y_ini, y_ult = col[0][1], col[-1][1]
        d.sym("3008", xL, y_ini - 15, "+L" if ci == 0 else f"+L{ci + 1}")
        taps = [y for _, y in col]
        pts = [y_ini - 15] + taps
        for a, b in zip(pts, pts[1:]):
            d.fio(xL, a, xL, b)
        for ty in taps:
            d.junc(xL, ty)
        for r, y in col:
            xe, ye = _desenha(d, r["logica"], xL, y, None)
            d.fio(xe, ye, xc, ye)
            t, op = r["saida"]
            d.sym(TIPOS_SAIDA[t], xc, ye, op)
            if r.get("comentario") and False:
                pass
        info.append((xL, y_ini, y_ult))
        d._toca(xc + 12, y_ult + 21)
        xL = xc + 12 + 36
    return info


def _desenha_dry(n, x, y):
    class _Nulo:
        def fio(self, *a, **k): pass
        def sym(self, *a, **k): pass
        def junc(self, *a, **k): pass
    return _desenha(_Nulo(), n, x, y, None)


# --------------------------------------------------------------------------------------- CLP (zona B)
def desenha_clp(d, clp, xc=24, yc=45):
    """Hardware: fonte 3011 [+6002] -> CPU 10206; entradas 10204 com dispositivo; saidas 10205 -> cargas -> 0V.
    -> dict com extremos usados. Retorna (x_max_entradas, y_retorno)."""
    al = clp.get("alimentacao", {})
    fonte = al.get("fonte") or {"id": "X2", "classe": "3011", "rotulo": "-X"}
    d.sym("3011", xc, yc - 27, fonte.get("rotulo", "-X"))
    prot = al.get("protecao")
    d.sym("10206", xc, yc, clp.get("rotulo", "-CLP"), extra=clp.get("ip", "192.128.0.1"))
    if prot:
        d.sym("6002", xc, yc - 21, prot[2])
        d.fio(xc, yc - 27, xc, yc - 21, "L")
        d.fio(xc + 6, yc - 27, xc + 6, yc - 21, "N")
        d.fio(xc, yc - 9, xc, yc, "L")
        d.fio(xc + 6, yc - 9, xc + 6, yc, "N")
    else:
        d.fio(xc, yc - 27, xc, yc, "L")
        d.fio(xc + 6, yc - 27, xc + 6, yc, "N")
    d.fio(xc + 12, yc - 27, xc + 12, yc, "PE")
    ents = clp["entradas"]
    xs = [xc + 36 + 18 * k for k in range(len(ents))]
    # +24V: p3 sobe ate a barra y=yc-27 e corre sobre os dispositivos
    yb = yc - 27
    d.fio(xc + 18, yc, xc + 18, yb, "+")
    barra = [xc + 18] + xs
    for a, b in zip(barra, barra[1:]):
        d.fio(a, yb, b, yb, "+")
    for x, e in zip(xs, ents):
        dv = e["dispositivo"]
        d.sym(dv[1], x, yc - 21, dv[2])
        d.fio(x, yb, x, yc - 21, "+")
        d.junc(x, yb)
        d.sym("10204", x, yc, e["operando"])
        d.fio(x, yc - 9, x, yc, "+")
    # saidas
    yo = yc + 24
    xo, saidas_pos = xc + 6, []
    for s in clp["saidas"]:
        cargas = _cargas(s)
        saidas_pos.append((xo, s, cargas))
        xo += 18 * len(cargas) + 18
        xo = max(xo, xo)
    y_ret = 0
    yl_max = 0
    for x, s, cargas in saidas_pos:
        d.sym("10205", x, yo, s["operando"])
        ypin = yo + 24
        yfim = ypin
        for sr in s.get("serie", []):
            d.fio(x, yfim, x, yfim + 9, "+")
            d.sym(sr[1], x, yfim + 9, sr[2])
            yfim += 21
        yl = yfim + 9
        yn = yfim + 3 if len(cargas) > 1 else None
        if yn is None:
            d.fio(x, yfim, x, yl, "+")
        else:
            d.fio(x, yfim, x, yn, "+")
            d.fio(x, yn, x, yl, "+")
            d.junc(x, yn)
        for j, c in enumerate(cargas):
            xj = x + 18 * j
            if j:
                d.fio(x + 18 * (j - 1), yn, xj, yn, "+")
                d.fio(xj, yn, xj, yl, "+")
                if j < len(cargas) - 1:
                    d.junc(xj, yn)
            d.sym(c[1], xj, yl, c[2])
        yl_max = max(yl_max, yl)
    y_ret = yl_max + 18
    # retorno 0V: M da CPU -> esquerda -> baixo -> sob as cargas
    d.fio(xc + 24, yc, xc + 24, yc - 6, "-")
    x_l = xc - 15
    d.fio(xc + 24, yc - 6, x_l, yc - 6, "-")
    d.fio(x_l, yc - 6, x_l, y_ret, "-")
    taps = [xj for x, s, cargas in saidas_pos for xj in [x + 18 * j for j in range(len(cargas))]]
    pts = [x_l] + sorted(taps)
    for a, b in zip(pts, pts[1:]):
        d.fio(a, y_ret, b, y_ret, "-")
    for xj in sorted(taps):
        d.fio(xj, yl_max + 12, xj, y_ret, "-")
        d.junc(xj, y_ret)
    return xs[-1] if xs else xc, y_ret


# --------------------------------------------------------------------------------------- potencia (zona A)
def desenha_potencia(d, pot, x0, y0=18):
    ms = pot["motores"]
    fonte, dj = pot.get("fonte", {}), pot["disjuntor"]
    d.sym(fonte.get("classe", "3005"), x0, y0, fonte.get("rotulo", "-X"))
    d.sym(dj[1], x0, y0 + 9, dj[2])
    for j in range(3):
        d.fio(x0 + 6 * j, y0, x0 + 6 * j, y0 + 9, "L")
    xk = [x0 + 36 * k for k in range(len(ms))]
    ybus = [y0 + 27, y0 + 33, y0 + 39]                 # barras L1 L2 L3
    yc = y0 + 48                                       # topo dos contatores
    for j in range(3):
        xj0 = x0 + 6 * j
        d.fio(xj0, y0 + 21, xj0, ybus[j], "L")
        xs = [xk_ + 6 * j for xk_ in xk]
        d.fio(xj0, ybus[j], xj0, yc, "L") if len(ms) and xs[0] == xj0 else None
        taps = []
        for xt in xs:
            if xt != xj0:
                d.fio(xt, ybus[j], xt, yc, "L")
            taps.append(xt)
        pts = sorted(set([xj0] + xs))
        for a, b in zip(pts, pts[1:]):
            d.fio(a, ybus[j], b, ybus[j], "L")
        for xt in set(taps):
            d.junc(xt, ybus[j])
    ypm = yc
    for m, x in zip(ms, xk):
        d.sym("2001", x, yc, m["contator"])
        ya = yc + 12
        if m.get("termico"):
            for j in range(3):
                d.fio(x + 6 * j, ya, x + 6 * j, ya + 6, "L")
            d.sym("6007", x, ya + 6, m["termico"])
            ya = ya + 6 + 12
        ym = ya + 12
        for j in range(3):
            d.fio(x + 6 * j, ya, x + 6 * j, ym, "L")
        d.sym("1000", x, ym, m.get("motor", "M"))
        ypm = ym
    # PE
    ype = y0 + 9
    d.fio(x0 + 18, y0, x0 + 18, ype, "PE")
    d.fio(x0 + 18, ype, x0 + 18, ypm, "PE")
    d.junc(x0 + 18, ype)
    prev = x0 + 18
    for x in xk[1:]:
        d.fio(prev, ype, x + 18, ype, "PE")
        d.fio(x + 18, ype, x + 18, ypm, "PE")
        d.junc(x + 18, ype)
        prev = x + 18
    d._toca(xk[-1] + 24, ypm + 24)
    return xk[-1] + 24, ypm + 24


def desenha_potencia_layout(d, L, nome):
    """Potencia no formato de docs/dsl-layout.md (trilhos/fontes/potencia): usa o motor layout.py + cad_build e
    FUNDE as entidades no desenho. -> (x_max, y_max) da zona."""
    import layout
    import cade_mcp
    import tempfile
    sub = {k: L[k] for k in ("trilhos", "fontes", "potencia", "terra") if k in L}
    low = layout.compilar(sub)
    with tempfile.TemporaryDirectory() as td:
        tmp = str(Path(td) / "pot.cad")
        res = cade_mcp.cad_build(titulo="pot", simbolos_json=json.dumps(low["simbolos"]),
                                 conexoes_json=json.dumps(low.get("conexoes", [])), fios_json=json.dumps(low.get("fios", [])),
                                 rails_json=json.dumps(low.get("rails", [])), out_path=tmp)
        if "ERRO" in res:
            raise DslErro(f"potencia: {res}")
        sub_cad = Cad.ler(tmp)
    xm = ym = 0
    for e in sub_cad.ents:
        d.cad.adicionar(Ent(e.id, e.labels, e.nums, e.extra))
        try:
            xs = [int(e.nums[8]), int(e.nums[10])] if e.id.startswith("40") else [int(e.nums[8]) + max(0, int(e.nums[14]) + int(e.nums[12]))]
            ys = [int(e.nums[9]), int(e.nums[11])] if e.id.startswith("40") else [int(e.nums[9]) + max(0, int(e.nums[15]) + int(e.nums[13]))]
            xm, ym = max(xm, *xs), max(ym, *ys)
        except (ValueError, IndexError):
            pass
    d._toca(xm, ym)
    return xm, ym


# ======================================================================================== compilar / construir
def compilar(spec, nome="novo.cad"):
    erros, avisos = validar(spec)
    if erros:
        raise DslErro("; ".join(erros))
    L = spec["layout"]
    d = Desenho()
    pot = L.get("potencia")
    if isinstance(pot, list):          # potencia do motor layout.py a esquerda; CLP e ladder a direita (docs/ladder.md §4)
        xm, _ = desenha_potencia_layout(d, L, nome)
        xc = int(L["clp"].get("x", xm + 36))
        xl, y_ret = desenha_clp(d, L["clp"], xc=xc)
        x_lad, y_lad = int(L["ladder"].get("x", xc - 15)), int(L["ladder"].get("y", y_ret + 6))
    else:
        xc = int(L["clp"].get("x", 39))
        xl, y_ret = desenha_clp(d, L["clp"], xc=xc)
        ybot = y_ret
        if pot:
            xm, ym = desenha_potencia(d, pot, int(pot.get("x", max(xl + 36, 210))))
            ybot = max(ybot, ym - 6)
        x_lad, y_lad = int(L["ladder"].get("x", 24)), int(L["ladder"].get("y", ybot + 6))
    desenha_ladder(d, rungs_normalizados(spec), x_lad, y_lad)
    for t in L.get("textos", []):
        d.texto(int(t["x"]), int(t["y"]), t["txt"])
    d.cad.footer = _footer(d, nome)
    return d, avisos


def _footer(d, nome):
    f = d.footer
    return f


def construir(spec, out):
    """Compila ladder/1 -> .cad e roda o gate. Retorno no formato de build_spec.construir."""
    import build_spec
    r = {"ok": False, "path": str(out), "titulo": spec.get("titulo"),
         "build": {"ok": False, "mensagem": ""},
         "testes": {"ok": False, "passaram": None, "total": None, "falhas": [], "saida": ""},
         "geo": {"curtos": [], "soltos": [], "curtos_msg": [], "soltos_msg": []},
         "fios": {"ok": None, "n": 0, "atravessam": []}, "avisos": [], "erros": [], "_build_raw": "", "_teste_raw": ""}
    try:
        d, av = compilar(spec, Path(out).name)
    except (DslErro, KeyError, ValueError, TypeError, IndexError) as e:
        r["erros"].append(f"layout invalido: {e}")
        return r
    r["avisos"] += av
    d.cad.salvar(out)
    if d.xmax > FOLHA_X or d.ymax > FOLHA_Y:
        r["avisos"].append(f"V8: desenho ate ({d.xmax},{d.ymax}) ultrapassa a folha segura ({FOLHA_X},{FOLHA_Y})")
    r["n_simbolos"] = len(d.cad.ents)
    r["_build_raw"] = f"OK {len(d.cad.ents)} entidades -> {out}"
    r["build"] = {"ok": True, "mensagem": r["_build_raw"]}
    gate_clp(out, spec, r)
    r["ok"] = bool(r["testes"]["ok"] and not r["geo"]["curtos"] and not r["geo"]["soltos"] and not r["erros"])
    return r


def gate_clp(path, spec, r):
    """Gate de um .cad com CLP: geo_check (curto/solto, exceto B das bobinas ladder), testes no modelo geometrico
    (clp_sim) E no modelo logico (DSL), com equivalencia entre os dois. Preenche r."""
    import build_spec
    import clp_sim
    import geo_check
    curtos, soltos = geo_check.analisar(str(path))[:2]
    soltos = [s for s in soltos if not _solto_permitido(s)]
    r["geo"] = {"curtos": curtos, "soltos": soltos, "curtos_msg": [build_spec.acionavel_curto(c) for c in curtos],
                "soltos_msg": [build_spec.acionavel_solto(s) for s in soltos]}
    r["erros"] += r["geo"]["curtos_msg"] + r["geo"]["soltos_msg"]
    ev, av = build_spec.conferir_vinculos(str(path))
    r["erros"] += ev
    r["avisos"] += av
    testes = spec.get("testes") or (spec.get("layout") or {}).get("testes") or []
    saida, ok, falhas, total = executar_testes(path, testes, spec)
    r["_teste_raw"] = saida
    r["testes"] = {"ok": ok, "passaram": total - len(falhas), "total": total, "falhas": falhas, "saida": saida}
    if not testes:
        r["erros"].append("sem testes: declare \"testes\" (casos {nome, entradas, inicial, esperado, status})")
    return r


def _solto_permitido(s):
    """Pino B de bobina ladder (trilho direito aberto) e permitido (docs/ladder.md §4)."""
    return bool(re.match(r"^.*\((10060|10061|10062)\)\.(p2|B)@", s)) or "(10206).p5" in s and False


def executar_testes(path, testes, spec=None):
    """-> (saida_texto, ok, falhas[], total). Roda no modelo geometrico e (se spec) no logico; exige igualdade."""
    import clp_sim
    import io
    import contextlib
    sim = clp_sim.CircuitoCLP(path)
    modelo = ModeloLogico(spec) if (spec and spec.get("layout")) else None
    buf = io.StringIO()
    falhas = []
    with contextlib.redirect_stdout(buf):
        ok_g = clp_sim.teste_casos(path, testes, sim)
    for cs in testes:
        inval = clp_sim.chaves_invalidas(sim, cs)
        for campo, k in inval:
            falhas.append({"nome": cs.get("nome", "?"), "obtido": f"chave {k!r} em '{campo}' inexistente", "status": "CHAVE", "esp": ""})
        fg, rg, _ = clp_sim.executar_caso(sim, cs)
        if fg:
            falhas.append({"nome": cs.get("nome", "?"), "obtido": "; ".join(fg), "status": rg["status"], "esp": cs.get("esperado")})
        if modelo is not None:
            fl, rl, _ = clp_sim.executar_caso(modelo, cs)
            if fl:
                falhas.append({"nome": cs.get("nome", "?") + " [modelo logico]", "obtido": "; ".join(fl),
                               "status": rl["status"], "esp": cs.get("esperado")})
            elif not fg and (rl["bobinas"], rl["lampadas"]) != (rg["bobinas"], rg["lampadas"]):
                falhas.append({"nome": cs.get("nome", "?") + " [equivalencia]",
                               "obtido": f"logico {rl['bobinas']}/{rl['lampadas']} != geometrico {rg['bobinas']}/{rg['lampadas']}",
                               "status": "DIVERGE", "esp": ""})
    texto = buf.getvalue()
    total = len(testes)
    n_ok = total - len({f["nome"].split(" [")[0] for f in falhas})
    ok = bool(total) and not falhas
    cab = f"{'PASSOU' if ok else 'FALHOU'}: {n_ok}/{total} (geometrico clp_sim" + (" + logico DSL)" if modelo else ")")
    for f in falhas:
        texto += f"  [FALHA] {f['nome']}: {f['obtido']}\n"
    return cab + "\n" + texto + f"RESULTADO: {n_ok}/{total} OK", ok, falhas, total


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    spec = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    r = construir(spec, argv[1])
    print(r["_build_raw"])
    print(r["_teste_raw"])
    for e in r["erros"] + r["geo"]["soltos_msg"]:
        print("ERRO:", e)
    for a in r["avisos"]:
        print("AVISO:", a)
    print("GATE: OK" if r["ok"] else "GATE: REPROVADO")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
