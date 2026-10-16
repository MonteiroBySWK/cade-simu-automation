#!/usr/bin/env python3
"""Simulador funcional OFFLINE de circuitos CADe, fiel ao app (sem GUI).

Fidelidade (docs/re-engenharia.md 9.2 e 11):
- Conectividade por GEOMETRIA, nao pelos nets gravados no arquivo (nums[21]/[22] sao ignorados):
  fio-fio une so por EXTREMO coincidente; juncao 4001/4012 une ao fio cujo segmento a contem;
  pino de simbolo so liga a fio que TERMINA no ponto-pino (docs/pinos-binario.json + rotacao n17).
  Mesmas regras (e as mesmas funcoes de pinos) de tools/geo_check.py.
- Potencial por "char de fase": fontes (3000..3011) estampam L1->1, L2->2, L3->3, N->N, PE->P por pino.
  Fio + contato fechado = mesma net. Duas estampas diferentes na mesma net = CURTO (status "CURTO").
- Semantica por CLASSE vem de docs/classes-papeis.json (esquema real do RE: `contatos:[{pinos,
  fecha_quando}]`, `aciona_por`, `parametros`); os nomes de pino do JSON (11/12/13/14/A1/...) sao os da
  ordem de desenho = p1..pN de docs/pinos-binario.json. Tabela embutida e o fallback (arquivo ausente).
    contato(s)    cada par fecha por `estado==1|0|2|sempre` da PROPRIA entidade; o estado vem de:
                  - bobina / temporizador de MESMO ROTULO (2000..2008 e 7000..7003),
                  - saida do temporizador de mesmo rotulo (7004..7007<-9004, 7008..7011<-9005, 7012..7015<-9006),
                  - entrada externa (botoes 8000.., chaves, fusiveis 5000.., disjuntores 6000.. e o
                    relé termico 6007: seus contatos 8016..8019 seguem o MESMO rotulo).
                  Disjuntores/seccionadores/chaves comecam ABERTOS (estado 0, conduzem com 1); fusiveis
                  conduzem com estado 0; os polos do 6007 sempre conduzem.
    bobina        energiza quando um pino esta numa net com fase e o outro numa net com OUTRA estampa
    lampada       idem bobina, mas e so SAIDA observavel (nao realimenta o comando)
    temporizador  9004 ON-delay, 9005 OFF-delay, 9006 ON+OFF, 9007 intermitente: carga como a bobina;
                  tempo = atoi(rotulo 5) x unidade(rotulo 4: '3'=1 '0'=10 '1'=100 '2'=1000 ticks de 100 ms)
- Sem fonte no desenho (ladder 10050/10051/10060): cai no modelo legado (1o contato = fase, retorno comum
  das bobinas).

Esquema simplificado (legado, ainda aceito em {"classes": {"<id>": {...}}}), por classe:
  papel: contato|bobina|lampada|polos|contato_temp (aliases: na, nc, nf, ton, tof, sinalizador)
  modo: NA|NC|FECHADO      pinos: [pinoA, pinoB] (default: 2 primeiros do binario)
  tipo: ton|tof (contato_temp)   tempo: segundos fixos | tempo_label/tempo_num: indice do campo do .cad
  O tempo tambem pode vir do caso ("tempos": {rotulo: s}); sem valor, 0 s.

Estado de entradas: {chave: bool} (True = acionado: botao pressionado / termico disparado /
disjuntor ligado / fusivel queimado).

API:
  Circuito(path).resolve(ent, inicial=None)           -> (status, {bobinas})      (compat)
  Circuito(path).estado(ent, inicial=None, avanca=0)  -> {bobinas, lampadas, temporizadores, status, curtos}
  teste(path)  / teste_casos(path, casos)             -> bool
status in {OK, RACE, INSTAVEL, CURTO}.

Casos (teste_casos): {"nome","entradas":{k:bool},"inicial":[...],"esperado":[bobinas]|null,
  "esperado_lampadas":[...]|null,"esperado_temporizadores":[...]|null,"status":"OK"|"RACE"|"CURTO"|null,
  "avanca": segundos (alias "tempo"), "tempos": {rotulo: segundos},
  "passos": [{"entradas":{..},"avanca":s, + esperado*}, ...]}   # sequencia com estado persistente
`esperado_temporizadores` = temporizadores cuja SAIDA (contatos temporizados) esta ligada.

Uso:
  python3 tools/netlist_sim.py out/intercalada.cad            # imprime netlist (contatos, bobinas, lampadas)
  python3 tools/netlist_sim.py out/intercalada.cad --test     # roda a suite embutida (KM1/KM2)
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

T = Path(__file__).resolve().parent
sys.path.insert(0, str(T))
import geo_check as G  # noqa: E402
from dissect import parse_ent, split_all as split_entities  # noqa: E402

import re  # noqa: E402
import temporizador as TM  # noqa: E402

PAPEIS_JSON = T.parent / "docs" / "classes-papeis.json"
EPS = 1e-9

# --- tabela de papeis (embutida) ------------------------------------------------------------------
# Fallback quando docs/classes-papeis.json nao existe. Formas legadas (papel/modo) + 'elemento' (multi-contato).
_NA = {"papel": "contato", "modo": "NA"}
_NC = {"papel": "contato", "modo": "NC"}
PAPEIS_EMBUTIDOS = {
    **{c: dict(_NA) for c in ("8000", "8016", "7000", "10050")},
    **{c: dict(_NC) for c in ("8001", "8017", "7001", "10051")},
    **{c: {"papel": "bobina"} for c in ("9000", "10060")},
    "9008": {"papel": "lampada"},
    "2001": {"papel": "polos", "modo": "NA"},               # contatos principais do contator (rotulo = bobina)
    "6007": {"papel": "polos", "modo": "FECHADO"},          # termico: polos passam sempre; dispara por clique/rotulo
    **{c: {"papel": "polos", "modo": "NA"} for c in ("6009", "6010")},   # disjuntor: comeca ABERTO (liga por clique)
}


def _emb_elemento(fam, *pares, **extra):
    d = {"papel": "elemento", "fam": fam,
         "contatos": [{"pinos": [a, b], "cond": c} for a, b, c in pares]}
    d.update(extra)
    return d


def _embutidos_extra():
    t = {}
    for c, fam in (("7002", "rele"), ("8002", "ent"), ("8018", "ent")):        # NA-NC: 11-12 NC, 13-14 NA
        t[c] = _emb_elemento(fam, ("p1", "p3", "0"), ("p2", "p4", "1"))
    for c, fam in (("7003", "rele"), ("8003", "ent"), ("8019", "ent")):        # comutado: 11-12 NC, 11-14 NA
        t[c] = _emb_elemento(fam, ("p1", "p2", "0"), ("p1", "p3", "1"))
    for c, tipo in (("9004", "ton"), ("9005", "tof"), ("9006", "ton_tof"), ("9007", "intermitente")):
        t[c] = {"papel": "temporizador", "tipo": tipo, "pinos": ["p1", "p2"]}
    for base, tmr in (("7004", "9004"), ("7008", "9005"), ("7012", "9006")):
        n = int(base)
        t[str(n)] = _emb_elemento("tmp", ("p1", "p2", "1"), segue=[tmr, "9007"])
        t[str(n + 1)] = _emb_elemento("tmp", ("p1", "p2", "0"), segue=[tmr, "9007"])
    return t


PAPEIS_EMBUTIDOS.update(_embutidos_extra())

_PAPEIS_VALIDOS = {"contato", "bobina", "lampada", "polos", "contato_temp", "elemento", "temporizador"}
# contatos instantaneos que seguem bobina/temporizador de MESMO rotulo (RE 11.3); os demais seguem entrada externa
_REL = {"2000", "2001", "2002", "2006", "2008", "7000", "7001", "7002", "7003"}
_TIMER_DE_CONTATO = {**{str(c): "9004" for c in range(7004, 7008)}, **{str(c): "9005" for c in range(7008, 7012)},
                     **{str(c): "9006" for c in range(7012, 7016)}}
_TIMER_TIPO = {"temporizador_on": "ton", "temporizador_off": "tof", "temporizador_on_off": "ton_tof",
               "temporizador_intermitente": "intermitente"}
_NAO_MODELADOS = {"9001", "9002", "9015"}      # biestavel, telerruptor, gerador de pulsos: sem modelo (RE: baixa)
_COND = {"estado==1": "1", "estado==0": "0", "estado==2": "2", "sempre": "S"}
_PROTECOES = {str(c) for c in range(6000, 6021) if c != 6007} | {str(c) for c in range(5005, 5010)}


def _normalizar_papel(e):
    """Aceita a entrada do esquema SIMPLIFICADO (papel como string) -> dict interno ou None."""
    if not isinstance(e, dict):
        return None
    papel = str(e.get("papel") or e.get("role") or "").strip().lower()
    alias = {"na": ("contato", "NA"), "no": ("contato", "NA"), "nc": ("contato", "NC"), "nf": ("contato", "NC"),
             "contato_na": ("contato", "NA"), "contato_nc": ("contato", "NC"),
             "coil": "bobina", "lamp": "lampada", "sinalizador": "lampada",
             "ton": ("contato_temp", None), "tof": ("contato_temp", None)}
    r = dict(e)
    a = alias.get(papel, papel)
    if isinstance(a, tuple):
        r["papel"] = a[0]
        if a[1] and not r.get("modo"):
            r["modo"] = a[1]
        if papel in ("ton", "tof") and not r.get("tipo"):
            r["tipo"] = papel
    else:
        r["papel"] = a
    if r["papel"] not in _PAPEIS_VALIDOS:
        return None
    if r.get("modo"):
        r["modo"] = str(r["modo"]).upper().replace("NF", "NC").replace("NO", "NA")
    return r


def _nomes_pinos(cid):
    """Nomes de pino da classe na ordem de desenho (p1..pN do binario, ordem numerica)."""
    nomes = list(G.pinos_da_classe(cid))
    if nomes and all(re.fullmatch(r"p\d+", n) for n in nomes):
        nomes.sort(key=lambda n: int(n[1:]))
    return nomes


def _mapa_pinos(cid, nomes_json):
    """nomes do JSON do RE (11/13/A1...) -> nomes da tabela do binario, por POSICAO (RE: pinos = p1..pN)."""
    bin_ = _nomes_pinos(cid)
    if not bin_ or not nomes_json:
        return None
    if set(nomes_json) <= set(bin_):
        return {n: n for n in nomes_json}
    if len(nomes_json) == len(bin_):
        m = {}
        for j, b in zip(nomes_json, bin_):
            m.setdefault(j, b)
        return m
    return None


def _normalizar_real(cid, e):
    """Entrada do esquema REAL de docs/classes-papeis.json -> dict interno ou None (sem modelo eletrico)."""
    papel = str(e.get("papel") or "").strip().lower()
    nomes = [str(n) for n in (e.get("pinos") or [])]
    mapa = _mapa_pinos(cid, nomes)
    if mapa is None or cid in _NAO_MODELADOS:
        return None
    if papel in ("bobina", "lampada", "sinalizador") or papel in _TIMER_TIPO:
        if len(nomes) != 2 or mapa[nomes[0]] == mapa[nomes[1]]:
            return None
        par = [mapa[nomes[0]], mapa[nomes[1]]]
        if papel in _TIMER_TIPO:
            return {"papel": "temporizador", "tipo": _TIMER_TIPO[papel], "pinos": par}
        return {"papel": "bobina" if papel == "bobina" else "lampada", "pinos": par}
    cs = e.get("contatos") or []
    if not cs:
        return None
    contatos = []
    for c in cs:
        pa = [str(x) for x in (c.get("pinos") or [])]
        cond = _COND.get(str(c.get("fecha_quando", "")).replace(" ", ""))
        if len(pa) != 2 or cond is None or any(x not in mapa for x in pa):
            return None
        contatos.append({"pinos": [mapa[pa[0]], mapa[pa[1]]], "cond": cond})
    if papel.startswith("contato_temporizado"):
        fam = "tmp"
    elif cid in _REL:
        fam = "rele"
    else:
        fam = "ent"
    r = {"papel": "elemento", "fam": fam, "contatos": contatos}
    if fam == "tmp":
        r["segue"] = [_TIMER_DE_CONTATO.get(cid, "9004"), "9007"]
    return r


def _eh_real(e):
    return any(k in e for k in ("contatos", "aciona_por", "evidencia", "aba", "designacao_padrao"))


def carregar_papeis(path=None):
    """Tabela classe -> modelo. Parte da embutida e e SOBREPOSTA por docs/classes-papeis.json (esquema real do
    RE ou o simplificado em {"classes": ...}); entradas sem modelo eletrico usavel (logica, GRAFCET, PLC...)
    mantem a embutida."""
    tab = {k: dict(v) for k, v in PAPEIS_EMBUTIDOS.items()}
    p = Path(path) if path else PAPEIS_JSON
    if p.is_file():
        try:
            raw = json.loads(p.read_text())
        except (OSError, ValueError):
            return tab
        if not isinstance(raw, dict):
            return tab
        classes = raw["classes"] if isinstance(raw.get("classes"), dict) else raw
        for cid, e in classes.items():
            if str(cid).startswith("_") or not isinstance(e, dict):
                continue
            cid = str(cid)
            if _eh_real(e):
                n = _normalizar_real(cid, e)
            else:
                n = _normalizar_papel(e)
                if n:
                    conhecidos = set(G.pinos_da_classe(cid))
                    if n.get("pinos") and not set(n["pinos"]) <= conhecidos:
                        n.pop("pinos")       # nome de pino que a tabela do binario nao conhece
            if n:
                tab[cid] = n
    return tab


def _nome(rot):
    return (rot or "").lstrip("-").strip()


def _segundos(v):
    """'5', '5s', '2,5' -> float; None se nao der."""
    try:
        return float(str(v).strip().lower().rstrip("s").replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


class _Temp:
    """Temporizador em tempo CONTINUO (segundos). tipos: ton, tof, ton_tof, intermitente.
    `legado`: contato temporizado que embute o proprio tempo (esquema simplificado), T pode ser 0 s."""
    __slots__ = ("tipo", "T", "saida", "el", "fase", "legado")

    def __init__(self, tipo, T, legado=False):
        self.tipo, self.T, self.legado = tipo, float(T), legado
        self.saida = False
        self.el = 0.0
        self.fase = True                    # intermitente: meio-periodo corrente (True = estado 1)

    def estado(self, ativo):
        """estado visto por contatos instantaneos/polos de mesmo rotulo."""
        return bool(ativo) and (self.fase if self.tipo == "intermitente" else True)

    def aplicar(self, ativo):
        """efeitos instantaneos / de tempo zero. True se algo observavel mudou."""
        mud, t = False, self.tipo
        if t == "ton":
            if not ativo:
                self.el = 0.0
                if self.saida:
                    self.saida, mud = False, True
            elif not self.saida and self.el >= self.T - EPS:
                self.saida, mud = True, True
        elif t == "tof":
            if ativo:
                self.el = 0.0
                if not self.saida:
                    self.saida, mud = True, True
            elif self.saida and self.el >= self.T - EPS:
                self.saida, mud = False, True
        elif t == "ton_tof":
            if self.saida == bool(ativo):
                self.el = 0.0
            elif self.el >= self.T - EPS:
                self.saida, self.el, mud = bool(ativo), 0.0, True
        else:                               # intermitente
            if not ativo:
                self.el = 0.0
                if not self.fase:
                    self.fase, mud = True, True
            elif self.el >= self.T - EPS:
                self.fase, self.el, mud = (not self.fase), 0.0, True
        return mud

    def proximo(self, ativo):
        """tempo ate a proxima mudanca (None se nada esta correndo)."""
        t = self.tipo
        if (t == "ton" and ativo and not self.saida) or (t == "tof" and not ativo and self.saida) \
                or (t == "ton_tof" and self.saida != bool(ativo)) or (t == "intermitente" and ativo):
            return max(self.T - self.el, 0.0)
        return None

    def passo(self, ativo, dt):
        """avanca dt (<= proximo). True se uma saida mudou."""
        t = self.tipo
        if t == "ton":
            if ativo:
                self.el += dt
                if not self.saida and self.el >= self.T - EPS:
                    self.saida = True
                    return True
        elif t == "tof":
            if not ativo and self.saida:
                self.el += dt
                if self.el >= self.T - EPS:
                    self.saida = False
                    return True
        elif t == "ton_tof":
            if self.saida != bool(ativo):
                self.el += dt
                if self.el >= self.T - EPS:
                    self.saida, self.el = bool(ativo), 0.0
                    return True
        elif ativo:
            self.el += dt
            if self.el >= self.T - EPS:
                self.fase, self.el = (not self.fase), 0.0
                return True
        return False


class Circuito:
    def __init__(self, path, papeis=None, tick=TM.TICK_PADRAO):
        self.papeis = papeis if papeis is not None else carregar_papeis()
        self.tick = float(tick)
        d = Path(path).read_bytes().decode("latin1")
        _, ents, _ = split_entities(d)
        ps = [p for p in map(parse_ent, ents) if p and len(p["nums"]) > 17]
        find, extremos = self._geometria(ps)
        ids = {}                                   # raiz geometrica -> id inteiro (1..)

        def nid(pt):
            r = find(pt)
            if r not in ids:
                ids[r] = len(ids) + 1
            return ids[r]

        fresh = [100000]

        def solto():
            fresh[0] += 1
            return fresh[0]

        self.contatos = []     # (tipo 'NO'/'NC', A, B, chave) — contatos NA/NC (compat/tabela)
        self.bobinas = {}      # chave -> (A, B) da 1a ocorrencia
        self.lampadas = {}     # chave -> (A, B)
        self.entradas = []     # chaves externas (botoes/termicos/disjuntores)
        self.soltos = []       # pinos de papel funcional sem fio no ponto
        self.fixos = []        # (no, char de fase) estampados pelas fontes
        self._bob = []         # (chave, A, B) por instancia
        self._lamp = []
        self._cont = []        # dicts: chave, a, b, cond('1','0','2','S'), fam, cid, temp(None|legado), segue
        self._polos = []       # (legado) dicts: chave, modo, pares
        self._tmr = []         # temporizadores reais: dicts id, chave, a, b, cid, tipo, ticks
        for p in ps:
            cid = p["id"]
            if cid in G.SKIP:
                continue
            x, y, o = int(p["nums"][8]), int(p["nums"][9]), int(p["nums"][17] or 0)
            rot = (p["labels"] or [""])[0]
            chave = _nome(rot) or cid
            papel = self.papeis.get(cid)
            pinos = {}                              # nome -> (no, ligado)
            offs = G.pinos_da_classe(cid)
            for nome, (dx, dy) in offs.items():
                rx, ry = G._rot(dx, dy, o)
                pt = (x + rx, y + ry)
                if pt in extremos:
                    pinos[nome] = (nid(pt), True)
                else:
                    pinos[nome] = (solto(), False)
            if cid in G.FONTE:
                for nome, (no, lig) in pinos.items():
                    if lig and nome in G.CHAR:
                        self.fixos.append((no, G.CHAR[nome]))
                continue
            if not papel:
                continue
            kind = papel["papel"]
            nomes = list(offs)

            def marca_soltos(usados):
                for nm in usados:
                    if not pinos[nm][1]:
                        self.soltos.append(f"{rot or cid}({cid}).{nm}")

            if kind == "elemento":
                usados = []
                for c in papel["contatos"]:
                    usados += [n for n in c["pinos"] if n not in usados]
                if any(n not in pinos for n in usados):
                    continue
                marca_soltos(usados)
                for c in papel["contatos"]:
                    self._cont.append({"chave": chave, "a": pinos[c["pinos"][0]][0], "b": pinos[c["pinos"][1]][0],
                                       "cond": c["cond"], "fam": papel.get("fam", "ent"), "cid": cid, "temp": None,
                                       "segue": set(papel.get("segue") or ())})
                continue
            if kind == "temporizador":
                par = papel.get("pinos") or nomes[:2]
                if len(par) < 2 or par[0] not in pinos or par[1] not in pinos:
                    continue
                marca_soltos(par[:2])
                lab = list(p["labels"]) + [""] * 8
                self._tmr.append({"chave": chave, "a": pinos[par[0]][0], "b": pinos[par[1]][0], "cid": cid,
                                  "tipo": papel.get("tipo", _TIMER_TIPO_CLASSE.get(cid, "ton")),
                                  "ticks": TM.ticks_dos_rotulos(lab[TM.IDX_UNIDADE], lab[TM.IDX_TEMPO])})
                continue
            par = papel.get("pinos") or nomes[:2]
            a = b = None
            if kind in ("contato", "bobina", "lampada", "contato_temp"):
                if len(par) < 2 or par[0] not in pinos or par[1] not in pinos:
                    continue
                a, b = pinos[par[0]][0], pinos[par[1]][0]
                marca_soltos(par[:2])
            if kind == "bobina":
                self._bob.append((chave, a, b))
                self.bobinas.setdefault(chave, (a, b))
            elif kind == "lampada":
                self._lamp.append((chave, a, b))
                self.lampadas.setdefault(chave, (a, b))
            elif kind == "contato":
                self._cont.append({"chave": chave, "a": a, "b": b, "cond": "0" if papel.get("modo") == "NC" else "1",
                                   "fam": "any", "cid": cid, "temp": None, "segue": set()})
            elif kind == "contato_temp":
                self._cont.append({"chave": chave, "a": a, "b": b, "cond": "0" if papel.get("modo") == "NC" else "1",
                                   "fam": "any", "cid": cid, "segue": set(),
                                   "temp": {"tipo": str(papel.get("tipo", "ton")).lower(),
                                            "tempo": self._tempo_do_simbolo(p, papel)}})
            elif kind == "polos":
                modo = papel.get("modo", "NA")
                for pa, pb in self._pares_polos(offs, pinos):
                    self._cont.append({"chave": chave, "a": pa, "b": pb,
                                       "cond": "S" if modo == "FECHADO" else ("0" if modo == "NC" else "1"),
                                       "fam": "any", "cid": cid, "temp": None, "segue": set()})
        # ids unicos: contatos temporizados legados e temporizadores reais (estado de tempo e por instancia)
        for lista, sel in ((self._cont, lambda c: c["temp"]), (self._tmr, lambda c: True)):
            total, vistos = defaultdict(int), defaultdict(int)
            for c in lista:
                if sel(c):
                    total[c["chave"]] += 1
            for c in lista:
                if sel(c):
                    vistos[c["chave"]] += 1
                    c["id"] = c["chave"] if total[c["chave"]] == 1 else f"{c['chave']}#{vistos[c['chave']]}"
        self._tkeys = defaultdict(list)             # chave -> ids de temporizadores reais com esse rotulo
        for t in self._tmr:
            self._tkeys[t["chave"]].append(t["id"])
        self.temporizadores = {t["id"]: t["chave"] for t in self._tmr}
        self.contatos = [("NC" if c["cond"] == "0" else "NO", c["a"], c["b"], c["chave"])
                         for c in self._cont if c["cond"] in ("1", "0")]
        nomes_bob = set(self.bobinas)

        def eh_entrada(c):
            if c["temp"] or c["fam"] == "tmp":
                return bool(c["temp"]) and c["chave"] not in nomes_bob
            if c["cond"] == "S":
                return False
            if c["fam"] in ("rele", "any"):
                return c["chave"] not in nomes_bob and c["chave"] not in self._tkeys
            return True
        self.entradas = sorted({c["chave"] for c in self._cont if eh_entrada(c)})
        # fonte / retorno
        self._legado = not self.fixos
        if self._legado:                            # ladder / sem fonte: 1o contato = fase, retorno = B comum das bobinas
            self.supply = self._cont[0]["a"] if self._cont else None
            cont = defaultdict(int)
            for _, _, b in self._bob:
                cont[b] += 1
            self.ret = max(cont, key=cont.get) if cont else None
            self.fixos = [(n, ch) for n, ch in ((self.supply, "1"), (self.ret, "N")) if n is not None]
        else:
            self.supply = next((n for ch in "123" for n, c in self.fixos if c == ch), None)
            self.ret = next((n for n, c in self.fixos if c == "N"), None)
        # protecoes (disjuntores/seccionadores): rotulos que o autor de teste precisa fechar para dar tensao
        self.protecoes = sorted({_nome((p["labels"] or [""])[0]) or p["id"] for p in ps if p["id"] in _PROTECOES})

    # --- geometria (regras de geo_check / re-engenharia 9.2) ---------------------------------------
    @staticmethod
    def _geometria(ps):
        parent = {}

        def find(a):
            parent.setdefault(a, a)
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        fios = []
        for p in ps:
            if p["id"] in G.WIRE:
                a = (int(p["nums"][8]), int(p["nums"][9]))
                b = (int(p["nums"][10]), int(p["nums"][11]))
                fios.append((a, b))
                union(a, b)
        for p in ps:                                # juncao 4001 / 4012
            if p["id"] in ("4001", "4012"):
                pt = (int(p["nums"][8]), int(p["nums"][9]))
                find(pt)
                for a, b in fios:
                    x1, y1, x2, y2 = min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])
                    if (y1 == y2 == pt[1] and x1 <= pt[0] <= x2) or (x1 == x2 == pt[0] and y1 <= pt[1] <= y2):
                        union(pt, a)
        extremos = {pt for a, b in fios for pt in (a, b)}
        return find, extremos

    @staticmethod
    def _pares_polos(offs, pinos):
        """Polos de um multipolar: pinos de mesmo dx (rotacao 0) pareados por dy crescente (1-2, 3-4, 5-6)."""
        col = defaultdict(list)
        for nome, (dx, dy) in offs.items():
            if nome in pinos:
                col[dx].append((dy, nome))
        pares = []
        for dx in sorted(col):
            ordem = [n for _, n in sorted(col[dx])]
            for i in range(0, len(ordem) - 1, 2):
                pares.append((pinos[ordem[i]][0], pinos[ordem[i + 1]][0]))
        return pares

    @staticmethod
    def _tempo_do_simbolo(p, papel):
        """Tempo ajustado no proprio simbolo (campo indicado em classes-papeis.json) ou None."""
        for chave, fonte in (("tempo", None), ("tempo_label", p["labels"]), ("tempo_num", p["nums"])):
            v = papel.get(chave)
            if v is None:
                continue
            if fonte is None:
                return _segundos(v)
            try:
                return _segundos(fonte[int(v)])
            except (IndexError, ValueError, TypeError):
                return None
        return None

    # --- avaliacao combinacional -------------------------------------------------------------------
    @staticmethod
    def _val(v):
        return int(v) if isinstance(v, (bool, int)) else (1 if v else 0)

    def _estado(self, c, ent, coil, tact, tobj):
        """estado (0/1/2) da entidade do contato, segundo a familia (RE 11.3)."""
        if c["temp"]:                                                # contato temporizado legado
            return 1 if tobj[c["id"]].saida else 0
        k, fam = c["chave"], c["fam"]
        if fam == "tmp":                                             # saida do temporizador de mesmo rotulo
            for i in self._tkeys.get(k, ()):
                t = tobj[i]
                tp = next(x for x in self._tmr if x["id"] == i)
                if tp["cid"] in c["segue"]:
                    if tp["tipo"] == "intermitente":
                        if t.estado(tact.get(i, False)):
                            return 1
                    elif t.saida:
                        return 1
            return 0
        if fam in ("rele", "any"):
            if k in coil:
                return 1 if coil[k] else 0
            ids = self._tkeys.get(k)
            if ids:
                return 1 if any(tobj[i].estado(tact.get(i, False)) for i in ids) else 0
        return self._val(ent.get(k, False))

    def _avaliar(self, ent, coil, tact, tobj):
        """Uma passada: une redes por contatos fechados, estampa fases, energiza bobinas/lampadas/temporizadores.
        -> (novo_coil, novo_tact, lampadas_on, curtos)."""
        parent = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[ry] = rx

        for c in self._cont:
            cond = c["cond"]
            if cond == "S":
                fechado = True
            elif c["temp"]:
                fechado = (self._estado(c, ent, coil, tact, tobj) == 1) if cond == "1" else \
                    (self._estado(c, ent, coil, tact, tobj) == 0)
            else:
                fechado = self._estado(c, ent, coil, tact, tobj) == int(cond)
            if fechado:
                union(c["a"], c["b"])
        chars = defaultdict(set)
        for no, ch in self.fixos:
            chars[find(no)].add(ch)

        def energizado(a, b):
            sa, sb = chars.get(find(a), set()) - {"P"}, chars.get(find(b), set()) - {"P"}
            return bool(sa and sb and sa != sb)

        novo = {k: False for k in self.bobinas}
        for k, a, b in self._bob:
            if energizado(a, b):
                novo[k] = True
        ntact = {t["id"]: energizado(t["a"], t["b"]) for t in self._tmr}
        lamp = {k for k, a, b in self._lamp if energizado(a, b)}
        curtos = sorted("+".join(sorted(s)) for s in chars.values() if len(s) > 1)
        return novo, ntact, lamp, curtos

    def _assentar(self, ent, coil, tact, tobj):
        """Relaxa a logica ate o ponto fixo (selo/intertravamento). -> (status, coil, tact, lampadas, curtos)."""
        vistos = set()
        lamp, curtos = set(), []
        for _ in range(40):
            novo, ntact, lamp, curtos = self._avaliar(ent, coil, tact, tobj)
            if novo == coil and ntact == tact:
                return ("CURTO" if curtos else "OK"), novo, ntact, lamp, curtos
            assin = (tuple(sorted(k for k, v in novo.items() if v)), tuple(sorted(k for k, v in ntact.items() if v)))
            if assin in vistos:
                return "RACE", novo, ntact, lamp, curtos
            vistos.add(assin)
            coil, tact = novo, ntact
        return "INSTAVEL", coil, tact, lamp, curtos

    # --- tempo (ON/OFF-delay, intermitente) --------------------------------------------------------
    def _timers(self, tempos=None):
        """{id: {chave, tipo, tempo(s), real}} — contatos temporizados legados + temporizadores 9004..9007."""
        tp = tempos or {}
        t = {}
        for c in self._cont:
            if c["temp"]:
                tempo = tp.get(c["id"], tp.get(c["chave"], c["temp"]["tempo"]))
                t[c["id"]] = {"chave": c["chave"], "tipo": c["temp"]["tipo"],
                              "tempo": float(tempo) if tempo is not None else 0.0, "real": False}
        for r in self._tmr:
            tempo = tp.get(r["id"], tp.get(r["chave"]))
            seg = float(tempo) if tempo is not None else max(r["ticks"], 1) * self.tick
            t[r["id"]] = {"chave": r["chave"], "tipo": r["tipo"], "tempo": seg, "real": True}
        return t

    def _ativos(self, ent, coil, tact):
        out = {}
        for c in self._cont:
            if c["temp"]:
                out[c["id"]] = (coil[c["chave"]] if c["chave"] in coil else bool(ent.get(c["chave"], False)))
        for r in self._tmr:
            out[r["id"]] = bool(tact.get(r["id"], False))
        return out

    def novo_estado(self, inicial=None, tempos=None):
        """Estado persistente (bobinas ligadas, temporizadores) para passos sucessivos."""
        ini = set(inicial or ())
        tim = self._timers(tempos)
        coil = {k: (k in ini) for k in self.bobinas}
        tobj = {}
        for i, t in tim.items():
            o = _Temp(t["tipo"], t["tempo"], legado=not t["real"])
            if i in ini or t["chave"] in ini:
                o.saida = True
                if o.tipo == "ton":
                    o.el = o.T
            tobj[i] = o
        tact = {r["id"]: (r["id"] in ini or r["chave"] in ini) for r in self._tmr}   # `inicial` = ja energizado
        return {"coil": coil, "tact": tact, "tobj": tobj, "tim": tim}

    def avancar(self, st, ent, avanca=0.0):
        """Aplica `ent` constante por `avanca` s sobre o estado `st` (mutado). -> dict de estado()."""
        tobj = st["tobj"]
        status, coil, tact, lamp, curtos = self._assentar(ent, st["coil"], st["tact"], tobj)
        restante = float(avanca or 0.0)
        for _ in range(100000):
            if not tobj or status in ("RACE", "INSTAVEL"):
                break
            ativo = self._ativos(ent, coil, tact)
            mud = False
            for i, t in tobj.items():
                mud = t.aplicar(ativo[i]) or mud
            if mud:                                              # efeitos instantaneos (TOF liga, tempo 0, ...)
                status, coil, tact, lamp, curtos = self._assentar(ent, coil, tact, tobj)
                continue
            if restante <= EPS:
                break
            evs = [e for e in (t.proximo(ativo[i]) for i, t in tobj.items()) if e is not None]
            dt = restante if not evs else min(restante, min(evs))
            if dt <= 0:
                break
            for i, t in tobj.items():
                mud = t.passo(ativo[i], dt) or mud
            restante -= dt
            if mud:
                status, coil, tact, lamp, curtos = self._assentar(ent, coil, tact, tobj)
        st["coil"], st["tact"] = coil, tact
        tem = {}
        for i, t in tobj.items():
            info = st["tim"][i]
            est = t.estado(tact.get(i, False))
            tem[i] = {"tipo": t.tipo, "tempo": t.T, "decorrido": round(t.el, 6),
                      "saida": est if t.tipo == "intermitente" else t.saida}
            if info["real"]:
                tem[i]["estado"] = est            # o que os contatos instantaneos/polos de mesmo rotulo veem
        return {"status": status, "bobinas": sorted(k for k, v in coil.items() if v),
                "lampadas": sorted(lamp), "temporizadores": tem, "curtos": curtos}

    # --- API publica -------------------------------------------------------------------------------
    def estado(self, ent, inicial=None, avanca=0.0, tempos=None):
        """{status, bobinas:[...], lampadas:[...], temporizadores:{id:{tipo,tempo,decorrido,saida,estado}},
        curtos:[...]}. `avanca` em segundos (1 tick = 100 ms)."""
        return self.avancar(self.novo_estado(inicial, tempos), ent, avanca)

    def resolve(self, ent, inicial=None, avanca=0.0, tempos=None):
        """ent: {chave: bool} (True = acionado). inicial: bobinas ja energizadas.
        Retorna (status, set) onde status in {'OK','RACE','INSTAVEL','CURTO'}."""
        e = self.estado(ent, inicial, avanca, tempos)
        return e["status"], set(e["bobinas"])

    def ligar_protecoes(self, ent=None):
        """copia de `ent` com os disjuntores/seccionadores FECHADOS (eles comecam abertos no app)."""
        r = dict(ent or {})
        for k in self.protecoes:
            r.setdefault(k, True)
        return r


_TIMER_TIPO_CLASSE = {"9004": "ton", "9005": "tof", "9006": "ton_tof", "9007": "intermitente"}


def tabela(path):
    c = Circuito(path)
    print(f"# {path} | supply={c.supply} retorno={c.ret}"
          f"{' (legado: sem fonte no desenho)' if c._legado else ''}")
    print("contatos:", [(t, a, b, k) for t, a, b, k in c.contatos])
    print("bobinas:", c.bobinas, "| entradas:", c.entradas)
    print("lampadas:", c.lampadas)
    tim = c._timers()
    if tim:
        print("temporizadores:", tim)
    if c.soltos:
        print("pinos soltos:", c.soltos)
    return c


def _confere(cs, e):
    """Compara so os campos esperados presentes no caso."""
    cond = True
    if cs.get("status") is not None:
        cond = cond and e["status"] == cs["status"]
    if cs.get("esperado") is not None:
        cond = cond and set(e["bobinas"]) == set(cs["esperado"])
    if cs.get("esperado_lampadas") is not None:
        cond = cond and set(e["lampadas"]) == set(cs["esperado_lampadas"])
    if cs.get("esperado_temporizadores") is not None:
        on = {i for i, t in e["temporizadores"].items() if t["saida"]}
        cond = cond and on == set(cs["esperado_temporizadores"])
    return cond


def chaves_invalidas(c, cs):
    """Chaves citadas por um caso que nao existem no circuito -> [(campo, chave)].
    Teste com chave inexistente seria vacuo (falso verde): o chamador deve reprovar."""
    tim = c._timers()
    ruim = []
    for b in [cs] + list(cs.get("passos") or []):
        for k in (b.get("entradas") or {}):
            if k not in c.entradas and k not in c.bobinas:
                ruim.append(("entradas", k))
        for campo, validas in (("inicial", set(c.bobinas) | set(tim) | {t["chave"] for t in tim.values()}),
                               ("esperado", set(c.bobinas)), ("esperado_lampadas", set(c.lampadas)),
                               ("esperado_temporizadores", set(tim))):
            for k in (b.get(campo) or []):
                if k not in validas:
                    ruim.append((campo, k))
    return ruim


def executar_caso(c, cs):
    """Executa um caso (simples ou com `passos`) -> (aprovado, estado_final)."""
    st = c.novo_estado(cs.get("inicial", []), cs.get("tempos"))
    passos = cs.get("passos")
    if passos:
        cond, e = True, None
        for p in passos:
            e = c.avancar(st, p.get("entradas", {}), p.get("avanca", p.get("tempo", 0)))
            cond = cond and _confere(p, e)
        return cond and _confere(cs, e), e
    e = c.avancar(st, cs.get("entradas", {}), cs.get("avanca", cs.get("tempo", 0)))
    return _confere(cs, e), e


def teste_casos(path, casos):
    """Roda casos declarados na spec (ver docstring do modulo). True se todos passam.
    Linha: `[OK |FALHA] nome: KM=[...] status=S esperado=[...]` (+ lampadas/temporizadores quando usados)."""
    c = Circuito(path)
    ok = 0
    for cs in casos:
        cond, e = executar_caso(c, cs)
        ok += cond
        extra = ""
        if cs.get("esperado_lampadas") is not None or e["lampadas"]:
            extra += f" lampadas={e['lampadas']} esperado_lampadas={cs.get('esperado_lampadas')}"
        if cs.get("esperado_temporizadores") is not None:
            on = sorted(i for i, t in e["temporizadores"].items() if t["saida"])
            extra += f" temporizadores={on} esperado_temporizadores={cs.get('esperado_temporizadores')}"
        print(f"  [{'OK ' if cond else 'FALHA'}] {cs.get('nome', '?')}: KM={e['bobinas']} status={e['status']} "
              f"esperado={cs.get('esperado')}{extra}")
    print(f"RESULTADO: {ok}/{len(casos)} OK")
    return bool(casos) and ok == len(casos)


def teste(path):
    c = Circuito(path)
    ok = 0
    tot = 0

    def check(nome, ent, esperado=None, st=None, inicial=None):
        nonlocal ok, tot
        tot += 1
        status, got = c.resolve(ent, inicial)
        cond = True
        if st is not None:
            cond = cond and status == st
        if esperado is not None:
            cond = cond and got == set(esperado)
        ok += cond
        extra = f" status={status}" if st is not None else ""
        print(f"  [{'OK ' if cond else 'FALHA'}] {nome}: KM={sorted(got)}{extra} "
              f"esperado={sorted(esperado) if esperado is not None else '-'}")

    S1, S2, S0 = "S1", "S2", "S0"
    RT1, RT2 = "RT1", "RT2"
    # 1) S1 liga KM1
    check("S1 liga KM1", {S1: True}, ["KM1"], st="OK")
    # 2) intertravamento (sequencial): KM1 já ligado, aperta S2 -> KM2 NÃO entra
    check("KM2 bloqueado com KM1 ligado", {S2: True}, ["KM1"], st="OK", inicial={"KM1"})
    # 3) e o inverso: KM2 ligado, aperta S1 -> KM1 NÃO entra
    check("KM1 bloqueado com KM2 ligado", {S1: True}, ["KM2"], st="OK", inicial={"KM2"})
    # 4) selo (memória): KM1 ligado e nada acionado -> KM1 permanece
    check("selo mantém KM1", {}, ["KM1"], st="OK", inicial={"KM1"})
    # 5) S0 (NF, desliga) -> tudo cai
    check("S0 desliga tudo", {S0: True}, [], st="OK", inicial={"KM1"})
    # 6) S0 não é auto-religamento: soltar S0 não religa
    check("sem auto-religamento", {}, [], st="OK", inicial=set())
    # 7) térmico RT1 aberto barra a permissão
    check("RT1 aberto bloqueia", {RT1: True, S1: True}, [], st="OK")
    # 8) térmico RT2 aberto barra
    check("RT2 aberto bloqueia", {RT2: True, S1: True}, [], st="OK")
    # 9) pressão simultânea = corrida (relés) -> solver detecta
    check("S1+S2 simultâneo = corrida", {S1: True, S2: True}, None, st="RACE")
    # 10) caminho simétrico: S2 liga KM2
    check("S2 liga KM2", {S2: True}, ["KM2"], st="OK")
    # 11) selo mantém KM2
    check("selo mantém KM2", {}, ["KM2"], st="OK", inicial={"KM2"})
    # 12) S0 desliga vindo de KM2
    check("S0 desliga (de KM2)", {S0: True}, [], st="OK", inicial={"KM2"})
    # 13) RT1 aberto barra o caminho S2 também
    check("RT1 aberto bloqueia S2", {RT1: True, S2: True}, [], st="OK")
    # 14) RT2 aberto barra o caminho S2 também
    check("RT2 aberto bloqueia S2", {RT2: True, S2: True}, [], st="OK")
    # 15) estado vazio não energiza nada
    check("repouso = tudo desligado", {}, [], st="OK")
    print(f"RESULTADO: {ok}/{tot} OK")
    return ok == tot


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); raise SystemExit(2)
    args = [a for a in sys.argv[1:] if a != "--test"]
    if "--test" in sys.argv:
        ok = teste(args[0])
        raise SystemExit(0 if ok else 1)
    tabela(args[0])
