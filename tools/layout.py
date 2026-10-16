#!/usr/bin/env python3
"""Motor de layout: spec TOPOLOGICA (sem x/y) -> spec "baixa" para build_spec.py.

Uso:
  python3 tools/layout.py in.layout.json [out.spec.json]
  python3 tools/layout.py --gen-dims          # regenera tools/symbol_dims.json (usa cade_mcp)

Forma da entrada (ver docs/dsl-layout.md):
  {"titulo": "...",
   "trilhos": {"L1":14,"L2":20,"L3":26,"N":290,"x0":25,"x1":395},
   "fontes":  [{"classe":"3004","id":"X1","rotulo":"-X","fases":["L1","L2","L3"],"neutro":"N"}],
   "comando": [{"id":"m1","de":"L1","para":"N",
                "serie":[["RT1","8017","-F2"], ...],
                "ramos":[{"via":[id,classe,rot],"selo":[...],"serie":[...],
                          "carga":[...],"indica":[...]}]}],
   "potencia":[{"id":"m1","fases":["L1","L2","L3"],"neutro":"N",
                "colunas":[["Q1","6009","-Q1"], ..., ["M1","1000","-M1"]]}],
   "terra": {"id":"PE","classe":"3002","rotulo":"TERRA","neutro":"N"}}

Comando v2 (rede serie-paralelo recursiva; ver docs/dsl-layout.md): no lugar de serie/ramos,
   {"id":"c1","de":"L1","para":"N",
    "rede":{"serie":[["RT1","8017","-RT1"],
                     {"paralelo":[["S1","8000","-S1"],["S2","8000","-S2"],["selo","7000","-KM1"]]},
                     {"paralelo":[["KM1","9000","-KM1"],["H1","9008","-H1"]]}]}}
   ou "rungs":[rede,rede,...] (varios degraus). "trilhos_comando":{"nomes":["C1","C2"],
   "transformador":{"id":"T1","primario":["L1","L2"]},"fonte":{"id":"X2"}} cria outro par de
   trilhos. Nao cabendo na folha: serpentina (serie alta) / faixas amarradas (largura).

Fonte unica multi-terminal (recomendado; estampa as fases certas no app):
   "fontes": [{"id":"X1","classe":"3007","rotulo":"-X",
               "pinos":{"L1":"L1","L2":"L2","L3":"L3","N":"N","PE":"PE"}}]
   + trilho "PE" e "pe":"PE" em cada grupo de potencia (PE do motor != neutro).
"""
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
PINS = json.loads((TOOLS / "symbol_pins.json").read_text())
def _sheet():
    """Limite superior util da folha (tools/sheet.json, medido no app: docs/folha.md).
    So o MAXIMO e usado; os layouts partem do canto sup-esq ja validado visualmente."""
    try:
        d = json.loads((TOOLS / "sheet.json").read_text())
        return int(d["x_seguro_max"]), int(d["y_seguro_max"])
    except Exception:
        return 455, 295       # fallback conservador


SHEET_X, SHEET_Y = _sheet()
GAP = 20          # folga entre colunas (dx = largura_max + GAP)
PHASE_DX = 6      # distancia entre fases (pinos 1-3-5)
ROW_PITCH = 60    # distancia entre ramos (fileiras) de comando
FALLBACK_DIM = (18, 15)


def _dims():
    p = TOOLS / "symbol_dims.json"
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


DIMS = _dims()


def dim(classe):
    w, h = DIMS.get(classe, FALLBACK_DIM)
    return int(w), int(h)


def pin_off(classe, pino):
    info = PINS.get(classe, {})
    off = (info.get("pins") or {}).get(pino)
    if off is None and pino in ("A", "B"):
        off = info.get(pino)
    if off is None:
        raise ValueError(f"classe {classe} sem pino {pino}")
    return off


def _width(classe):
    """Largura efetiva: corpo ou o pino mais a direita (o que for maior)."""
    w, _ = dim(classe)
    info = PINS.get(classe, {})
    xs = [o[0] for o in (info.get("pins") or {}).values()] + \
         [info[k][0] for k in ("A", "B") if k in info]
    return max([w] + xs)


class Layout:
    def __init__(self, titulo):
        self.titulo = titulo
        self.rails = []
        self.simbolos = []
        self.conexoes = []
        self.fios = []          # segmentos manuais (rede serie-paralelo v2)
        self.ids = set()

    def sym(self, id_, classe, rotulo, x, y):
        if id_ in self.ids:
            raise ValueError(f"id duplicado: {id_}")
        self.ids.add(id_)
        self.simbolos.append({"classe": classe, "x": int(x), "y": int(y),
                              "rotulo": rotulo, "id": id_})

    def con(self, de, para):
        self.conexoes.append({"de": list(de), "para": list(para)})

    def fio(self, x1, y1, x2, y2):
        """Segmento reto manual (ignora comprimento zero e duplicatas)."""
        a, b = (int(x1), int(y1)), (int(x2), int(y2))
        if a == b:
            return
        f = {"x1": a[0], "y1": a[1], "x2": b[0], "y2": b[1]}
        if f not in self.fios and {"x1": b[0], "y1": b[1], "x2": a[0], "y2": a[1]} not in self.fios:
            self.fios.append(f)


def _t(t):
    """[id, classe, rotulo?] -> (id, classe, rotulo)"""
    if len(t) < 2:
        raise ValueError(f"simbolo invalido: {t}")
    return t[0], str(t[1]), (t[2] if len(t) > 2 else "")


def _eh_rede(blk):
    return "rede" in blk or "rungs" in blk or "degraus" in blk


def _legado_para_rede(blk):
    """bloco legado {serie, ramos:[{via,selo,serie,carga,indica}]} -> bloco com `rede` equivalente."""
    ser = [list(x) for x in blk.get("serie", [])]
    ramos = []
    for r in blk.get("ramos", []):
        s = []
        if r.get("via") and r.get("selo"):
            s.append({"paralelo": [list(r["via"]), list(r["selo"])]})
        elif r.get("via"):
            s.append(list(r["via"]))
        s += [list(x) for x in r.get("serie", [])]
        s.append({"paralelo": [list(r["carga"]), list(r["indica"])]} if r.get("indica") else list(r["carga"]))
        ramos.append({"serie": s})
    cauda = [] if not ramos else [ramos[0] if len(ramos) == 1 else {"paralelo": ramos}]
    novo = {k: v for k, v in blk.items() if k not in ("serie", "ramos")}
    novo["rede"] = {"serie": ser + cauda}
    return novo


def compilar(spec):
    """spec topologica (dict) -> spec baixa {titulo, rails, simbolos, conexoes[, fios]}.

    Comando em DUAS formas (por bloco): legada (`serie`+`ramos`, fileiras horizontais) e
    REDE serie-paralelo recursiva (`rede`/`rungs`, colunas verticais; ver _comando_rede).
    Se a forma legada nao couber na folha, os blocos legados sao traduzidos para `rede`
    (que quebra em colunas/faixas) em vez de falhar."""
    try:
        return _compilar(spec)
    except ValueError:
        legados = [i for i, b in enumerate(spec.get("comando", [])) if not _eh_rede(b)]
        if not legados:
            raise
        alt = dict(spec)
        alt["comando"] = [_legado_para_rede(b) if i in legados else b
                          for i, b in enumerate(spec["comando"])]
        try:
            return _compilar(alt)
        except ValueError:
            pass                            # devolve o erro da forma original
        raise


def _compilar(spec):
    L = Layout(spec.get("titulo", "NOVO"))
    tr = dict(spec["trilhos"])
    x0, x1 = int(tr.pop("x0", 25)), int(tr.pop("x1", 395))
    rails = {k: int(v) for k, v in tr.items()}
    ctx = _Ctx(L, rails, x0, x1)
    # trilhos de cima (fases) = metade superior; de baixo (N, PE) = metade inferior.
    meio = (min(rails.values()) + max(rails.values())) / 2
    cima = [v for v in rails.values() if v <= meio]
    y_cima = max(cima) if cima else min(rails.values())
    top0 = y_cima + 14                      # primeira linha util sob os trilhos
    ctx.top0 = top0
    blocos = spec.get("comando", [])
    tc = spec.get("trilhos_comando")
    ctx.preparar_comando(blocos, tc)        # mede redes novas, cria trilhos C*, desloca trilhos de baixo
    baixo = [v for v in rails.values() if v > meio]
    para = [b.get("para") for b in blocos if b.get("para") in rails and not _eh_rede(b)] or \
           [b.get("para") for b in blocos if b.get("para") in rails]
    y_baixo = rails[para[0]] if para else (min(baixo) if baixo else max(rails.values()))

    cursor = x0 + 5                         # proximo x livre (esquerda -> direita)

    # ---- fontes: coladas aos trilhos, em escada na faixa da esquerda ----
    fx_max = cursor
    for f in spec.get("fontes", []):
        if f.get("pinos"):
            # fonte unica multi-terminal (ex.: 3007 = L1,L2,L3,N,PE): pino -> trilho
            cl = f.get("classe", "3007")
            L.sym(f["id"], cl, f.get("rotulo", "-X"), cursor, top0)
            for pino, trilho in f["pinos"].items():
                L.con((f["id"], pino), (trilho, "rail"))
            fx_max = max(fx_max, cursor + _width(cl))
            continue
        fases = f.get("fases") or []
        for i, fase in enumerate(fases):
            sid = f["id"] if len(fases) == 1 else f"{f['id']}_{fase}"
            if len(fases) > 1 and f["id"][-1:].isdigit():
                sid = f"{f['id'][:-1]}{i + 1}"      # X1 -> X1,X2,X3
            x = cursor + 8 * i
            y = top0 + 8 * i
            L.sym(sid, f.get("classe", "3004"), f.get("rotulo", "-X"), x, y)
            L.con((sid, "A"), (fase, "rail"))
            L.con((sid, "B"), (f.get("neutro", "N"), "rail"))
            fx_max = max(fx_max, x + _width(f.get("classe", "3004")))
    cursor = fx_max + 15 if spec.get("fontes") else cursor

    # ---- fonte/transformador do par de trilhos de comando ----
    if tc:
        cursor = _fonte_comando(L, ctx, tc, cursor, top0) + 15

    # ---- comando ----
    reserva = sum(_pot_largura(pw) + GAP for pw in spec.get("potencia", []))
    for blk in blocos:
        if _eh_rede(blk):
            cursor = _comando_rede(L, ctx, blk, cursor, reserva) + 40
        else:
            cursor = _comando(L, blk, cursor, top0, y_baixo) + 40

    # ---- potencia: grupos de N colunas por fase, alinhados ----
    for pw in spec.get("potencia", []):
        cursor = _potencia(L, pw, cursor, top0) + GAP

    # ---- terra ----
    t = spec.get("terra")
    if t:
        cl = t.get("classe", "3002")
        _, h = dim(cl)
        L.sym(t.get("id", "PE"), cl, t.get("rotulo", "TERRA"),
              x0 + 35, rails[t.get("neutro", "N")] - h)
        L.con((t.get("id", "PE"), "A"), (t.get("neutro", "N"), "rail"))

    ctx.fechar()                            # ligacoes entre faixas + lista final de trilhos
    out = {"titulo": L.titulo, "rails": L.rails, "simbolos": L.simbolos,
           "conexoes": L.conexoes}
    if L.fios:
        out["fios"] = L.fios
    _check_folha(out)
    return out


def _comando(L, blk, x, y0, y_baixo):
    de, para = blk["de"], blk["para"]
    ser = [_t(s) for s in blk.get("serie", [])]
    ramos = blk.get("ramos", [])
    xcol = x
    y = y0
    if ser:
        cur = None
        for sid, cl, rot in ser:
            L.sym(sid, cl, rot, xcol, y)
            L.con((de, "rail") if cur is None else cur, (sid, "A"))
            cur = (sid, "B")
            y += dim(cl)[1] + 20
        head = cur
        y_ult = y - 20 - dim(ser[-1][1])[1]
        h_ult = dim(ser[-1][1])[1]
        y_ramos = y_ult + h_ult + 50
        xend = xcol + max(_width(c) for _, c, _ in ser)
    else:
        head = (de, "rail")
        y_ramos = y0
        xend = xcol

    # monta slots por ramo
    plano = []   # lista de listas [(papel,(id,cl,rot))]
    for r in ramos:
        sl = []
        if r.get("via"):
            sl.append(("via", _t(r["via"])))
        if r.get("selo"):
            sl.append(("selo", _t(r["selo"])))
        for s in r.get("serie", []):
            sl.append(("serie", _t(s)))
        sl.append(("carga", _t(r["carga"])))
        if r.get("indica"):
            sl.append(("indica", _t(r["indica"])))
        plano.append(sl)
    nslots = max((len(s) for s in plano), default=0)
    wmax = [max((_width(s[i][1][1]) for s in plano if i < len(s)), default=0)
            for i in range(nslots)]
    xs = []
    xc = xcol
    for i in range(nslots):
        xs.append(xc)
        xc += wmax[i] + GAP
    n = len(ramos)
    pitch = ROW_PITCH
    if n > 1:
        disp = (y_baixo - 20) - y_ramos - 15
        pitch = min(ROW_PITCH, disp // (n - 1))
        if pitch < 28:
            raise ValueError("ramos de comando nao cabem na folha")
    for k, (r, sl) in enumerate(zip(ramos, plano)):
        yy = y_ramos + k * pitch
        cur = head
        via = selo = None
        carga_par = None
        for i, (papel, (sid, cl, rot)) in enumerate(sl):
            L.sym(sid, cl, rot, xs[i], yy)
            if papel == "via":
                L.con(cur, (sid, "A"))
                via = sid
                cur = (sid, "B")
            elif papel == "selo":
                L.con((via, "A"), (sid, "A"))
                L.con((via, "B"), (sid, "B"))
            elif papel == "serie":
                L.con(cur, (sid, "A"))
                cur = (sid, "B")
            elif papel == "carga":
                L.con(cur, (sid, "A"))
                carga_par = sid
                cur = (sid, "B")
                L.con((sid, "B"), (para, "rail"))
            elif papel == "indica":
                L.con((carga_par, "A"), (sid, "A"))
                L.con((carga_par, "B"), (sid, "B"))
        xend = max(xend, xs[len(sl) - 1] + _width(sl[-1][1][1]))
    return xend


# ======================================================================================
# Rede serie-paralelo RECURSIVA (comando v2)
#
#   {"id":"c1","de":"L1","para":"N",
#    "rede": {"serie":[ ["RT1","8017","-RT1"], ["S0","8001","-S0"],
#                       {"paralelo":[ ["S1","8000","-S1"], ["S1b","8000","-S1"], ["selo","7000","-KM1"] ]},
#                       {"paralelo":[ ["KM1","9000","-KM1"], ["H1","9008","-H1"] ]} ]}}
#   "rungs": [rede, rede, ...]   (varios degraus independentes entre os mesmos trilhos)
#
# Folha = [id, classe, rotulo] de 2 terminais verticais (A em cima, B embaixo). Desenho:
# degrau = COLUNA vertical (serie desce; paralelo = ramos lado a lado, alinhados pelo topo),
# entre o trilho `de` (cima) e `para` (baixo). Cada rede eletrica (no) vira um barramento
# horizontal com verticais retas nos pinos (vertices em todo ponto de ligacao: fio so une
# fio por extremo). Pinos ligados a trilhos usam o roteador (vertice no trilho).
# Nao cabe na folha -> quebra automatica: (a) serie alta demais = serpentina em colunas;
# (b) largura demais = nova FAIXA (novo par de trilhos amarrados ao primeiro por fios).
# ======================================================================================
GN = 10           # folga vertical entre o barramento e o pino do simbolo
RUNG_GAP = 30     # entre degraus (colunas) vizinhos
CHUNK_GAP = 44    # entre colunas de um mesmo degrau quebrado em serpentina
MARGEM_X = 12     # reserva a direita da folha (rotulos)
GRADE = 6         # passo entre ramos paralelos = multiplo da grade (eixos de Par vizinhos alinham)


class _No:
    """no da rede: kind in {leaf, serie, par}."""
    __slots__ = ("kind", "kids", "sid", "cl", "rot", "pa", "pb", "na", "nb", "w", "h")

    def __init__(self, kind, kids=None):
        self.kind, self.kids = kind, kids or []


def _folha(t):
    sid, cl, rot = _t(t)
    info = PINS.get(cl)
    if info is None:
        raise ValueError(f"{sid}: classe {cl} sem geometria de pinos (tools/symbol_pins.json)")
    nomeados = info.get("pins") or {}
    if nomeados:
        if set(nomeados) == {"p1", "p2"}:
            na, nb = "p1", "p2"
        elif set(nomeados) <= {"A", "B", "p1", "p2"} and {"A", "B"} <= set(nomeados):
            na, nb = "A", "B"
        else:
            raise ValueError(f"{sid} (classe {cl}) tem {len(nomeados)} terminais ({sorted(nomeados)}); "
                             f"a rede de comando aceita so simbolos de 2 terminais (A/B)")
        pa, pb = nomeados[na], nomeados[nb]
    elif "A" in info and "B" in info:
        na, nb, pa, pb = "A", "B", info["A"], info["B"]
    else:
        raise ValueError(f"{sid} (classe {cl}) sem terminais A/B conhecidos")
    if pb[1] <= pa[1]:
        raise ValueError(f"{sid} (classe {cl}): terminais na mesma altura (A={pa}, B={pb}); "
                         f"a rede de comando precisa de simbolo vertical (A em cima, B embaixo)")
    n = _No("leaf")
    n.sid, n.cl, n.rot = sid, cl, rot
    n.pa, n.pb, n.na, n.nb = tuple(pa), tuple(pb), na, nb
    n.w, n.h = dim(cl)
    return n


def _expr(e):
    """JSON -> arvore. Folha = [id, classe, rotulo]; {"serie":[..]} / {"paralelo":[..]} aninhaveis;
    uma lista de expressoes solta = serie."""
    if isinstance(e, dict):
        chaves = [k for k in ("serie", "paralelo") if k in e]
        if len(chaves) != 1 or set(e) - {"serie", "paralelo"}:
            raise ValueError(f"expressao invalida {e}: use exatamente uma chave 'serie' ou 'paralelo'")
        kind = "serie" if chaves[0] == "serie" else "par"
        itens = e[chaves[0]]
        if not isinstance(itens, list) or not itens:
            raise ValueError(f"'{chaves[0]}' precisa de uma lista nao vazia")
        kids = []
        for it in itens:
            k = _expr(it)
            kids += k.kids if k.kind == kind else [k]      # achata serie-em-serie / paralelo-em-paralelo
        return kids[0] if len(kids) == 1 else _No(kind, kids)
    if isinstance(e, (list, tuple)):
        if 2 <= len(e) <= 3 and all(isinstance(v, str) for v in e):
            return _folha(e)
        return _expr({"serie": list(e)})
    raise ValueError(f"expressao invalida: {e!r}")


def _par_layout(kids):
    ms = [_med(k) for k in kids]
    offs, pos = [], 0
    for lw, rw, _h in ms:
        offs.append(pos + lw)
        pos += -(-(lw + rw + GAP) // GRADE) * GRADE      # passo em multiplos da grade: eixos alinhados
    total = pos - GAP
    return ms, offs, (offs[0] + offs[-1]) // 2, total


def _med(no):
    """-> (lw, rw, H): extensao a esquerda/direita do EIXO (coluna de entrada/saida) e altura
    do nivel de entrada ao de saida (barramento a barramento)."""
    if no.kind == "leaf":
        xs = [0, no.w, no.pa[0], no.pb[0]]
        lw, rw = no.pa[0] - min(xs), max(xs) - no.pa[0]
        return lw, rw, GN + max(no.h - no.pa[1], no.pb[1] - no.pa[1]) + GN
    ms = [_med(k) for k in no.kids]
    if no.kind == "serie":
        return max(m[0] for m in ms), max(m[1] for m in ms), sum(m[2] for m in ms)
    _, _, center, total = _par_layout(no.kids)
    return center, total - center, max(m[2] for m in ms)


def _folhas(no):
    if no.kind == "leaf":
        yield no
    for k in no.kids:
        yield from _folhas(k)


class _UF:
    def __init__(self):
        self.p = {}

    def find(self, a):
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def _walk(no, i, o, uf, fresh):
    """une os pinos aos nos eletricos: i = no de entrada, o = no de saida."""
    if no.kind == "leaf":
        uf.union(("p", no.sid, "A"), i)
        uf.union(("p", no.sid, "B"), o)
    elif no.kind == "serie":
        toks = [i] + [("n", next(fresh)) for _ in no.kids[:-1]] + [o]
        for k, kid in enumerate(no.kids):
            _walk(kid, toks[k], toks[k + 1], uf, fresh)
    else:
        for kid in no.kids:
            _walk(kid, i, o, uf, fresh)


def _colocar(L, no, ax, yi, yo, pp, ch):
    """posiciona o no com o EIXO em x=ax, nivel de entrada yi e de saida yo (>= yi+H).
    pp[(id,'A'|'B')] = (x, y, nivel, coluna)."""
    if no.kind == "leaf":
        x, y = ax - no.pa[0], yi + GN - no.pa[1]
        L.sym(no.sid, no.cl, no.rot, x, y)
        pp[(no.sid, "A")] = (ax, yi + GN, yi, ch)
        pp[(no.sid, "B")] = (x + no.pb[0], y + no.pb[1], yo, ch)
    elif no.kind == "serie":
        cur = yi
        for i, k in enumerate(no.kids):
            ko = yo if i == len(no.kids) - 1 else cur + _med(k)[2]
            _colocar(L, k, ax, cur, ko, pp, ch)
            cur = ko
    else:
        _, offs, center, _t_ = _par_layout(no.kids)
        left = ax - center
        for k, off in zip(no.kids, offs):
            _colocar(L, k, left + off, yi, yo, pp, ch)


def _redes(L, uf, pp, nomes, bordas, folhas):
    """desenha cada no eletrico: trilho (roteador) ou barramento manual (fios)."""
    grupos = {}
    for tok in list(uf.p):
        grupos.setdefault(uf.find(tok), []).append(tok)
    for root in sorted(grupos, key=str):
        toks = grupos[root]
        trilhos = sorted({t[1] for t in toks if t[0] == "r"})
        pins = [t for t in toks if t[0] == "p"]
        if len(trilhos) > 1:
            raise ValueError("degrau em curto: os trilhos 'de' e 'para' ficaram no mesmo no")
        if trilhos:
            for _, sid, ab in sorted(pins):
                f = folhas[sid]
                L.con((sid, f.na if ab == "A" else f.nb), (nomes[trilhos[0]], "rail"))
            continue
        ups = [pp[(s, ab)] for _, s, ab in pins if ab == "B"]
        lows = [pp[(s, ab)] for _, s, ab in pins if ab == "A"]
        if not ups or not lows:
            raise ValueError("no sem origem ou sem destino na rede (expressao incompleta)")
        lb = {u[2] for u in ups}
        la = {d[2] for d in lows}
        if len(lb) != 1 or len(la) != 1:
            raise ValueError("niveis inconsistentes na rede (bug do motor)")
        lb, la = lb.pop(), la.pop()
        if la == lb:                                           # barramento comum
            if len(ups) == 1 and len(lows) == 1 and ups[0][0] == lows[0][0]:
                L.fio(ups[0][0], ups[0][1], lows[0][0], lows[0][1])
                continue
            xs = sorted({p[0] for p in ups + lows})
            for a, b in zip(xs, xs[1:]):
                L.fio(a, lb, b, lb)
            for u in ups:
                L.fio(u[0], u[1], u[0], lb)
            for d in lows:
                L.fio(d[0], lb, d[0], d[1])
        elif la < lb:                                          # serpentina: sobe para a proxima coluna
            xm = bordas[ups[0][3]] + 18
            xu = sorted({u[0] for u in ups} | {xm})
            for a, b in zip(xu, xu[1:]):
                L.fio(a, lb, b, lb)
            for u in ups:
                L.fio(u[0], u[1], u[0], lb)
            L.fio(xm, lb, xm, la)
            xl = sorted({d[0] for d in lows} | {xm})
            for a, b in zip(xl, xl[1:]):
                L.fio(a, la, b, la)
            for d in lows:
                L.fio(d[0], la, d[0], d[1])
        else:
            raise ValueError("nivel de entrada abaixo do de saida (rede invalida)")


def _pot_largura(pw):
    """largura estimada de um grupo de potencia (reserva na faixa 0)."""
    nf = len(pw.get("fases", [])) or 3
    mx = 0
    for c in pw.get("colunas", []):
        est = _estagio(c)
        mx = max(mx, sum(max(_width(cl), PHASE_DX * (nf - 1) + 1) + GAP for _, cl, _, _ in est) - GAP)
    return mx


class _Ctx:
    """estado compartilhado: trilhos (y/extensao), faixas e amarracoes."""

    def __init__(self, L, rails, x0, x1):
        self.L, self.rails, self.x0, self.x1 = L, rails, x0, x1
        self.R = {}                 # nome -> dict do trilho (o mesmo objeto de L.rails)
        for nome, y in rails.items():
            self._novo_trilho(nome, y, x0, x1)
        self.prep = {}
        self.top0 = 0
        self.nties = 0
        self.right_ties = []        # (j, nome_anterior, nome_novo, y_ant, y_novo)

    def _novo_trilho(self, nome, y, xa, xb):
        d = {"nome": nome, "y": y, "x0": xa, "x1": xb}
        self.R[nome] = d
        self.L.rails.append(d)
        self.rails[nome] = y

    def set_y(self, nome, y):
        self.R[nome]["y"] = y
        self.rails[nome] = y

    # ---- preparacao: mede as redes, cria C*, desloca trilhos de baixo ----
    def preparar_comando(self, blocos, tc):
        L, R = self.L, self.R
        auto = set()                # trilhos de comando com y automatico
        if tc:
            nomes = tc.get("nomes") or ["C1", "C2"]
            if len(nomes) != 2:
                raise ValueError("trilhos_comando.nomes: exatamente 2 trilhos [topo, base]")
            if not (tc.get("transformador") or tc.get("fonte")):
                raise ValueError("trilhos_comando sem 'transformador' nem 'fonte': o par de trilhos ficaria "
                                 "sem alimentacao")
            self.c_nomes = nomes
            if nomes[0] not in R:
                self._novo_trilho(nomes[0], self.top0 + (30 if tc.get("transformador") else 14),
                                  self.x0, self.x0)
            if nomes[1] not in R:
                self._novo_trilho(nomes[1], -10 ** 6, self.x0, self.x0)
                auto.add(nomes[1])
        sheet_y = SHEET_Y
        for blk in blocos:
            if not _eh_rede(blk):
                continue
            for k in ("de", "para"):
                if blk.get(k) not in R:
                    raise ValueError(f"comando '{blk.get('id')}': '{k}'='{blk.get(k)}' nao e um trilho "
                                     f"(trilhos: {sorted(R)})")
            if any(k in blk for k in ("serie", "ramos")):
                raise ValueError(f"comando '{blk.get('id')}': misture 'rede'/'rungs' com 'serie'/'ramos' no "
                                 f"mesmo bloco nao e permitido (use blocos separados)")
            if "rede" in blk:
                fontes = [blk["rede"]]
            else:
                fontes = blk.get("rungs") or blk.get("degraus")
            if not isinstance(fontes, list) or not fontes:
                raise ValueError(f"comando '{blk.get('id')}': 'rungs' precisa de uma lista nao vazia de redes")
            arvores = [_expr(r) for r in fontes]
            de, para = blk["de"], blk["para"]
            ystart = max(self.top0, R[de]["y"] + 14) if R[de]["y"] > -10 ** 5 else self.top0
            yi = ystart - GN
            base_y = R[para]["y"] if para not in auto else None
            lowest = max(d["y"] for d in R.values())
            extra = (lowest - base_y) if base_y is not None else 0
            hlim = (sheet_y - 8 - extra) - yi
            rungs, hmax = [], 0
            for t in arvores:
                chunks = _quebrar(t, hlim)
                rungs.append(chunks)
                hmax = max(hmax, max(_med(c)[2] for c in chunks))
            need = yi + hmax
            if para in auto:
                if need > R[para]["y"]:
                    self.set_y(para, need)
            elif need > R[para]["y"]:
                delta, y0 = need - R[para]["y"], R[para]["y"]
                for d in R.values():
                    if d["y"] >= y0:
                        self.set_y(d["nome"], d["y"] + delta)
            self.prep[id(blk)] = {"rungs": rungs, "ystart": ystart, "yi": yi, "hmax": hmax}
        for nome in auto:
            if R[nome]["y"] < -10 ** 5:      # nenhum bloco usou: abaixo do C1
                self.set_y(nome, R[self.c_nomes[0]]["y"] + 40)
        for d in R.values():
            if d["y"] > SHEET_Y:
                raise ValueError(f"trilho {d['nome']} em y={d['y']} fora da folha (max {SHEET_Y})")

    # ---- faixas extras ----
    def y_livre(self):
        ys = [d["y"] for d in self.R.values()]
        for s in self.L.simbolos:
            ys.append(s["y"] + dim(s["classe"])[1])
        for f in self.L.fios:
            ys += [f["y1"], f["y2"]]
        return max(ys) + 16

    def fechar(self):
        """amarra as faixas: `para` pela direita (x depois de tudo), `de` ja amarrado pela esquerda."""
        if not self.right_ties:
            return
        L = self.L
        xs = [self.x1]
        for s in L.simbolos:
            xs.append(s["x"] + _width(s["classe"]))
        for d in self.R.values():
            if not any(d["nome"] in (a, b) for _, a, b, _, _ in self.right_ties):
                xs.append(d["x1"])
        for f in L.fios:
            xs += [f["x1"], f["x2"]]
        base = max(xs)
        for j, a, b, ya, yb in self.right_ties:
            xr = base + 6 + 5 * j
            if xr > SHEET_X:
                raise ValueError("amarracao das faixas fora da folha")
            for nome in (a, b):
                self.R[nome]["x1"] = max(self.R[nome]["x1"], xr)
            L.fio(xr, ya, xr, yb)


def _quebrar(no, hlim):
    """serie alta demais -> colunas (serpentina): lista de nos; senao [no]."""
    if _med(no)[2] <= hlim:
        return [no]
    if no.kind != "serie":
        raise ValueError(f"grupo paralelo com altura {_med(no)[2]} > {hlim} (limite da folha); "
                         f"nao ha como quebrar em colunas dentro de um paralelo")
    hs = [_med(k)[2] for k in no.kids]
    for k, hk in zip(no.kids, hs):
        if hk > hlim:
            raise ValueError(f"elemento aninhado alto demais ({hk} > {hlim}); simplifique a rede")
    total = sum(hs)
    ncols = -(-total // hlim)
    chunks = None
    for cap in range(-(-total // ncols), hlim + 1, 5):      # colunas equilibradas (menor cap que cabe)
        cur, atual, h, ok = [], [], 0, True
        for k, hk in zip(no.kids, hs):
            if atual and h + hk > cap:
                cur.append(atual)
                atual, h = [], 0
            atual.append(k)
            h += hk
        cur.append(atual)
        if len(cur) <= ncols:
            chunks = cur
            break
    if chunks is None:                                    # nao equilibrou: enche cada coluna ate o limite
        chunks, atual, h = [], [], 0
        for k, hk in zip(no.kids, hs):
            if atual and h + hk > hlim:
                chunks.append(atual)
                atual, h = [], 0
            atual.append(k)
            h += hk
        chunks.append(atual)
    return [c[0] if len(c) == 1 else _No("serie", c) for c in chunks]


def _fonte_comando(L, ctx, tc, x, top0):
    """transformador (3012: primario p1/p2 nos trilhos `primario`, secundario p3/p4 nos trilhos de
    comando) e/ou fonte monofasica propria (3003: L->topo, N->base). -> x final."""
    c1, c2 = ctx.c_nomes
    xmax = x
    xi = x
    x_c1, x_c2 = [], []
    tr = tc.get("transformador")
    if tr:
        cl = tr.get("classe", "3012")
        tid = tr.get("id", "T1")
        prim = tr.get("primario") or ["L1", "L2"]
        if len(prim) != 2 or any(p not in ctx.R for p in prim):
            raise ValueError(f"transformador.primario deve ter 2 trilhos existentes (trilhos: {sorted(ctx.R)})")
        L.sym(tid, cl, tr.get("rotulo", "-T1"), xi, top0)
        L.con((tid, "p1"), (prim[0], "rail"))
        L.con((tid, "p2"), (prim[1], "rail"))
        L.con((tid, "p4"), (c1, "rail"))
        L.con((tid, "p3"), (c2, "rail"))
        x_c1.append(xi + pin_off(cl, "p4")[0])
        x_c2.append(xi + pin_off(cl, "p3")[0])
        xmax = xi + _width(cl)
        xi = xmax + 12
    fo = tc.get("fonte")
    if fo:
        cl = fo.get("classe", "3003")
        fid = fo.get("id", "X2")
        L.sym(fid, cl, fo.get("rotulo", "-X2"), xi, top0)
        # padrao sem cruzamento: o pino da direita (N) vai ao trilho de cima (C1)
        mapa = fo.get("pinos") or {"L": c2, "N": c1}
        for pino, tri in mapa.items():
            if tri not in (c1, c2):
                raise ValueError(f"fonte.pinos: '{tri}' nao e trilho de comando ({c1}/{c2})")
            L.con((fid, pino), (tri, "rail"))
            (x_c1 if tri == c1 else x_c2).append(xi + pin_off(cl, pino)[0])
        xmax = max(xmax, xi + _width(cl))
    if not x_c1 or not x_c2:
        raise ValueError("trilhos_comando: os dois trilhos precisam de alimentacao")
    ctx.R[c1]["x0"] = ctx.R[c1]["x1"] = min(x_c1)
    ctx.R[c2]["x0"] = ctx.R[c2]["x1"] = min(x_c2)
    return xmax


def _comando_rede(L, ctx, blk, x, reserva):
    """degraus da rede serie-paralelo; devolve o x final da faixa 0."""
    pr = ctx.prep[id(blk)]
    de, para = blk["de"], blk["para"]
    bid = str(blk.get("id") or "c")
    rungs = pr["rungs"]

    def larg(r):
        return sum(sum(_med(c)[:2]) for c in r) + CHUNK_GAP * (len(r) - 1)

    xmax = SHEET_X - MARGEM_X
    x_faixa = ctx.x0 + 5
    lim0 = xmax - reserva - 40
    faixas, cur, k = [[]], x, 0
    for r in rungs:
        w = larg(r)
        lim = lim0 if k == 0 else xmax - 14
        if cur + w > lim:
            if k >= 1 and not faixas[k]:
                raise ValueError(f"degrau com largura {w} nao cabe nem sozinho numa faixa (max {lim - x_faixa})")
            faixas.append([])
            k += 1
            cur = x_faixa
            if cur + w > xmax - 14:
                raise ValueError(f"degrau com largura {w} nao cabe na folha ({SHEET_X})")
        faixas[k].append((r, cur))
        cur += w + RUNG_GAP
    xend0 = x
    nomes_prev = (de, para)
    j = None
    for k, items in enumerate(faixas):
        if not items:
            continue
        if k == 0:
            de_k, para_k, yi = de, para, pr["yi"]
            hk = None
        else:
            hk = max(max(_med(c)[2] for c in r) for r, _ in items)
            y_top = ctx.y_livre()
            yi = y_top + 14 - GN
            y_para = yi + hk
            if y_para > SHEET_Y - 4:
                raise ValueError(f"faixa extra nao cabe na folha (y={y_para} > {SHEET_Y}); "
                                 f"reduza a rede ou use 'rungs' em menos degraus")
            de_k, para_k = f"{de}~{bid}{k}", f"{para}~{bid}{k}"
            if j is None:                       # todas as faixas de um bloco compartilham a amarracao
                j = ctx.nties
                ctx.nties += 1
            xt = ctx.x0 - 6 - 5 * j
            if xt < 12:
                raise ValueError("blocos com faixas demais: sem espaco para as amarracoes na margem esquerda")
            ctx._novo_trilho(de_k, y_top, xt, ctx.x0)
            ctx._novo_trilho(para_k, y_para, ctx.x0, ctx.x0)
            ya = ctx.R[nomes_prev[0]]["y"]
            ctx.R[nomes_prev[0]]["x0"] = min(ctx.R[nomes_prev[0]]["x0"], xt)
            L.fio(xt, ya, xt, y_top)
            ctx.right_ties.append((j, nomes_prev[1], para_k, ctx.R[nomes_prev[1]]["y"], y_para))
            nomes_prev = (de_k, para_k)
        for r, xl in items:
            xr = _degrau(L, r, xl, yi, de_k, para_k)
            if k == 0:
                xend0 = max(xend0, xr)
            ctx.R[de_k]["x1"] = max(ctx.R[de_k]["x1"], xr + 6)
            ctx.R[para_k]["x1"] = max(ctx.R[para_k]["x1"], xr + 6)
    return xend0


def _degrau(L, chunks, x_left, yi, de_nome, para_nome):
    """posiciona um degrau (1 ou mais colunas) e desenha suas redes. -> x direito."""
    uf, fresh = _UF(), iter(range(10 ** 6))
    toks = [("r", "de")] + [("n", next(fresh)) for _ in chunks[:-1]] + [("r", "para")]
    pp, bordas, folhas, cur = {}, [], {}, x_left
    for j, no in enumerate(chunks):
        lw, rw, H = _med(no)
        _walk(no, toks[j], toks[j + 1], uf, fresh)
        _colocar(L, no, cur + lw, yi, yi + H, pp, j)
        for f in _folhas(no):
            folhas[f.sid] = f
        cur += lw + rw
        bordas.append(cur)
        cur += CHUNK_GAP
    _redes(L, uf, pp, {"de": de_nome, "para": para_nome}, bordas, folhas)
    return bordas[-1]


def _tops_bots(classe):
    """(pinos_topo, pinos_base) por fase, ordenados; motor tem so topo + PE."""
    pins = (PINS.get(classe, {}).get("pins") or {})
    if "U1" in pins:
        return [p for p in ("U1", "V1", "W1") if p in pins], [], "PE" if "PE" in pins else None
    top = [p for p in ("1", "3", "5") if p in pins]
    bot = [p for p in ("2", "4", "6") if p in pins]
    return top, bot, None


def _estagio(c):
    """item de coluna -> lista de membros [(id, classe, rotulo, ordem|None)].
    Formas: [id,cls,rot] | [id,cls,rot,{"ordem":[fases]}] | {"paralelo":[item,...]}"""
    if isinstance(c, dict):
        out = []
        for m in c["paralelo"]:
            out += _estagio(m)
        return out
    sid, cl, rot = _t(c)
    ordem = None
    if len(c) > 3 and isinstance(c[3], dict):
        ordem = c[3].get("ordem")
    return [(sid, cl, rot, ordem)]


def _potencia(L, pw, x, y0):
    """Grupo de potencia: estagios em cascata; um estagio pode ter varios contatores
    em PARALELO (ex.: reversao). Cada membro pode permutar as fases de entrada
    (`ordem`: nomes de fase na ordem dos pinos 1,3,5). Contatores em paralelo sao
    unidos por trilhos auxiliares (entrada e saida) — fios so se encontram em
    extremo, nunca em T sem junta."""
    fases = pw["fases"]
    neutro = pw.get("neutro", "N")
    estagios = [_estagio(c) for c in pw["colunas"]]
    nf = len(fases)
    pid = pw.get("id", "P")
    src = [(f, "rail") for f in fases]       # fonte de cada fase: pino (id,pino) ou trilho
    src_y = None                              # y do pino de saida do estagio anterior
    src_direto = False                        # src sao pinos de UM simbolo (id,pino)
    y = y0
    xend = x

    def mk_rails(prefixo, ys, xs_por_fase):
        nomes = []
        for i, yy in enumerate(ys):
            nm = f"{pid}_{prefixo}{i + 1}"
            xs = xs_por_fase[i]
            L.rails.append({"nome": nm, "y": yy, "x0": min(xs), "x1": max(xs)})
            nomes.append(nm)
        return nomes

    for k, est in enumerate(estagios):
        n = len(est)
        # --- posicao dos membros ---
        xs_m = []
        xc = x
        for sid, cl, rot, _o in est:
            xs_m.append(xc)
            xc += max(_width(cl), PHASE_DX * (nf - 1) + 1) + GAP
        # --- trilhos de entrada se >1 membro vem de pinos de um simbolo ---
        if n > 1 and src_direto:
            ry = [src_y + 11 + 6 * i for i in range(nf)]
            # x de cada pino de origem
            pxs = [p for p in _src_x]
            tops = {}
            for mi, (sid, cl, rot, ordem) in enumerate(est):
                top, _, _ = _tops_bots(cl)
                for pi in range(nf):
                    fi = fases.index(ordem[pi]) if ordem else pi
                    tops.setdefault(fi, []).append(xs_m[mi] + pin_off(cl, top[pi])[0])
            xs = [[pxs[i]] + tops.get(i, []) for i in range(nf)]
            nomes = mk_rails("e", ry, xs)
            for i in range(nf):
                L.con((src[i][0], src[i][1]), (nomes[i], "rail"))
            src = [(nm, "rail") for nm in nomes]
            src_direto = False
            y = ry[-1] + 10
        # --- coloca membros ---
        ult_bots = []
        for mi, (sid, cl, rot, ordem) in enumerate(est):
            top, bot, pe = _tops_bots(cl)
            if len(top) < nf:
                raise ValueError(f"{sid} ({cl}) tem {len(top)} pinos de topo < {nf} fases")
            L.sym(sid, cl, rot, xs_m[mi], y)
            for pi in range(nf):
                fi = fases.index(ordem[pi]) if ordem else pi
                s = src[fi]
                L.con((s[0], s[1]), (sid, top[pi]))
            if pe:
                L.con((sid, pe), (pw.get("pe", neutro), "rail"))
            ult_bots.append((sid, cl, bot))
            xend = max(xend, xs_m[mi] + max(_width(cl), PHASE_DX * (nf - 1) + 1))
        h = max(dim(cl)[1] for _, cl, _, _ in est)
        bots = ult_bots[0][2]
        if not bots:
            break                              # motor: fim da cascata
        # --- saida do estagio ---
        yb = y + pin_off(est[0][1], bots[0])[1]
        if n == 1:
            sid = est[0][0]
            src = [(sid, bots[i]) for i in range(nf)]
            src_direto = True
            _src_x[:] = [xs_m[0] + pin_off(est[0][1], bots[i])[0] for i in range(nf)]
            src_y = yb
            y += h + 20
        else:
            ry = [yb + 11 + 6 * i for i in range(nf)]
            xs = [[xs_m[mi] + pin_off(cl, b[i])[0] for mi, (_s, cl, b) in enumerate(ult_bots)]
                  for i in range(nf)]
            # o proximo estagio (alinhado ao 1o membro) tambem toca o trilho
            xs = [v + [xs_m[0] + PHASE_DX * i] for i, v in enumerate(xs)]
            nomes = mk_rails("s", ry, xs)
            for mi, (sid, cl, b) in enumerate(ult_bots):
                for i in range(nf):
                    L.con((sid, b[i]), (nomes[i], "rail"))
            src = [(nm, "rail") for nm in nomes]
            src_direto = False
            y = ry[-1] + 10
    return xend


_src_x = []


def _check_folha(spec):
    boxes = []
    for s in spec["simbolos"]:
        w, h = dim(s["classe"])
        w = _width(s["classe"])
        b = (s["x"], s["y"], s["x"] + w, s["y"] + h)
        if b[2] > SHEET_X or b[3] > SHEET_Y:
            raise ValueError(f"{s['id']} fora da folha: {b} (max {SHEET_X}x{SHEET_Y})")
        for o_id, o in boxes:
            if b[0] < o[2] and o[0] < b[2] and b[1] < o[3] and o[1] < b[3]:
                raise ValueError(f"sobreposicao: {s['id']} x {o_id}")
        boxes.append((s["id"], b))
    for r in spec.get("rails", []):
        if r["y"] > SHEET_Y or r["x1"] > SHEET_X:
            raise ValueError(f"trilho {r['nome']} fora da folha: y={r['y']} x1={r['x1']} "
                             f"(max {SHEET_X}x{SHEET_Y})")
    for f in spec.get("fios", []):
        if max(f["x1"], f["x2"]) > SHEET_X or max(f["y1"], f["y2"]) > SHEET_Y:
            raise ValueError(f"fio fora da folha: {f}")


def gen_dims():
    sys.path.insert(0, str(TOOLS))
    import cade_mcp as C
    _, protos, _, _ = C._lib()
    out = {}
    for k, p in protos.items():
        try:
            out[k] = [int(p["nums"][14]), int(p["nums"][15])]
        except (ValueError, IndexError):
            pass
    (TOOLS / "symbol_dims.json").write_text(json.dumps(out, sort_keys=True))
    print(f"{len(out)} classes -> tools/symbol_dims.json")


def main(argv):
    if argv and argv[0] == "--gen-dims":
        gen_dims()
        return 0
    if not argv:
        print(__doc__)
        return 2
    spec = json.loads(Path(argv[0]).read_text())
    low = compilar(spec.get("layout", spec))
    low.setdefault("titulo", spec.get("titulo", "NOVO"))
    txt = json.dumps(low, indent=1, ensure_ascii=False)
    if len(argv) > 1:
        Path(argv[1]).write_text(txt)
    else:
        print(txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
