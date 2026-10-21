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
CASOS = ["intercalada.layout.json", "partida_direta.layout.json", "reversao.layout.json"]


def _low(nome):
    return layout.compilar(json.loads((EX / nome).read_text(encoding="utf-8"))["layout"])


def test_sem_coordenadas_na_entrada():
    for nome in CASOS:
        d = json.loads((EX / nome).read_text(encoding="utf-8"))["layout"]
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
            assert b[2] <= layout.SHEET_X and b[3] <= layout.SHEET_Y, (nome, s["id"], b)
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
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    f = subprocess.run([sys.executable, str(TOOLS / "wires_check.py"), out],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout, f.stdout, r.returncode, f.returncode


def test_gate_intercalada():
    with tempfile.TemporaryDirectory() as t:
        so, fo, rc, frc = _gate("intercalada.layout.json", t)
        assert "GATE: OK" in so and rc == 0, so[-600:]
        assert "RESULTADO: 15/15 OK" in so
        assert frc == 0 and "FIOS: ok" in fo, fo


def test_gate_partida_direta_1_motor():
    # casos vem da chave "testes" da spec; o gate reprova se algum falhar
    with tempfile.TemporaryDirectory() as t:
        so, fo, rc, frc = _gate("partida_direta.layout.json", t)
        assert "GATE: OK" in so and rc == 0, so[-600:]
        assert "RESULTADO: 6/6 OK" in so
        assert frc == 0 and "FIOS: ok" in fo, fo


def test_reversao_layout_paralelo_e_inversao_de_fases():
    low = _low("reversao.layout.json")
    pos = {s["id"]: s for s in low["simbolos"]}
    assert pos["KM1p"]["y"] == pos["KM2p"]["y"] and pos["KM2p"]["x"] > pos["KM1p"]["x"]
    assert pos["M1"]["x"] == pos["KM1p"]["x"] and pos["M1"]["y"] > pos["KM1p"]["y"]
    rails = {r["nome"] for r in low["rails"]}
    assert {"m1_e1", "m1_e2", "m1_e3", "m1_s1", "m1_s2", "m1_s3"} <= rails
    cons = {(tuple(c["de"]), tuple(c["para"])) for c in low["conexoes"]}
    # KM1: 1,3,5 <- fases em ordem; KM2: inverte L1 e L3 (1<-L3, 5<-L1)
    assert (("m1_e1", "rail"), ("KM1p", "1")) in cons
    assert (("m1_e3", "rail"), ("KM1p", "5")) in cons
    assert (("m1_e3", "rail"), ("KM2p", "1")) in cons
    assert (("m1_e2", "rail"), ("KM2p", "3")) in cons
    assert (("m1_e1", "rail"), ("KM2p", "5")) in cons
    # ambos os contatores alimentam o MESMO motor (via trilhos de saida)
    assert (("KM1p", "2"), ("m1_s1", "rail")) in cons
    assert (("KM2p", "2"), ("m1_s1", "rail")) in cons
    assert (("m1_s1", "rail"), ("M1", "U1")) in cons


def test_gate_reversao():
    with tempfile.TemporaryDirectory() as t:
        so, fo, rc, frc = _gate("reversao.layout.json", t)
        assert "GATE: OK" in so and rc == 0, so[-600:]
        assert "RESULTADO: 13/13 OK" in so
        assert frc == 0 and "FIOS: ok" in fo, fo


def test_reversao_fases_na_geometria():
    """Netlist por geometria: KM1 liga L1,L2,L3 a 1,3,5; KM2 inverte L1<->L3;
    saidas 2/4/6 dos dois contatores caem nos mesmos U1/V1/W1 do motor."""
    import geo_check
    with tempfile.TemporaryDirectory() as t:
        out = Path(t) / "r.cad"
        r = subprocess.run([sys.executable, str(TOOLS / "build_spec.py"),
                            str(EX / "reversao.layout.json"), str(out)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        assert r.returncode == 0, r.stdout[-400:]
        redes = {}
        geo_check.analisar(str(out), redes)
    R = lambda rot, cid, pino: redes[(rot, cid, pino)]
    X = lambda p: R("-X", "3007", p)
    K1 = lambda p: R("-KM1", "2001", "p" + str(p))   # p1..p3 = 1,3,5 ; p4..p6 = 2,4,6
    K2 = lambda p: R("-KM2", "2001", "p" + str(p))
    M = lambda p: R("-M1", "1000", p)               # p1..p3 = U1,V1,W1
    F = lambda p: R("-RT1", "6007", p)               # p4..p6 = saidas 2,4,6 do rele termico
    Q = lambda p: R("-Q1", "6009", p)
    for i, f in enumerate(("L1", "L2", "L3"), 1):
        assert X(f) == Q(f"p{i}")                   # fonte -> disjuntor
    for i in (1, 2, 3):
        assert F(f"p{i + 3}") == K1(i)              # KM1: ordem direta
    assert F("p4") == K2(3) and F("p5") == K2(2) and F("p6") == K2(1)   # KM2: L1<->L3
    for top, bot in ((1, 4), (2, 5), (3, 6)):
        assert K1(bot) == K2(bot) == M(f"p{top}")
    assert len({M("p1"), M("p2"), M("p3")}) == 3
    assert X("PE") == M("p4")


def test_geo_check_pega_curto_de_fase():
    import geo_check
    # PE da fonte ligado ao trilho N => estampas 'N' e 'P' na mesma net = CURTO
    base = json.loads((TOOLS / "examples" / "partida_direta.layout.json").read_text(encoding="utf-8"))
    base["layout"]["fontes"][0]["pinos"]["PE"] = "N"
    with tempfile.TemporaryDirectory() as t:
        f = Path(t) / "x.layout.json"; f.write_text(json.dumps(base), encoding="utf-8")
        out = Path(t) / "o.cad"
        r = subprocess.run([sys.executable, str(TOOLS / "build_spec.py"), str(f), str(out)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        curtos, _ = geo_check.analisar(str(out))
        assert curtos and "N" in curtos[0] and "P" in curtos[0], curtos
        assert r.returncode == 1 and "REPROVADO" in r.stdout


def test_gate_reprova_sem_testes_e_com_teste_errado():
    import json
    base = json.loads((TOOLS / "examples" / "partida_direta.layout.json").read_text(encoding="utf-8"))
    for nome, mut in (("sem", lambda d: d.__setitem__("testes", [])),
                      ("errado", lambda d: d["testes"][1].__setitem__("esperado", []))):
        d = json.loads(json.dumps(base)); mut(d)
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / f"{nome}.layout.json"; f.write_text(json.dumps(d), encoding="utf-8")
            r = subprocess.run([sys.executable, str(TOOLS / "build_spec.py"), str(f), str(Path(t) / "o.cad")],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
            assert r.returncode == 1 and "REPROVADO" in r.stdout, (nome, r.stdout[-400:])


def test_sem_entidade_orfa_do_doador():
    """Regressao: a entidade 0 (colada ao 'CADe_SIMU*') era uma 3004 solta em (93,45)."""
    from dissect import parse_ent, split_all
    with tempfile.TemporaryDirectory() as t:
        out = Path(t) / "o.cad"
        r = subprocess.run([sys.executable, str(TOOLS / "build_spec.py"),
                            str(TOOLS / "examples" / "partida_direta.layout.json"), str(out)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        assert "GATE: OK" in r.stdout, r.stdout[-400:]
        d = out.read_bytes().decode("latin1")
        assert d.startswith("CADe_SIMU*0*3007#"), d[:60]       # a 1a entidade e a nossa fonte
        _, ents, _ = split_all(d)
        ps = [p for p in map(parse_ent, ents) if p]
        assert [p["seq"] for p in ps][:3] == ["0", "1", "2"]
        assert not [p for p in ps if p["id"] == "3004"], "fonte 3004 solta de doador"
        assert not [p for p in ps if p["nums"][8:10] == ["93", "45"]]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
