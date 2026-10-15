#!/usr/bin/env python3
"""Extrai gramática observada dos .cad do corpus.

Uso:
    python3 tools/extract_ids.py corpus/*.cad > docs/dicionario-simbolos.md
    python3 tools/extract_ids.py --summary corpus/*.cad
"""
import glob
import re
import sys

ID_RE = re.compile(r"(\d{4})#([^#*]*)")


def parse_file(path):
    raw = open(path, "rb").read()
    txt = raw.decode("latin1")
    header = txt[:120]
    # header: CADe_SIMU*modo*versao...
    parts = txt.split("*")
    modo = parts[1] if len(parts) > 1 else "?"
    versao_raw = parts[2] if len(parts) > 2 else "?"
    versao = versao_raw.split("#")[0]
    titulo = ""
    m = re.search(r"\*(\d+)#([^#]*?)#+", txt)
    if m:
        titulo = m.group(2)
    ids = ID_RE.findall(txt)
    fios = txt.count("4000#")
    return {
        "path": path,
        "bytes": len(raw),
        "nstars": txt.count("*"),
        "nhash": txt.count("#"),
        "modo": modo,
        "versao": versao,
        "titulo": titulo,
        "ids": ids,
        "fios": fios,
        "has_dollar": "$$$" in txt,
    }


def main(args):
    files = [a for a in args if not a.startswith("-")]
    summary = "--summary" in args
    if not files:
        files = sorted(glob.glob("corpus/*.cad"))
    infos = [parse_file(f) for f in files]
    # agregado de IDs
    agg = {}
    for info in infos:
        for code, sub in info["ids"]:
            key = (code, sub)
            agg.setdefault(key, {"count": 0, "files": set()})
            agg[key]["count"] += 1
            agg[key]["files"].add(info["path"].split("/")[-1])

    if summary:
        for info in infos:
            print(
                f"{info['path']}: {info['bytes']}b modo={info['modo']} "
                f"versao={info['versao']} titulo={info['titulo']!r} "
                f"stars={info['nstars']} hash={info['nhash']} "
                f"fios={info['fios']} $$$={info['has_dollar']} "
                f"entidades={len(info['ids'])}"
            )
        return

    print("# Dicionário de símbolos — gerado por tools/extract_ids.py")
    print()
    print("## Arquivos")
    print()
    print("| arquivo | bytes | modo | versao | titulo | `*` | `#` | fios `4000#` | $$$ | entidades |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for info in infos:
        print(
            f"| `{info['path']}` | {info['bytes']} | {info['modo']} | "
            f"{info['versao']} | {info['titulo']!r} | {info['nstars']} | "
            f"{info['nhash']} | {info['fios']} | {info['has_dollar']} | {len(info['ids'])} |"
        )
    print()
    print("## IDs `NNNN#SUB` únicos")
    print()
    print("| ID | SUB | ocorrências | arquivos |")
    print("|---|---|---|---|")
    for (code, sub), v in sorted(agg.items(), key=lambda kv: (-kv[1]["count"], kv[0])):
        files_s = ", ".join(sorted(v["files"]))
        print(f"| {code} | {sub!r} | {v['count']} | {files_s} |")
    print()
    print("## Notas")
    print()
    print("- `4000#` = fio/cabo (hipótese a confirmar na Fase 2).")
    print("- Coordenadas negativas preservadas no round-trip (ver Review Focus).")
    print("- Entidades desconhecidas devem fazer round-trip byte-idêntico.")


if __name__ == "__main__":
    main(sys.argv[1:])
