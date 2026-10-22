#!/usr/bin/env python3
"""Disseca .cad em entidades e alinha campos por ID (probe RE — Fase Pratica5)."""
import re, sys

def split_entities(d):
    # header até o primeiro '#*N*ID#' ; footer a partir do primeiro '$$$'
    m = re.search(r'#(?=\*\d+\*-?\d+#)', d)
    header, rest = d[:m.start()+1], d[m.start()+1:]
    f = rest.find('$$$')
    body, footer = rest[:f], rest[f:]
    ents = []
    for e in re.split(r'#(?=\*\d+\*-?\d+#)', body):
        ents += _desgruda(e)
    return header, ents, footer


# Entidade = `*seq*id#` + rotulos + `*n`x23 + `#%s` (string final, quase sempre vazia). Quando a string
# NAO e vazia (IP do CPU 10206, texto da classe 8) a proxima entidade vem colada a ela, sem '#':
# `...*31*32#192.128.0.1*26*10204#I0.1...`. Sem separar, o 10204 seguinte some dentro do 10206.
_GRUDADA = re.compile(r'#((?:\*-?\d+){4,})#([^#*]*)(?=\*\d+\*-?\d+#)')


def _desgruda(e):
    out = []
    while True:
        m = _GRUDADA.search(e)
        if not m:
            out.append(e)
            return out
        out.append(e[:m.end()])
        e = e[m.end():]

def split_all(d):
    """Como split_entities, mas a entidade 0 (serializada colada ao 'CADe_SIMU*') entra em ents.
    A entidade 0 e uma entidade comum (seq 0): no acervo e o 1o simbolo/fonte do desenho."""
    header, ents, footer = split_entities(d)
    m = re.match(r'CADe_SIMU\*(\d+\*-?\d+#.*)#$', header, re.S)
    if m:
        ents = ['*' + m.group(1)] + ents
        header = 'CADe_SIMU*'
    return header, ents, footer


def parse_ent(e):
    m = re.match(r'\*(\d+)\*(-?\d+)#(.*)$', e, re.S)
    if not m: return None
    seq, idc, tail = m.group(1), m.group(2), m.group(3)
    # sub e labels até o último '#' antes dos nums? heurística: campos alpha vs nums
    # separa tail em blocos '#' e acha onde começam os nums '*n...'
    parts = tail.split('#')
    # o bloco de nums é o último bloco não-vazio começando com '*'
    nums = []
    labels = []
    for i, p in enumerate(parts):
        if p.startswith('*') and re.fullmatch(r'(\*-?\d+)+', p):
            nums = p[1:].split('*')
            labels = parts[:i]
            break
    else:
        labels = parts
    extra = ''
    if nums:
        resto = tail.split('#', i + 1)
        extra = resto[i + 1] if len(resto) > i + 1 else ''
    return {'seq': seq, 'id': idc, 'labels': labels, 'nums': nums, 'raw': e, 'extra': extra}

def show_group(ents, idc, maxn=6):
    g = [p for p in map(parse_ent, ents) if p and p['id'] == idc]
    print(f'=== ID {idc} ({len(g)} ent)')
    for p in g[:maxn]:
        print(f"  seq={p['seq']} labels={p['labels']}")
        print(f"    nums={p['nums']}")
    return g

if __name__ == '__main__':
    d = open(sys.argv[1], 'rb').read().decode('latin1')
    header, ents, footer = split_entities(d)
    print('HEADER:', header[:200]); print('NENT:', len(ents)); print('FOOTER:', footer[:150])
    for idc in sys.argv[2:]:
        show_group(ents, idc)
