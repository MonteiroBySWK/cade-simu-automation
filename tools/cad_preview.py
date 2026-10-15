#!/usr/bin/env python3
"""Render esquemático aproximado de .cad (conferência geométrica, não oficial).

Uso: python3 tools/cad_preview.py entrada.cad -o saida.png [--scale 3]
Desenha fios (4000/4001/4009/4010/4018/4019), símbolos (bbox X,Y,W,H+id) e textos (id 8).
"""
import sys
sys.path.insert(0, __import__('pathlib').Path(__file__).resolve().parent.as_posix())
from dissect import split_entities, parse_ent
from PIL import Image, ImageDraw

WIRE = {'4000', '4001', '4009', '4010', '4018', '4019'}
CORES = {'4000': (200, 0, 0), '4001': (200, 0, 0), '4009': (0, 0, 200),
         '4010': (0, 150, 0), '4018': (0, 150, 0), '4019': (0, 0, 200)}

def main(a):
    src, out, scale = a[0], 'out/preview.png', 3
    i = 1
    while i < len(a):
        if a[i] == '-o': out = a[i+1]; i += 2
        elif a[i] == '--scale': scale = int(a[i+1]); i += 2
        else: i += 1
    d = open(src, 'rb').read().decode('latin1')
    _, ents, _ = split_entities(d)
    ps = [p for p in map(parse_ent, ents) if p]
    W, H = 440, 220
    img = Image.new('RGB', (W*scale, H*scale), 'white')
    dr = ImageDraw.Draw(img)
    S = lambda v: int(v) * scale
    for p in ps:
        n = p['nums']
        if len(n) < 16: continue
        x, y = int(n[8]), int(n[9])
        if p['id'] in WIRE:
            x2, y2 = int(n[10]), int(n[11])
            c = CORES.get(p['id'], (0, 0, 0))
            if x == x2 and y == y2:
                dr.ellipse([S(x)-3, S(y)-3, S(x)+3, S(y)+3], fill=c)
            else:
                dr.line([S(x), S(y), S(x2), S(y2)], fill=c, width=max(1, scale//2))
        elif p['id'] == '8':
            txt = p['raw'].split('#')[-1][:40]
            dr.text((S(x), S(y)), txt, fill=(0, 0, 0))
        else:
            w, h = int(n[14]), int(n[15])
            dr.rectangle([S(x), S(y), S(x+w), S(y+h)], outline=(0, 0, 0))
            lab = (p['labels'] + [''])[0]
            dr.text((S(x), S(y)-9), f"{p['id']}#{lab}", fill=(150, 0, 150))
    img.save(out)
    print(f"preview -> {out} ({len(ps)} ents)")

if __name__ == '__main__':
    main(sys.argv[1:])
