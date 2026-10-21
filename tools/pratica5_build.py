#!/usr/bin/env python3
"""Pratica5 LAICOPI — amplia 'Acionamento de motor de forma intercalada CLP.cad'.

Base equivalente ao Pratica5_Part_Intercalada.cad (não consta no acervo;
mapeamento: K1=C1, K2=C2). Acrescenta RT1/RT2, H1-H4 e intertravamento
PERMISSAO = RT1_OK E RT2_OK em 2 camadas (ladder + comando).

Uso: python3 tools/pratica5_build.py  ->  pratica5/Pratica5_Complementar_ALUNO.cad
"""
import re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys as _s
from pathlib import Path as _P
_s.path.insert(0, str(_P(__file__).resolve().parent))
import cade_config  # noqa: E402
BASE = cade_config.acervo() / "Acionamento de motor de forma intercalada CLP.cad"
WORK = ROOT / "pratica5"
BASECOPY = WORK / "Pratica5_Part_Intercalada.cad"
FINAL = WORK / "Pratica5_Complementar_ALUNO.cad"
CLI = ROOT / "src/cade_cli/target/debug/cade_cli"

def split_file(d):
    m = re.search(r'#(?=\*\d+\*\d+#)', d)
    header, rest = d[:m.start()+1], d[m.start()+1:]
    f = rest.find('$$$')
    return header, re.split(r'#(?=\*\d+\*\d+#)', rest[:f]), rest[f:]

def ent_dict(raw):
    m = re.match(r'\*(\d+)\*(\d+)#(.*)$', raw, re.S)
    seq, ide, tail = m.group(1), m.group(2), m.group(3)
    parts = tail.split('#')
    nums, labels = [], parts
    for i, p in enumerate(parts):
        if p.startswith('*') and re.fullmatch(r'(\*-?\d+)+', p):
            nums, labels = p[1:].split('*'), parts[:i]
            break
    return {'seq': seq, 'id': ide, 'labels': labels, 'nums': nums, 'raw': raw}

def set_nums(raw, idx_val):
    """Troca campos nums por índice. idx_val: {indice: novo_valor}."""
    d = ent_dict(raw)
    n = d['nums'][:]
    for i, v in idx_val.items():
        n[i] = str(v)
    return '*' + d['seq'] + '*' + d['id'] + '#' + '#'.join(d['labels']) + '#*' + '*'.join(n)

def set_seq(raw, seq):
    d = ent_dict(raw)
    return '*' + str(seq) + '*' + d['id'] + '#' + '#'.join(d['labels']) + '#*' + '*'.join(d['nums'])

def set_sub(raw, sub):
    d = ent_dict(raw)
    lab = [sub] + d['labels'][1:]
    return '*' + d['seq'] + '*' + d['id'] + '#' + '#'.join(lab) + '#*' + '*'.join(d['nums'])

def wire4018(seq, x1, y1, x2, y2, net):
    return f"*{seq}*4018##########*0*0*0*0*0*0*0*0*{x1}*{y1}*{x2}*{y2}*0*0*0*0*0*0*0*0*0*{net}*0"

def wire4019(seq, x1, y1, x2, y2, net):
    return f"*{seq}*4019##########*0*0*0*0*0*0*0*0*{x1}*{y1}*{x2}*{y2}*0*0*0*0*0*0*0*0*0*{net}*0"

def wire4000(seq, x1, y1, x2, y2, idx):
    return f"*{seq}*4000##########*0*0*0*0*0*0*0*0*{x1}*{y1}*{x2}*{y2}*0*0*0*0*0*0*0*0*0*{idx}*0"

def dot(seq, x, y, net):
    return f"*{seq}*4001##########*0*0*0*0*0*0*0*0*{x}*{y}*{x}*{y}*0*0*0*0*0*0*0*0*0*{net}*0"

def text(seq, x, y, s):
    w = max(21, int(len(s) * 1.8) + 2)
    return f"*{seq}*8### 0# 0# 0# 0# 0# 0# 0# 0*0*0*0*0*0*0*0*0*{x}*{y}*{x+w}*{y+3}*0*0*0*0*0*0*0*0*0*0*0#{s}"

def main():
    WORK.mkdir(exist_ok=True)
    raw0 = BASE.read_bytes()
    d = raw0.decode('latin1')
    header, ents, footer = split_file(d)
    # 0) round-trip do splitter
    assert (header + '#'.join(ents) + footer).encode('latin1') == raw0, "splitter quebrou round-trip"
    by_seq = {}
    for e in ents:
        dd = ent_dict(e)
        by_seq[dd['seq']] = e
    print(f"ents={len(ents)} maxseq={max(int(s) for s in by_seq)}")
    idx4000 = max([int(ent_dict(e)['nums'][21]) for e in ents if ent_dict(e)['id'] == '4000' and len(ent_dict(e)['nums']) > 21])
    print("max idx 4000# =", idx4000)

    def mod(seq, fn):
        by_seq[str(seq)] = fn(by_seq[str(seq)])

    # ---- CAMADA LADDER: contatos NF RT em serie antes das bobinas ----
    mod(72, lambda r: set_nums(r, {22: 62}))                                  # Q0.2NC B 29->62
    mod(90, lambda r: set_nums(r, {8: 276, 9: 72, 10: 285, 11: 72, 21: 62}))   # fio (276-285) A62
    mod(73, lambda r: set_nums(r, {8: 330}))                                  # bobina Q0.1 ->330
    mod(77, lambda r: set_nums(r, {22: 64}))                                  # Q0.1NC B 33->64
    mod(102, lambda r: set_nums(r, {8: 276, 9: 111, 10: 285, 11: 111, 21: 64}))
    mod(78, lambda r: set_nums(r, {8: 330}))
    # ---- RISER net11: abre espaco p/ cadeia NF ----
    mod(28, lambda r: set_nums(r, {11: 100}))                                 # (24,81)->(24,100)
    mod(29, lambda r: set_nums(r, {10: 114}))                                 # trilho (24-114,162)
    # ---- POWER: nada a modificar (RT abaixo dos motores) ----

    new = []
    maxseq = max(int(s) for s in by_seq)
    S = [maxseq + 1]
    print(f"novas seqs a partir de {S[0]}")
    def nxt():
        v = S[0]; S[0] += 1; return v

    # contatos ladder (clona 10051# s72/s77)
    t72, t77 = by_seq['72'], by_seq['77']
    def nc_ladder(donor, seq, x, y, sub, a, b):
        r = set_seq(donor, seq)
        r = set_sub(r, sub)
        return set_nums(r, {8: x, 9: y, 21: a, 22: b})
    new.append(nc_ladder(t72, nxt(), 285, 72, 'RT1', 62, 63))
    new.append(nc_ladder(t72, nxt(), 306, 72, 'RT2', 63, 29))
    new.append(wire4018(nxt(), 297, 72, 306, 72, 63))
    new.append(wire4018(nxt(), 318, 72, 330, 72, 29))
    new.append(nc_ladder(t77, nxt(), 285, 111, 'RT1', 64, 65))
    new.append(nc_ladder(t77, nxt(), 306, 111, 'RT2', 65, 33))
    new.append(wire4018(nxt(), 297, 111, 306, 111, 65))
    new.append(wire4018(nxt(), 318, 111, 330, 111, 33))

    # cadeia NF no riser net11 (clona 8017# do bombas)
    DON8017 = "*5*8017#RT1##95#96######*1*1*0*0*0*0*0*0*141*42*0*0*-18*-3*6*15*0*0*0*1*0*4*17"
    DON8016 = "*4*8016#RT1##97#98######*1*1*0*0*0*0*0*0*204*39*0*0*-18*-3*6*15*0*0*0*1*0*4*5"
    DON6007 = "*139*6007#RT1##1#3#5#2#4#6##*1*1*1*1*1*1*0*0*15*162*0*0*-15*-3*21*15*0*0*0*1*0*38*39"
    DON9008 = "*32*9008#-H1##X1#X2#0#####*1*1*0*0*0*0*0*0*162*180*0*0*-15*-3*9*15*0*0*0*1*0*83*128"
    def placed(donor, seq, x, y, sub, a, b):
        r = set_seq(donor, seq); r = set_sub(r, sub)
        return set_nums(r, {8: x, 9: y, 21: a, 22: b})
    new.append(placed(DON8017, nxt(), 24, 100, 'RT1', 11, 11))
    new.append(wire4019(nxt(), 24, 115, 24, 120, 11))
    new.append(placed(DON8017, nxt(), 24, 120, 'RT2', 11, 11))
    new.append(wire4019(nxt(), 24, 135, 24, 162, 11))

    # bloco de alarmes (feed net6 x54 / retorno net11 x30)
    new.append(wire4018(nxt(), 54, 87, 54, 100, 6))      # coluna L+
    new.append(wire4018(nxt(), 30, 97, 30, 133, 11))     # coluna retorno
    new.append(wire4018(nxt(), 24, 97, 30, 97, 11))      # tap riser
    new.append(wire4018(nxt(), 36, 100, 66, 100, 6))     # ponte feed
    new.append(wire4018(nxt(), 30, 133, 66, 133, 11))    # ponte retorno
    new.append(dot(nxt(), 54, 100, 6))
    new.append(dot(nxt(), 24, 97, 11))
    for x, rt in ((36, 'RT1'), (66, 'RT2')):
        new.append(wire4018(nxt(), x, 100, x, 103, 6))
        new.append(placed(DON8016, nxt(), x, 103, rt, 6, 6))
        new.append(wire4018(nxt(), x, 118, x, 121, 6))
    new.append(placed(DON9008, nxt(), 36, 121, '-H3', 6, 11))
    new.append(placed(DON9008, nxt(), 66, 121, '-H4', 6, 11))
    new.append(wire4018(nxt(), 36, 136, 36, 133, 11))
    new.append(wire4018(nxt(), 66, 136, 66, 133, 11))

    # pilotos H1/H2 em paralelo com K1/K2
    new.append(placed(DON9008, nxt(), 60, 144, '-H1', 10, 11))
    new.append(wire4018(nxt(), 42, 140, 60, 140, 10))
    new.append(dot(nxt(), 42, 140, 10))
    new.append(wire4018(nxt(), 60, 140, 60, 144, 10))
    new.append(wire4019(nxt(), 60, 156, 60, 162, 11))
    new.append(dot(nxt(), 60, 162, 11))
    new.append(placed(DON9008, nxt(), 108, 144, '-H2', 9, 11))
    new.append(wire4018(nxt(), 90, 140, 108, 140, 9))
    new.append(dot(nxt(), 90, 140, 9))
    new.append(wire4018(nxt(), 108, 140, 108, 144, 9))
    new.append(wire4019(nxt(), 108, 156, 108, 162, 11))
    new.append(dot(nxt(), 108, 162, 11))

    # termicos na potencia + stubs
    new.append(placed(DON6007, nxt(), 120, 156, 'RT1', 66, 67))
    new.append(placed(DON6007, nxt(), 150, 156, 'RT2', 68, 69))
    i4000 = [idx4000 + 1]
    def w4(x1, y1, x2, y2):
        v = i4000[0]; i4000[0] += 1; return wire4000(nxt(), x1, y1, x2, y2, v)
    new.append(w4(129, 153, 129, 156))
    new.append(w4(159, 153, 159, 156))
    new.append(w4(130, 171, 130, 183))
    new.append(w4(160, 171, 160, 183))

    # textos: identificacao, legenda, tabela I/O
    T = [('M1 EM FUNCIONAMENTO', 56, 168), ('M2 EM FUNCIONAMENTO', 56, 174),
         ('H3 SOBRECARGA M1', 24, 166), ('H4 SOBRECARGA M2', 84, 166),
         ('PERMISSAO = RT1_OK E RT2_OK', 24, 180),
         ('LEGENDA: RT=rele termico H=piloto', 150, 180),
         ('NF 95-96 / NA 97-98', 150, 186),
         ('TABELA I/O', 24, 186),
         ('I0.1 LIGA / I0.2 CONFIRMA', 24, 192),
         ('Q0.1->K1(M1) Q0.2->K2(M2)', 24, 198),
         ('RT1_OK/RT2_OK termicos NC', 24, 204),
         ('H1 M1 H2 M2 H3 FALTA1 H4 FALTA2', 150, 192)]
    for s, x, y in T:
        new.append(text(nxt(), x, y, s))

    ordered = sorted(by_seq.values(), key=lambda e: int(ent_dict(e)['seq'])) + new
    # guarda: nenhuma entidade original perdida (por seq)
    assert len(by_seq) == len(ents), f"seq duplicada na base: {len(ents)} partes, {len(by_seq)} unicas"
    out = (header + '#'.join(ordered) + footer).encode('latin1')
    shutil.copyfile(BASE, BASECOPY)
    FINAL.write_bytes(out)
    print(f"novas ents={len(new)} bytes={len(out)}")

    # validacao: cade_core parse+emit round-trip + CLI validate
    r = subprocess.run([str(CLI), 'validate', str(FINAL)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout.strip() or r.stderr.strip())
    assert r.returncode == 0, "validate falhou"
    from tempfile import mkdtemp
    import os
    tmp = mkdtemp(prefix='opencode-rt-')
    j, c = os.path.join(tmp, 'a.json'), os.path.join(tmp, 'a.cad')
    assert subprocess.run([str(CLI), 'parse', str(FINAL), '-o', j]).returncode == 0
    assert subprocess.run([str(CLI), 'emit', j, '-o', c]).returncode == 0
    assert Path(c).read_bytes() == out, "round-trip divergiu"
    print("ROUNDTRIP OK")

if __name__ == '__main__':
    main()
