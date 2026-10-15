#!/usr/bin/env python3
"""Pipeline Fase 4 (baseline): imagem PNG/JPG/BMP → cade.json + preview + log.

Baseline honesto v0.1: sem ML. Extrai estatísticas (tinta, projeções H/V)
via PIL+numpy e gera `cade.json` em formato template-mínimo (aceito por
`cade_cli new-from-json`) + bloco `analise` com decisões e confiança.
O `.cad` final é gerado de forma determinística via `cade_cli`, logo
sempre abre no CADe_SIMU (critério F2 parcial; precisão ≥80% fica p/ ML futuro).

Uso:
    python3 tools/img2json.py "Exemplos/.../exemplo01.png" -o out/exemplo01.json --preview out/exemplo01.preview.png
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def analisar(png: Path):
    img = Image.open(png).convert("L")
    a = np.asarray(img)
    h, w = a.shape
    tinta = a < 128
    densidade = float(tinta.mean())
    # projeções: linhas com muita tinta = possíveis fios horizontais/verticais
    proj_h = tinta.mean(axis=1)
    proj_v = tinta.mean(axis=0)
    linhas_h = [int(i) for i in np.where(proj_h > 0.30)[0][:50]]
    linhas_v = [int(i) for i in np.where(proj_v > 0.30)[0][:50]]
    return {
        "w": w,
        "h": h,
        "densidade_tinta": round(densidade, 4),
        "linhas_horizontais_candidatas": linhas_h[:20],
        "linhas_verticais_candidatas": linhas_v[:20],
        "n_h": len(linhas_h),
        "n_v": len(linhas_v),
    }


def main(argv):
    if len(argv) < 1 or "-h" in argv or "--help" in argv:
        print(__doc__)
        return 2
    src = Path(argv[0])
    out_json = Path("out/img.json")
    out_preview = None
    i = 1
    while i < len(argv):
        if argv[i] == "-o" and i + 1 < len(argv):
            out_json = Path(argv[i + 1])
            i += 2
        elif argv[i] == "--preview" and i + 1 < len(argv):
            out_preview = Path(argv[i + 1])
            i += 2
        else:
            i += 1
    info = analisar(src)
    # Decisões baseline com confiança explícita (baixa — sem classificador ainda)
    decisoes = [
        {
            "simbolo": "fios_horizontais",
            "qtd": info["n_h"],
            "confianca": 0.40,
            "nota": "projeção H >30% tinta; pode incluir texto/linhas de legenda",
        },
        {
            "simbolo": "fios_verticais",
            "qtd": info["n_v"],
            "confianca": 0.40,
            "nota": "projeção V >30% tinta",
        },
        {
            "simbolo": "classificacao_contatos/bobinas",
            "qtd": 0,
            "confianca": 0.0,
            "nota": "não implementado v0.1 — requer template matching/ML (Fase 4 completa)",
        },
    ]
    data = {
        "meta": {"titulo": src.stem[:24] or "-X", "modo": "0", "versao": "3000"},
        "analise": {"fonte_imagem": str(src), **info, "decisoes": decisoes},
        "simbolos": [],
        "fios": [],
        "textos": [],
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"img2json {src} -> {out_json} ({info['w']}x{info['h']} tinta={info['densidade_tinta']})")
    if out_preview:
        img = Image.open(src).convert("RGB")
        d = ImageDraw.Draw(img)
        for y in info["linhas_horizontais_candidatas"]:
            d.line([(0, y), (info["w"], y)], fill=(255, 0, 0))
        for x in info["linhas_verticais_candidatas"]:
            d.line([(x, 0), (x, info["h"])], fill=(0, 0, 255))
        out_preview.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_preview)
        print(f"preview -> {out_preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
