#!/usr/bin/env python3
"""Simulador funcional de circuitos CADe por NETLIST (sem GUI).

Lê o .cad, monta o grafo de NETs e resolve a lógica dos contatos/bobinas por
relaxação (contatos auxiliares dependem das bobinas — selo/intertravamento).
Permite montar uma TABELA-VERDADE e ASSERir o comportamento (prova funcional).

Modelo:
- Contatos: NO {8000,8016,7000,10050} fecham quando o comando está ON;
            NC {8001,8017,7001,10051} fecham quando OFF.
- Bobinas: {9000,10060}. Auxiliares (7000/7001) cujo rótulo casa com uma bobina
  são comandados por ela; botões/térmicos são ENTRADAS externas.
- Fonte (supply) = net do A do 1º elemento em série; retorno = net comum dos B das bobinas.

Uso:
  python3 tools/netlist_sim.py out/intercalada.cad            # imprime tabela-verdade
  python3 tools/netlist_sim.py out/intercalada.cad --test     # roda os asserts
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dissect import parse_ent, split_entities  # noqa: E402

NO = {"8000", "8016", "7000", "10050"}
NC = {"8001", "8017", "7001", "10051"}
COIL = {"9000", "10060"}
WIRE = {"4000", "4018", "4009", "4001"}


def _nome(rot):
    return (rot or "").lstrip("-").strip()


class Circuito:
    def __init__(self, path):
        d = Path(path).read_bytes().decode("latin1")
        _, ents, _ = split_entities(d)
        self.contatos = []   # (tipo 'NO'/'NC', A, B, chave)
        self.bobinas = {}    # chave -> (A, B)
        self.entradas = []   # chaves externas (botões/térmicos)
        coil_names = set()
        ps = [p for p in map(parse_ent, ents) if p]
        for p in ps:
            if p["id"] in COIL and len(p["nums"]) > 22:
                k = _nome(p["labels"][0] if p["labels"] else p["id"])
                self.bobinas[k] = (int(p["nums"][21]), int(p["nums"][22]))
                coil_names.add(k)
        for p in ps:
            if p["id"] in NO or p["id"] in NC:
                if len(p["nums"]) <= 22:
                    continue
                k = _nome(p["labels"][0] if p["labels"] else p["id"])
                a, b = int(p["nums"][21]), int(p["nums"][22])
                if a == 0 or b == 0:
                    continue
                self.contatos.append(("NO" if p["id"] in NO else "NC", a, b, k))
                if k not in coil_names:
                    self.entradas.append(k)
        self.entradas = sorted(set(self.entradas))
        # fonte/retorno
        self.supply = self.contatos[0][1] if self.contatos else 21
        bcount = defaultdict(int)
        for a, b in self.bobinas.values():
            bcount[b] += 1
        self.ret = max(bcount, key=bcount.get) if bcount else None

    def resolve(self, ent, inicial=None):
        """ent: {chave: bool} (True = acionado). inicial: bobinas já energizadas.
        Retorna (status, set) onde status ∈ {'OK','RACE','INSTAVEL'}."""
        coil = {k: (k in (inicial or set())) for k in self.bobinas}
        vistos = set()
        for _ in range(40):
            parent = {}

            def find(x):
                parent.setdefault(x, x)
                while parent[x] != x:
                    parent[x] = parent[parent[x]]; x = parent[x]
                return x

            def union(x, y):
                rx, ry = find(x), find(y)
                if rx != ry:
                    parent[ry] = rx

            for tipo, a, b, k in self.contatos:
                fechado = (ent.get(k, False) if k not in self.bobinas else coil.get(k, False))
                if tipo == "NC":
                    fechado = not fechado
                if fechado:
                    union(a, b)
            novo = {}
            for k, (a, b) in self.bobinas.items():
                novo[k] = (self.ret is not None and find(a) == find(self.supply) and find(b) == find(self.ret))
            assin = tuple(sorted(k for k, v in novo.items() if v))
            if novo == coil:
                return "OK", {k for k, v in novo.items() if v}
            if assin in vistos:
                return "RACE", {k for k, v in novo.items() if v}
            vistos.add(assin)
            coil = novo
        return "INSTAVEL", {k for k, v in coil.items() if v}


def tabela(path):
    c = Circuito(path)
    print(f"# {path} | supply={c.supply} retorno={c.ret}")
    print("contatos:", [(t, a, b, k) for t, a, b, k in c.contatos])
    print("bobinas:", c.bobinas, "| entradas:", c.entradas)
    return c


def teste_casos(path, casos):
    """Roda casos declarados na spec: [{"nome","entradas":{k:bool},"inicial":[...],
    "esperado":[...]|null,"status":"OK"|"RACE"|null}]. True se todos passam."""
    c = Circuito(path)
    ok = 0
    for cs in casos:
        status, got = c.resolve(cs.get("entradas", {}), set(cs.get("inicial", [])))
        cond = True
        if cs.get("status") is not None:
            cond = cond and status == cs["status"]
        if cs.get("esperado") is not None:
            cond = cond and got == set(cs["esperado"])
        ok += cond
        print(f"  [{'OK ' if cond else 'FALHA'}] {cs.get('nome', '?')}: KM={sorted(got)} status={status} "
              f"esperado={cs.get('esperado')}")
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
