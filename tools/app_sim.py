#!/usr/bin/env python3
"""Verificador E2E: abre o .cad no CADe_SIMU (Wine), simula, aciona entradas e LE o estado por imagem.

Fecha o laco com a VERDADE do app (o netlist_sim e so um modelo). Tudo por X11 (xdotool + import):

  - coordenada -> pixel: a vista do app (zoom/scroll) e CALIBRADA a cada screenshot casando os fios
    (4000) do proprio .cad com os pixels da imagem (correlacao FFT); px = ox + s*(x - xmin).
  - leitura (calibrada empiricamente, ver docs/app-sim.md): em simulacao o app pinta de VERMELHO PURO
    (255,0,0) todo simbolo ATIVO (contato acionado: NA fechado / NF aberto, bobina energizada, lampada
    acesa); bobina energizada tambem enche o corpo de cinza (192); fio sem tensao e cinza (128), com
    fase L1-L3 vinho (128,0,0), N azul, PE verde; motor energizado enche o disco de cinza.
  - entradas: botoeira (8000/8001) = mousedown/mouseup (segura); disjuntor/termico/seletor = clique alterna.
    `inicial` (selo) e obtido PRESSIONANDO a sequencia que leva as bobinas aquele estado (BFS no app).

Uso (manual):
  python3 tools/app_sim.py out/x.cad                       # abre, Play, imprime o estado de repouso
  python3 tools/app_sim.py out/x.cad --layout spec.json    # roda "testes" da spec e imprime caso x resultado
  python3 tools/app_sim.py out/x.cad --layout spec.json --saida out/app_sim/x
Como biblioteca:
  import app_sim; r = app_sim.executar_casos("out/x.cad", casos)   # -> dict (ok, casos[], tempo_s, ...)

Memoria: UM Wine por vez. Se ja houver CADe_SIMU rodando, espera ate `esperar_s` e desiste (nao mata o
alheio). Sempre faz `down` ao terminar (a menos de manter=True).
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import wine_mgr as W  # noqa: E402
from dissect import parse_ent, split_all  # noqa: E402

DISP = os.environ.get("DISPLAY", ":1")
ARQ_APP = "app_sim.cad"                       # copia no dir do EXE (nao colide com o wv_tmp.cad do wine_mgr)
CALIB_ARQ = ROOT / "out" / "app_sim" / "calibracao.json"

FIO = {"4000", "4009", "4010", "4018", "4019"}
IGNORA = FIO | {"4001", "4002", "4003", "4004", "4012", "8", "20000"}
BOBINA = {"9000", "10060"}
SAIDA_CLP = {"10205"}                        # celula DO do CLP modular (acesa com a saida em 1)
LAMPADA = {"9008"}
BOTOEIRA = {"8000", "8001"}                  # momentaria: segurar o mouse
CONTATO_NA = {"7000", "8000", "8016", "10050"}
CONTATO_NF = {"7001", "8001", "8017", "10051"}
# toolbar (px relativos a janela, alinhados a esquerda): Play, Stop
BTN_PLAY, BTN_STOP = (505, 32), (528, 32)
# O menu Ver/'Zoom Todo' NAO e mais usado: o popup nao aparece em captura de janela (XWayland) e a posicao mudou
# com a janela maximizada. A vista util = filha MDI MAXIMIZADA (duplo-clique na barra de titulo da filha), que no
# Wine atual da escala 4 px/unidade sem scroll: px = 24 + 4*x, py = 69 + 4*y (confirmado pela calibracao FFT).
TITULO_FILHA = (600, 85)                     # barra de titulo da filha MDI quando NAO maximizada
BTN_STOP_COR = RED = (255, 0, 0)
CINZA_FILL = (192, 192, 192)


class AppSimErro(RuntimeError):
    pass


# --------------------------------------------------------------------------- arquivo .cad

def norm(rot):
    return (rot or "").strip().lstrip("-").upper()


def _pinos_da_classe(cid):
    import geo_check as G
    return G.pinos_da_classe(cid), G._rot


class Cad:
    """Entidades do .cad que importam para a imagem: fios (calibracao) e simbolos (regioes/cliques)."""

    def __init__(self, path):
        self.path = str(path)
        d = Path(path).read_bytes().decode("latin1")
        _, ents, _ = split_all(d)
        self.fios, self.simbolos = [], []
        for p in (parse_ent(e) for e in ents):
            if not p or len(p["nums"]) < 18:
                continue
            n = p["nums"]
            x, y = int(n[8]), int(n[9])
            if p["id"] in FIO:
                self.fios.append((x, y, int(n[10]), int(n[11])))
            elif p["id"] not in IGNORA:
                o = int(n[17] or 0)
                rot = (p["labels"] or [""])[0] or p["id"]
                self.simbolos.append({"classe": p["id"], "rotulo": rot, "chave": norm(rot), "x": x, "y": y, "o": o,
                                      "box": tuple(int(v) for v in n[12:16])})
        self.xmin = min(min(f[0], f[2]) for f in self.fios) if self.fios else 0
        self.ymin = min(min(f[1], f[3]) for f in self.fios) if self.fios else 0
        for s in self.simbolos:
            s["tipo"] = tipo_simbolo(s["classe"])
            s["pinos"] = self._pinos(s)

    @staticmethod
    def _pinos(s):
        try:
            pins, rot = _pinos_da_classe(s["classe"])
        except Exception:
            return []
        return [(nome, s["x"] + rot(dx, dy, s["o"])[0], s["y"] + rot(dx, dy, s["o"])[1]) for nome, (dx, dy) in pins.items()]

    def regiao(self, s, margem=5):
        """Retangulo (x0,y0,x1,y1) em unidades do .cad onde o simbolo e desenhado."""
        pts = [(px, py) for _, px, py in s["pinos"]] or [(s["x"], s["y"])]
        x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
        y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
        if s["classe"] in ("10204", "10205", "10206") and len(s["box"]) == 4 and s["box"][2] > 0:
            dx, dy, w, h = s["box"]                 # celula DI/DO do CLP: a caixa gravada (-12,-3,12,27)
            return s["x"] + dx, s["y"] + dy, s["x"] + dx + w, s["y"] + dy + h
        if s["classe"] == "1000":                   # motor: disco abaixo dos pinos
            x0, x1, y1 = min(x0, s["x"] - 12), max(x1, s["x"] + 12), max(y1, s["y"] + 18)
        return x0 - margem, y0 - margem, x1 + margem, y1 + margem

    def ponto_clique(self, s):
        """Centro do corpo (meio dos pinos). Para 3 polos (2001/6007/6009) o polo central."""
        pts = [(px, py) for _, px, py in s["pinos"]] or [(s["x"], s["y"])]
        return (min(p[0] for p in pts) + max(p[0] for p in pts)) / 2, (min(p[1] for p in pts) + max(p[1] for p in pts)) / 2

    def achar(self, rotulo_ou_chave, classes=None):
        k = norm(rotulo_ou_chave)
        c = [s for s in self.simbolos if s["chave"] == k and (classes is None or s["classe"] in classes)]
        return c

    def entradas(self, aliases=None):
        """chave -> {"simbolo": atuador|None, "modo": "segurar"|"alternar"|None, "nota": str}.

        - botoeira (8000/8001): segurar (mousedown). Disjuntor (6009/6010): clique alterna.
        - rele termico: o app liga o contato 8016/8017 ao elemento de potencia 6007 pelo MESMO ROTULO
          (verificado no app); o disparo e o clique no 6007. Contato sem 6007 de mesmo rotulo = inacionavel.
        `aliases` {"RT1": "F1"}: forca o atuador de uma entrada por outro rotulo."""
        aliases = {norm(k): norm(v) for k, v in (aliases or {}).items()}
        bobinas = {s["chave"] for s in self.simbolos if s["classe"] in BOBINA}
        pot = {}
        for s in self.simbolos:
            if s["classe"] == "6007":
                pot.setdefault(s["chave"], s)
        out = {}
        for s in self.simbolos:
            k = s["chave"]
            if k in bobinas:
                continue
            if s["tipo"] == "botoeira":
                out.setdefault(k, {"simbolo": s, "modo": "segurar", "nota": ""})
            elif s["tipo"] == "disjuntor":
                out.setdefault(k, {"simbolo": s, "modo": "alternar", "nota": ""})
            elif s["classe"] == "6007":
                out.setdefault(k, {"simbolo": s, "modo": "alternar", "nota": "disparo do termico (clique)"})
        for s in self.simbolos:
            k = s["chave"]
            if s["classe"] in ("8016", "8017") and k not in bobinas:
                alvo = aliases.get(k, k)
                if alvo in pot:
                    out[k] = {"simbolo": pot[alvo], "modo": "alternar",
                              "nota": f"contato {s['rotulo']} acompanha o termico {pot[alvo]['rotulo']}" if alvo != k
                              else "disparo do termico (clique no 6007 de mesmo rotulo)"}
                elif k not in out:
                    sug = sorted(pot)
                    out[k] = {"simbolo": None, "modo": None,
                              "nota": f"contato {s['rotulo']} ({s['classe']}) sem rele termico 6007 de mesmo rotulo: o app nao o "
                                      f"aciona (6007 existentes: {sug}); use o MESMO rotulo no 6007 e no contato"}
        for k, v in aliases.items():
            if k not in out and v in pot:
                out[k] = {"simbolo": pot[v], "modo": "alternar", "nota": f"alias {k}->{v}"}
        return out


def tipo_simbolo(cid):
    if cid in ("10060", "10061", "10062"):
        return "bobina_ladder"                   # OUT/SET/RST do ladder (estado = vermelho no corpo)
    if cid in BOBINA:
        return "bobina"
    if cid in LAMPADA:
        return "lampada"
    if cid in BOTOEIRA:
        return "botoeira"
    if cid == "8017":
        return "termico"                          # contato NF 95-96 (segue o 6007 de mesmo rotulo)
    if cid == "8016":
        return "contato_aux_termico"             # contato NA 97-98
    if cid in ("7000", "7001", "10050", "10051"):
        return "contato"
    if cid in ("6002", "6003", "6009", "6010"):
        return "disjuntor"                         # DJ1 6002/6003: de mesmo rotulo do aux 8016; alterna ANTES do teste
    if cid in SAIDA_CLP:
        return "saida_clp"
    if cid in ("2001",):
        return "contator_potencia"
    if cid == "6007":
        return "termico_potencia"
    if cid == "1000":
        return "motor"
    if cid.startswith("30"):
        return "fonte"
    return "outro"


# --------------------------------------------------------------------------- calibracao (coordenada -> pixel)

def _tinta(a):
    """bool HxW: pixel que nao e branco nem o cinza-claro (192) da grade de pontos."""
    return ~(((a == 255).all(2)) | ((a == 192).all(2)))


def _dilata(m):
    d = m.copy()
    d[1:, :] |= m[:-1, :]; d[:-1, :] |= m[1:, :]
    e = d.copy()
    e[:, 1:] |= d[:, :-1]; e[:, :-1] |= d[:, 1:]
    return e


def _erode(m):
    e = m.copy()
    e[1:, :] &= m[:-1, :]; e[:-1, :] &= m[1:, :]
    f = e.copy()
    f[:, 1:] &= e[:, :-1]; f[:, :-1] &= e[:, 1:]
    return f


def _solidos(m):
    """Regioes cheias (>=5x5) de tinta: fundo cinza do MDI, enchimentos grandes. Fios de 1 px nao entram."""
    core = _erode(_erode(m))
    return _dilata(_dilata(core))


def _mascara_fios(cad, s):
    w = int(round(s * (max(max(f[0], f[2]) for f in cad.fios) - cad.xmin))) + 2
    h = int(round(s * (max(max(f[1], f[3]) for f in cad.fios) - cad.ymin))) + 2
    im = Image.new("1", (w, h), 0)
    dr = ImageDraw.Draw(im)
    for x1, y1, x2, y2 in cad.fios:
        dr.line([(round(s * (x1 - cad.xmin)), round(s * (y1 - cad.ymin))),
                 (round(s * (x2 - cad.xmin)), round(s * (y2 - cad.ymin)))], fill=1)
    return np.asarray(im, dtype=bool)


def _prox(n):
    k = 1
    while k < n:
        k *= 2
    return k


def _correlaciona(tinta_d, m):
    H, Wd = tinta_d.shape
    h, w = m.shape
    N = (_prox(H + h), _prox(Wd + w))
    F = np.fft.rfft2(tinta_d.astype(np.float32), N)
    G = np.fft.rfft2(m.astype(np.float32), N)
    return np.fft.irfft2(F * np.conj(G), N), N


class Calib:
    def __init__(self, s, ox, oy, score, cobertura):
        self.s, self.ox, self.oy, self.score, self.cobertura = s, ox, oy, score, cobertura

    def px(self, x, y):
        return self.ox + self.s * x, self.oy + self.s * y

    def como_dict(self):
        return {"escala": float(self.s), "ox": round(float(self.ox), 2), "oy": round(float(self.oy), 2),
                "score": round(float(self.score), 3), "fios_sobre_tinta": round(float(self.cobertura), 3)}


def _area_desenho(a):
    """(y0,y1,x0,x1) da area de desenho em pixels: corta toolbar, paletas e o FUNDO CINZA do MDI.

    Quando a filha MDI nao esta maximizada (WM pequeno), a folha e cortada embaixo; o fundo cinza
    (128,128,128) delimita o fim da area visivel. Sem isso a calibracao cobra fios que estao fora
    da vista e falha (`partida_trafo_comando`, 22/10/2026).
    """
    H, Wd = a.shape[:2]
    y0, y1, x0, x1 = 100, H - 22, 28, Wd - 28
    cinza = (a == np.array([128, 128, 128], dtype=np.uint8)).all(2)
    for y in range(y0, H):
        if cinza[y, x0:x1].mean() > 0.9:
            y1 = y
            break
    for x in range(Wd - 1, x1, -1):
        if cinza[y0:y1, x].mean() > 0.9:
            x1 = x
            break
    return y0, max(y0, y1), x0, max(x0, x1)


def calibrar(img, cad, hint=None, min_cobertura=0.85):
    """Casa os fios do .cad com a imagem. Devolve Calib ou None. `hint`=escala anterior (caminho rapido)."""
    if not cad.fios:
        return None
    a = np.asarray(img.convert("RGB"))
    H, Wd = a.shape[:2]
    y0, y1, x0, x1 = _area_desenho(a)               # so a area realmente visivel da folha
    tinta = np.zeros((H, Wd), dtype=bool)
    tinta[y0:y1, x0:x1] = _tinta(a)[y0:y1, x0:x1]
    tinta &= ~_solidos(tinta)                        # fundo cinza do MDI etc. nao e fio
    td = _dilata(tinta)
    cand = []
    if hint:
        cand.append(hint)
    base = (1.0, 2.0, 1.5, 0.5, 3.0, 0.75, 1.25, 2.5, 4.0)
    cand += [s for s in base if s not in cand]
    # varredura fina: a janela do app pode abrir em zoom que "cabe" (1,4..2,0 px/unidade)
    cand += [round(0.5 + 0.1 * i, 1) for i in range(36) if round(0.5 + 0.1 * i, 1) not in cand]
    melhor = None
    for s in cand:
        m = _mascara_fios(cad, s)
        n = int(m.sum())
        if n == 0:
            continue
        R, N = _correlaciona(td, m)
        flat = np.argsort(R.ravel())[::-1][:40]      # picos brutos; o certo tem mais acertos mesmo cortado
        for idx in flat:
            dy, dx = divmod(int(idx), R.shape[1])
            if dy > N[0] // 2:
                dy -= N[0]
            if dx > N[1] // 2:
                dx -= N[1]
            # so a parte da mascara que cai dentro da area de desenho conta (vista pode estar rolada)
            ya, yb = max(0, y0 - dy), min(m.shape[0], y1 - dy)
            xa, xb = max(0, x0 - dx), min(m.shape[1], x1 - dx)
            if yb <= ya or xb <= xa:
                continue
            dentro = int(m[ya:yb, xa:xb].sum())
            if dentro < 150 or dentro < 0.25 * n:
                continue
            acertos = float(R.ravel()[idx])
            cob = acertos / dentro
            ys, xs = ya + dy, xa + dx
            dens = td[ys:ys + (yb - ya), xs:xs + (xb - xa)].mean()
            sc = cob - dens
            if melhor is None or sc > melhor[0]:
                melhor = (sc, cob, s, dx, dy)
        if melhor and melhor[1] >= 0.95 and melhor[0] > 0.6:
            break                                   # bom o bastante: nao testa os outros zooms
    if not melhor or melhor[1] < min_cobertura:
        return None
    sc, cob, s, dx, dy = melhor
    # px = dx + s*(x - xmin)  =>  ox = dx - s*xmin
    return Calib(s, dx - s * cad.xmin, dy - s * cad.ymin, sc, cob)


# --------------------------------------------------------------------------- leitura do estado

def _conta(a, rect, cor):
    x0, y0, x1, y1 = rect
    sub = a[max(y0, 0):max(y1, 0), max(x0, 0):max(x1, 0)]
    if sub.size == 0:
        return 0
    return int((sub == np.array(cor, dtype=np.uint8)).all(2).sum())


def _conta_cheio(a, rect, cor):
    """Pixels da cor cujos 8 vizinhos tambem sao da cor (preenchimento solido; ignora os pontos da grade)."""
    x0, y0, x1, y1 = rect
    sub = a[max(y0 - 1, 0):max(y1 + 1, 0), max(x0 - 1, 0):max(x1 + 1, 0)]
    if sub.shape[0] < 3 or sub.shape[1] < 3:
        return 0
    m = (sub == np.array(cor, dtype=np.uint8)).all(2)
    c = m[1:-1, 1:-1].copy()
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            c &= m[dy:dy + m.shape[0] - 2, dx:dx + m.shape[1] - 2]
    return int(c.sum())


def ler_estado(img, cad, cal, base=None):
    """Estado dos simbolos pela cor. `base`: leitura de repouso (so para contar mudancas); opcional."""
    a = np.asarray(img.convert("RGB"))
    H, Wd = a.shape[:2]
    itens = []
    for s in cad.simbolos:
        if s["tipo"] in ("fonte",) and not s["pinos"]:
            continue
        x0, y0, x1, y1 = cad.regiao(s)
        (px0, py0), (px1, py1) = cal.px(x0, y0), cal.px(x1, y1)
        rect = (int(np.floor(px0)), int(np.floor(py0)), int(np.ceil(px1)) + 1, int(np.ceil(py1)) + 1)
        dentro = rect[0] >= 0 and rect[1] >= 100 and rect[2] <= Wd and rect[3] <= H - 20
        verm = _conta(a, rect, RED)
        cinza = _conta_cheio(a, rect, CINZA_FILL)
        itens.append({"rotulo": s["rotulo"], "chave": s["chave"], "classe": s["classe"], "tipo": s["tipo"],
                      "x": s["x"], "y": s["y"], "ativo": verm >= 3, "vermelho_px": verm, "cinza_px": cinza,
                      "visivel": dentro})
    bob = {}
    lamp = {}
    cont = {}
    sai = {}
    bl = {}
    for it in itens:
        if it["tipo"] == "bobina_ladder":
            bl[it["chave"]] = bl.get(it["chave"], False) or it["ativo"]
        elif it["tipo"] == "saida_clp":
            sai[it["chave"]] = sai.get(it["chave"], False) or it["ativo"]
        elif it["tipo"] == "bobina":
            bob[it["chave"]] = bob.get(it["chave"], False) or it["ativo"]
        elif it["tipo"] == "lampada":
            lamp[it["chave"]] = lamp.get(it["chave"], False) or it["ativo"]
        elif it["tipo"] in ("contato", "botoeira", "termico", "contato_aux_termico"):
            k = f'{it["rotulo"]}({it["classe"]})@{it["x"]},{it["y"]}'
            cont[k] = it["ativo"]
    motores = {it["chave"]: it["ativo"] or it["cinza_px"] >= 12 for it in itens if it["tipo"] == "motor"}
    return {"bobinas": bob, "lampadas": lamp, "saidas_clp": sai, "bobinas_ladder": bl, "contatos_acionados": cont, "motores": motores,
            "fora_da_janela": [it["rotulo"] for it in itens if not it["visivel"]],
            "simbolos": itens}


def _cor_em(img, x, y, cor, r=9):
    a = np.asarray(img.convert("RGB"))[22:42, x - r:x + r]
    return int((a == np.array(cor, dtype=np.uint8)).all(2).sum())


def toolbar_ativa(img):
    """Botao Play verde presente = app desbloqueado (sem dialogo modal; modal deixa tudo cinza)."""
    return _cor_em(img, BTN_PLAY[0], 32, (0, 255, 0)) >= 5


def em_simulacao(img):
    """Botao Stop (528,32) VERMELHO = simulacao rodando (sinal confiavel neste Wine).

    O criterio antigo (Pausa em (551,32)) falhava: ali o botao so fica vermelho em outro estado (pausado)."""
    return _cor_em(img, BTN_STOP[0], 32, RED) >= 5


def vista_maximizada(img):
    """True se a filha MDI esta maximizada (sem a barra de titulo da filha e sem o fundo cinza do MDI).

    O criterio antigo so olhava o pixel do titulo (azul/cinza). Em 22/10/2026 a barra veio
    verde-agua e a filha pequena passou batido: o `zoom_todo` nao maximizava e a calibracao
    falhava (`partida_trafo_comando`). Agora tambem mede o fundo cinza na metade de baixo.
    """
    a = np.asarray(img.convert("RGB"))
    y, x = TITULO_FILHA[1], TITULO_FILHA[0]
    if a.shape[0] <= y or a.shape[1] <= x:
        return True
    r, g, b = (int(v) for v in a[y, x])
    azul = b > 160 and r < 90 and 70 < g < 170        # barra de titulo ativa do Windows (0,120,215)
    cinza = (r, g, b) == (128, 128, 128)               # fundo do MDI (filha inativa/pequena)
    if azul or cinza:
        return False
    sub = a[560:min(a.shape[0], 1000), 60:min(a.shape[1] - 1, 940)]
    if sub.size:
        frac = float((sub == np.array([128, 128, 128], dtype=np.uint8)).all(2).mean())
        if frac > 0.6:                                 # fundo do MDI domina: filha NAO maximizada
            return False
    return True


# --------------------------------------------------------------------------- app (Wine)

def _xdo(*args):
    r = subprocess.run(["xdotool", *args], env=dict(os.environ, DISPLAY=DISP), capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout


class AppSim:
    def __init__(self, cad, saida=None, verbose=False):
        self.cad = Cad(cad)
        self.cad_path = Path(cad)
        self.saida = Path(saida).resolve() if saida else ROOT / "out" / "app_sim" / self.cad_path.stem
        self.saida.mkdir(parents=True, exist_ok=True)
        self.win = None
        self.cal = None
        self._pressed_at = None
        self.lancou = False                       # so mata o Wine que ESTE objeto subiu
        self.verbose = verbose
        self.n_shot = 0
        self.log_ev = []

    def _log(self, m):
        self.log_ev.append(m)
        if self.verbose:
            print(f"[app_sim] {m}", flush=True)

    # -- ciclo de vida
    def _janela(self):
        for w in _xdo("search", "--name", "CADe_SIMU").split():
            n = _xdo("getwindowname", w).strip()
            if n.startswith("CADe_SIMU 4.0 -") and ".cad" in n:
                return w
        return None

    def _pos(self):
        g = _xdo("getwindowgeometry", self.win)
        pos = geo = None
        for ln in g.splitlines():
            s = ln.strip()
            if s.startswith("Position:"):
                pos = tuple(int(v) for v in s.split()[1].split(","))
            elif s.startswith("Geometry:"):
                geo = tuple(int(v) for v in s.split()[1].split("x"))
        return pos, geo

    def _teclado(self):
        for w in _xdo("search", "--name", "CADE SIMU 4.0").split():
            if "176x189" in _xdo("getwindowgeometry", w).replace("Geometry: ", "").replace("\n", " "):
                pos = [l for l in _xdo("getwindowgeometry", w).splitlines() if "Position" in l]
                if pos:
                    x, y = (int(v) for v in pos[0].split()[1].split(","))
                    return x, y
        return None

    def _desbloqueado(self):
        if not self.win:
            return False
        try:
            img, _ = self.screenshot("_probe.png")
        except AppSimErro:
            return False
        return toolbar_ativa(img)

    def _tentativa_abrir(self, tempo_total=70):
        """Sobe o app, digita a senha UMA vez por aparicao do teclado, espera a toolbar ativa.
        False se o app morrer ('Erro de acesso Key') ou estourar o tempo."""
        dst = W.EXE_DIR / ARQ_APP
        dst.write_bytes(self.cad_path.read_bytes())
        self.lancou = True
        out = open(W.LOGDIR / "wine_app.log", "ab") if W.LOGDIR.exists() else subprocess.DEVNULL
        subprocess.Popen(["wine", W.EXE, ARQ_APP], cwd=str(W.EXE_DIR), env=dict(os.environ, DISPLAY=DISP),
                         stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
        t0 = time.time()
        envios = 0
        ultimo_envio = 0.0
        vivo_desde = None
        while time.time() - t0 < tempo_total:
            if time.time() - t0 > 6 and not W.pids_cade():
                self._log("processo morreu durante a abertura")
                return False
            k = self._teclado()
            if k and time.time() - ultimo_envio > 4 and envios < 3:
                x, y = k
                for tecla in ("4", "9", "6", "2", "OK"):
                    fx, fy = W.TECLAS[tecla]
                    _xdo("mousemove", str(int(x + fx * 176)), str(int(y + fy * 189)), "click", "1")
                    time.sleep(0.2)
                envios += 1
                ultimo_envio = time.time()
                self._log(f"senha enviada ({envios}) em {ultimo_envio-t0:.1f}s")
                time.sleep(1.5)
                continue
            self.win = self._janela() or self.win
            if self.win and not k and time.time() - t0 > 3 and self._desbloqueado():
                if vivo_desde is None:
                    vivo_desde = time.time()
                if time.time() - vivo_desde >= 2.0:
                    return bool(W.pids_cade())
            else:
                vivo_desde = None
            time.sleep(0.5)
        return False

    def abrir(self, esperar_s=120, tentativas=3):
        """Sobe o Wine com o .cad. Retry com down/up se o app morrer ('Erro de acesso Key')."""
        t0 = time.time()
        while W.pids_cade() and time.time() - t0 < esperar_s:
            self._log("CADe_SIMU ja rodando (outro agente?): aguardando liberar")
            time.sleep(3)
        if W.pids_cade():
            raise AppSimErro("Wine/CADe_SIMU ocupado por outro processo; rode `python3 tools/wine_mgr.py down` se for seu")
        for i in range(tentativas):
            try:
                if self._tentativa_abrir():
                    self._log(f"aberto (tentativa {i+1}) em {time.time()-t0:.1f}s")
                    return self
            finally:
                pass
            self._log(f"tentativa {i+1} falhou; down + retry")
            W.cmd_down()
            time.sleep(1.5)
        raise AppSimErro(f"nao consegui abrir o app apos {tentativas} tentativas (ver logs/wine_mgr.log)")

    def fechar(self):
        """down so se ESTE objeto subiu o Wine (nunca derruba o de outro agente)."""
        try:
            if self.lancou:
                W.cmd_down()
                self.lancou = False
        finally:
            try:
                (W.EXE_DIR / ARQ_APP).unlink()
            except OSError:
                pass
            self.win = None

    def __enter__(self):
        return self.abrir()

    def __exit__(self, *a):
        self.fechar()

    # -- imagem
    def screenshot(self, nome=None):
        out = self.saida / (nome or f"shot{self.n_shot:03d}.png")
        self.n_shot += 1
        for _ in range(4):
            self.saida.mkdir(parents=True, exist_ok=True)
            subprocess.run(["import", "-window", self.win, str(out)], env=dict(os.environ, DISPLAY=DISP),
                           capture_output=True, timeout=20)
            try:
                return Image.open(out).convert("RGB"), out
            except (OSError, ValueError):
                time.sleep(0.5)
        raise AppSimErro("screenshot da janela falhou")

    def _snap_calibra(self, nome=None):
        img, p = self.screenshot(nome)
        cal = calibrar(img, self.cad, hint=self.cal.s if self.cal else None)
        if cal:
            self.cal = cal
            try:
                CALIB_ARQ.parent.mkdir(parents=True, exist_ok=True)
                CALIB_ARQ.write_text(json.dumps({"cad": self.cad_path.name, **cal.como_dict()}, indent=1), encoding="utf-8")
            except OSError:
                pass
        return img, p, cal

    # -- acoes de baixo nivel
    def _clica_win(self, wx, wy, down_up=None):
        (px, py), _ = self._pos()
        X, Y = str(int(px + wx)), str(int(py + wy))
        if down_up is None:
            _xdo("mousemove", X, Y, "click", "1")
        elif down_up == "down":
            _xdo("mousemove", X, Y, "mousedown", "1")
        else:
            _xdo("mouseup", "1")

    def _estado_sim(self):
        img, _ = self.screenshot("_probe.png")
        return em_simulacao(img)

    def janela_dialogo(self):
        """Janela pequena e visivel diferente da principal: MessageBox do app (ex.: titulo 'Erro').

        Em 22/10/2026 o aviso de CURTO abria uma janela SEPARADA ('Erro', 150x82): o `import -window`
        da principal nao a ve e o app fica bloqueado. Por isso detectamos e fechamos por aqui."""
        for w in _xdo("search", "--onlyvisible", "--name", ".*").split():
            if w == self.win:
                continue
            g = _xdo("getwindowgeometry", w)
            pos = geo = None
            for ln in g.splitlines():
                s = ln.strip()
                if s.startswith("Position:"):
                    pos = tuple(int(v) for v in s.split()[1].split(","))
                elif s.startswith("Geometry:"):
                    geo = tuple(int(v) for v in s.split()[1].split("x"))
            if pos and geo and geo[0] <= 420 and geo[1] <= 320:
                return {"win": w, "pos": pos, "geo": geo, "nome": _xdo("getwindowname", w).strip()}
        return None

    def fechar_dialogo(self):
        """Fecha o MessageBox (Return; se nao sumir, clica no OK). -> dict do dialogo fechado ou None."""
        d = self.janela_dialogo()
        if not d:
            return None
        for tentativa in ("Return", "clique"):
            if tentativa == "Return":
                _xdo("windowactivate", d["win"])
                _xdo("key", "Return")
            else:
                x, y = d["pos"]
                w, h = d["geo"]
                _xdo("mousemove", str(x + w // 2), str(y + h - 14), "click", "1")
            time.sleep(0.5)
            if self.janela_dialogo() is None:
                return d
        return None

    def play(self, espera=1.0):
        self._clica_win(*BTN_PLAY)
        time.sleep(espera)
        for _ in range(3):
            if self._estado_sim():
                return True
            self._clica_win(*BTN_PLAY)
            time.sleep(espera)
        raise AppSimErro("nao entrou em simulacao (Play)")

    def stop(self, espera=0.8):
        self._clica_win(*BTN_STOP)
        time.sleep(espera)

    def zoom_todo(self):
        """Maximiza a filha MDI (duplo-clique na barra de titulo): folha em escala 4 sem scroll. Idempotente."""
        _xdo("windowsize", self.win, "1918", "1052")      # janela alta o bastante p/ a folha inteira (WM pode ignorar)
        time.sleep(0.8)
        for _ in range(3):
            img, _ = self.screenshot("_probe.png")
            if vista_maximizada(img):
                return self
            self._clica_win(*TITULO_FILHA)
            self._clica_win(*TITULO_FILHA)
            time.sleep(1.2)
        self._log("aviso: nao consegui maximizar a MDI; seguindo na vista atual (calibracao acha o zoom)")
        return self

    def reiniciar(self):
        """stop + play: zera bobinas/memoria/disjuntores (estado de repouso)."""
        self.stop()
        self.play()
        self.cal = self.cal  # mantem a escala como hint

    def _alvo(self, rotulo_ou_coord, aliases=None):
        """-> (wx, wy, entrada|None) em pixels da janela, com calibracao fresca."""
        cal = self.cal                           # vista fixa (sem scroll): reaproveita a calibracao (FFT custa ~1,5 s)
        if cal is None:
            img, _, cal = self._snap_calibra("_cal.png")
        if cal is None:
            raise AppSimErro("calibracao falhou (fios do .cad nao casam com a imagem)")
        if isinstance(rotulo_ou_coord, (tuple, list)):
            x, y = rotulo_ou_coord
            return (*cal.px(x, y), None)
        k = norm(rotulo_ou_coord)
        ents = self.cad.entradas(aliases)
        if k in ents:
            e = ents[k]
            if e["simbolo"] is None:
                raise AppSimErro(e["nota"])
            cx, cy = self.cad.ponto_clique(e["simbolo"])
            return (*cal.px(cx, cy), e)
        cs = self.cad.achar(k)
        if not cs:
            raise AppSimErro(f"simbolo {rotulo_ou_coord!r} inexistente (disponiveis: {sorted({s['chave'] for s in self.cad.simbolos})})")
        cx, cy = self.cad.ponto_clique(cs[0])
        return (*cal.px(cx, cy), None)

    def pressionar(self, rotulo_ou_coord, segurar_s=0.6, aliases=None):
        """mousedown, espera, solta (NAO solta se segurar_s=None: use soltar() depois)."""
        wx, wy, _ = self._alvo(rotulo_ou_coord, aliases)
        self._pressed_at = (wx, wy)
        self._clica_win(wx, wy, "down")
        if segurar_s is not None:
            time.sleep(segurar_s)
            self.soltar()

    def soltar(self):
        """mouseup no MESMO ponto do mousedown. Soltar na esquina (0,0) fazia o app nao ver o
        release e a botoeira ficava presa (bug observado nos goldens de 22/10/2026)."""
        wx, wy = self._pressed_at or (0, 0)
        self._clica_win(wx, wy, "up")
        self._pressed_at = None

    def alternar(self, rotulo_ou_coord, espera=0.6, aliases=None):
        wx, wy, _ = self._alvo(rotulo_ou_coord, aliases)
        self._clica_win(wx, wy)
        time.sleep(espera)

    def estado(self, nome=None):
        img, p, cal = self._snap_calibra(nome)
        if cal is None:
            raise AppSimErro("calibracao falhou ao ler o estado")
        r = ler_estado(img, self.cad, cal)
        r["calibracao"] = cal.como_dict()
        r["em_simulacao"] = em_simulacao(img)
        r["screenshot"] = str(p)
        return r


# --------------------------------------------------------------------------- casos

def _ativos(est):
    return {k for k, v in est["bobinas"].items() if v}


def _executa_entradas(app, entradas, aliases=None):
    """Aciona as entradas True. Alternaveis (termico/disjuntor) primeiro; botoeiras por ultimo e so a
    ULTIMA fica segurada (ponteiro unico; as anteriores levam um pulso). -> (chave segurada|None, varias)."""
    ents = app.cad.entradas(aliases)
    chaves = [norm(k) for k, v in (entradas or {}).items() if v]
    for k in chaves:
        if k not in ents:
            raise AppSimErro(f"entrada {k!r} sem simbolo acionavel no .cad (acionaveis: {sorted(ents)})")
        if ents[k]["simbolo"] is None:
            raise AppSimErro(ents[k]["nota"])
    chaves.sort(key=lambda k: ents[k]["modo"] == "segurar")
    botoes = [k for k in chaves if ents[k]["modo"] == "segurar"]
    seg = None
    for k in chaves:
        if ents[k]["modo"] == "segurar":
            if k != botoes[-1]:
                app.pressionar(k, segurar_s=0.5, aliases=aliases)
            else:
                app.pressionar(k, segurar_s=None, aliases=aliases)
                seg = k
        else:
            app.alternar(k, aliases=aliases)
    return seg, len(botoes) > 1


def descobrir_iniciais(app, alvos, profundidade=2, max_probes=24):
    """Para cada alvo (frozenset de bobinas) acha uma sequencia de botoeiras (pulso) que o produz.
    BFS com replay (stop/play entre tentativas). -> {alvo: [chaves...] | None}"""
    ents = app.cad.entradas()
    botoes = sorted(k for k, e in ents.items() if e["modo"] == "segurar")
    res = {a: (None if a else []) for a in alvos}
    pend = {a for a in alvos if a}
    if not pend:
        return res
    vistos = {frozenset(): []}
    fila = [[]]
    probes = 0
    while fila and pend and probes < max_probes:
        caminho = fila.pop(0)
        if len(caminho) >= profundidade:
            continue
        for b in botoes:
            if probes >= max_probes or not pend:
                break
            seq = caminho + [b]
            probes += 1
            app.reiniciar()
            for k in seq:
                app.pressionar(k, segurar_s=0.5)
                time.sleep(0.4)
            est = frozenset(_ativos(app.estado(f"_seq{probes:02d}.png")))
            app._log(f"seq {seq} -> {sorted(est)}")
            if est not in vistos:
                vistos[est] = seq
                fila.append(seq)
            for a in list(pend):
                if est == a:
                    res[a] = seq
                    pend.discard(a)
    return res


def executar_casos(cad, casos=None, saida=None, verbose=False, manter=False, ligar_disjuntores=False,
                   settle_s=0.7, aliases=None):
    """Roda `casos` (formato dos "testes" das specs) no APP e devolve pass/fail por caso.

    caso = {"nome","entradas":{"S1":true},"inicial":["KM1"],"esperado":["KM1"],"esperado_lampadas":["H1"],"status"}
    `esperado` e `esperado_lampadas` sao CONJUNTOS exatos de rotulos ativos (bobinas / lampadas).
    Caso com status 'RACE' nao e avaliavel no app (corrida): resultado 'ignorado' com o obtido.
    """
    t0 = time.time()
    casos = casos or []
    out = {"ok": False, "cad": str(cad), "casos": [], "avisos": [], "repouso": None, "tempo_s": None,
           "screenshots": str(saida or ROOT / "out" / "app_sim" / Path(cad).stem)}
    app = AppSim(cad, saida=saida, verbose=verbose)
    out["screenshots"] = str(app.saida)
    try:
        app.abrir()
        out["tempo_abrir_s"] = round(time.time() - t0, 1)
        app.play()
        app.zoom_todo()
        rep = app.estado("repouso.png")
        out["repouso"] = {"bobinas_ativas": sorted(_ativos(rep)),
                          "lampadas_acesas": sorted(k for k, v in rep["lampadas"].items() if v),
                          "calibracao": rep["calibracao"], "screenshot": rep["screenshot"],
                          "fora_da_janela": rep["fora_da_janela"]}
        if rep["fora_da_janela"]:
            out["avisos"].append(f"simbolos fora da janela (nao lidos): {rep['fora_da_janela']}")
        # estados iniciais que os casos pedem
        alvos = {frozenset(norm(k) for k in (c.get("inicial") or [])) for c in casos}
        seqs = descobrir_iniciais(app, alvos) if any(alvos) else {a: [] for a in alvos}
        todos_ok = True
        for i, c in enumerate(casos):
            nome = c.get("nome", f"caso{i}")
            r = {"nome": nome, "entradas": c.get("entradas") or {}, "inicial": c.get("inicial") or [],
                 "esperado": c.get("esperado"), "esperado_lampadas": c.get("esperado_lampadas"),
                 "status_pedido": c.get("status")}
            tc = time.time()
            try:
                alvo = frozenset(norm(k) for k in (c.get("inicial") or []))
                seq = seqs.get(alvo)
                app.reiniciar()
                if ligar_disjuntores:
                    for s in app.cad.simbolos:
                        if s["tipo"] == "disjuntor":
                            app.alternar(s["chave"], espera=0.3)
                if seq is None:
                    r.update(resultado="indeterminado", motivo=f"nao achei sequencia de botoes que leve a {sorted(alvo)}")
                    out["casos"].append(r)
                    todos_ok = False
                    continue
                for k in seq:
                    app.pressionar(k, segurar_s=0.5)
                    time.sleep(0.4)
                if seq and _ativos(app.estado("_pre.png")) != set(alvo):
                    r["aviso"] = "estado inicial nao reproduziu na repeticao"
                seg, varios = _executa_entradas(app, c.get("entradas"), aliases)
                time.sleep(settle_s)
                est = app.estado(f"caso{i:02d}_{_slug(nome)}.png")
                if seg:
                    app.soltar()
                obt = _ativos(est)
                obt_l = {k for k, v in est["lampadas"].items() if v}
                r["obtido"] = sorted(obt)
                r["obtido_lampadas"] = sorted(obt_l)
                r["motores_ativos"] = sorted(k for k, v in est["motores"].items() if v)
                r["screenshot"] = est["screenshot"]
                if varios:
                    r["aviso"] = "mais de uma botoeira: so a ultima fica pressionada (ponteiro unico)"
                ok = True
                if c.get("esperado") is not None:
                    ok = ok and obt == {norm(k) for k in c["esperado"]}
                if c.get("esperado_lampadas") is not None:
                    ok = ok and obt_l == {norm(k) for k in c["esperado_lampadas"]}
                if c.get("status") == "RACE":
                    r["resultado"] = "ignorado"
                    r["motivo"] = "status RACE (corrida) nao e avaliavel no app"
                else:
                    r["resultado"] = "ok" if ok else "falha"
                    todos_ok = todos_ok and ok
            except AppSimErro as e:
                inac = "nao o aciona" in str(e) or "sem simbolo acionavel" in str(e)
                r.update(resultado="nao_acionavel" if inac else "erro", motivo=str(e))
                todos_ok = False
            r["tempo_s"] = round(time.time() - tc, 1)
            out["casos"].append(r)
        out["ok"] = bool(casos) and todos_ok
    except AppSimErro as e:
        out["erro"] = str(e)
    finally:
        if not manter:
            app.fechar()
    out["tempo_s"] = round(time.time() - t0, 1)
    out["log"] = app.log_ev[-30:]
    return out


def _slug(s):
    return "".join(c if c.isalnum() else "_" for c in s)[:40]


# --------------------------------------------------------------------------- roteiro (evidencias por tempo)

def _ligados(d):
    return sorted(k for k, v in d.items() if v)


def executar_roteiro(cad, roteiro, saida=None, verbose=False, manter=False):
    """Roda um ROTEIRO no app e confere o estado em cada foto (CLP + ladder + lampadas). Retorna dict.

    roteiro = [passo...]; passo = {"op": ..., ...}:
      {"op":"alternar","alvo":"DJ1"}                     clique que alterna (disjuntor/termico). DJ1 ANTES de testar.
      {"op":"pressionar","alvo":"B1","segurar_s":0.6}    botoeira (mousedown, espera, mouseup)
      {"op":"segurar","alvo":"B1"} / {"op":"soltar"}
      {"op":"marca"}                                      zera o cronometro (t=0 das fotos)
      {"op":"esperar","s":1.0}
      {"op":"foto","nome":"t2","ate_s":2.0,"esperado":{"bobinas":["C1"],"lampadas":["H1"],"saidas_clp":["Q0.1"],
                                                       "bobinas_ladder":["Q0.1"]}}
          ate_s = espera ate esse instante do cronometro (se ainda nao passou); cada chave de `esperado` e comparada
          como CONJUNTO EXATO de ativos (so as chaves citadas).
    Sempre faz `down` do Wine ao final (a menos de manter=True)."""
    t0 = time.time()
    out = {"ok": False, "cad": str(cad), "passos": [], "fotos": [], "avisos": []}
    app = AppSim(cad, saida=saida, verbose=verbose)
    out["screenshots"] = str(app.saida)
    try:
        app.abrir()
        app.play()
        app.zoom_todo()
        app.estado("_calibra.png")
        marca = time.time()
        todos = True
        for i, p in enumerate(roteiro):
            op = p["op"]
            if op == "alternar":
                app.alternar(p["alvo"], espera=p.get("espera_s", 0.6))
            elif op == "pressionar":
                app.pressionar(p["alvo"], segurar_s=p.get("segurar_s", 0.6))
            elif op == "segurar":
                app.pressionar(p["alvo"], segurar_s=None)
            elif op == "soltar":
                app.soltar()
            elif op == "marca":
                marca = time.time()
            elif op == "esperar":
                time.sleep(float(p["s"]))
            elif op == "aguardar":
                # espera o estado (conjuntos exatos das chaves citadas) ou estoura timeout_s; registra o instante
                alvo, lim, ti = p["estado"], float(p.get("timeout_s", 8)), time.time()
                alcancou, obs = False, {}
                while time.time() - ti < lim:
                    img, _ = app.screenshot("_poll.png")
                    est = ler_estado(img, app.cad, app.cal)
                    obs = {"bobinas": _ligados(est["bobinas"]), "lampadas": _ligados(est["lampadas"]),
                           "saidas_clp": _ligados(est["saidas_clp"]), "bobinas_ladder": _ligados(est["bobinas_ladder"])}
                    if all(sorted(v) == obs.get(k) for k, v in alvo.items()):
                        alcancou = True
                        break
                if alcancou:                       # o quadro que satisfez a condicao vira a evidencia (nome do passo)
                    try:
                        shutil.copy(app.saida / "_poll.png", app.saida / f"{p.get('nome', f'aguardar{i}')}.png")
                    except OSError:
                        pass
                reg = {"nome": p.get("nome", f"aguardar{i}"), "tipo": "aguardar", "alcancou": alcancou,
                       "t_s": round(time.time() - marca, 2), "espera_s": round(time.time() - ti, 2), "obtido": obs,
                       "esperado": alvo, "ok": alcancou, "falhas": [] if alcancou else [f"timeout; obtido {obs}"]}
                if verbose:
                    print(f"[roteiro] aguardar {reg['nome']}: {'ok' if alcancou else 'TIMEOUT'} t={reg['t_s']}s", flush=True)
                out["fotos"].append(reg)
                todos = todos and alcancou
            elif op == "foto":
                if p.get("ate_s") is not None:
                    falta = float(p["ate_s"]) - (time.time() - marca)
                    if falta > 0:
                        time.sleep(falta)
                t_ini = time.time() - marca
                img, caminho = app.screenshot(f"{p['nome']}.png")
                t_cap = time.time() - marca
                est = ler_estado(img, app.cad, app.cal or calibrar(img, app.cad)) if (app.cal or True) else None
                obs = {"bobinas": _ligados(est["bobinas"]), "lampadas": _ligados(est["lampadas"]),
                       "saidas_clp": _ligados(est["saidas_clp"]), "bobinas_ladder": _ligados(est["bobinas_ladder"])}
                falhas = []
                for k, v in (p.get("esperado") or {}).items():
                    if sorted(v) != obs.get(k):
                        falhas.append(f"{k}: obtido {obs.get(k)} esperado {sorted(v)}")
                f = {"nome": p["nome"], "t_s": round(t_cap, 2), "obtido": obs, "esperado": p.get("esperado"),
                     "ok": not falhas, "falhas": falhas, "screenshot": str(caminho)}
                if verbose:
                    print(f"[roteiro] {f['nome']} t={f['t_s']}s {obs} {'OK' if not falhas else 'FALHA ' + str(falhas)}", flush=True)
                out["fotos"].append(f)
                todos = todos and not falhas
            else:
                raise AppSimErro(f"op desconhecida: {op}")
            out["passos"].append({"i": i, **{k: v for k, v in p.items() if k != "esperado"}, "t_s": round(time.time() - marca, 2)})
        out["ok"] = todos
    except AppSimErro as e:
        out["erro"] = str(e)
    finally:
        if not manter:
            app.fechar()
    out["tempo_s"] = round(time.time() - t0, 1)
    return out


# --------------------------------------------------------------------------- CLI

def _casos_de(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(d, list):
        return d
    return d.get("testes") or (d.get("layout") or {}).get("testes") or []


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cad")
    ap.add_argument("--layout", help="spec/layout/casos .json com a chave 'testes'")
    ap.add_argument("--roteiro", help="roteiro .json (lista de passos, veja executar_roteiro): fotos por instante")
    ap.add_argument("--saida", help="diretorio dos screenshots (default out/app_sim/<nome>)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--alias", action="append", default=[], metavar="ENTRADA=ROTULO",
                    help="atuador alternativo (ex.: RT1=F1: o caso 'RT1' dispara o termico F1)")
    ap.add_argument("--manter", action="store_true", help="nao dar down no fim")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    if a.roteiro:
        ro = json.loads(Path(a.roteiro).read_text(encoding="utf-8"))
        r = executar_roteiro(a.cad, ro["passos"] if isinstance(ro, dict) else ro, saida=a.saida, verbose=True, manter=a.manter)
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0 if r["ok"] else 1
    casos = _casos_de(a.layout) if a.layout else []
    aliases = dict(x.split("=", 1) for x in a.alias)
    r = executar_casos(a.cad, casos, saida=a.saida, verbose=a.verbose, manter=a.manter, aliases=aliases)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        if r.get("erro"):
            print("ERRO:", r["erro"])
        print(f"repouso: {r.get('repouso')}")
        for c in r["casos"]:
            print(f"  [{c.get('resultado','?'):>13}] {c['nome']}: obtido={c.get('obtido')} lamp={c.get('obtido_lampadas')} "
                  f"esperado={c.get('esperado')} ({c.get('tempo_s')}s) {c.get('motivo','')}")
        print(f"{'OK' if r['ok'] else 'FALHOU'} em {r['tempo_s']}s; screenshots em {r['screenshots']}")
    return 0 if r["ok"] or not casos else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
