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
SHEET_X, SHEET_Y = 455, 295
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
        self.ids = set()

    def sym(self, id_, classe, rotulo, x, y):
        if id_ in self.ids:
            raise ValueError(f"id duplicado: {id_}")
        self.ids.add(id_)
        self.simbolos.append({"classe": classe, "x": int(x), "y": int(y),
                              "rotulo": rotulo, "id": id_})

    def con(self, de, para):
        self.conexoes.append({"de": list(de), "para": list(para)})


def _t(t):
    """[id, classe, rotulo?] -> (id, classe, rotulo)"""
    if len(t) < 2:
        raise ValueError(f"simbolo invalido: {t}")
    return t[0], str(t[1]), (t[2] if len(t) > 2 else "")


def compilar(spec):
    """spec topologica (dict) -> spec baixa {titulo, rails, simbolos, conexoes}."""
    L = Layout(spec.get("titulo", "NOVO"))
    tr = dict(spec["trilhos"])
    x0, x1 = int(tr.pop("x0", 25)), int(tr.pop("x1", 395))
    rails = {k: int(v) for k, v in tr.items()}
    for nome, y in rails.items():
        L.rails.append({"nome": nome, "y": y, "x0": x0, "x1": x1})
    # trilhos de cima (fases) = metade superior; de baixo (N, PE) = metade inferior.
    # y_baixo = trilho "para" do comando (neutro), senao o mais alto da metade inferior.
    meio = (min(rails.values()) + max(rails.values())) / 2
    cima = [v for v in rails.values() if v <= meio]
    baixo = [v for v in rails.values() if v > meio]
    y_cima = max(cima) if cima else min(rails.values())
    para = [b.get("para") for b in spec.get("comando", []) if b.get("para") in rails]
    y_baixo = rails[para[0]] if para else (min(baixo) if baixo else max(rails.values()))
    top0 = y_cima + 14                      # primeira linha util sob os trilhos

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

    # ---- comando ----
    for blk in spec.get("comando", []):
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

    out = {"titulo": L.titulo, "rails": L.rails, "simbolos": L.simbolos,
           "conexoes": L.conexoes}
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
