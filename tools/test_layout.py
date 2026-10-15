#!/usr/bin/env python3
"""Testes do motor de layout (pytest ou `python3 tools/test_layout.py`)."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import layout  # noqa: E402

EX = TOOLS / "examples"
CASOS = ["intercalada.layout.json", "partida_direta.layout.json"]


def _low(nome):
    return layout.compilar(json.loads((EX / nome).read_text())["layout"])


def test_sem_coordenadas_na_entrada():
    for nome in CASOS:
        d = json.loads((EX / nome).read_text())["layout"]
        def varre(o):
            if isinstance(o, dict):
                assert not ({"x", "y"} & set(o)), o
                for v in o.values():
                    varre(v)
            elif isinstance(o, list):
                for v in o:
                    varre(v)
        varre(d)


def test_dentro_da_folha_e_sem_sobreposicao():
    for nome in CASOS:
        low = _low(nome)          # _check_folha ja levanta; reconfere aqui
        boxes = []
        for s in low["simbolos"]:
            w, h = layout.dim(s["classe"])
            w = layout._width(s["classe"])
            b = (s["x"], s["y"], s["x"] + w, s["y"] + h)
            assert b[2] <= 455 and b[3] <= 295, (nome, s["id"], b)
            for o in boxes:
                assert not (b[0] < o[2] and o[0] < b[2] and b[1] < o[3] and o[1] < b[3]), (nome, s["id"])
            boxes.append(b)


def test_potencia_alinhada_3_colunas_por_fase():
    low = _low("intercalada.layout.json")
    xs = {s["id"]: s["x"] for s in low["simbolos"]}
    assert xs["Q1"] == xs["F1"] == xs["KM1p"] == xs["M1"]
    assert xs["Q2"] == xs["F2"] == xs["KM2p"] == xs["M2"]
    assert xs["Q2"] > xs["Q1"]


def _gate(nome, tmp):
    out = str(Path(tmp) / (nome + ".cad"))
    r = subprocess.run([sys.executable, str(TOOLS / "build_spec.py"), str(EX / nome), out],
                       capture_output=True, text=True, timeout=600)
    f = subprocess.run([sys.executable, str(TOOLS / "wires_check.py"), out],
                       capture_output=True, text=True)
    return r.stdout, f.stdout, r.returncode, f.returncode


def test_gate_intercalada():
    with tempfile.TemporaryDirectory() as t:
        so, fo, rc, frc = _gate("intercalada.layout.json", t)
        assert "GATE: OK" in so and rc == 0, so[-600:]
        assert "RESULTADO: 15/15 OK" in so
        assert frc == 0 and "FIOS: ok" in fo, fo


def test_gate_partida_direta_1_motor():
    # cad_test e fixo p/ a intercalada: so os casos de KM1/RT1 se aplicam aqui.
    with tempfile.TemporaryDirectory() as t:
        so, fo, rc, frc = _gate("partida_direta.layout.json", t)
        assert "GATE: OK" in so and rc == 0, so[-600:]
        for caso in ("S1 liga KM1", "selo mantém KM1", "S0 desliga tudo",
                     "sem auto-religamento", "RT1 aberto bloqueia:"):
            linha = [l for l in so.splitlines() if caso in l]
            assert linha and "[OK ]" in linha[0], (caso, linha)
        assert frc == 0 and "FIOS: ok" in fo, fo


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
