#!/usr/bin/env python3
"""Simulador funcional OFFLINE de circuitos CADe, fiel ao app (sem GUI).

Fidelidade (docs/re-engenharia.md 9.2):
- Conectividade por GEOMETRIA, nao pelos nets gravados no arquivo (nums[21]/[22] sao ignorados):
  fio-fio une so por EXTREMO coincidente; juncao 4001/4012 une ao fio cujo segmento a contem;
  pino de simbolo so liga a fio que TERMINA no ponto-pino (docs/pinos-binario.json + rotacao n17).
  Mesmas regras (e as mesmas funcoes de pinos) de tools/geo_check.py.
- Potencial por "char de fase": fontes (3000..3011) estampam L1->1, L2->2, L3->3, N->N, PE->P por pino.
  Fio + contato fechado = mesma net. Duas estampas diferentes na mesma net = CURTO (status "CURTO").
- Modelo por PAPEL de classe (tabela embutida; docs/classes-papeis.json, quando existe, tem precedencia):
    contato      NA/NC de 2 pinos, comandado pelo rotulo (bobina de mesmo rotulo ou entrada externa)
    bobina       energiza quando um pino esta numa net com fase e o outro numa net com OUTRA estampa
    lampada      idem bobina, mas e so SAIDA observavel (nao realimenta o comando)
    polos        contatos de potencia multipolares (2001 contator; 6007/6009/6010 passam sempre)
    contato_temp contato temporizado 7004..7015: segue o temporizador-carga de mesmo
                 rotulo (tipo do timer; sem timer, tipo pela faixa da classe e contagem
                 propria); avanca por passos de tempo
    temporizador carga A1/A2 9004 (ton) / 9005 (tof) / 9006 (tonof) / 9007 (intermitente):
                 tempo = atoi(label5) x mult(label4) ticks de 100 ms; 9015 (pulso) sem modelo
- Sem fonte no desenho (ladder 10050/10051/10060): cai no modelo legado (1o contato = fase, retorno comum
  das bobinas).

Esquema aceito em docs/classes-papeis.json ({"classes": {"<id>": {...}}}), por classe:
  papel: contato|bobina|lampada|polos|contato_temp|temporizador (aliases: na, nc, nf, ton, tof,
    temporizador_ON/OFF/ON_OFF/intermitente, contato_temporizado_NA/NC/NA_NC/comutado)
  modo: NA|NC|FECHADO      pinos: [pinoA, pinoB] (default: 2 primeiros do binario)
  tipo: ton|tof|tonof|intermitente (contato_temp; default pela faixa 7004..7015) ou
    temporizador (default ton)   tempo: segundos fixos | tempo_label/tempo_num: indice do campo do .cad
  O tempo tambem pode vir do caso ("tempos": {rotulo: s}); sem valor, 0 s.
  Temporizador-carga (9004..9007): tempo proprio = atoi(label5) x mult(label4) ticks de 100 ms
  (label4 '3'->x1, '0'->x10, '1'->x100, '2'->x1000).

Estado de entradas: {chave: bool} (True = acionado: botao pressionado / termico disparado).

API:
  Circuito(path).resolve(ent, inicial=None)           -> (status, {bobinas})      (compat)
  Circuito(path).estado(ent, inicial=None, avanca=0)  -> {bobinas, lampadas, temporizadores, status, curtos}
  teste(path)  / teste_casos(path, casos)             -> bool
status in {OK, RACE, INSTAVEL, CURTO}.

Casos (teste_casos): {"nome","entradas":{k:bool},"inicial":[...],"esperado":[bobinas]|null,
  "esperado_lampadas":[...]|null,"esperado_temporizadores":[...]|null,"status":"OK"|"RACE"|"CURTO"|null,
  "avanca": segundos (alias "tempo"), "tempos": {rotulo: segundos},
  "passos": [{"entradas":{..},"avanca":s, + esperado*}, ...]}   # sequencia com estado persistente

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

PAPEIS_JSON = T.parent / "docs" / "classes-papeis.json"

# --- tabela de papeis (embutida) ------------------------------------------------------------------
# Equivalente ao modelo anterior (NA/NC/bobina) + lampada 9008 + polos de potencia.
# Temporizadores eletricos (9004..9007 + contatos 7004..7015) vêm do JSON do RE
# (docs/classes-papeis.json): "temporizador" (carga A1/A2) e "contato_temp".
_NA = {"papel": "contato", "modo": "NA"}
_NC = {"papel": "contato", "modo": "NC"}
PAPEIS_EMBUTIDOS = {
    **{c: dict(_NA) for c in ("8000", "8016", "7000", "10050")},
    **{c: dict(_NC) for c in ("8001", "8017", "7001", "10051")},
    **{c: {"papel": "bobina"} for c in ("9000", "10060")},
    "9008": {"papel": "lampada"},
    "2001": {"papel": "polos", "modo": "NA"},               # contatos principais do contator (rotulo = bobina)
    "2002": {"papel": "polos", "modo": "NA"},               # contator 4 polos (reversao mono/trifasica 4 polos)
    **{c: {"papel": "polos", "modo": "FECHADO"} for c in ("6007", "6009", "6010")},   # protecao: passa
    **{c: {"papel": "polos", "modo": "FECHADO"} for c in ("6002", "6004")},   # disjuntor 2/4 polos: passa (no app, fechar a mao)
}
_PAPEIS_VALIDOS = {"contato", "bobina", "lampada", "polos", "contato_temp", "temporizador"}


def _norm_tipo(t, padrao=None):
    """Canoniza o tipo de temporizador: ton|tof|tonof|intermitente (None se sem padrao)."""
    if t is None or str(t).strip() == "":
        return padrao
    s = str(t).strip().lower().replace("-", "_")
    return {"ton": "ton", "on": "ton",
            "tof": "tof", "off": "tof",
            "tonof": "tonof", "ton_tof": "tonof", "tonoff": "tonof", "on_off": "tonof", "onoff": "tonof",
            "intermitente": "intermitente", "blink": "intermitente",
            "pulso": "pulso", "pulse": "pulso"}.get(s, padrao)


def _ligacoes_re(cid, e):
    """Pares do RE (contatos[].pinos + fecha_quando) em nomes do binario.

    O JSON do RE usa os nomes eletricos ("55","67",...); o binario usa p1..pN na
    mesma ordem de e["pinos"] (docs/classes-papeis.json). Retorna
    [([pinoA, pinoB], modo)...] ou [] se nao der para mapear (o chamador cai no
    par padrao dos 2 primeiros pinos)."""
    try:
        contatos = e.get("contatos") or []
        nomes_re = [x for x in (e.get("pinos") or []) if isinstance(x, str)]
        nomes_bin = list(G.pinos_da_classe(str(cid)))
    except (AttributeError, TypeError):
        return []
    out = []
    for c in contatos:
        if not isinstance(c, dict):
            return []
        par = c.get("pinos") or []
        fq = str(c.get("fecha_quando") or "").strip()
        if len(par) < 2 or par[0] not in nomes_re or par[1] not in nomes_re:
            return []
        i, j = nomes_re.index(par[0]), nomes_re.index(par[1])
        if i >= len(nomes_bin) or j >= len(nomes_bin):
            return []
        if fq == "estado==1":
            modo = "NA"
        elif fq == "estado==0":
            modo = "NC"
        elif fq == "sempre":
            modo = "NA"
        else:
            return []
        out.append(([nomes_bin[i], nomes_bin[j]], modo))
    return out


def _normalizar_papel(e):
    """Aceita a entrada do JSON do RE (papel como string) -> dict interno ou None."""
    if not isinstance(e, dict):
        return None
    papel = str(e.get("papel") or e.get("role") or "").strip().lower()
    alias = {"na": ("contato", "NA"), "no": ("contato", "NA"), "nc": ("contato", "NC"), "nf": ("contato", "NC"),
             "contato_na": ("contato", "NA"), "contato_nc": ("contato", "NC"),
             "sensor_na": ("contato", "NA"), "sensor_nc": ("contato", "NC"),   # so 2 fios
             "coil": "bobina", "lamp": "lampada", "sinalizador": "lampada",
             "ton": ("contato_temp", None), "tof": ("contato_temp", None),
             "temporizador": ("temporizador", None),
             "temporizador_on": ("temporizador", "ton"),
             "temporizador_off": ("temporizador", "tof"),
             "temporizador_on_off": ("temporizador", "tonof"),
             "temporizador_onoff": ("temporizador", "tonof"),
             "temporizador_intermitente": ("temporizador", "intermitente"),
             "contato_temporizado": ("contato_temp", "NA"),
             "contato_temporizado_na": ("contato_temp", "NA"),
             "contato_temporizado_nc": ("contato_temp", "NC"),
             "contato_temporizado_na_nc": ("contato_temp", "NA_NC"),
             "contato_temporizado_comutado": ("contato_temp", "COMUTADO")}
    r = dict(e)
    if papel.startswith("sensor") and len(e.get("pinos") or []) > 2:
        return None                              # 3+ fios: sem modelo (A11 recusa)
    a = alias.get(papel, papel)
    if isinstance(a, tuple):
        r["papel"] = a[0]
        if a[1] and not r.get("modo") and a[0] in ("contato", "contato_temp"):
            r["modo"] = a[1]
        if a[0] == "temporizador" and a[1]:
            r.setdefault("tipo", a[1])
        if papel in ("ton", "tof") and not r.get("tipo"):
            r["tipo"] = papel
    else:
        r["papel"] = a
    if r["papel"] in ("contato_temp", "temporizador") and r.get("tipo"):
        r["tipo"] = _norm_tipo(r["tipo"], r["tipo"])
    if r["papel"] not in _PAPEIS_VALIDOS:
        return None
    if r.get("modo"):
        r["modo"] = str(r["modo"]).upper().replace("NF", "NC").replace("NO", "NA")
    return r


def carregar_papeis(path=None):
    """Tabela classe -> papel: embutida, sobreposta por docs/classes-papeis.json quando existir."""
    tab = {k: dict(v) for k, v in PAPEIS_EMBUTIDOS.items()}
    p = Path(path) if path else PAPEIS_JSON
    if p.is_file():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return tab
        classes = raw.get("classes", raw) if isinstance(raw, dict) else {}
        for cid, e in classes.items():
            n = _normalizar_papel(e)
            if not n:
                continue
            # nomes de pino do RE (A1/95/13...) nao existem na tabela do binario (p1/p2/1..6):
            # so aceite 'pinos' que existam na classe; senao use os 2 primeiros do binario.
            conhecidos = set(G.pinos_da_classe(str(cid)))
            if n.get("pinos") and not set(n["pinos"]) <= conhecidos:
                n.pop("pinos")
            if n.get("papel") == "contato_temp" and isinstance(e, dict):
                ligs = _ligacoes_re(str(cid), e)     # 7006/7007/7010/...: pares por fecha_quando
                if ligs:
                    n["ligacoes"] = ligs
            if str(cid) in tab and path is None:
                continue           # papel embutido (validado no app) prevalece; o JSON padrao do RE so ACRESCENTA
            tab[str(cid)] = n
    return tab


def _nome(rot):
    return (rot or "").lstrip("-").strip()


def _segundos(v):
    """'5', '5s', '2,5' -> float; None se nao der."""
    try:
        return float(str(v).strip().lower().rstrip("s").replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


class Circuito:
    def __init__(self, path, papeis=None):
        self.papeis = papeis if papeis is not None else carregar_papeis()
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

        self.contatos = []     # (tipo 'NO'/'NC', A, B, chave) — contatos de 2 pinos (compat/tabela)
        self.bobinas = {}      # chave -> (A, B) da 1a ocorrencia
        self.lampadas = {}     # chave -> (A, B)
        self.entradas = []     # chaves externas (botoes/termicos)
        self.soltos = []       # pinos de papel funcional sem fio no ponto
        self.fixos = []        # (no, char de fase) estampados pelas fontes
        self._bob = []         # (chave, A, B) por instancia (inclui temporizador-carga A1/A2)
        self._lamp = []
        self._cont = []        # dicts: chave, a, b, modo, cid, fonte, temp, id
                               # fonte: rotulo (bobina/entrada) | timer (segue 9004.. de mesmo rotulo)
                               #        | proprio (contagem propria; temp={tipo,tempo}, id unico)
        self._tim = []         # temporizadores-carga 9004..9007: {id, chave, tipo, tempo}
        self._por_rotulo = {}  # chave -> indice em _tim (1a ocorrencia)
        self._polos = []       # dicts: chave, modo, pares [(a,b)]
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
            nomes = list(offs)
            par = papel.get("pinos") or nomes[:2]
            a = b = None
            if papel["papel"] in ("contato", "bobina", "lampada", "contato_temp", "temporizador"):
                if len(par) < 2 or par[0] not in pinos or par[1] not in pinos:
                    continue
                a, b = pinos[par[0]][0], pinos[par[1]][0]
                for nm in par[:2]:
                    if not pinos[nm][1]:
                        self.soltos.append(f"{rot or cid}({cid}).{nm}")
            if papel["papel"] == "bobina":
                self._bob.append((chave, a, b))
                self.bobinas.setdefault(chave, (a, b))
            elif papel["papel"] == "lampada":
                self._lamp.append((chave, a, b))
                self.lampadas.setdefault(chave, (a, b))
            elif papel["papel"] == "contato":
                self._cont.append({"chave": chave, "a": a, "b": b, "modo": papel.get("modo", "NA"),
                                    "temp": None, "cid": cid, "fonte": "rotulo"})
            elif papel["papel"] == "contato_temp":
                tipo = _norm_tipo(papel.get("tipo")) or self._tipo_por_classe(cid)
                tempo = self._tempo_do_simbolo(p, papel)
                ligs = papel.get("ligacoes")
                pares = [(tuple(lg[0]), lg[1]) for lg in ligs] if ligs else [(tuple(par[:2]), papel.get("modo", "NA"))]
                for (na_, nb_), modo in pares:
                    if na_ not in pinos or nb_ not in pinos:
                        continue
                    for nm in (na_, nb_):
                        if not pinos[nm][1]:
                            self.soltos.append(f"{rot or cid}({cid}).{nm}")
                    self._cont.append({"chave": chave, "a": pinos[na_][0], "b": pinos[nb_][0],
                                       "modo": modo, "cid": cid, "fonte": "proprio",
                                       "temp": {"tipo": tipo, "tempo": tempo}})
            elif papel["papel"] == "temporizador":
                self._bob.append((chave, a, b))
                self.bobinas.setdefault(chave, (a, b))
                self._tim.append({"chave": chave, "tipo": _norm_tipo(papel.get("tipo"), "ton"),
                                  "tempo": self._tempo_do_temporizador(p["labels"]), "cid": cid})
            elif papel["papel"] == "polos":
                self._polos.append({"chave": chave, "modo": papel.get("modo", "NA"),
                                    "pares": self._pares_polos(offs, pinos)})
        # ids unicos para temporizadores (carga 9004.. e contatos de contagem propria).
        # contato 7004..7015 com 9004.. de MESMO rotulo nao conta sozinho: segue a saida
        # do temporizador-carga (como no app: copia de +0x30e24 por label igual).
        total = defaultdict(int)
        for t in self._tim:
            total[t["chave"]] += 1
        vistos = defaultdict(int)
        for t in self._tim:
            vistos[t["chave"]] += 1
            t["id"] = t["chave"] if total[t["chave"]] == 1 else f"{t['chave']}#{vistos[t['chave']]}"
        for i, t in enumerate(self._tim):
            self._por_rotulo.setdefault(t["chave"], i)
        usados = {t["id"] for t in self._tim}
        total_p, vistos_p = defaultdict(int), defaultdict(int)
        for c in self._cont:
            if c.get("fonte") == "proprio" and c["chave"] not in self._por_rotulo:
                total_p[c["chave"]] += 1
        for c in self._cont:
            if c.get("fonte") != "proprio":
                continue
            if c["chave"] in self._por_rotulo:
                c["fonte"] = "timer"
                c["temp"] = None
                continue
            vistos_p[c["chave"]] += 1
            base = c["chave"] if total_p[c["chave"]] == 1 else f"{c['chave']}#{vistos_p[c['chave']]}"
            k = vistos_p[c["chave"]]
            while base in usados:
                k += 1
                base = f"{c['chave']}#{k}"
            c["id"] = base
            usados.add(base)
        self.contatos = [("NC" if c["modo"] == "NC" else "NO", c["a"], c["b"], c["chave"])
                         for c in self._cont if c["modo"] in ("NA", "NC")]
        nomes_bob = set(self.bobinas)
        self.entradas = sorted({c["chave"] for c in self._cont if c["chave"] not in nomes_bob})
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

    @staticmethod
    def _atoi(s):
        """Prefixo inteiro com sinal (atoi do C); resto/invalido vira 0 ("0.5" -> 0)."""
        s = str(s or "").lstrip()
        sinal = -1 if s.startswith("-") else 1
        if s[:1] in ("-", "+"):
            s = s[1:]
        n = ""
        for c in s:
            if c.isdigit():
                n += c
            else:
                break
        try:
            return sinal * int(n) if n else 0
        except ValueError:
            return 0

    @classmethod
    def _tempo_do_temporizador(cls, labels):
        """Tempo do 9004..9007 em segundos: atoi(label5) x mult(label4) ticks de 100 ms.

        label4 (unidade): '3'->x1 | '0'->x10 | '1'->x100 | '2'->x1000 ticks; label5 = tempo.
        Ex. do .cad "#A1#A2#0#5#" = unidade '0', tempo 5 -> 50 ticks -> 5,0 s."""
        labels = labels or []
        un = str(labels[4]).strip() if len(labels) > 4 else ""
        mult = {"3": 1, "0": 10, "1": 100, "2": 1000}.get(un, 1)
        ticks = cls._atoi(labels[5] if len(labels) > 5 else "")
        return max(ticks * mult, 0) / 10.0

    @staticmethod
    def _tipo_por_classe(cid):
        """Tipo do contato 7004..7015 pela faixa da classe (ON: 7004..7007; OFF: 7008..7011)."""
        try:
            n = int(cid)
        except (TypeError, ValueError):
            return "ton"
        if 7004 <= n <= 7007:
            return "ton"
        if 7008 <= n <= 7011:
            return "tof"
        if 7012 <= n <= 7015:
            return "tonof"
        return "ton"

    # --- avaliacao combinacional -------------------------------------------------------------------
    def _controle(self, chave, ent, coil):
        """Estado do comando de um contato: bobina de mesmo rotulo, senao entrada externa."""
        if chave in self.bobinas:
            return coil.get(chave, False)
        return bool(ent.get(chave, False))

    def _avaliar(self, ent, coil, tm):
        """Uma passada: une redes por contatos fechados, estampa fases, energiza bobinas/lampadas.
        -> (novo_coil, lampadas_on, curtos)."""
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

        saidas = {}                                    # chave -> saida do temporizador-carga
        for e in self._tim:
            saidas.setdefault(e["chave"], tm.get(e["id"], False))
        interm = {e["chave"] for e in self._tim if e["tipo"] == "intermitente"}
        for c in self._cont:
            fonte = c.get("fonte", "rotulo")
            if fonte == "timer":
                fechado = bool(saidas.get(c["chave"], False))     # segue o 9004.. de mesmo rotulo
            elif fonte == "proprio":
                fechado = bool(tm.get(c["id"], False))            # contagem propria do contato
            else:
                fechado = self._controle(c["chave"], ent, coil)
                if c["chave"] in interm:                          # 9007: ate o instantaneo pisca
                    fechado = bool(saidas.get(c["chave"], False))
            if c["modo"] == "NC":
                fechado = not fechado
            if fechado:
                union(c["a"], c["b"])
        for pl in self._polos:
            if pl["chave"] in interm:                            # 9007 copia o pisca aos polos
                ativo = bool(saidas.get(pl["chave"], False))
            else:
                ativo = pl["modo"] == "FECHADO" or self._controle(pl["chave"], ent, coil)
            if pl["modo"] == "NC":
                ativo = not ativo
            if ativo:
                for a, b in pl["pares"]:
                    union(a, b)
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
        lamp = {k for k, a, b in self._lamp if energizado(a, b)}
        curtos = sorted("+".join(sorted(s)) for s in chars.values() if len(s) > 1)
        return novo, lamp, curtos

    def _assentar(self, ent, coil, tm):
        """Relaxa a logica ate o ponto fixo (selo/intertravamento). -> (status, coil, lampadas, curtos)."""
        vistos = set()
        lamp, curtos = set(), []
        for _ in range(40):
            novo, lamp, curtos = self._avaliar(ent, coil, tm)
            if novo == coil:
                return ("CURTO" if curtos else "OK"), novo, lamp, curtos
            assin = tuple(sorted(k for k, v in novo.items() if v))
            if assin in vistos:
                return "RACE", novo, lamp, curtos
            vistos.add(assin)
            coil = novo
        return "INSTAVEL", coil, lamp, curtos

    # --- tempo (ON/OFF/ON+OFF-delay, intermitente) -------------------------------------------------
    def _timers(self, tempos=None):
        t = {}
        for e in self._tim:
            tempo = (tempos or {}).get(e["id"], (tempos or {}).get(e["chave"], e["tempo"]))
            t[e["id"]] = {"chave": e["chave"], "tipo": e["tipo"],
                          "tempo": float(tempo) if tempo is not None else 0.0}
        for c in self._cont:
            if c.get("fonte") == "proprio":
                tempo = (tempos or {}).get(c["id"], (tempos or {}).get(c["chave"], c["temp"]["tempo"]))
                t[c["id"]] = {"chave": c["chave"], "tipo": c["temp"]["tipo"],
                              "tempo": float(tempo) if tempo is not None else 0.0}
        return t

    def _ativos(self, ent, coil):
        """Comando (energizacao) de cada temporizador: bobina de mesmo rotulo, senao entrada."""
        out = {}
        for e in self._tim:
            out[e["id"]] = self._controle(e["chave"], ent, coil)
        for c in self._cont:
            if c.get("fonte") == "proprio":
                out[c["id"]] = self._controle(c["chave"], ent, coil)
        return out

    @staticmethod
    def _passo_tempo(tim, tm, el, ativo, dt):
        """Avanca dt nos temporizadores; devolve True se alguma saida mudou.

        ton: conta energizado ate T (desenergizou: zera e abre na hora).
        tof: fecha na hora que energiza; desenergizado conta ate T e abre.
        tonof: mesmo T nos dois sentidos. intermitente: energizado alterna a
        cada T; desenergizado volta a 0 na hora. pulso (9015): sem modelo."""
        mudou = False
        for i, t in tim.items():
            a = ativo[i]
            tipo = t["tipo"]
            if tipo == "ton":
                if not a:
                    el[i], novo = 0.0, False
                else:
                    el[i] += dt
                    novo = el[i] >= t["tempo"] - 1e-9
            elif tipo == "tof":
                if a:
                    el[i], novo = 0.0, True
                elif tm[i]:
                    el[i] += dt
                    novo = el[i] < t["tempo"] - 1e-9
                else:
                    novo = False
            elif tipo == "tonof":
                if a:
                    if tm[i]:
                        el[i], novo = 0.0, True
                    else:
                        el[i] += dt
                        novo = el[i] >= t["tempo"] - 1e-9
                elif tm[i]:
                    el[i] += dt
                    novo = el[i] < t["tempo"] - 1e-9
                else:
                    el[i], novo = 0.0, False
            elif tipo == "intermitente":
                if not a:
                    el[i], novo = 0.0, False
                else:
                    T = max(t["tempo"], 0.1)         # T=0 (atoi) pisca a cada tick, como no app
                    el[i] += dt
                    if el[i] >= T - 1e-9:
                        el[i] -= T
                        novo = not tm[i]
                    else:
                        novo = tm[i]
            else:                                    # tipo sem modelo (ex. pulso): saida 0
                el[i], novo = 0.0, False
            if novo != tm[i]:
                tm[i] = novo
                mudou = True
        return mudou

    @staticmethod
    def _proximo_evento(tim, tm, el, ativo):
        """Menor tempo ate alguma saida mudar (None se nenhuma esta correndo)."""
        r = None
        for i, t in tim.items():
            tipo = t["tipo"]
            if tipo == "ton":
                corre = ativo[i] and not tm[i]
            elif tipo == "tof":
                corre = not ativo[i] and tm[i]
            elif tipo == "tonof":
                corre = (ativo[i] and not tm[i]) or (not ativo[i] and tm[i])
            elif tipo == "intermitente":
                corre = bool(ativo[i])
            else:
                corre = False
            if corre:
                T = max(t["tempo"], 0.1) if tipo == "intermitente" else t["tempo"]
                falta = max(T - el[i], 0.0)
                r = falta if r is None else min(r, falta)
        return r

    def novo_estado(self, inicial=None, tempos=None):
        """Estado persistente (bobinas ligadas, saidas/decorrido dos temporizadores) para passos sucessivos."""
        ini = set(inicial or ())
        tim = self._timers(tempos)
        coil = {k: (k in ini) for k in self.bobinas}
        tm = {i: (i in ini or t["chave"] in ini) for i, t in tim.items()}
        el = {i: (t["tempo"] if tm[i] and t["tipo"] == "ton" else 0.0) for i, t in tim.items()}
        return {"coil": coil, "tm": tm, "el": el, "tim": tim}

    def avancar(self, st, ent, avanca=0.0):
        """Aplica `ent` constante por `avanca` s sobre o estado `st` (mutado). -> dict de estado()."""
        tim, tm, el = st["tim"], st["tm"], st["el"]
        status, coil, lamp, curtos = self._assentar(ent, st["coil"], tm)
        restante = float(avanca or 0.0)
        for _ in range(200):
            if not tim or status in ("RACE", "INSTAVEL"):
                break
            ativo = self._ativos(ent, coil)
            if self._passo_tempo(tim, tm, el, ativo, 0.0):       # efeitos instantaneos (TOF liga, tempo 0)
                status, coil, lamp, curtos = self._assentar(ent, coil, tm)
                continue
            if restante <= 1e-9:
                break
            ev = self._proximo_evento(tim, tm, el, ativo)
            dt = restante if ev is None else min(restante, ev)
            if dt <= 0:
                break
            mudou = self._passo_tempo(tim, tm, el, ativo, dt)
            restante -= dt
            if mudou:
                status, coil, lamp, curtos = self._assentar(ent, coil, tm)
        st["coil"] = coil
        return {"status": status, "bobinas": sorted(k for k, v in coil.items() if v),
                "lampadas": sorted(lamp),
                "temporizadores": {i: {"tipo": t["tipo"], "tempo": t["tempo"],
                                       "decorrido": round(el[i], 6), "saida": tm[i]} for i, t in tim.items()},
                "curtos": curtos}

    # --- API publica -------------------------------------------------------------------------------
    def estado(self, ent, inicial=None, avanca=0.0, tempos=None):
        """{status, bobinas:[...], lampadas:[...], temporizadores:{id:{tipo,tempo,decorrido,saida}}, curtos:[...]}"""
        return self.avancar(self.novo_estado(inicial, tempos), ent, avanca)

    def resolve(self, ent, inicial=None, avanca=0.0, tempos=None):
        """ent: {chave: bool} (True = acionado). inicial: bobinas ja energizadas.
        Retorna (status, set) onde status in {'OK','RACE','INSTAVEL','CURTO'}."""
        e = self.estado(ent, inicial, avanca, tempos)
        return e["status"], set(e["bobinas"])


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
