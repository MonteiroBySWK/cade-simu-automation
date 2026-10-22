"""Testes da DSL ladder/1 (tools/ladder_dsl.py): validacao, modelo logico, geracao do .cad, gate e dados de pinos."""
import copy
import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import cade_mcp as C  # noqa: E402
import clp_sim  # noqa: E402
import ladder_dsl as L  # noqa: E402

EX = TOOLS / "examples"
LADDERS = sorted(EX.glob("*.ladder.json"))


def _spec(nome):
    return json.loads((EX / f"{nome}.ladder.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("arq", LADDERS, ids=lambda p: p.name)
def test_exemplos_passam_o_gate_completo(arq, tmp_path):
    spec = json.loads(arq.read_text(encoding="utf-8"))
    r = L.construir(spec, str(tmp_path / "x.cad"))
    assert r["ok"], (r["erros"], r["testes"]["falhas"])
    assert r["testes"]["total"] == len(spec["testes"])
    assert not r["geo"]["curtos"] and not r["geo"]["soltos"]


@pytest.mark.parametrize("arq", LADDERS, ids=lambda p: p.name)
def test_cabe_na_folha(arq):
    d, _ = L.compilar(json.loads(arq.read_text(encoding="utf-8")), "x.cad")
    assert d.xmax <= L.FOLHA_X and d.ymax <= L.FOLHA_Y


def test_dados_de_pinos_corrigidos():
    pins = lambda c: json.loads(C.cad_pins(c))   # noqa: E731
    assert pins("10205")["pinos_binario"]["p1"] == [0, 24]
    assert pins("10206")["pinos"] == {"+24V": [18, 0], "0V": [24, 0], "L": [0, 0], "N": [6, 0], "PE": [12, 0]}
    assert pins("10060")["pinos_ab"]["B"] == [12, 0]
    assert pins("10204")["pinos_binario"] == {"p1": [0, 0]}
    for c in ("10050", "10051"):
        assert pins(c)["pinos_ab"] == {"A": [0, 0], "B": [12, 0]}
    assert pins("10066")["pinos"] == {"IN": [0, 0], "Q": [15, 6]}


def test_cad_design_e_cad_test_com_ladder(tmp_path):
    spec = _spec("partida_sequencial_3")
    r = json.loads(C.cad_design(json.dumps(spec), str(tmp_path / "b.cad")))
    assert r["ok"], r["erros"]
    t = C.cad_test(str(tmp_path / "b.cad"), json.dumps(spec["testes"]))
    assert t.startswith("PASSOU")
    s = json.loads(C.cad_simulate(str(tmp_path / "b.cad"), '{"DJ1":true,"B1":true}'))
    assert s["bobinas_energizadas"] == ["C1", "C2", "C3"]
    g = json.loads(C.cad_gate(str(tmp_path / "b.cad"), json.dumps(spec["testes"])))
    assert g["ok"], g["erros"]


def test_sequencial_ton_2s_em_ticks():
    spec = _spec("partida_sequencial_3")
    m = L.ModeloLogico(spec)
    est = m.estado_zero()
    est, _ = m.rodar({"DJ1": True, "B1": True}, 3, est)
    est, r = m.rodar({"DJ1": True}, 10, est)
    assert r["bobinas"] == ["C3"]                       # 1 s depois: so M3
    est, r = m.rodar({"DJ1": True}, 20, est)
    assert "C2" in r["bobinas"]                         # ~2 s: M2
    est, r = m.regime({"DJ1": True}, est)
    assert r["bobinas"] == ["C1", "C2", "C3"]


def test_pratica5_base_corrigida_alterna_e_original_trava():
    spec = _spec("pratica5_complementar")
    m = L.ModeloLogico(spec)
    est = m.estado_zero()
    est, _ = m.rodar({"DJ1": True, "B1": True}, 3, est)
    vistos = set()
    for _ in range(80):
        est, r = m.rodar({"DJ1": True}, 1, est)
        vistos.add(tuple(r["bobinas"]))
    assert ("C1",) in vistos and ("C2",) in vistos      # M1 -> M2 -> M1 ...


def test_validacoes():
    base = _spec("partida_sequencial_3")
    s = copy.deepcopy(base)
    s["layout"]["ladder"]["rungs"][1]["logica"] = ["NA", "X9.9"]          # V1
    assert any("V1" in e for e in L.validar(s)[0])
    s = copy.deepcopy(base)
    s["layout"]["ladder"]["rungs"].append({"id": "r9", "logica": ["NA", "M0.1"], "saida": ["OUT", "Q0.3"]})
    assert any("V2" in e for e in L.validar(s)[0])                        # dois OUT
    s = copy.deepcopy(base)
    s["layout"]["clp"]["saidas"].append({"operando": "Q0.7", "carga": ["C9", "9000", "C9"]})
    assert any("V3" in e for e in L.validar(s)[0])
    s = copy.deepcopy(base)
    s["layout"]["ladder"]["rungs"][0]["saida"] = ["OUT", "C1"]            # V4: igual a rotulo fisico
    assert any("V4" in e for e in L.validar(s)[0])
    s = copy.deepcopy(base)
    s["layout"]["ladder"]["rungs"][2]["logica"] = {"serie": [["NA", "M0.1"], {"paralelo": [["TON", "T1", {"tempo": 1}], ["NA", "I0.1"]]}]}
    assert any("TON so pode" in e for e in L.validar(s)[0])
    assert L.validar(base) == ([], [])


def test_gate_pega_circuito_errado(tmp_path):
    spec = _spec("partida_sequencial_3")
    spec["testes"][0]["esperado"] = ["C1"]                                 # repouso nao liga C1
    r = L.construir(spec, str(tmp_path / "x.cad"))
    assert not r["ok"] and r["testes"]["falhas"]


def test_geometria_ton_inline_e_paralelo(tmp_path):
    spec = _spec("pratica5_complementar")
    d, _ = L.compilar(spec, "x.cad")
    p = tmp_path / "x.cad"
    d.cad.salvar(p)
    sim = clp_sim.CircuitoCLP(str(p))
    assert len(sim.tons) == 2 and {t["T"] for t in sim.tons} == {10}
    assert len(sim.ladder) >= 17 and len(sim.ent_clp) == 7 and len(sim.sai_clp) == 4
