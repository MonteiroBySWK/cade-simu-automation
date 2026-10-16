#!/usr/bin/env python3
"""Testes do comando v2 do motor de layout: rede serie-paralelo recursiva, varios degraus,
trilhos de comando (transformador/fonte) e quebra automatica (colunas/faixas).
pytest tools/test_layout_v2.py   (ou python3 tools/test_layout_v2.py)"""
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import layout  # noqa: E402

EX = TOOLS / "examples"
NOVOS = ["liga_desliga_2pontos", "partida_sequencial", "tres_degraus_lampadas",
         "intertravamento_sinalizacao", "partida_trafo_comando"]
LEGADOS = ["intercalada", "partida_direta", "reversao", "dois_motores_independentes",
           "partida_emergencia", "partida_sinalizacao"]

TRILHOS = {"L1": 14, "L2": 20, "L3": 26, "N": 282, "x0": 25, "x1": 395, "PE": 291}
FONTE = {"id": "X1", "classe": "3007", "rotulo": "-X",
         "pinos": {"L1": "L1", "L2": "L2", "L3": "L3", "N": "N", "PE": "PE"}}


def mono(rungs, trilhos=None):
    """spec minima monofasica (fonte 3003 entre L1 e N) so com comando."""
    return {"titulo": "T", "trilhos": trilhos or {"L1": 14, "N": 100, "x0": 25, "x1": 395},
            "fontes": [{"id": "X1", "classe": "3003", "pinos": {"L": "L1", "N": "N"}}],
            "comando": [{"id": "c1", "de": "L1", "para": "N", "rungs": rungs}]}


def rung(i):
    return {"serie": [[f"S{i}", "8001", f"-S{i}"],
                      {"paralelo": [[f"B{i}", "8000", f"-B{i}"], [f"s{i}", "7000", f"-K{i}"]]},
                      {"paralelo": [[f"K{i}", "9000", f"-K{i}"], [f"H{i}", "9008", f"-H{i}"]]}]}


def _low(nome):
    return layout.compilar(json.loads((EX / f"{nome}.layout.json").read_text())["layout"])


def _pos(low):
    return {s["id"]: s for s in low["simbolos"]}


def _build(spec, tmp, nome="x"):
    import build_spec
    out = str(Path(tmp) / f"{nome}.cad")
    r = build_spec.construir({"layout": spec, "testes": []}, out)
    assert r["build"]["ok"], r["build"]
    return out, r


def _redes(path):
    import geo_check
    redes = {}
    curtos, soltos = geo_check.analisar(path, redes)
    return redes, curtos, soltos


def _pino(redes, rot, cid, pino):
    return redes[(rot, cid, pino)]


# ---------------------------------------------------------------- exemplos novos (gate completo)
@pytest.mark.parametrize("nome", NOVOS)
def test_exemplo_novo_sem_coordenadas(nome):
    d = json.loads((EX / f"{nome}.layout.json").read_text())["layout"]

    def varre(o):
        if isinstance(o, dict):
            assert not ({"x", "y"} & set(o)), o
            for v in o.values():
                varre(v)
        elif isinstance(o, list):
            for v in o:
                varre(v)
    varre(d)


@pytest.mark.parametrize("nome", NOVOS)
def test_exemplo_novo_gate_ok(nome):
    with tempfile.TemporaryDirectory() as t:
        out = str(Path(t) / f"{nome}.cad")
        r = subprocess.run([sys.executable, str(TOOLS / "build_spec.py"), str(EX / f"{nome}.layout.json"), out],
                           capture_output=True, text=True, timeout=600)
        assert "GATE: OK" in r.stdout and r.returncode == 0, r.stdout[-900:]
        f = subprocess.run([sys.executable, str(TOOLS / "wires_check.py"), out], capture_output=True, text=True)
        assert f.returncode == 0 and "FIOS: ok" in f.stdout, f.stdout
        g = subprocess.run([sys.executable, str(TOOLS / "geo_check.py"), out], capture_output=True, text=True)
        assert g.returncode == 0 and "GEO: ok" in g.stdout, g.stdout


@pytest.mark.parametrize("nome", NOVOS)
def test_exemplo_novo_caixa_e_sobreposicao(nome):
    low = _low(nome)
    boxes = []
    for s in low["simbolos"]:
        w, h = layout._width(s["classe"]), layout.dim(s["classe"])[1]
        b = (s["x"], s["y"], s["x"] + w, s["y"] + h)
        assert b[2] <= layout.SHEET_X and b[3] <= layout.SHEET_Y, (nome, s["id"], b)
        for o in boxes:
            assert not (b[0] < o[2] and o[0] < b[2] and b[1] < o[3] and o[1] < b[3]), (nome, s["id"])
        boxes.append(b)
    # fios do motor: so segmentos retos (horizontais ou verticais)
    for f in low.get("fios", []):
        assert f["x1"] == f["x2"] or f["y1"] == f["y2"], f


@pytest.mark.parametrize("nome", NOVOS)
def test_determinismo(nome):
    d = json.loads((EX / f"{nome}.layout.json").read_text())["layout"]
    assert layout.compilar(copy.deepcopy(d)) == layout.compilar(copy.deepcopy(d))


@pytest.mark.parametrize("nome", LEGADOS)
def test_exemplos_antigos_continuam_na_forma_legada(nome):
    # nenhum dos exemplos antigos usa fios manuais (caminho legado intacto)
    low = _low(nome)
    assert "fios" not in low


# ---------------------------------------------------------------- geometria da rede
def test_serie_alinhada_em_coluna_e_paralelo_lado_a_lado():
    low = _low("liga_desliga_2pontos")
    p = _pos(low)
    # serie: RT1, S0, S3 no mesmo x (mesma coluna), descendo
    assert p["RT1"]["x"] == p["S0"]["x"] == p["S3"]["x"]
    assert p["RT1"]["y"] < p["S0"]["y"] < p["S3"]["y"]
    # paralelo S1 | S2 | selo1: mesmo y, x crescente, depois das series
    assert p["S1"]["y"] == p["S2"]["y"] == p["selo1"]["y"] > p["S3"]["y"]
    assert p["S1"]["x"] < p["S2"]["x"] < p["selo1"]["x"]
    # S0/S3 alinham ao ramo central (3 ramos, eixo no meio)
    assert p["S2"]["x"] == p["S3"]["x"]
    # cargas em paralelo logo abaixo, mesmo y
    assert p["KM1"]["y"] == p["H1"]["y"] > p["S1"]["y"]


def test_aninhado_paralelo_de_series_com_paralelos():
    low = _low("intertravamento_sinalizacao")
    p = _pos(low)
    # os dois ramos externos ficam lado a lado; cada um desce em serie
    assert p["S1"]["y"] == p["S2"]["y"]
    assert p["S1"]["x"] < p["S2"]["x"]
    assert p["nkm2"]["y"] > p["S1"]["y"] and p["nkm1"]["y"] == p["nkm2"]["y"]
    assert p["KM1"]["y"] > p["nkm2"]["y"] and p["KM2"]["y"] == p["KM1"]["y"]
    # degraus de sinalizacao: colunas independentes a direita, mesmo y de partida
    assert p["k1on"]["x"] > p["KM2"]["x"] and p["nk1"]["x"] > p["k1on"]["x"]
    assert p["k1on"]["y"] == p["nk1"]["y"] == p["RT1"]["y"]


def test_trilho_de_baixo_desce_para_caber_a_rede():
    low = layout.compilar(mono([rung(0), rung(1)]))
    rails = {r["nome"]: r for r in low["rails"]}
    assert rails["N"]["y"] > 100          # foi deslocado (rede de 3 niveis precisa de mais que 100)
    ymax = max(s["y"] + layout.dim(s["classe"])[1] for s in low["simbolos"])
    assert rails["N"]["y"] >= ymax


def test_primeiro_contato_ligado_ao_trilho_de():
    # regra de leitura do simulador legado: o 1o contato tem A no trilho de cima
    low = _low("partida_sequencial")
    pri = [s for s in low["simbolos"] if s["classe"] in ("8017", "8001", "8000", "7000", "7001")][0]
    assert {"de": [pri["id"], "A"], "para": ["L1", "rail"]} in low["conexoes"] or \
           {"de": ["L1", "rail"], "para": [pri["id"], "A"]} in low["conexoes"]


# ---------------------------------------------------------------- conectividade por geometria
def _rotulos_unicos(o):
    """rotulo = '-'+id em toda folha (o geo_check indexa pinos por rotulo)."""
    if isinstance(o, dict):
        for v in o.values():
            _rotulos_unicos(v)
    elif isinstance(o, list):
        if 2 <= len(o) <= 3 and all(isinstance(v, str) for v in o):
            o[:] = [o[0], o[1], "-" + o[0]]
        else:
            for v in o:
                _rotulos_unicos(v)


def test_rede_conecta_como_a_expressao():
    with tempfile.TemporaryDirectory() as t:
        d = json.loads((EX / "partida_sequencial.layout.json").read_text())["layout"]
        _rotulos_unicos(d["comando"])
        out, r = _build(d, t, "ps")
        redes, curtos, soltos = _redes(out)
        assert not curtos and not soltos
        R = lambda i, cid, pino: redes[("-" + i, cid, pino)]          # noqa: E731
        # serie: B(RT1) = ramo paralelo S0 || k2by (A de ambos)
        n = R("RT1", "8017", "p2")
        assert R("S0", "8001", "p1") == n and R("k2by", "7000", "p1") == n
        # saida do 1o paralelo = entrada do 2o (S1 || selo1)
        n2 = R("S0", "8001", "p2")
        assert R("k2by", "7000", "p2") == n2 and R("S1", "8000", "p1") == n2 and R("selo1", "7000", "p1") == n2
        # carga: bobina e lampada nos mesmos dois nos
        n3 = R("S1", "8000", "p2")
        assert R("selo1", "7000", "p2") == n3 and R("KM1", "9000", "p1") == n3 and R("H1", "9008", "p1") == n3
        # B da bobina e da lampada = neutro (mesmo no nos dois degraus)
        assert R("KM1", "9000", "p2") == R("H1", "9008", "p2") == R("KM2", "9000", "p2") == R("H2", "9008", "p2")
        # topo dos dois degraus = L1; e L1 != neutro
        assert R("RT1", "8017", "p1") == R("RT2", "8017", "p1")
        assert R("RT1", "8017", "p1") != R("KM1", "9000", "p2")
        # degrau 2: S3 -> k1ok -> (S2 || selo2) -> (KM2 || H2)
        assert R("S3", "8001", "p2") == R("k1ok", "7000", "p1")
        assert R("k1ok", "7000", "p2") == R("S2", "8000", "p1") == R("selo2", "7000", "p1")


def test_trilhos_de_comando_transformador_e_fonte():
    with tempfile.TemporaryDirectory() as t:
        d = json.loads((EX / "partida_trafo_comando.layout.json").read_text())["layout"]
        out, r = _build(d, t, "tc")
        redes, curtos, soltos = _redes(out)
        assert not curtos and not soltos           # p1..p4 do 3012 todos ligados
        R = lambda rot, cid, pino: redes[(rot, cid, pino)]            # noqa: E731
        c1 = R("-RT1", "8017", "p1")                # topo da rede = trilho C1
        c2 = R("-KM1", "9000", "p2")                # base da rede = trilho C2
        assert c1 != c2
        assert R("-T1", "3012", "p4") == c1 and R("-T1", "3012", "p3") == c2     # secundario
        assert R("-X2", "3003", "N") == c1 and R("-X2", "3003", "L") == c2       # fonte de comando
        assert R("-T1", "3012", "p1") != c1 and R("-T1", "3012", "p1") != c2     # primario separado
        # o comando NAO esta no L1/N principais
        assert R("-Q1", "6009", "p1") != c1 and R("-X", "3007", "N") != c2


def test_trilhos_comando_exige_alimentacao():
    s = mono([rung(0)])
    s["trilhos_comando"] = {"nomes": ["C1", "C2"]}
    with pytest.raises(ValueError, match="alimentacao"):
        layout.compilar(s)


# ---------------------------------------------------------------- quebra automatica
def test_quebra_em_faixas_quando_larga_demais():
    spec = mono([rung(i) for i in range(9)])
    low = layout.compilar(spec)                    # nao cabe em 1 linha: 2 faixas amarradas
    nomes = [r["nome"] for r in low["rails"]]
    assert any("~" in n for n in nomes) and sum(1 for n in nomes if n.startswith("N~")) == 1
    for s in low["simbolos"]:
        assert s["x"] + layout._width(s["classe"]) <= layout.SHEET_X and s["y"] + 15 <= layout.SHEET_Y
    assert len(low["simbolos"]) == 1 + 9 * 5
    with tempfile.TemporaryDirectory() as t:
        out, r = _build(spec, t, "faixas")
        redes, curtos, soltos = _redes(out)
        assert not curtos and not soltos
        # todos os degraus compartilham os mesmos dois nos (faixas amarradas)
        topo = {redes[(f"-S{i}", "8001", "p1")] for i in range(9)}
        base = {redes[(f"-K{i}", "9000", "p2")] for i in range(9)}
        assert len(topo) == 1 and len(base) == 1 and topo != base
        import wires_check
        assert wires_check.analisar(out)[1] == []


def test_nao_cabe_nem_em_faixas_da_erro_explicito():
    with pytest.raises(ValueError, match="nao cabe"):
        layout.compilar(mono([rung(i) for i in range(40)]))


def test_paralelo_largo_quebra_em_linhas_com_espinhas():
    ramos = [{"via": [f"B{i}", "8000", f"-S{i}"], "selo": [f"s{i}", "7000", f"-K{i}"],
              "carga": [f"K{i}", "9000", f"-K{i}"], "indica": [f"H{i}", "9008", f"-H{i}"]} for i in range(8)]
    spec = {"titulo": "x", "trilhos": TRILHOS, "fontes": [FONTE],
            "comando": [{"id": "m1", "de": "L1", "para": "N",
                         "serie": [["RT1", "8017", "-RT1"], ["S0", "8001", "-S0"]], "ramos": ramos}]}
    low = layout.compilar(spec)
    p = _pos(low)
    assert p["B0"]["y"] == p["B4"]["y"] < p["B5"]["y"]            # 2 linhas de ramos
    with tempfile.TemporaryDirectory() as t:
        out, r = _build(spec, t, "linhas")
        redes, curtos, soltos = _redes(out)
        assert not curtos and not soltos
        import wires_check
        assert wires_check.analisar(out)[1] == []
        entrada = redes[("-S0", "8001", "p2")]
        for i in range(8):                       # todo ramo: via/selo no no de entrada...
            assert redes[(f"-S{i}", "8000", "p1")] == entrada
            assert redes[(f"-K{i}", "7000", "p1")] == entrada
        neutro = redes[("-K0", "9000", "p2")]    # ...e toda carga no mesmo no de saida
        for i in range(8):
            assert redes[(f"-K{i}", "9000", "p2")] == neutro == redes[(f"-H{i}", "9008", "p2")]
        assert neutro != entrada


def test_quebra_em_colunas_quando_serie_alta_demais():
    ser = [[f"E{i}", "7000", f"-K{i}"] for i in range(30)]
    spec = mono([{"serie": ser + [{"paralelo": [["K", "9000", "-K"], ["H", "9008", "-H"]]}]}])
    low = layout.compilar(spec)
    xs = sorted({s["x"] for s in low["simbolos"] if s["id"].startswith("E")})
    assert len(xs) >= 2                                    # varias colunas (serpentina)
    assert max(r["y"] for r in low["rails"]) <= layout.SHEET_Y
    with tempfile.TemporaryDirectory() as t:
        out, r = _build(spec, t, "serp")
        redes, curtos, soltos = _redes(out)
        assert not curtos and not soltos
        # continuidade: topo da 1a coluna -> ... -> bobina, e a emenda entre colunas e 1 no
        ult1 = max((i for i in range(30) if low and _pos(low)[f"E{i}"]["x"] == xs[0]))
        assert redes[(f"-K{ult1}", "7000", "p2")] == redes[(f"-K{ult1 + 1}", "7000", "p1")]
        assert redes[("-K", "9000", "p1")] == redes[("-K29", "7000", "p2")]


def test_forma_antiga_que_nao_cabe_vira_rede_em_vez_de_erro():
    ramos = [{"via": [f"B{i}", "8000", f"-S{i}"], "selo": [f"s{i}", "7000", f"-K{i}"],
              "carga": [f"K{i}", "9000", f"-K{i}"], "indica": [f"H{i}", "9008", f"-H{i}"]} for i in range(8)]
    spec = {"titulo": "x", "trilhos": TRILHOS, "fontes": [FONTE],
            "comando": [{"id": "m1", "de": "L1", "para": "N",
                         "serie": [["RT1", "8017", "-RT1"], ["S0", "8001", "-S0"]], "ramos": ramos}]}
    with pytest.raises(ValueError):
        layout._compilar(copy.deepcopy(spec))              # forma legada pura: erro explicito
    low = layout.compilar(spec)                            # compilar(): traduz e quebra
    assert len(low["simbolos"]) == 1 + 2 + 8 * 4
    assert low.get("fios")
    assert all(r["y"] <= layout.SHEET_Y for r in low["rails"])


def test_paralelo_largo_demais_da_erro_claro():
    par = {"paralelo": [[f"B{i}", "8000", f"-B{i}"] for i in range(60)]}
    with pytest.raises(ValueError, match="nao cabe"):
        layout.compilar(mono([{"serie": [par, ["K", "9000", "-K"]]}]))


# ---------------------------------------------------------------- validacao de entrada
def test_erros_de_expressao():
    with pytest.raises(ValueError, match="2 terminais"):
        layout.compilar(mono([{"serie": [["Q", "2001", "-KM"], ["K", "9000", "-K"]]}]))
    with pytest.raises(ValueError, match="vertical|terminais"):
        layout.compilar(mono([{"serie": [["Z", "9041", "-Z"], ["K", "9000", "-K"]]}]))
    with pytest.raises(ValueError, match="uma chave"):
        layout.compilar(mono([{"serie": [["K", "9000", "-K"]], "paralelo": []}]))
    with pytest.raises(ValueError, match="nao vazia"):
        layout.compilar(mono([{"paralelo": []}]))
    with pytest.raises(ValueError, match="duplicado"):
        layout.compilar(mono([{"serie": [["K", "9000", "-K"], ["K", "9000", "-K"]]}]))
    with pytest.raises(ValueError, match="nao e um trilho"):
        s = mono([rung(0)])
        s["comando"][0]["para"] = "X"
        layout.compilar(s)


def test_expressao_achata_e_aceita_lista_solta():
    t = layout._expr({"serie": [["A", "8000", "-A"], {"serie": [["B", "8000", "-B"], ["C", "8000", "-C"]]}]})
    assert t.kind == "serie" and len(t.kids) == 3
    t2 = layout._expr([["A", "8000", "-A"], {"paralelo": [["B", "8000", "-B"]]}])    # lista = serie; ramo unico some
    assert t2.kind == "serie" and all(k.kind == "leaf" for k in t2.kids)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
