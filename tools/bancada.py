#!/usr/bin/env python3
"""Bancada de teste por classe: prova, no app real, o comportamento que o RE declara para cada item da paleta.

Etapas (independentes):
  python3 tools/bancada.py --gerar                 # escreve out/bancada/*.cad (sem Wine)
  python3 tools/bancada.py --netlist               # roda o netlist_sim nos mesmos casos (sem Wine)
  python3 tools/bancada.py --app [arquivo ...]     # roda no app (Wine, UM por vez); grava docs/bancada-resultados.json
  python3 tools/bancada.py --relatorio             # gera docs/cobertura.md (+ verificado_app em classes-papeis.json)

Ideia: micro-circuitos "fonte -> [elemento sob teste] -> LAMPADA 9008 -> N". A lampada acende <=> o elemento
conduz. Varios elementos por arquivo (um ciclo de app custa ~50 s). Contatos comandados ganham uma bobina de
MESMO rotulo acionada por um botao NA; botoes/fins de curso/sensores sao segurados (um ponteiro so);
interruptores/disjuntores/fusiveis/seletores sao clicados. O ESPERADO vem de docs/classes-papeis.json (RE),
NUNCA do netlist_sim. Divergencia app x RE vira correcao do campo semantico + secao 11.7 do re-engenharia.

Leitura: lampada/carga acesa = pixels vermelhos puros (app_sim). Classes sem expectativa no RE entram como
SONDAS (resultado "observado", nao "ok"). O que a imagem nao distingue fica "nao verificado".
"""
import json
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

PAPEIS_JSON = ROOT / "docs" / "classes-papeis.json"
BIN_JSON = ROOT / "docs" / "pinos-binario.json"
RESULTADOS = ROOT / "docs" / "bancada-resultados.json"
COBERTURA = ROOT / "docs" / "cobertura.md"
SAIDA = ROOT / "out" / "bancada"
DATA = "2026-10-15"

# --------------------------------------------------------------------------- catalogo do RE

_CAT = {}


def catalogo():
    if not _CAT:
        raw = json.loads(PAPEIS_JSON.read_text())
        _CAT["papeis"] = {k: v for k, v in raw.items() if not k.startswith("_")}
        b = json.loads(BIN_JSON.read_text())["classes"]
        _CAT["bin"] = {k: {n: tuple(o) for n, o in v["pins"].items()} for k, v in b.items()}
    return _CAT


def papel(cid):
    return catalogo()["papeis"].get(str(cid), {})


def pinos_bin(cid):
    return catalogo()["bin"].get(str(cid), {})


def _ordem(n):
    return int(n[1:]) if n[1:].isdigit() else 0


def mapa_pinos(cid):
    """{nome do RE: pN do binario} pela ordem; None se tamanhos/duplicatas impedem (ex.: 6015)."""
    nomes = papel(cid).get("pinos") or []
    pn = list(pinos_bin(cid))              # ordem de desenho (insercao do JSON)
    if not nomes or len(nomes) != len(pn) or len(set(nomes)) != len(nomes):
        return None
    return dict(zip(nomes, pn))


def _estado_fecha(cond, estado):
    if cond == "sempre":
        return True
    if cond and cond.startswith("estado=="):
        try:
            return int(cond.split("==")[1]) == estado
        except ValueError:
            return False
    return False


def pares_fechados(cid, estado):
    """Pares de pinos (pN) que conduzem no `estado`, derivados do campo `contatos` do RE."""
    mp = mapa_pinos(cid)
    out = []
    for c in papel(cid).get("contatos") or []:
        a, b = c["pinos"][:2]
        if mp and a in mp and b in mp and _estado_fecha(c.get("fecha_quando"), estado):
            out.append((mp[a], mp[b]))
    return out


def tem_modelo_contatos(cid):
    return bool(mapa_pinos(cid) and papel(cid).get("contatos"))


def lampadas_acesas(cid, estado):
    """Pinos de BASE (pN) alimentados quando TODOS os pinos de topo estao em L e cada base tem uma lampada."""
    pins = pinos_bin(cid)
    topo_y = min(dy for dx, dy in pins.values())
    topo = {n for n, (dx, dy) in pins.items() if dy == topo_y}
    ligado = set(topo)
    for _ in range(len(pins)):
        for a, b in pares_fechados(cid, estado):
            if a in ligado or b in ligado:
                ligado |= {a, b}
    return {n for n in ligado if n not in topo}


def eh_temporizado(cid):
    return str(papel(cid).get("papel", "")).startswith("contato_temporizado")


def acende_par(a, b):
    """Carga energizada do RE (§11.3): (fase,N), (N,fase), (fase_i,fase_j i!=j), (+,-), (-,+), (+,N)."""
    if not a or not b or a == b or "P" in (a, b):
        return False
    fases = set("123")
    if a in fases and b in fases:
        return True
    if (a in fases and b == "N") or (b in fases and a == "N"):
        return True
    return {a, b} in ({"+", "-"}, {"+", "N"})


FASE = {"L": "1", "L1": "1", "L2": "2", "L3": "3", "N": "N", "PE": "P"}


def char_pino(cid, nome_re):
    if cid == "3008":
        return "+"
    if cid == "3009":
        return "-"
    if cid == "3010":
        return "+" if nome_re == "p1" else "-"
    return FASE.get(nome_re)


# --------------------------------------------------------------------------- prototipos / emissao

_LIB = {}


def _lib():
    if not _LIB:
        import cade_mcp
        h, protos, f, w = cade_mcp._lib()
        _LIB.update(header=h, protos=protos, footer=f, wire=w, mod=cade_mcp)
    return _LIB


def classes_geraveis():
    """Classes que o gerador (cad_build) aceita = ha prototipo no acervo/corpus."""
    return set(_lib()["protos"])


def tem_prototipo(cid):
    P = _lib()["protos"]
    return cid in P and len(P[cid]["nums"]) >= 23


# classe sem prototipo -> classe da mesma familia de onde clonar a entidade (10 rotulos / 23 numeros)
CLONE = {"7003": "7002", "7008": "7004", "7009": "7005", "7010": "7006", "7011": "7007", "7012": "7004",
         "8020": "8003", "8021": "8002", "8022": "8002", "9001": "9000", "9002": "9000", "9014": "9000",
         "9015": "9004", "9009": "9008", "9010": "9008", "9011": "9008", "9012": "9008", "9013": "9008",
         "5009": "5008", "1055": "1054"}


def proto(cid):
    """(labels, nums, sintetico). Sem prototipo clona a da mesma familia."""
    P = _lib()["protos"]
    src, sint = cid, False
    if cid not in P or len(P[cid]["nums"]) < 23:     # ausente ou prototipo mal lido do acervo
        src = CLONE.get(cid) or ("7000" if len(pinos_bin(cid)) <= 2 else "7002")
        if src not in P or len(P[src]["nums"]) < 23:
            raise KeyError(f"sem prototipo para {cid}")
        sint = True
    p = P[src]
    return list(p["labels"]), list(p["nums"]), sint


def caixa(cid, nums_proto, sint):
    """Caixa de selecao (dx,dy,w,h): a do prototipo (orientacao 0) ou deduzida dos pinos."""
    pins = pinos_bin(cid)
    if not sint and nums_proto[17] == "0":
        return nums_proto[12:16]
    xs = [dx for dx, dy in pins.values()] or [0]
    ys = [dy for dx, dy in pins.values()] or [0]
    return [str(-12), str(min(ys) - 3), str(max(xs) + 6), str(max(ys) - min(ys) + 6)]


class Sym:
    def __init__(self, ident, classe, x, y, rotulo, extra=None):
        self.id, self.classe, self.x, self.y = ident, str(classe), int(x), int(y)
        self.rotulo, self.extra = rotulo, extra or {}

    def pino(self, nome):
        dx, dy = pinos_bin(self.classe)[nome]
        return (self.x + dx, self.y + dy)

    @property
    def centro(self):
        pts = [self.pino(n) for n in pinos_bin(self.classe)] or [(self.x, self.y)]
        return ((min(p[0] for p in pts) + max(p[0] for p in pts)) / 2,
                (min(p[1] for p in pts) + max(p[1] for p in pts)) / 2)


class Desenho:
    def __init__(self):
        self.simbolos, self.fios, self.ids = [], [], {}

    def sym(self, ident, classe, x, y, rotulo="", extra=None):
        if ident in self.ids:
            raise ValueError(f"id duplicado: {ident}")
        s = Sym(ident, classe, x, y, rotulo, extra)
        self.ids[ident] = s
        self.simbolos.append(s)
        return s

    def fio(self, a, b):
        a, b = (int(a[0]), int(a[1])), (int(b[0]), int(b[1]))
        if a != b and (a, b) not in self.fios and (b, a) not in self.fios:
            self.fios.append((a, b))

    def poly(self, *pts):
        for a, b in zip(pts, pts[1:]):
            self.fio(a, b)

    def emitir(self, path):
        L = _lib()
        ents = []
        for a, b in self.fios:
            n = list(L["wire"]["nums"])
            n[8], n[9], n[10], n[11] = (str(v) for v in (a[0], a[1], b[0], b[1]))
            for k in range(8):
                n[k] = "0"
            ents.append({"id": "4000", "labels": L["wire"]["labels"], "nums": n})
        for s in self.simbolos:
            labs, nums, sint = proto(s.classe)
            box = caixa(s.classe, nums, sint)
            n = list(nums)
            for k in range(6):
                n[k] = "1" if k < len(pinos_bin(s.classe)) else "0"
            n[8], n[9], n[10], n[11] = str(s.x), str(s.y), "0", "0"
            n[12], n[13], n[14], n[15] = box
            n[16], n[17], n[21], n[22] = "0", "0", "0", "0"      # orientacao 0 = tabela de pinos do binario
            if sint:
                labs = [""] * len(labs)
                for i, nm in enumerate((papel(s.classe).get("pinos") or [])[:6]):
                    labs[2 + i] = "" if (nm[0] == "p" and nm[1:].isdigit()) else nm
            labs[0] = s.rotulo
            for k, v in s.extra.items():
                labs[int(k)] = str(v)
            ents.append({"id": s.classe, "labels": labs, "nums": n})
        body = "#".join(f"*{i}*{e['id']}#" + "#".join(e["labels"]) + "#*" + "*".join(e["nums"])
                        for i, e in enumerate(ents))
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(("CADe_SIMU" + body + "#" + L["footer"]).encode("latin1"))
        try:
            code, out = L["mod"]._run("validate", str(path))
        except FileNotFoundError:                    # cade_cli nao compilado: nao bloqueia a geracao
            return True, "sem cade_cli (validate ignorado)"
        return code == 0, out


# --------------------------------------------------------------------------- arquivo de bancada

PASSO = 24                 # distancia entre colunas de lampada
RAIL_L, RAIL_N = (20, 125), (160, 265)      # y dos trilhos L / N nas duas linhas
X0, X1 = 70, 440           # faixa util em x (as fontes L/N ficam em x=30)
YT = 12                    # queda do trilho L ao pino de topo


class Arquivo:
    """Um .cad de bancada: desenho + celulas (elemento sob teste + suas lampadas) + casos."""

    def __init__(self, nome, titulo=""):
        self.nome, self.titulo = nome, titulo
        self.d = Desenho()
        self.celulas = []
        self.lampadas = {}       # rotulo -> Sym (lampada 9008 ou a propria carga lida por cor)
        self.motores = []        # Sym lidos por enchimento
        self.casos = []
        self.linha, self.x = 0, X0
        self.taps = {}           # (linha, 0=L|1=N) -> {x}
        self.trilhos = True
        self.n = {"H": 0, "D": 0, "S": 0, "K": 0, "X": 0}
        self.classes = set()
        self.sinteticas = set()
        self.linhas = {0}

    # -- util
    def ident(self, p):
        self.n[p] += 1
        return f"{p}{self.n[p]}"

    @property
    def rl(self):
        return RAIL_L[self.linha]

    @property
    def rn(self):
        return RAIL_N[self.linha]

    def tap(self, tr, x):
        self.taps.setdefault((self.linha, tr), set()).add(int(x))

    def reservar(self, largura):
        if self.x + largura > X1:
            if self.linha >= 1:
                return False
            self.linha, self.x = 1, X0
            self.linhas.add(1)
            if self.x + largura > X1:
                return False
        return True

    def lampada(self, x, y):
        i = self.ident("H")
        s = self.d.sym(i, "9008", x, y, f"-{i}")
        self.lampadas[s.rotulo] = s
        self.classes.add("9008")
        return s

    def _usa(self, cid):
        self.classes.add(cid)
        if proto(cid)[2]:
            self.sinteticas.add(cid)

    # -- celulas
    @staticmethod
    def largura_dut(cid):
        pins = pinos_bin(cid)
        topo_y = min(dy for dx, dy in pins.values())
        n = len([1 for dx, dy in pins.values() if dy > topo_y]) or 1
        xs = [dx for dx, dy in pins.values()]
        return max(PASSO * n, max(xs) - min(xs) + 18) + 6

    def add_dut(self, cid, rotulo, ctrl, tipo, ident=None, extra=None):
        """Topo(s) em L; cada pino de base -> lampada -> N. None se nao coube."""
        pins = pinos_bin(cid)
        topo_y = min(dy for dx, dy in pins.values())
        topo = sorted((n for n, (dx, dy) in pins.items() if dy == topo_y), key=lambda n: pins[n][0])
        base = sorted((n for n, (dx, dy) in pins.items() if dy > topo_y), key=lambda n: (pins[n][0], pins[n][1]))
        if not base:
            raise ValueError(f"{cid}: sem pinos de base")
        if not self.reservar(self.largura_dut(cid)):
            return None
        ident = ident or self.ident("D")
        xmin = min(dx for dx, dy in pins.values())
        s = self.d.sym(ident, cid, self.x - xmin, self.rl + YT, rotulo, extra)
        for n in topo:
            px, py = s.pino(n)
            self.d.fio((px, self.rl), (px, py))
            self.tap(0, px)
        ybase = max(s.pino(n)[1] for n in base)
        k = len(base)
        lamps = {}
        for j, n in enumerate(base):
            px, py = s.pino(n)
            xj = self.x + PASSO * j
            ylev = ybase + 6 + 3 * (k - 1 - j)
            yl = ybase + 6 + 3 * k + 8
            lamp = self.lampada(xj, yl)
            self.d.poly((px, py), (px, ylev), (xj, ylev), (xj, yl))
            self.d.fio((xj, yl + 12), (xj, self.rn))
            self.tap(1, xj)
            lamps[n] = lamp.rotulo
        self.celulas.append({"tipo": tipo, "classe": cid, "id": ident, "rotulo": rotulo, "ctrl": ctrl,
                             "lamps": lamps, "sym": s})
        self._usa(cid)
        self.x += self.largura_dut(cid)
        return s

    def add_comando(self, rotulo, classe="9000", extra=None, botao="8000"):
        """Botao NA -> bobina/temporizador de `rotulo` -> N. Os contatos de mesmo rotulo leem o estado."""
        if not self.reservar(40):
            return None
        ib, ik = self.ident("S"), self.ident("K")
        rb = f"-{ib}"
        b = self.d.sym(ib, botao, self.x, self.rl + YT, rb)
        self.d.fio((self.x, self.rl), b.pino("p1"))
        self.tap(0, self.x)
        k = self.d.sym(ik, classe, self.x, self.rl + YT + 12 + 8, rotulo, extra)
        self.d.fio(b.pino("p2"), k.pino("p1"))
        self.d.fio(k.pino("p2"), (self.x, self.rn))
        self.tap(1, self.x)
        self._usa(botao)
        self._usa(classe)
        self.celulas.append({"tipo": "comando", "classe": classe, "id": ik, "rotulo": rotulo, "ctrl": rotulo,
                             "botao": ib, "lamps": {}, "sym": k, "rotulo_botao": rb})
        self.x += 40
        return b, k

    def add_carga(self, cid, rotulo, pino_topo=None, pino_base=None, tipo="carga"):
        """Carga direta L -> carga -> N lida pela cor do proprio simbolo (bobina, lampada, sinalizador...)."""
        pins = pinos_bin(cid)
        topo = pino_topo or min(pins, key=lambda n: (pins[n][1], pins[n][0]))
        base = pino_base or max(pins, key=lambda n: (pins[n][1], pins[n][0]))
        w = max(dx for dx, dy in pins.values()) - min(dx for dx, dy in pins.values()) + 26
        if not self.reservar(w):
            return None
        ident = self.ident("D")
        xmin = min(dx for dx, dy in pins.values())
        s = self.d.sym(ident, cid, self.x - xmin + 6, self.rl + YT, rotulo)
        self.d.fio((s.pino(topo)[0], self.rl), s.pino(topo))
        self.tap(0, s.pino(topo)[0])
        self.d.fio(s.pino(base), (s.pino(base)[0], self.rn))
        self.tap(1, s.pino(base)[0])
        self.lampadas[rotulo] = s
        self.celulas.append({"tipo": tipo, "classe": cid, "id": ident, "rotulo": rotulo, "ctrl": None,
                             "lamps": {"p1": rotulo}, "sym": s, "pinos": (topo, base)})
        self._usa(cid)
        self.x += w
        return s

    def add_fonte(self, fontes, lampadas, nome):
        """fontes: [(classe, dx)]; lampadas: [('X1.L1','X1.N'), ...] entre trilhos locais adjacentes."""
        # pinos e posicoes relativas
        rel, ids = {}, []
        for i, (cid, dx) in enumerate(fontes):
            ident = f"X{i + 1}"
            ids.append(ident)
            for nm, pn in (mapa_pinos(cid) or {}).items():
                rel[f"{ident}.{nm}"] = (dx + pinos_bin(cid)[pn][0], cid, nm)
        usados = []
        for a, b in lampadas:
            for p in (a, b):
                if p not in usados:
                    usados.append(p)
        usados.sort(key=lambda p: -rel[p][0])
        xmaxp = max(rel[p][0] for p in usados)
        largura = xmaxp + 20 + PASSO * len(lampadas) + 14
        if not self.reservar(largura):
            return None
        xs, y0 = self.x, self.rl
        pos = {}
        srcs = {}
        for i, (cid, dx) in enumerate(fontes):
            ident = self.ident("X")
            s = self.d.sym(ident, cid, xs + dx, y0, f"-{ident}")
            srcs[ids[i]] = s
            self._usa(cid)
        for p in usados:
            _, cid, nm = rel[p]
            sid = p.split(".")[0]
            pos[p] = (srcs[sid].pino(mapa_pinos(cid)[nm]), char_pino(cid, nm))
        rail_y = {p: y0 + 10 + 24 * i for i, p in enumerate(usados)}
        taps = {p: {pos[p][0][0]} for p in usados}
        xr = xs + xmaxp + 20
        info = []
        for j, (a, b) in enumerate(lampadas):
            ia, ib = usados.index(a), usados.index(b)
            if abs(ia - ib) != 1:
                raise ValueError(f"{nome}: {a}-{b} nao sao trilhos adjacentes")
            cima, baixo = (a, b) if ia < ib else (b, a)
            xj = xr + PASSO * j
            lamp = self.lampada(xj, rail_y[cima] + 4)
            self.d.fio((xj, rail_y[cima]), (xj, rail_y[cima] + 4))
            self.d.fio((xj, rail_y[cima] + 16), (xj, rail_y[baixo]))
            taps[cima].add(xj)
            taps[baixo].add(xj)
            info.append((lamp.rotulo, cima, baixo))
        for p in usados:
            (px, py), _ = pos[p]
            self.d.fio((px, py), (px, rail_y[p]))
            xt = sorted(taps[p])
            for u, v in zip(xt, xt[1:]):
                self.d.fio((u, rail_y[p]), (v, rail_y[p]))
        for rot, cima, baixo in info:
            ch = (pos[cima][1], pos[baixo][1])
            self.celulas.append({"tipo": "fonte", "classe": "9008", "id": rot, "rotulo": rot, "ctrl": None,
                                 "lamps": {"p1": rot}, "fixo": acende_par(*ch), "chars": ch, "nome": nome,
                                 "fontes": [c for c, _ in fontes], "par": (cima, baixo)})
        self.x += largura
        return info

    def add_motor(self, cid, ligacoes, fonte, rotulo, nome=None):
        """fonte: classe (3004 3 fases | 3003 L,N | 3010 +,-). ligacoes: {pino_motor(RE): pino_fonte(RE)}.
        Motor logo abaixo da fonte; liga em Z (nivel distinto por fio)."""
        mp = mapa_pinos(cid)
        w = 56
        if not self.reservar(w):
            return None
        ixs = self.ident("X")
        fs = self.d.sym(ixs, fonte, self.x, self.rl, f"-{ixs}")
        ik = self.ident("D")
        ym = self.rl + 40
        ms = self.d.sym(ik, cid, self.x, ym, rotulo)
        fmp = mapa_pinos(fonte)
        for k, (pm, pf) in enumerate(ligacoes.items()):
            a, b = fs.pino(fmp[pf]), ms.pino(mp[pm])
            if a[0] == b[0]:
                self.d.fio(a, b)
            else:
                yl = self.rl + 12 + 6 * k
                self.d.poly(a, (a[0], yl), (b[0], yl), b)
        self.motores.append(ms)
        self.lampadas[rotulo] = ms
        self.celulas.append({"tipo": "motor", "classe": cid, "id": ik, "rotulo": rotulo, "ctrl": None,
                             "lamps": {"p1": rotulo}, "sym": ms, "fonte": fonte,
                             "ligacoes": ligacoes, "nome": nome})
        self._usa(cid)
        self._usa(fonte)
        self.x += w
        return ms

    def fechar_trilhos(self):
        """Fontes L/N por linha e segmentos de trilho (vertice em cada tap)."""
        if not any(k[1] == 0 and v for k, v in self.taps.items()):
            return
        for ln in sorted(self.linhas):
            rl, rn = RAIL_L[ln], RAIL_N[ln]
            tl = self.taps.get((ln, 0), set()) | {30}
            tn = self.taps.get((ln, 1), set()) | {30}
            self.d.sym(f"XL{ln}", "3000", 30, rl, f"-XL{ln}")
            self.d.sym(f"XN{ln}", "3001", 30, rn, f"-XN{ln}")
            for tr, y in ((tl, rl), (tn, rn)):
                xs = sorted(tr)
                for u, v in zip(xs, xs[1:]):
                    self.d.fio((u, y), (v, y))
            self.classes |= {"3000", "3001"}

    def cad_path(self):
        return SAIDA / f"{self.nome}.cad"

    def gerar(self):
        self.fechar_trilhos()
        return self.d.emitir(self.cad_path())


# --------------------------------------------------------------------------- casos e esperado

class Caso:
    """passos: ('segurar', id) | ('soltar',) | ('clicar', id) | ('esperar', s) |
               ('ler', nome, estados, modo)  modo: 'verifica' | 'sonda' | ('alterna', [lampadas])
    estados: {ctrl: n} para celulas por rotulo/id; contatos temporizados leem '<ctrl>.saida'."""

    def __init__(self, nome, passos, doc="", alterna=None):
        self.nome, self.passos, self.doc = nome, passos, doc
        self.alterna = alterna          # ctrl cujas lampadas devem ser vistas acesas E apagadas (9007)


def esperado_leitura(arq, estados):
    """{lampada: bool|None} derivado so do RE (None = sem expectativa -> sonda)."""
    out = {}
    for c in arq.celulas:
        t, cid = c["tipo"], c["classe"]
        if t == "comando":
            continue
        if t == "fonte":
            out[c["rotulo"]] = bool(c["fixo"])
            continue
        if t in ("carga", "motor"):
            out[c["rotulo"]] = c.get("esperado_energizado")
            continue
        est = estados.get(f"{c['ctrl']}.saida" if eh_temporizado(cid) else c["ctrl"], 0)
        acesos = lampadas_acesas(cid, est) if (tem_modelo_contatos(cid) and est is not None) else None
        for n, lab in c["lamps"].items():
            out[lab] = (n in acesos) if acesos is not None else None
    return out


# --------------------------------------------------------------------------- execucao no app

def _lampadas_obtidas(est, arq, img=None, cal=None):
    """{rotulo: bool} por cor. Cargas/lampadas: vermelho puro; motores: vermelho ou enchimento cinza 192."""
    import app_sim as A
    import numpy as np
    pos = {(it["x"], it["y"], it["classe"]): it for it in est["simbolos"]}
    out = {}
    arr = np.asarray(img.convert("RGB")) if img is not None else None
    for rot, s in arq.lampadas.items():
        if s in arq.motores and arr is not None and cal is not None:
            (px0, py0), (px1, py1) = cal.px(s.x - 14, s.y - 2), cal.px(s.x + 32, s.y + 30)
            rect = (int(px0), int(py0), int(px1), int(py1))
            out[rot] = A._conta(arr, rect, A.RED) >= 3 or A._conta_cheio(arr, rect, A.CINZA_FILL) >= 12
            continue
        it = pos.get((s.x, s.y, s.classe))
        out[rot] = bool(it and it["ativo"])
    return out


def executar_app(arq, verbose=False, saida=None):
    """Roda os casos do arquivo no app. -> dict {executado, tempo_s, erro, casos:[{nome, leituras:[...]}]}"""
    import app_sim as A
    t0 = time.time()
    res = {"executado": False, "casos": [], "erro": None}
    app = A.AppSim(str(arq.cad_path()), saida=saida or (ROOT / "out" / "app_sim" / f"bancada_{arq.nome}"),
                   verbose=verbose)
    try:
        app.abrir()
        app.play()
        app.zoom_todo()
        app._snap_calibra("_calib0.png")
        for caso in arq.casos:
            tc = time.time()
            r = {"nome": caso.nome, "leituras": []}
            try:
                app.reiniciar()
                seg = False
                for p in caso.passos:
                    tipo = p[0]
                    if tipo in ("segurar", "clicar"):
                        s = arq.d.ids[p[1]]
                        if app.cal is None:
                            app._snap_calibra("_cal.png")
                        wx, wy = app.cal.px(*s.centro)
                        if tipo == "segurar":
                            app._clica_win(wx, wy, "down")
                            seg = True
                        else:
                            app._clica_win(wx, wy)
                            time.sleep(0.45)
                    elif tipo == "soltar":
                        app.soltar()
                        seg = False
                        time.sleep(0.3)
                    elif tipo == "esperar":
                        time.sleep(float(p[1]))
                    elif tipo == "ler":
                        time.sleep(0.5)
                        img, pth, cal = app._snap_calibra(f"{_slug(caso.nome)}_{_slug(p[1])}.png")
                        est = A.ler_estado(img, app.cad, cal)
                        ob = _lampadas_obtidas(est, arq, img, cal)
                        r["leituras"].append({"nome": p[1], "obtido": sorted(k for k, v in ob.items() if v),
                                              "t": round(time.time() - tc, 1), "screenshot": str(pth)})
                if seg:
                    app.soltar()
            except A.AppSimErro as e:
                r["erro"] = str(e)
            r["tempo_s"] = round(time.time() - tc, 1)
            res["casos"].append(r)
        res["executado"] = True
    except A.AppSimErro as e:
        res["erro"] = str(e)
    finally:
        app.fechar()
    res["tempo_s"] = round(time.time() - t0, 1)
    return res


def _slug(s):
    return "".join(c if c.isalnum() else "_" for c in str(s))[:40]


# --------------------------------------------------------------------------- definicao das bancadas

class Fila:
    """Sequencia de arquivos 'base_NN': abre outro quando o atual enche."""

    def __init__(self, base, preparar=None, sem_trilhos=False):
        self.base, self.preparar, self.arqs = base, preparar, []
        self.sem_trilhos = sem_trilhos
        self.novo()

    def novo(self):
        a = Arquivo(f"{self.base}_{len(self.arqs) + 1:02d}")
        if self.preparar:
            self.preparar(a)
        self.arqs.append(a)
        return a

    @property
    def atual(self):
        return self.arqs[-1]

    def coloca(self, fn):
        for _ in range(2):
            r = fn(self.atual)
            if r is not None:
                return r
            self.novo()
        raise RuntimeError(f"{self.base}: elemento nao cabe nem em arquivo vazio")


def _contato_cls(papeis_ok):
    return [c for c in papeis_ok if c in catalogo()["papeis"] and pinos_bin(c)]


def bancada_fontes():
    f = Fila("fontes")
    specs = [
        ("3000+3001", [("3000", 18), ("3001", 0)], [("X1.L", "X2.N")]),
        ("3003", [("3003", 0)], [("X1.N", "X1.L")]),
        ("3000+3002 (L-PE)", [("3002", 18), ("3000", 0)], [("X1.PE", "X2.L")]),
        ("3011", [("3011", 0)], [("X1.PE", "X1.N"), ("X1.N", "X1.L")]),
        ("3004", [("3004", 0)], [("X1.L3", "X1.L2"), ("X1.L2", "X1.L1")]),
        ("3004 L1-L3", [("3004", 0)], [("X1.L3", "X1.L1")]),
        ("3005", [("3005", 0)], [("X1.PE", "X1.L3"), ("X1.L3", "X1.L2"), ("X1.L2", "X1.L1")]),
        ("3006", [("3006", 0)], [("X1.N", "X1.L3"), ("X1.L3", "X1.L2"), ("X1.L2", "X1.L1")]),
        ("3007", [("3007", 0)], [("X1.PE", "X1.N"), ("X1.N", "X1.L3"), ("X1.L3", "X1.L2"), ("X1.L2", "X1.L1")]),
        ("3008+3009", [("3008", 12), ("3009", 0)], [("X1.p1", "X2.p1")]),
        ("3009+3008", [("3009", 12), ("3008", 0)], [("X1.p1", "X2.p1")]),
        ("3010", [("3010", 0)], [("X1.p2", "X1.p1")]),
        ("3008+3001 (+,N)", [("3008", 12), ("3001", 0)], [("X1.p1", "X2.N")]),
    ]
    for nome, fontes, lamps in specs:
        f.coloca(lambda a, n=nome, fo=fontes, l=lamps: a.add_fonte(fo, l, n))
    for a in f.arqs:
        a.trilhos = False
        a.titulo = "Fontes (par de potenciais -> lampada)"
        a.casos = [Caso("repouso", [("ler", "repouso", {}, "verifica")])]
    return f.arqs


def _comando_prep(rotulo="-K1", classe="9000"):
    def prep(a):
        a.add_comando(rotulo, classe)
    return prep


def _casos_comandados(a):
    cmds = [c for c in a.celulas if c["tipo"] == "comando"]
    casos = [Caso("repouso", [("ler", "repouso", {c["ctrl"]: 0 for c in cmds}, "verifica")])]
    for c in cmds:
        k = c["ctrl"]
        casos.append(Caso(f"{c['rotulo_botao']} segura {k}",
                          [("segurar", c["botao"]), ("ler", f"{k} energizada", {k: 1}, "verifica"),
                           ("soltar",), ("ler", f"{k} solta", {k: 0}, "verifica")]))
    a.casos = casos


def bancada_contatos():
    """Contatos auxiliares e polos de potencia comandados por bobina 9000 de mesmo rotulo."""
    f = Fila("contatos", _comando_prep("-K1"))
    for cid in ("7000", "7001", "7002", "7003", "2000", "2001", "2002", "2006", "2008"):
        f.coloca(lambda a, c=cid: a.add_dut(c, "-K1", "-K1", "contato"))
    for a in f.arqs:
        a.titulo = "Contatos auxiliares e polos comandados por bobina 9000 (rotulo -K1)"
        _casos_comandados(a)
    return f.arqs


def _casos_momentaneos(a, prefixo="segura"):
    duts = [c for c in a.celulas if c["tipo"] == "momentaneo"]
    casos = [Caso("repouso", [("ler", "repouso", {}, "verifica")])]
    for c in duts:
        casos.append(Caso(f"{prefixo} {c['classe']} ({c['id']})",
                          [("segurar", c["id"]), ("ler", f"{c['classe']} pressionado", {c["ctrl"]: 1}, "verifica"),
                           ("soltar",), ("ler", f"{c['classe']} solto", {}, "verifica")]))
    a.casos = casos


def bancada_botoes():
    f = Fila("botoes")
    n = 0
    for cid in ("8000", "8001", "8002", "8003", "8004", "8005", "8006", "8007",
                "8012", "8013", "8014", "8015"):
        n += 1
        i = f"D{n}"
        f.coloca(lambda a, c=cid, i=i: a.add_dut(c, f"-S{i[1:]}", i, "momentaneo", ident=i))
    for a in f.arqs:
        a.titulo = "Botoes e fins de curso (segurar = estado 1)"
        _casos_momentaneos(a)
    return f.arqs


def bancada_sensores():
    """Detectores de 2 fios (pinos 1,2): momentaneos pelo RE; conducao pela lampada."""
    f = Fila("sensores")
    n = 0
    for cid, v in sorted(catalogo()["papeis"].items(), key=lambda kv: int(kv[0])):
        if not v["papel"].startswith("sensor") or not tem_modelo_contatos(cid):
            continue
        if len(pinos_bin(cid)) != 2 or (v.get("pinos") or []) != ["1", "2"]:
            continue
        n += 1
        i = f"D{n}"
        f.coloca(lambda a, c=cid, i=i: a.add_dut(c, f"-B{i[1:]}", i, "momentaneo", ident=i))
    for a in f.arqs:
        a.titulo = "Detectores 2 fios (clique segura = estado 1 segundo o RE)"
        _casos_momentaneos(a, "segura")
    return f.arqs


# ciclo de estados por clique, por classe ('alterna' = 0,1,0..; None = sem expectativa de ciclo)
CICLO3 = {"8020", "8021"}
ALTERNADORES = ["8008", "8009", "8010", "8011", "2003", "2004", "2005", "2007",
                "5000", "5001", "5002", "5003", "5004", "5005", "5006", "5007", "5008", "5009",
                "6000", "6001", "6002", "6003", "6004", "6005", "6006", "6008", "6009", "6010", "6011", "6012",
                "6013", "6014", "8020", "8021", "8022"]


def estado_apos(cid, n):
    return n % 3 if cid in CICLO3 else n % 2


def bancada_alternadores(classes=None):
    f = Fila("alternadores")
    n = 0
    for cid in classes or ALTERNADORES:
        n += 1
        i = f"D{n}"
        f.coloca(lambda a, c=cid, i=i: a.add_dut(c, f"-Q{i[1:]}", i, "alterna", ident=i))
    for a in f.arqs:
        a.titulo = "Interruptores, seccionadores, fusiveis, disjuntores e seletores (clique alterna)"
        duts = [c for c in a.celulas if c["tipo"] == "alterna"]
        passos = []
        casos = [Caso("repouso", [("ler", "repouso", {c["ctrl"]: 0 for c in duts}, "verifica")])]
        for k in (1, 2, 3):
            passos += [("clicar", c["id"]) for c in duts]
            passos.append(("ler", f"apos {k} clique(s)",
                           {c["ctrl"]: estado_apos(c["classe"], k) for c in duts}, "verifica"))
        casos.append(Caso("cliques sucessivos (todos)", passos))
        a.casos = casos
    return f.arqs


def bancada_termico():
    a = Arquivo("termico_01", "Rele termico 6007 e contatos 8016..8019 (rotulo -F1) + 8017 com outro rotulo")
    a.add_dut("6007", "-F1", "-F1", "termico", ident="F")
    for cid in ("8016", "8017", "8018", "8019"):
        a.add_dut(cid, "-F1", "-F1", "contato")
    a.add_dut("8017", "-F9", "-F9", "contato")          # rotulo diferente: nao acompanha o disparo
    a.casos = [
        Caso("repouso", [("ler", "repouso", {"-F1": 0, "-F9": 0}, "verifica")]),
        Caso("disparo por clique no 6007", [("clicar", "F"), ("ler", "disparado", {"-F1": 1, "-F9": 0}, "verifica"),
                                            ("clicar", "F"), ("ler", "rearmado", {"-F1": 0, "-F9": 0}, "verifica")]),
    ]
    return [a]


def bancada_temporizadores(T=4):
    """9004/9005/9006/9007 com contatos de mesmo rotulo (instantaneo 7000 + temporizados). T s (unidade '0')."""
    f = Fila("temporizadores")
    extra = {4: "0", 5: str(T)}
    grupos = [("9004", "-KT1", ("7004", "7005", "7006", "7007")),
              ("9005", "-KT2", ("7008", "7009", "7010", "7011")),
              ("9006", "-KT3", ("7012", "7013", "7014", "7015")),
              ("9007", "-KT4", ("7004", "7005"))]
    for cid, rot, contatos in grupos:
        # o grupo inteiro tem de caber na mesma linha/arquivo
        larg = 40 + sum(Arquivo.largura_dut(c) for c in contatos) + Arquivo.largura_dut("7000")
        a = f.atual
        if not a.reservar(larg):
            a = f.novo()
        a.add_comando(rot, cid, extra=extra)
        a.add_dut("7000", rot, rot, "contato")
        for c in contatos:
            a.add_dut(c, rot, rot, "contato")
    for a in f.arqs:
        a.titulo = f"Temporizadores 9004..9007 (T={T} s)"
        cmds = [c for c in a.celulas if c["tipo"] == "comando"]
        casos = []
        base = {c["ctrl"]: 0 for c in cmds}
        base.update({f"{c['ctrl']}.saida": 0 for c in cmds})
        casos.append(Caso("repouso", [("ler", "repouso", dict(base), "verifica")]))
        for c in cmds:
            k, ib, cid = c["ctrl"], c["botao"], c["classe"]
            on, off = dict(base), dict(base)
            if cid == "9004":      # ON-delay
                passos = [("segurar", ib), ("esperar", 0.4),
                          ("ler", "antes de T", {**base, k: 1, f"{k}.saida": 0}, "verifica"),
                          ("esperar", T + 4),
                          ("ler", "apos T", {**base, k: 1, f"{k}.saida": 1}, "verifica"),
                          ("soltar",), ("esperar", 0.6),
                          ("ler", "desenergizado", {**base}, "verifica")]
            elif cid == "9005":    # OFF-delay
                passos = [("segurar", ib), ("esperar", 0.4),
                          ("ler", "energizado", {**base, k: 1, f"{k}.saida": 1}, "verifica"),
                          ("soltar",), ("esperar", 0.2),
                          ("ler", "solto (dentro de T)", {**base, k: 0, f"{k}.saida": 1}, "verifica"),
                          ("esperar", T + 4),
                          ("ler", "apos T", {**base}, "verifica")]
            elif cid == "9006":    # ON+OFF delay
                passos = [("segurar", ib), ("esperar", 0.4),
                          ("ler", "antes de T", {**base, k: None, f"{k}.saida": 0}, "verifica"),
                          ("esperar", T + 4),
                          ("ler", "apos T", {**base, k: None, f"{k}.saida": 1}, "verifica"),
                          ("soltar",), ("esperar", 0.2),
                          ("ler", "solto (dentro de T)", {**base, k: None, f"{k}.saida": 1}, "verifica"),
                          ("esperar", T + 4),
                          ("ler", "apos T solto", {**base, k: None}, "verifica")]
            else:                  # 9007 intermitente: so observa se alterna
                passos = [("segurar", ib)]
                for j in range(8):
                    passos += [("esperar", 1.0), ("ler", f"amostra {j}", {**base, k: None, f"{k}.saida": None},
                                                  "sonda")]
                passos.append(("soltar",))
            casos.append(Caso(f"{cid} {k}", passos, alterna=k if cid == "9007" else None))
        a.casos = casos
    return f.arqs


def bancada_bobinas():
    """Bobinas alternativas (9014, 9002) comandando contato 7000 de mesmo rotulo (pela lampada)."""
    f = Fila("bobinas")
    for i, cid in enumerate(("9014", "9002", "9015"), 1):
        rot = f"-KB{i}"
        a = f.atual
        if not a.reservar(40 + Arquivo.largura_dut("7000") + Arquivo.largura_dut("7001")):
            a = f.novo()
        a.add_comando(rot, cid, extra={4: "0", 5: "2"} if cid == "9015" else None)
        a.add_dut("7000", rot, rot, "contato")
        a.add_dut("7001", rot, rot, "contato")
    for a in f.arqs:
        a.titulo = "Bobinas 9014/9002/9015 -> contatos 7000/7001 do mesmo rotulo"
        cmds = [c for c in a.celulas if c["tipo"] == "comando"]
        base = {c["ctrl"]: 0 for c in cmds}
        casos = [Caso("repouso", [("ler", "repouso", dict(base), "verifica")])]
        for c in cmds:
            k, ib = c["ctrl"], c["botao"]
            if c["classe"] == "9002":     # telerruptor: alterna a cada pulso (nota do RE)
                casos.append(Caso(f"{c['classe']} {k}",
                                  [("segurar", ib), ("esperar", 0.3), ("ler", "1o pulso", {**base, k: 1}, "verifica"),
                                   ("soltar",), ("esperar", 0.3), ("ler", "apos soltar", {**base, k: 1}, "verifica"),
                                   ("segurar", ib), ("esperar", 0.3), ("ler", "2o pulso", {**base, k: 0}, "verifica"),
                                   ("soltar",), ("esperar", 0.3), ("ler", "apos soltar 2", {**base, k: 0}, "verifica")]))
            elif c["classe"] == "9015":   # gerador de pulsos: sonda
                casos.append(Caso(f"{c['classe']} {k}",
                                  [("segurar", ib)] + sum([[("esperar", 0.8), ("ler", f"amostra {j}", {**base, k: None},
                                                            "sonda")] for j in range(6)], []) + [("soltar",)]))
            else:
                casos.append(Caso(f"{c['classe']} {k}",
                                  [("segurar", ib), ("ler", f"{k} energizada", {**base, k: 1}, "verifica"),
                                   ("soltar",), ("ler", f"{k} solta", {**base, k: 0}, "verifica")]))
        a.casos = casos
    return f.arqs


def bancada_cargas():
    """Cargas diretas L->carga->N lidas pela cor do proprio simbolo. Esperado so p/ 9000/9008 (cor validada)."""
    f = Fila("cargas")
    itens = [("9008", "-HA"), ("9000", "-KA"), ("9009", "-HB"), ("9010", "-HC"), ("9011", "-HD"), ("9012", "-HE"),
             ("9013", "-HF"), ("8101", "-HG"), ("8103", "-HH"), ("9001", "-KB"), ("9003", "-KC"), ("9004", "-KD"),
             ("9005", "-KE"), ("9006", "-KF"), ("9007", "-KG"), ("9014", "-KH"), ("9015", "-KI"), ("9002", "-KJ")]
    for cid, rot in itens:
        def fn(a, cid=cid, rot=rot):
            pins = pinos_bin(cid)
            topo = "p1"
            base = max(pins, key=lambda n: (pins[n][1], pins[n][0]))
            if cid == "9001":
                base = "p3"
            r = a.add_carga(cid, rot, topo, base)
            if r is not None:
                a.celulas[-1]["esperado_energizado"] = True if cid in ("9008", "9000") else None
            return r
        f.coloca(fn)
    for a in f.arqs:
        a.titulo = "Cargas diretas lidas pela cor (9008/9000 verificam; demais observam)"
        a.casos = [Caso("repouso (energizado desde o Play)", [("ler", "energizado", {}, "verifica")])]
    return f.arqs


def bancada_motores():
    f = Fila("motores")
    trif = {"U1": "L1", "V1": "L2", "W1": "L3"}
    mono = {"U1": "L", "V1": "N"}
    cc = {"A1": "p1", "A2": "p2"}
    itens = [("1000", trif, "3004"), ("1002", mono, "3003"), ("1003", trif, "3004"), ("1004", trif, "3004"),
             ("1005", trif, "3004"), ("1006", cc, "3010"), ("1007", cc, "3010"), ("1008", mono, "3003"),
             ("1009", mono, "3003"), ("1010", trif, "3004"), ("1000", {"U1": "L1"}, "3004")]
    for i, (cid, lig, fonte) in enumerate(itens):
        rot = f"-M{i + 1}"

        def fn(a, cid=cid, lig=lig, fonte=fonte, rot=rot, i=i):
            r = a.add_motor(cid, lig, fonte, rot, nome="so L1" if i == len(itens) - 1 else None)
            if r is not None:
                # RE (media): "gira se fases distintas nos pinos de fase"
                a.celulas[-1]["esperado_energizado"] = (len(lig) >= 2) if cid in ("1000",) else None
            return r
        f.coloca(fn)
    for a in f.arqs:
        a.titulo = "Motores: fonte direta; energizado = enchimento cinza / vermelho"
        a.casos = [Caso("repouso (energizado desde o Play)", [("ler", "energizado", {}, "verifica")])]
    return f.arqs


BANCADAS = [bancada_fontes, bancada_contatos, bancada_botoes, bancada_alternadores, bancada_termico,
            bancada_temporizadores, bancada_bobinas, bancada_cargas, bancada_motores, bancada_sensores]


def construir(gerar=True):
    arqs = []
    for fn in BANCADAS:
        arqs += fn()
    if gerar:
        for a in arqs:
            ok, out = a.gerar()
            if not ok:
                raise RuntimeError(f"{a.nome}: validate falhou: {out}")
    return arqs


# --------------------------------------------------------------------------- avaliacao

def _celula_da_lampada(arq):
    m = {}
    for c in arq.celulas:
        for lab in c["lamps"].values():
            m[lab] = c
    return m


def avaliar(arq, res):
    """Linhas {caso, leitura, lampada, classe, esperado, obtido} de um resultado (app ou netlist) de `arq`."""
    rows = []
    cel = _celula_da_lampada(arq)
    for caso, rc in zip(arq.casos, res.get("casos", [])):
        lei = [p for p in caso.passos if p[0] == "ler"]
        obt_por_leitura = []
        for p, rl in zip(lei, rc.get("leituras", [])):
            esp = esperado_leitura(arq, p[2])
            obt = set(rl.get("obtido") or [])
            obt_por_leitura.append(obt)
            for lamp, e in esp.items():
                c = cel.get(lamp)
                rows.append({"caso": caso.nome, "leitura": p[1], "lampada": lamp, "classe": c["classe"] if c else None,
                             "celula": c["id"] if c else None, "ctrl": c.get("ctrl") if c else None,
                             "esperado": e, "obtido": lamp in obt, "alterna": False})
        if caso.alterna and obt_por_leitura:
            for c in arq.celulas:
                if c["ctrl"] != caso.alterna or c["tipo"] == "comando":
                    continue
                for lab in c["lamps"].values():
                    vistos = {lab in o for o in obt_por_leitura}
                    rows.append({"caso": caso.nome, "leitura": "amostras", "lampada": lab, "classe": c["classe"],
                                 "celula": c["id"], "ctrl": c["ctrl"], "esperado": "alterna",
                                 "obtido": sorted(vistos), "alterna": True})
    return rows


def linha_ok(r):
    if r["esperado"] is None:
        return None
    if r["alterna"]:
        return r["obtido"] == [False, True]
    return r["esperado"] == r["obtido"]


def executar_netlist(arq):
    """Mesmos passos no netlist_sim. -> {executado, erro, casos:[{nome, leituras:[{nome, obtido}]}]}"""
    out = {"executado": False, "erro": None, "casos": []}
    try:
        import netlist_sim as N
        c = N.Circuito(str(arq.cad_path()))
    except Exception as e:  # noqa: BLE001
        out["erro"] = f"{type(e).__name__}: {e}"
        return out
    chave = lambda i: (arq.d.ids[i].rotulo or "").lstrip("-").strip()  # noqa: E731
    try:
        for caso in arq.casos:
            st = c.novo_estado()
            ent = {}
            r = {"nome": caso.nome, "leituras": []}
            e = None
            for p in caso.passos:
                if p[0] == "segurar":
                    ent[chave(p[1])] = True
                elif p[0] == "soltar":
                    ent = {k: False for k in ent if k in {chave(q[1]) for q in caso.passos if q[0] == "clicar"}} \
                        if False else {k: v for k, v in ent.items() if k in _clicados(caso, chave)}
                elif p[0] == "clicar":
                    ent[chave(p[1])] = not ent.get(chave(p[1]), False)
                elif p[0] == "esperar":
                    e = c.avancar(st, ent, float(p[1]))
                elif p[0] == "ler":
                    e = c.avancar(st, ent, 0.0)
                    obt = {f"-{n}" for n in e["lampadas"]} | {f"-{n}" for n in e["bobinas"]}
                    r["leituras"].append({"nome": p[1], "obtido": sorted(obt)})
            out["casos"].append(r)
        out["executado"] = True
    except Exception as ex:  # noqa: BLE001
        out["erro"] = f"{type(ex).__name__}: {ex}"
    return out


def _clicados(caso, chave):
    return {chave(q[1]) for q in caso.passos if q[0] == "clicar"}


# --------------------------------------------------------------------------- resultados (persistencia)

def _assinatura(arq):
    import hashlib
    return hashlib.sha1(arq.cad_path().read_bytes()).hexdigest()[:12]


def carregar_resultados():
    if RESULTADOS.is_file():
        try:
            return json.loads(RESULTADOS.read_text())
        except ValueError:
            pass
    return {"data": DATA, "arquivos": {}}


def salvar_resultados(r):
    RESULTADOS.write_text(json.dumps(r, ensure_ascii=False, indent=1, sort_keys=True) + "\n")


def registrar(r, arq, chave, execucao):
    a = r["arquivos"].setdefault(arq.nome, {})
    a["assinatura"] = _assinatura(arq)
    a["titulo"] = arq.titulo
    a["classes"] = sorted(arq.classes)
    a[chave] = {**execucao, "data": DATA}
    return r


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--gerar", action="store_true", help="so escreve os .cad (out/bancada)")
    ap.add_argument("--netlist", action="store_true", help="roda o netlist_sim nos mesmos casos")
    ap.add_argument("--app", action="store_true", help="roda no app (Wine); nomes de arquivo como argumentos")
    ap.add_argument("--relatorio", action="store_true", help="gera docs/cobertura.md e verificado_app no JSON")
    ap.add_argument("--listar", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("nomes", nargs="*")
    a = ap.parse_args(argv)
    arqs = construir(gerar=True)
    sel = [x for x in arqs if not a.nomes or x.nome in a.nomes or any(x.nome.startswith(n) for n in a.nomes)]
    if a.listar or a.gerar:
        for x in arqs:
            print(f"{x.nome}: {len(x.celulas)} celulas, {len(x.lampadas)} lampadas, {len(x.casos)} casos, "
                  f"classes={sorted(x.classes)}")
    if a.netlist:
        r = carregar_resultados()
        for x in sel:
            registrar(r, x, "netlist", executar_netlist(x))
            n = r["arquivos"][x.nome]["netlist"]
            print(f"netlist {x.nome}: {'ok' if n['executado'] else 'ERRO ' + str(n['erro'])}")
        salvar_resultados(r)
    if a.app:
        for x in sel:
            ex = executar_app(x, verbose=a.verbose)
            r = carregar_resultados()
            registrar(r, x, "app", ex)
            salvar_resultados(r)
            rows = avaliar(x, ex)
            falhas = [w for w in rows if linha_ok(w) is False]
            print(f"app {x.nome}: executado={ex['executado']} {ex['tempo_s']}s erro={ex['erro']} "
                  f"leituras={len(rows)} divergencias={len(falhas)}", flush=True)
            for w in falhas[:12]:
                print("   DIVERGE", w["caso"], "|", w["leitura"], "|", w["lampada"], w["classe"],
                      "esperado", w["esperado"], "obtido", w["obtido"])
    if a.relatorio:
        import bancada_relatorio as R
        R.gerar(arqs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
