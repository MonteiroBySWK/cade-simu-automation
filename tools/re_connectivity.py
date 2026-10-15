#!/usr/bin/env python3
"""RE da CONECTIVIDADE: nets (A/B) × geometria. Qual manda na simulação?

Para cada .cad do acervo:
- pino de símbolo = (X+dxA, Y+dyA) com net A (idem B), via tools/symbol_pins.json;
- endpoint de fio (4000/4018/4009) com seu net (nums[21]).
Mede:
  (1) fração de endpoints de fio que tocam (±1px) um pino de símbolo;
  (2) entre esses toques, fração em que o net do fio == net do pino;
  (3) fração de endpoints de fio que tocam outro endpoint de fio;
  (4) entre junções de fio-fio, fração com net igual.
Se (2) e (4) forem ~100%, nets e geometria são redundantes (qualquer modelo serve).
Se divergirem, um é o autoritativo e o outro é decorativo.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dissect import parse_ent, split_entities  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ACERVO = Path("/home/monteiro/Downloads/CADe_SIMU 4.0 [BR]/CADe_SIMU 4.0 [BR]/Atividades para Simular/115 arquivos CADe_SIMU/Arquivos .cad")
WIRE = {"4000", "4018", "4009"}
PINS = json.loads((ROOT / "tools" / "symbol_pins.json").read_text())


def processa(path):
    d = path.read_bytes().decode("latin1")
    _, ents, _ = split_entities(d)
    pin_at = defaultdict(list)   # (x,y) -> [net,...]
    weep = []                    # (x,y,net)
    for e in ents:
        p = parse_ent(e)
        if not p or len(p["nums"]) < 23:
            continue
        n = p["nums"]
        try:
            x, y, a, b = int(n[8]), int(n[9]), int(n[21]), int(n[22])
        except ValueError:
            continue
        if p["id"] in WIRE or p["id"] == "4001":
            if p["id"] == "4001":
                continue
            try:
                x2, y2 = int(n[10]), int(n[11])
            except ValueError:
                continue
            weep.append((x, y, a)); weep.append((x2, y2, a))
        else:
            m = PINS.get(p["id"])
            if not m:
                continue
            if "A" in m and a:
                pin_at[(x + m["A"][0], y + m["A"][1])].append(a)
            if "B" in m and b:
                pin_at[(x + m["B"][0], y + m["B"][1])].append(b)
    return pin_at, weep


def main(argv):
    files = sorted(ACERVO.glob("*.cad")) if ACERVO.is_dir() else []
    if argv:
        files = [Path(a) for a in argv]
    toque_no_pino = toque_net_ok = 0
    fio_fio = fio_fio_ok = 0
    pinos_sem_fio = pinos_total = 0
    for f in files:
        try:
            pin_at, weep = processa(f)
        except Exception:
            continue
        wcoord = Counter((x, y) for x, y, _ in weep)
        for (x, y, wnet) in weep:
            hits = []
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    hits += pin_at.get((x + dx, y + dy), [])
            if hits:
                toque_no_pino += 1
                if wnet in hits:
                    toque_net_ok += 1
            elif wcoord[(x, y)] > 1:
                fio_fio += 1
                # net do outro endpoint de fio não é trivial; só conta a junção
        for (x, y), nets in pin_at.items():
            pinos_total += 1
            if wcoord[(x, y)] == 0:
                pinos_sem_fio += 1
    print(f"arquivos: {len(files)}")
    print(f"(1) endpoints de fio sobre pino: {toque_no_pino}")
    if toque_no_pino:
        print(f"(2) ... com net do fio == net do pino: {toque_net_ok} "
              f"({100*toque_net_ok/toque_no_pino:.1f}%)")
    print(f"(3) endpoints de fio sobre outro endpoint de fio: {fio_fio}")
    print(f"(4) pinos totais (com net): {pinos_total} | sem fio no ponto: {pinos_sem_fio} "
          f"({100*pinos_sem_fio/max(pinos_total,1):.1f}%)")


if __name__ == "__main__":
    main(sys.argv[1:])
