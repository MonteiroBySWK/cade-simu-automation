"""Regressoes da revisao de bugs/gaps (2026-10-21)."""
import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import build_spec  # noqa: E402
import cade_mcp as M  # noqa: E402
import dissect  # noqa: E402


@pytest.fixture(scope="module")
def reversao(tmp_path_factory):
    out = tmp_path_factory.mktemp("r") / "r.cad"
    spec = json.loads((TOOLS / "examples" / "reversao.layout.json").read_text(encoding="utf-8"))
    r = build_spec.construir(spec, str(out))
    assert r["ok"], r.get("erros")
    return str(out)


def test_cad_test_sem_casos_nao_aplica_suite_de_outro_circuito(reversao):
    # antes: a suite fixa da intercalada era aplicada a qualquer circuito com KM1+KM2 (13/15)
    assert M.cad_test(reversao).startswith("SEM_TESTES")


def test_cad_simulate_expoe_lampadas_e_curtos(reversao):
    d = json.loads(M.cad_simulate(reversao, '{"S1": true}'))
    assert d["bobinas_energizadas"] == ["KM1"] and d["lampadas_acesas"] == ["H1"] and d["curtos"] == []


def test_cad_build_vazio_e_erro(tmp_path):
    assert M.cad_build("x", "[]", out_path=str(tmp_path / "v.cad")).startswith("ERRO")


def test_cad_pins_nome_do_binario():
    assert json.loads(M.cad_pins("9004"))["nome"]          # vem de docs/classes-papeis.json


def test_dissect_id_negativo_e_curto():
    d = "CADe_SIMU*0*-1###R+#*1*1*0*0#*1*3###*0*0*54*66#*2*4000###*0*0*1*2#$$$fim"
    h, ents, _ = dissect.split_all(d)
    assert h == "CADe_SIMU*" and [dissect.parse_ent(e)["id"] for e in ents] == ["-1", "3", "4000"]


def test_lint_aceita_trilhos_de_comando():
    spec = json.loads((TOOLS / "examples" / "partida_trafo_comando.layout.json").read_text(encoding="utf-8"))
    assert not [a for a in build_spec.lint_layout(spec.get("layout", spec)) if "nao e um trilho" in a]
