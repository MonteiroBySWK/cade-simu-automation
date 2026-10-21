#!/usr/bin/env python3
"""Gera tools/symbol_lib.json: entidade-prototipo (rotulos padrao + geometria) por CLASSE.

Fonte: corpus/*.cad + acervo ($CADE_ACERVO, opcional). Roda so quando se quer ATUALIZAR o catalogo
(o resultado e versionado, entao quem clona o repo NAO precisa do app nem do acervo).
Uso: python3 tools/gen_symbol_lib.py
"""
import json
import sys
from pathlib import Path

T = Path(__file__).resolve().parent
sys.path.insert(0, str(T))
import cade_config  # noqa: E402
from dissect import parse_ent, split_all  # noqa: E402

lib = {}
fontes = sorted((T.parent / "corpus").glob("*.cad"))
ac = cade_config.acervo()
if ac.is_dir():
    fontes += sorted(ac.glob("*.cad"))
else:
    print(f"aviso: acervo ausente ({ac}); usando so corpus/", file=sys.stderr)
for f in fontes:
    try:
        _, ents, _ = split_all(f.read_bytes().decode("latin1"))
    except Exception:
        continue
    for e in ents:
        p = parse_ent(e)
        if p and p["id"] not in lib and len(p["nums"]) >= 23:
            lib[p["id"]] = {"labels": p["labels"], "nums": p["nums"]}
(T / "symbol_lib.json").write_text(json.dumps(lib, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
print(f"{len(lib)} classes -> tools/symbol_lib.json")
