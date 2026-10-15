#!/usr/bin/env python3
"""Simulador lógico das 2 rungs de intercalada (verificação T1–T7 + equivalência base).

Netlist extraída do .cad e AUTO-CHECADA contra o arquivo antes de simular.
Contatos 10050#=NA, 10051#=NF. RT=1 significa térmico DISPARADO.

Uso: python3 tools/ladder_sim.py base.cad final.cad
"""
import sys
sys.path.insert(0, __import__('pathlib').Path(__file__).resolve().parent.as_posix())
from dissect import split_entities, parse_ent

def rung_contacts(path):
    d = open(path, 'rb').read().decode('latin1')
    _, ents, _ = split_entities(d)
    out = []
    for p in map(parse_ent, ents):
        if p and p['id'] in ('10050', '10051') and len(p['nums']) > 22:
            y = int(p['nums'][9])
            if y in (72, 111, 129):
                out.append((y, int(p['nums'][8]), p['id'], (p['labels'] + [''])[0],
                            p['nums'][21], p['nums'][22]))
    return sorted(out)

def check(path, expect):
    got = rung_contacts(path)
    assert got == sorted(expect), f"netlist divergente em {path}:\n{got}"
    return True

# (y, x, id, sub, A, B) — RUNG1 serie; RUNG2 tronco+2 ramos; SEL (y129) em // com I0.2+B3
BASE = [
    (72, 201, '10050', 'I0.1', '25', '26'), (72, 222, '10050', 'I0.2', '26', '27'),
    (72, 243, '10051', 'B3:L', '27', '28'), (72, 264, '10051', 'Q0.2', '28', '29'),
    (111, 201, '10050', 'I0.1', '25', '30'), (111, 222, '10050', 'I0.2', '30', '31'),
    (111, 243, '10050', 'B3:L', '31', '34'), (111, 264, '10051', 'Q0.1', '34', '33'),
    (129, 222, '10050', 'Q0.2', '30', '34'),
]
FINAL = [
    (72, 201, '10050', 'I0.1', '25', '26'), (72, 222, '10050', 'I0.2', '26', '27'),
    (72, 243, '10051', 'B3:L', '27', '28'), (72, 264, '10051', 'Q0.2', '28', '62'),
    (72, 285, '10051', 'RT1', '62', '63'), (72, 306, '10051', 'RT2', '63', '29'),
    (111, 201, '10050', 'I0.1', '25', '30'), (111, 222, '10050', 'I0.2', '30', '31'),
    (111, 243, '10050', 'B3:L', '31', '34'), (111, 264, '10051', 'Q0.1', '34', '64'),
    (111, 285, '10051', 'RT1', '64', '65'), (111, 306, '10051', 'RT2', '65', '33'),
    (129, 222, '10050', 'Q0.2', '30', '34'),
]

def solve(table, inp):
    """inp: dict I0.1,I0.2,B3,RT1,RT2 (0/1). Retorna (Q0.1,Q0.2) por ponto fixo."""
    Q = {'Q0.1': 0, 'Q0.2': 0}
    def closed(y, x, ide, sub, a, b):
        ref = sub
        v = inp.get(ref, Q.get(ref, 0))
        return (v == 0) if ide == '10051' else (v == 1)
    for _ in range(10):
        nQ = {}
        # rung1: serie 25->29
        chain1 = sorted([c for c in table if c[0] == 72], key=lambda c: c[1])
        net = '25'
        for (y, x, ide, sub, a, b) in chain1:
            assert a == net, f"cadeia rung1 quebrada em {sub}"
            net = b
        assert net == '29', "rung1 nao termina na bobina (net 29)"
        ok = all(closed(*c) for c in chain1)
        nQ['Q0.1'] = 1 if ok else 0
        # rung2: tronco 25->30, ramos (30->31->34 | 30->34), comum 34->33
        tr = {c[3]: c for c in table if c[0] == 111}
        seal = [c for c in table if c[0] == 129]
        assert len(seal) == 1 and seal[0][3] == 'Q0.2', "selo mudou"
        def C(k): return closed(*tr[k])
        br1 = C('I0.2') and tr['I0.2'][4] == '30' and tr['B3:L'][4] == '31' and C('B3:L')
        br2 = closed(*seal[0])
        com = C('Q0.1') and (C('RT1') if 'RT1' in tr else True) and (C('RT2') if 'RT2' in tr else True)
        nQ['Q0.2'] = 1 if (C('I0.1') and (br1 or br2) and com) else 0
        if nQ == Q: break
        Q = nQ
    return Q['Q0.1'], Q['Q0.2']

def main():
    base, final = sys.argv[1], sys.argv[2]
    check(base, BASE); print("netlist base OK")
    check(final, FINAL); print("netlist final OK (RT1/RT2 em serie nas 2 rungs)")
    fails = []
    def T(nome, inp, esp):
        q = solve(FINAL, inp)
        h = {'H1': q[0], 'H2': q[1], 'H3': inp['RT1'], 'H4': inp['RT2']}
        ok = q == esp
        print(f"{nome}: Q={q} H1={h['H1']} H2={h['H2']} H3={h['H3']} H4={h['H4']} esperado Q={esp} -> {'PASS' if ok else 'FAIL'}")
        if not ok: fails.append(nome)
    I = {'I0.1': 0, 'I0.2': 0, 'B3:L': 0, 'RT1': 0, 'RT2': 0}
    T("T1a parte M1 (I0.1+I0.2, B3=0, sadio)", {**I, 'I0.1': 1, 'I0.2': 1}, (1, 0))
    T("T1b parte M2 (I0.1+I0.2+B3=1, sadio)", {**I, 'I0.1': 1, 'I0.2': 1, 'B3:L': 1}, (0, 1))
    T("T2 RT1 com M1 (tudo 1)", {'I0.1': 1, 'I0.2': 1, 'B3:L': 1, 'RT1': 1, 'RT2': 0}, (0, 0))
    T("T3 RT2 com comando M2", {'I0.1': 1, 'I0.2': 1, 'B3:L': 1, 'RT1': 0, 'RT2': 1}, (0, 0))
    T("T4 ambos ligados + RT1", {'I0.1': 1, 'I0.2': 1, 'B3:L': 1, 'RT1': 1, 'RT2': 0}, (0, 0))
    T("T5 LIGA com termico atuado", {'I0.1': 1, 'I0.2': 1, 'B3:L': 1, 'RT1': 0, 'RT2': 1}, (0, 0))
    T("T6 rearmado sem LIGA", {**I}, (0, 0))
    T("T7 rearmado + LIGA M1", {**I, 'I0.1': 1, 'I0.2': 1}, (1, 0))
    # equivalencia base x final com RT=0 (sequencia original preservada)
    n = 0
    for a in (0, 1):
        for b in (0, 1):
            for c in (0, 1):
                inp = {'I0.1': a, 'I0.2': b, 'B3:L': c, 'RT1': 0, 'RT2': 0}
                if solve(BASE, inp) != solve(FINAL, inp):
                    fails.append(f"EQUIV RT=0 {inp}"); print("EQUIV FAIL", inp)
                n += 1
    print(f"equivalencia base==final (RT=0): {n}/8 combinacoes")
    print("RESULTADO:", "FAIL " + str(fails) if fails else "ALL PASS")
    return 1 if fails else 0

if __name__ == '__main__':
    raise SystemExit(main())
