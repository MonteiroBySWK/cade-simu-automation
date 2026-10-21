#!/usr/bin/env python3
"""Testes do verificador E2E (tools/app_sim.py).

- Unitarios (sem Wine): calibracao coordenada->pixel e leitura de cor em imagens sinteticas.
- Smoke E2E (precisa de DISPLAY + wine + CADe_SIMU; `skipif` caso contrario): abre
  tools/examples/partida_direta no app, Play, S1 liga KM1, selo, S0 desliga.
"""
import json
import os
import shutil
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import app_sim as A  # noqa: E402

EX = TOOLS / "examples"


def _cad(tmp_path, nome="partida_direta"):
    import build_spec
    spec = json.loads((EX / f"{nome}.layout.json").read_text(encoding="utf-8"))
    out = tmp_path / f"{nome}.cad"
    build_spec.construir(spec, str(out))   # o .cad e gravado mesmo se o gate acusar (nao testamos o gate aqui)
    assert out.is_file()
    return out, spec["testes"]


def _tela(cad, s, ox, oy, size=(956, 523)):
    """Imagem sintetica no estilo do app: fundo branco, fios cinza (128) em px = ox + s*x."""
    im = Image.new("RGB", size, (255, 255, 255))
    d = ImageDraw.Draw(im)
    for x1, y1, x2, y2 in cad.fios:
        d.line([(ox + s * x1, oy + s * y1), (ox + s * x2, oy + s * y2)], fill=(128, 128, 128))
    return im


@pytest.mark.parametrize("s,ox,oy", [(1.0, 32, 102), (2.0, 31, 102), (2.0, -40, 20)])
def test_calibra_escala_e_offset(tmp_path, s, ox, oy):
    cad_path, _ = _cad(tmp_path)
    cad = A.Cad(cad_path)
    cal = A.calibrar(_tela(cad, s, ox, oy), cad)
    assert cal is not None
    assert cal.s == s
    # px = ox + s*x  (tolerancia de 1 px pela dilatacao/arredondamento)
    px, py = cal.px(cad.xmin, cad.ymin)
    assert abs(px - (ox + s * cad.xmin)) <= 1 and abs(py - (oy + s * cad.ymin)) <= 1


def test_calibra_recusa_imagem_vazia(tmp_path):
    cad_path, _ = _cad(tmp_path)
    cad = A.Cad(cad_path)
    assert A.calibrar(Image.new("RGB", (956, 523), (255, 255, 255)), cad) is None


def test_le_bobina_e_lampada_pelo_vermelho(tmp_path):
    cad_path, _ = _cad(tmp_path)
    cad = A.Cad(cad_path)
    s, ox, oy = 2.0, 31, 102
    im = _tela(cad, s, ox, oy)
    d = ImageDraw.Draw(im)
    bob = next(x for x in cad.simbolos if x["classe"] == "9000")
    lamp = next(x for x in cad.simbolos if x["classe"] == "9008")
    for sim in (bob,):   # bobina energizada: contorno vermelho + enchimento cinza 192
        cx, cy = ox + s * sim["x"], oy + s * (sim["y"] + 6)
        d.rectangle([cx - 8, cy - 5, cx + 8, cy + 5], fill=(192, 192, 192), outline=(255, 0, 0))
    cal = A.calibrar(im, cad)
    est = A.ler_estado(im, cad, cal)
    assert est["bobinas"] == {"KM1": True}
    assert est["lampadas"] == {"H1": False}
    assert lamp["chave"] == "H1"


def test_entradas_termico_exige_mesmo_rotulo(tmp_path):
    cad_path, _ = _cad(tmp_path)
    cad = A.Cad(cad_path)
    ents = cad.entradas()
    assert ents["S1"]["modo"] == "segurar" and ents["S0"]["modo"] == "segurar"
    # 6007 e contato 8017 com o MESMO rotulo (-RT1): o clique no 6007 dispara e o contato segue
    assert ents["RT1"]["modo"] == "alternar"
    assert ents["RT1"]["simbolo"] is not None


def test_cli_sem_display_nao_quebra_importacao():
    assert callable(A.executar_casos) and callable(A.main)


def _tem_ambiente():
    if os.environ.get("CADE_E2E") != "1":      # opt-in: este teste ABRE o Wine (~1 min)
        return False
    if not os.environ.get("DISPLAY") or not shutil.which("wine") or not shutil.which("xdotool"):
        return False
    return (A.W.EXE_DIR / A.W.EXE).is_file() and not A.W.pids_cade()


@pytest.mark.skipif(not _tem_ambiente(), reason="opt-in: defina CADE_E2E=1 (e tenha DISPLAY/wine/CADe_SIMU livres) — abre o Wine")
def test_e2e_partida_direta_no_app(tmp_path):
    cad_path, testes = _cad(tmp_path)
    casos = [c for c in testes if c["nome"] in ("repouso desligado", "S1 liga KM1", "selo mantem KM1", "S0 desliga")]
    r = A.executar_casos(cad_path, casos, saida=str(tmp_path / "shots"))
    assert not r.get("erro"), r
    res = {c["nome"]: c["resultado"] for c in r["casos"]}
    assert res == {c["nome"]: "ok" for c in casos}, r["casos"]
    assert r["ok"]
    assert not A.W.pids_cade(), "o verificador deve sempre dar down"
    assert (tmp_path / "shots" / "repouso.png").is_file()
