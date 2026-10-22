#!/usr/bin/env python3
"""Simulador GEOMETRICO de circuitos com CLP modular + ladder (CADe_SIMU 4.0), por ticks de 100 ms.

E o "modelo geometrico" de docs/ladder.md §3.2: le o .cad (nada vem da DSL) e roda a mesma ordem de
avaliacao do modelo logico (tools/ladder_dsl.py, §3.1). Os dois tem de dar o mesmo resultado nos testes.

Conectividade por GEOMETRIA (re-engenharia §9.2, mesmas funcoes de netlist_sim/geo_check): fio-fio so
por extremo, 4001 une ao fio que o contem, pino so liga a extremo de fio. Nets gravados sao ignorados.

Potenciais por "char": fontes 3000..3011 (L1->1, L2->2, L3->3, N->N, PE->P), 3008 -> '+', 3009 -> '-',
CPU 10206 alimentada (fase+N ou 2 fases em L/N) -> '+' em p3 e '-' em p4, saida 10205 com bit 1 -> '+'.
Contatos eletricos conduzem nos dois sentidos; contatos ladder (10050 NA / 10051 NF) so de A para B.

Um tick (estado anterior -> novo; tudo sincrono, como o commit da passada 7 do app):
  1. rede fisica com os contatores do tick anterior e as entradas do caso; 10205 estampa '+' com o bit do
     tick ANTERIOR; bobinas 9000 / lampadas 9008 energizam se os dois pinos tem chars diferentes (fora
     PE) -> estado fisico novo; entradas 10204: bit = net com '+'.
  2. ladder com os bits do tick anterior: '+' do trilho (3008) avanca pelos contatos fechados; bobina
     10060 (OUT) = A com '+' e B sem fio ou com '-'; 10061 SET / 10062 RST; TON 10066: IN com '+' soma 1
     no acumulador (senao zera), Q estampa '+' com acc >= T do tick anterior; bit do label0 = acc >= T.
     T = tempo x base (labels[5] x {'3':1,'0':10,'1':100,'2':1000} ticks), minimo 1.
Disjuntores (6002/6003/6009/6010) e termico 6007 sao entradas que ALTERNAM: `"DJ1": true` = disjuntor
LIGADO (no app ele comeca desligado a cada Play), `"RT1": true` = termico DISPARADO. Contatos 8016/8017
seguem o disjuntor/termico de MESMO rotulo (a chave e o rotulo); 7000/7001/2001 seguem a bobina 9000 de
mesmo rotulo. Botoeiras (8000/8001) sao momentaneas (soltas quando nao citadas).

API:
  c = CircuitoCLP(path)
  c.regime(entradas, estado=None) -> (estado, resumo)      roda ate estabilizar (max 2000 ticks)
  c.rodar(entradas, ticks, estado=None) -> (estado, resumo) exatamente N ticks
  teste_casos(path, casos) -> bool                          imprime no formato do cad_test
Caso: {"nome","entradas":{..},"inicial":[ops ou bobinas],"esperado":[bobinas 9000],"esperado_lampadas":[..],
       "esperado_bits":{op:0|1},"status":"OK|OSCILA|INDEFINIDO|CURTO","ticks":N | "tempo_s":s,
       "sequencia":[passo...]}  (passo = mesmos campos; o estado passa de um passo ao seguinte)
"""
import json
import sys
from pathlib import Path

T = Path(__file__).resolve().parent
sys.path.insert(0, str(T))
import geo_check as G  # noqa: E402
import netlist_sim as NS  # noqa: E402
from dissect import parse_ent, split_all  # noqa: E402

LADDER_NA, LADDER_NF = {"10050"}, {"10051"}
OUT, SET, RST, TON = "10060", "10061", "10062", "10066"
CPU, ENTRADA, SAIDA = "10206", "10204", "10205"
FONTE_MAIS, FONTE_MENOS = "3008", "3009"
BOTAO_NA, BOTAO_NF = {"8000"}, {"8001"}
AUX = {"7000", "7001"}
DISJUNTOR = {"6002", "6003", "6009", "6010"}
TERMICO = {"6007"}
POLOS_CONTATOR = {"2001"}
BOBINA, LAMPADA = {"9000"}, {"9008"}
CLASSES_CLP = {CPU, ENTRADA, SAIDA, FONTE_MAIS, OUT, SET, RST, TON} | LADDER_NA | LADDER_NF
BASE_TICKS = {"3": 1, "0": 10, "1": 100, "2": 1000}   # radio do dialogo do TON: 0,1 s / 1 s / 10 s / x60 s
MAX_TICKS = 2000
FASES = {"1", "2", "3", "N"}


def tem_clp(path):
    """True se o .cad tem CPU/entradas/saidas de CLP ou elementos ladder (usa este simulador)."""
    _, ents, _ = split_all(Path(path).read_bytes().decode("latin1"))
    return any((parse_ent(e) or {}).get("id") in CLASSES_CLP for e in ents)


def _nome(rot):
    return (rot or "").lstrip("-").strip()


def ton_ticks(labels):
    """Preset do TON em ticks a partir dos labels gravados ([op,'','IN','Q',base,tempo])."""
    lab = list(labels) + [""] * 6
    try:
        n = float(str(lab[5]).replace(",", ".").strip() or 0)
    except ValueError:
        n = 0.0
    return max(1, int(round(n * BASE_TICKS.get(str(lab[4]).strip(), 10))))


class CircuitoCLP:
    def __init__(self, path):
        d = Path(path).read_bytes().decode("latin1")
        _, ents, _ = split_all(d)
        ps = [p for p in map(parse_ent, ents) if p and len(p["nums"]) > 17]
        find, extremos = NS.Circuito._geometria(ps)
        ids = {}
        prox = [0]

        def no(pt):
            if pt not in extremos:
                prox[0] += 1
                return ("solto", prox[0]), False
            r = find(pt)
            if r not in ids:
                ids[r] = len(ids)
            return ids[r], True

        self.fixos = []          # (no, char)
        self.cpus = []           # {L,N,mais,menos}
        self.ent_clp = []        # (op, no)
        self.sai_clp = []        # (op, no)
        self.ladder = []         # {tipo:'NA'|'NF', op, a, b}
        self.bob_ladder = []     # {tipo:'OUT'|'SET'|'RST', op, a, b, b_ligado}
        self.tons = []           # {op, a(IN), b(Q), T, idx}
        self.contatos = []       # {modo:'NA'|'NC', chave, a, b, cid}
        self.polos = []          # {chave, tipo:'contator'|'disjuntor'|'passa', pares}
        self.bobinas = {}        # chave -> [(a,b)]
        self.lampadas = {}
        self.disjuntores, self.termicos, self.botoes = set(), set(), set()
        papeis = NS.carregar_papeis()
        brutos = []
        for p in ps:
            cid = p["id"]
            if cid in G.SKIP:
                continue
            x, y, o = int(p["nums"][8]), int(p["nums"][9]), int(p["nums"][17] or 0)
            pin = {}
            for nome, (dx, dy) in G.pinos_da_classe(cid).items():
                rx, ry = G._rot(dx, dy, o)
                pin[nome] = no((x + rx, y + ry))
            brutos.append((cid, (p["labels"] or [""])[0], pin, p))
        self.nomes_bob = {_nome(r) for cid, r, _, _ in brutos if cid in BOBINA}
        for cid, rot, pin, p in brutos:
            n = {k: v[0] for k, v in pin.items()}
            chave = _nome(rot) or cid
            if cid in G.FONTE:
                self.fixos += [(v, G.CHAR[k]) for k, (v, lig) in pin.items() if lig and k in G.CHAR]
            elif cid == FONTE_MAIS:
                self.fixos += [(v, "+") for v, lig in pin.values() if lig]
            elif cid == FONTE_MENOS:
                self.fixos += [(v, "-") for v, lig in pin.values() if lig]
            elif cid == CPU:
                self.cpus.append({"L": n["p1"], "N": n["p2"], "mais": n["p3"], "menos": n["p4"]})
            elif cid == ENTRADA:
                self.ent_clp.append((rot.strip(), n["p1"]))
            elif cid == SAIDA:
                self.sai_clp.append((rot.strip(), n["p1"]))
            elif cid in LADDER_NA | LADDER_NF:
                self.ladder.append({"tipo": "NA" if cid in LADDER_NA else "NF", "op": rot.strip(),
                                    "a": n["p1"], "b": n["p2"]})
            elif cid in (OUT, SET, RST):
                self.bob_ladder.append({"tipo": {OUT: "OUT", SET: "SET", RST: "RST"}[cid], "op": rot.strip(),
                                        "a": n["p1"], "b": n["p2"], "b_ligado": pin["p2"][1]})
            elif cid == TON:
                self.tons.append({"op": rot.strip(), "a": n["p1"], "b": n["p2"], "T": ton_ticks(p["labels"]),
                                  "idx": len(self.tons)})
            elif cid in BOBINA | LAMPADA:
                (self.bobinas if cid in BOBINA else self.lampadas).setdefault(chave, []).append((n["p1"], n["p2"]))
            elif cid in DISJUNTOR | TERMICO | POLOS_CONTATOR:
                tipo = "disjuntor" if cid in DISJUNTOR else ("passa" if cid in TERMICO else "contator")
                (self.disjuntores if cid in DISJUNTOR else self.termicos if cid in TERMICO else set()).add(chave)
                self.polos.append({"chave": chave, "tipo": tipo,
                                   "pares": NS.Circuito._pares_polos(G.pinos_da_classe(cid), pin)})
            else:
                pa = papeis.get(cid)
                if not pa or pa.get("papel") != "contato" or "p1" not in n or "p2" not in n:
                    continue
                if cid in BOTAO_NA | BOTAO_NF:
                    self.botoes.add(chave)
                self.contatos.append({"modo": "NC" if pa.get("modo") == "NC" else "NA", "chave": chave,
                                      "a": n["p1"], "b": n["p2"], "cid": cid})
        # entradas validas: botoes, disjuntores, termicos e contatos que nao seguem bobina
        self.entradas = sorted(self.botoes | self.disjuntores | self.termicos |
                               {c["chave"] for c in self.contatos if c["chave"] not in self.nomes_bob})
        self.alternaveis = (self.disjuntores | self.termicos) - self.botoes
        self.operandos = sorted({o for o, _ in self.ent_clp} | {o for o, _ in self.sai_clp} |
                                {c["op"] for c in self.ladder} | {b["op"] for b in self.bob_ladder} |
                                {t["op"] for t in self.tons})
        self._cache = {}

    # ------------------------------------------------------------------ estado
    def estado_zero(self, inicial=()):
        ini = set(inicial or ())
        return {"bits": {o: (1 if o in ini else 0) for o in self.operandos},
                "fis": {k: k in ini for k in self.bobinas},
                "acc": [0] * len(self.tons)}

    def _contato_fechado(self, c, ent, fis):
        k = c["chave"]
        if c["cid"] in AUX or (k in self.nomes_bob and c["cid"] not in BOTAO_NA | BOTAO_NF):
            ativo = bool(fis.get(k, False))           # auxiliar de contator (7000/7001)
        else:
            ativo = bool(ent.get(k, False))           # botao / disjuntor / termico de mesmo rotulo / direta
        return (not ativo) if c["modo"] == "NC" else ativo

    def _rede(self, ent, fis):
        chave = (tuple(sorted((k, bool(v)) for k, v in ent.items())), tuple(sorted(fis.items())))
        if chave in self._cache:
            return self._cache[chave]
        parent = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for c in self.contatos:
            if self._contato_fechado(c, ent, fis):
                union(c["a"], c["b"])
        for pl in self.polos:
            ok = (pl["tipo"] == "passa" or (pl["tipo"] == "disjuntor" and bool(ent.get(pl["chave"], False)))
                  or (pl["tipo"] == "contator" and bool(fis.get(pl["chave"], False))))
            if ok:
                for a, b in pl["pares"]:
                    union(a, b)
        self._cache[chave] = find
        return find

    def tick(self, est, ent):
        """Um tick de 100 ms: est (bits, fis, acc do tick anterior) -> (novo, info)."""
        bits, fis, acc = est["bits"], est["fis"], est["acc"]
        find = self._rede(ent, fis)
        chars = {}
        for no, ch in self.fixos:
            chars.setdefault(find(no), set()).add(ch)
        cpu_on = False
        for c in self.cpus:
            sl = chars.get(find(c["L"]), set()) & FASES
            sn = chars.get(find(c["N"]), set()) & FASES
            if sl and sn and sl != sn:
                cpu_on = True
                chars.setdefault(find(c["mais"]), set()).add("+")
                chars.setdefault(find(c["menos"]), set()).add("-")
        for op, no in self.sai_clp:
            if bits.get(op):
                chars.setdefault(find(no), set()).add("+")

        def energ(a, b):
            sa, sb = chars.get(find(a), set()) - {"P"}, chars.get(find(b), set()) - {"P"}
            return bool(sa and sb and sa != sb)

        novo_fis = {k: any(energ(a, b) for a, b in v) for k, v in self.bobinas.items()}
        lamp = sorted(k for k, v in self.lampadas.items() if any(energ(a, b) for a, b in v))
        curtos = sorted("+".join(sorted(s)) for s in chars.values() if len(s - {"P"}) > 1
                        or ("P" in s and s & {"1", "2", "3", "+", "-"}))
        nb = dict(bits)
        for op, no in self.ent_clp:
            nb[op] = 1 if "+" in chars.get(find(no), set()) else 0
        # ladder: '+' direcional a partir das nets com '+' (contatos com os bits do tick anterior)
        mais = {r for r, s in chars.items() if "+" in s}

        def tem(no):
            return find(no) in mais
        mudou = True
        while mudou:
            mudou = False
            for c in self.ladder:
                fech = bool(bits.get(c["op"])) if c["tipo"] == "NA" else not bits.get(c["op"])
                if fech and tem(c["a"]) and not tem(c["b"]):
                    mais.add(find(c["b"]))
                    mudou = True
            for t in self.tons:
                if acc[t["idx"]] >= t["T"] and not tem(t["b"]):
                    mais.add(find(t["b"]))
                    mudou = True
        menos = {r for r, s in chars.items() if "-" in s}
        sets, rsts, outs = set(), set(), {}
        for b in self.bob_ladder:
            v = tem(b["a"]) and (not b["b_ligado"] or find(b["b"]) in menos)
            if b["tipo"] == "OUT":
                outs[b["op"]] = outs.get(b["op"], False) or v
            elif v:
                (sets if b["tipo"] == "SET" else rsts).add(b["op"])
        for op, v in outs.items():
            nb[op] = 1 if v else 0
        for op in sets:
            nb[op] = 1
        for op in rsts:
            nb[op] = 0
        nacc = list(acc)
        for t in self.tons:
            nacc[t["idx"]] = min(acc[t["idx"]] + 1, t["T"]) if tem(t["a"]) else 0
        for t in self.tons:
            nb[t["op"]] = 0
        for t in self.tons:                       # bit do TON = acc >= T (mesmo label em varios: OU)
            if nacc[t["idx"]] >= t["T"]:
                nb[t["op"]] = 1
        return ({"bits": nb, "fis": novo_fis, "acc": nacc},
                {"lampadas": lamp, "curtos": curtos, "cpu": cpu_on, "indefinido": sorted(sets & rsts)})

    @staticmethod
    def _assin(est):
        return (tuple(sorted(est["bits"].items())), tuple(sorted(est["fis"].items())), tuple(est["acc"]))

    def rodar(self, ent, ticks, est=None):
        """Exatamente `ticks` ticks (0 = so le o estado atual)."""
        est = est or self.estado_zero()
        indef = set()
        _, info = self.tick(est, ent)
        for _ in range(max(0, int(ticks))):
            est, info = self.tick(est, ent)
            indef |= set(info["indefinido"])
        st = "CURTO" if info["curtos"] else ("INDEFINIDO" if indef else "OK")
        return est, self._resumo(est, info, st, ticks=int(ticks))

    def regime(self, ent, est=None, max_ticks=MAX_TICKS):
        """Roda ate (bits, fisico, acc) ficarem iguais por 2 ticks seguidos. Ciclo -> OSCILA."""
        est = est or self.estado_zero()
        vistos = {self._assin(est): 0}
        estavel, indef, info = 0, set(), None
        for i in range(1, max_ticks + 1):
            novo, info = self.tick(est, ent)
            indef |= set(info["indefinido"])
            mesmo = self._assin(novo) == self._assin(est)
            est = novo
            if mesmo:
                estavel += 1
                if estavel >= 2:
                    st = "CURTO" if info["curtos"] else ("INDEFINIDO" if indef else "OK")
                    return est, self._resumo(est, info, st, ticks=i)
                continue
            estavel = 0
            a = self._assin(novo)
            if a in vistos:
                return est, self._resumo(est, info, "OSCILA", ticks=i)
            vistos[a] = i
        return est, self._resumo(est, info, "OSCILA", ticks=max_ticks)

    @staticmethod
    def _resumo(est, info, status, ticks=None):
        return {"status": status, "bobinas": sorted(k for k, v in est["fis"].items() if v),
                "lampadas": info["lampadas"], "bits": dict(est["bits"]), "curtos": info["curtos"],
                "cpu": info["cpu"], "ticks": ticks}

    def imagem_inicial(self, caso):
        """t=0 (docs/ladder.md §3.1): bits = inicial + entradas com o hardware em repouso (botoes soltos,
        disjuntores/termicos como no 1o passo); fisicos = saidas avaliadas com esses bits."""
        ini = set(caso.get("inicial") or ())
        est = self.estado_zero(ini)
        ent = {k: v for k, v in primeira_entrada(caso).items() if k in self.alternaveis}
        e1, _ = self.tick(est, ent)
        for op, _ in self.ent_clp:
            est["bits"][op] = 1 if (op in ini or e1["bits"][op]) else 0
        e2, _ = self.tick(est, ent)
        est["fis"] = {k: (k in ini) or e2["fis"][k] for k in est["fis"]}
        for t in self.tons:
            if t["op"] in ini:
                est["acc"][t["idx"]] = t["T"]
        return est


def primeira_entrada(caso):
    seq = caso.get("sequencia") or caso.get("passos")
    return dict((seq[0].get("entradas") if seq else caso.get("entradas")) or {})


def ticks_do_passo(p):
    if p.get("ticks") is not None:
        return int(p["ticks"])
    if p.get("tempo_s") is not None:
        return int(round(float(p["tempo_s"]) * 10))
    return None


def confere(p, r):
    """Falhas (lista de strings) de um passo/caso contra o resultado r."""
    falhas = []
    if p.get("status") is not None and r["status"] != p["status"]:
        falhas.append(f"status {r['status']} != {p['status']}")
    if p.get("esperado") is not None and set(r["bobinas"]) != {_nome(k) for k in p["esperado"]}:
        falhas.append(f"bobinas {r['bobinas']} != {sorted(_nome(k) for k in p['esperado'])}")
    if p.get("esperado_lampadas") is not None and set(r["lampadas"]) != {_nome(k) for k in p["esperado_lampadas"]}:
        falhas.append(f"lampadas {r['lampadas']} != {sorted(_nome(k) for k in p['esperado_lampadas'])}")
    for op, v in (p.get("esperado_bits") or {}).items():
        if int(bool(r["bits"].get(op, 0))) != int(bool(v)):
            falhas.append(f"bit {op}={r['bits'].get(op, 0)} (esperado {int(bool(v))})")
    return falhas


def executar_caso(sim, caso):
    """sim: objeto com imagem_inicial/rodar/regime (CircuitoCLP ou ladder_dsl.ModeloLogico).
    -> (falhas[], resultado_final, [(nome_passo, falhas, resultado)])"""
    est = sim.imagem_inicial(caso)
    passos = caso.get("sequencia") or caso.get("passos")
    hist = []
    if passos:
        r = None
        for i, p in enumerate(passos):
            n = ticks_do_passo(p)
            ent = p.get("entradas") or {}
            est, r = sim.rodar(ent, n, est) if n is not None else sim.regime(ent, est)
            hist.append((p.get("nome", f"passo {i + 1}"), confere(p, r), r))
        falhas = [f"{nm}: {f}" for nm, fs, _ in hist for f in fs]
        if caso.get("status") is not None:
            falhas += [f"{nm}: status {rr['status']} != {caso['status']}" for nm, _, rr in hist
                       if rr["status"] != caso["status"]]
        return falhas, r, hist
    n = ticks_do_passo(caso)
    ent = caso.get("entradas") or {}
    est, r = sim.rodar(ent, n, est) if n is not None else sim.regime(ent, est)
    return confere(caso, r), r, hist


def chaves_invalidas(c, caso):
    """[(campo, chave)] citadas pelo caso que nao existem no circuito (teste vacuo = falso verde)."""
    ruim = []
    validas_ini = set(c.operandos) | set(c.bobinas)
    for b in [caso] + list(caso.get("sequencia") or caso.get("passos") or []):
        for k in (b.get("entradas") or {}):
            if k not in c.entradas:
                ruim.append(("entradas", k))
        for k in (b.get("inicial") or []):
            if k not in validas_ini:
                ruim.append(("inicial", k))
        for k in (b.get("esperado") or []):
            if _nome(k) not in c.bobinas:
                ruim.append(("esperado", k))
        for k in (b.get("esperado_lampadas") or []):
            if _nome(k) not in c.lampadas:
                ruim.append(("esperado_lampadas", k))
        for k in (b.get("esperado_bits") or {}):
            if k not in c.operandos:
                ruim.append(("esperado_bits", k))
    return ruim


def teste_casos(path, casos, sim=None):
    """Roda os casos; imprime `[OK |FALHA] nome: KM=[..] status=S esperado=[..]` + `RESULTADO: n/m OK`."""
    sim = sim or CircuitoCLP(path)
    ok = 0
    for cs in casos:
        falhas, r, hist = executar_caso(sim, cs)
        ok += not falhas
        on = sorted(k for k, v in r["bits"].items() if v)
        print(f"  [{'OK ' if not falhas else 'FALHA'}] {cs.get('nome', '?')}: KM={r['bobinas']} status={r['status']} "
              f"esperado={cs.get('esperado') if not hist else '(sequencia)'} lampadas={r['lampadas']} bits1={on}"
              + (f" -- {'; '.join(falhas)}" if falhas else ""))
        for nm, fs, rr in hist:
            print(f"      - {nm}: KM={rr['bobinas']} lampadas={rr['lampadas']} ticks={rr['ticks']}"
                  f"{' -- ' + '; '.join(fs) if fs else ''}")
    print(f"RESULTADO: {ok}/{len(casos)} OK")
    return bool(casos) and ok == len(casos)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    c = CircuitoCLP(argv[0])
    if len(argv) > 1:
        casos = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        if isinstance(casos, dict):
            casos = casos.get("testes") or (casos.get("layout") or {}).get("testes") or []
        return 0 if teste_casos(argv[0], casos, c) else 1
    print("entradas:", c.entradas)
    print("operandos:", c.operandos)
    print("bobinas:", sorted(c.bobinas), "lampadas:", sorted(c.lampadas))
    print("TON:", [(t["op"], t["T"]) for t in c.tons])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
