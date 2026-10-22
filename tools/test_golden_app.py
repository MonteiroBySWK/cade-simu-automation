#!/usr/bin/env python3
"""Testes do gravador de goldens do app (tools/golden_app.py). Sem Wine: observador falso."""
import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import golden_app as G  # noqa: E402


class ObsFalso:
    """Observador de mentira: registra as chamadas e devolve estados em fila."""

    def __init__(self, estados=None):
        self.chamadas = []
        self.aberto = False
        self.estados = list(estados or [])

    def abrir(self):
        self.aberto = True
        return self

    def fechar(self):
        self.aberto = False

    def reiniciar(self):
        self.chamadas.append(("reiniciar",))

    def esperar(self, ms):
        self.chamadas.append(("esperar", ms))

    def pressionar(self, alvo):
        self.chamadas.append(("pressionar", alvo))

    def soltar(self):
        self.chamadas.append(("soltar",))

    def alternar(self, alvo):
        self.chamadas.append(("alternar", alvo))

    def observar(self):
        self.chamadas.append(("observar",))
        return self.estados.pop(0) if self.estados else {}


CENARIO = {"versao": 1, "descricao": "teste", "acoes": [
    {"acao": "reiniciar"},
    {"acao": "esperar", "ms": 300},
    {"acao": "pressionar", "alvo": "-s1"},
    {"acao": "soltar", "alvo": "S1"},
    {"acao": "esperar", "ms": 200},
    {"acao": "alternar", "alvo": "rt1"},
]}


def test_um_passo_por_acao_com_tempo_acumulado():
    obs = ObsFalso([
        {"bobinas": {}, "lampadas": {}, "motores": {}, "saidas_clp": {}},
        {"bobinas": {"KM1": True, "KM2": False}, "lampadas": {"H1": True}},
        {"bobinas": {"KM1": True}, "motores": {"M1": True}, "saidas_clp": {"Q0.1": True}},
        {"bobinas": {}},
        {"bobinas": {"KM1": True}},
        {"bobinas": {}, "curto": True},
    ])
    passos = G.executar_cenario(CENARIO, obs)
    assert [p["i"] for p in passos] == [0, 1, 2, 3, 4, 5]
    assert [p["t_ms"] for p in passos] == [0, 300, 300, 300, 500, 500]


def test_observa_depois_de_cada_acao_na_ordem_do_cenario():
    obs = ObsFalso()
    G.executar_cenario(CENARIO, obs)
    assert obs.chamadas == [
        ("reiniciar",), ("observar",),
        ("esperar", 300), ("observar",),
        ("pressionar", "S1"), ("observar",),
        ("soltar",), ("observar",),
        ("esperar", 200), ("observar",),
        ("alternar", "RT1"), ("observar",),
    ]


def test_ativos_ordenados_e_curto_so_quando_verdadeiro():
    obs = ObsFalso([
        {"bobinas": {"KM2": True, "KM1": True}, "lampadas": {"H2": False, "H1": True},
         "motores": {}, "saidas_clp": {"Q0.2": True, "Q0.1": False}},
        {"bobinas": {}, "curto": False},
    ])
    passos = G.executar_cenario({"acoes": [{"acao": "reiniciar"}, {"acao": "reiniciar"}]}, obs)
    assert passos[0]["bobinas"] == ["KM1", "KM2"]
    assert passos[0]["lampadas"] == ["H1"]
    assert passos[0]["motores"] == []
    assert passos[0]["saidas_clp"] == ["Q0.2"]
    assert "curto" not in passos[1]


def test_campos_ausentes_no_observador_ficam_de_fora():
    obs = ObsFalso([{"bobinas": {"KM1": True}}])
    passos = G.executar_cenario({"acoes": [{"acao": "alternar", "alvo": "Q1"}]}, obs)
    assert {k: v for k, v in passos[0].items() if k != "t_parede_ms"} == {"i": 0, "t_ms": 0, "bobinas": ["KM1"]}


def test_acao_desconhecida_da_erro_explicito():
    with pytest.raises(G.GoldenErro, match="desconhecida"):
        G.executar_cenario({"acoes": [{"acao": "apertar", "alvo": "S1"}]}, ObsFalso())


def test_acao_sem_alvo_da_erro():
    with pytest.raises(G.GoldenErro, match="alvo"):
        G.executar_cenario({"acoes": [{"acao": "pressionar"}]}, ObsFalso())


def _caso(tmp_path, cenario=CENARIO, nome="partida_direta"):
    d = tmp_path / nome
    d.mkdir()
    (d / "circuito.cad").write_text("", encoding="utf-8")
    (d / "cenario.json").write_text(json.dumps(cenario), encoding="utf-8")
    return d


def test_gravar_escreve_golden_fonte_app(tmp_path):
    d = _caso(tmp_path, {"descricao": "d", "acoes": [{"acao": "reiniciar"}]})
    obs = ObsFalso([{"bobinas": {"KM1": True}, "lampadas": {"H1": True}, "motores": {}, "saidas_clp": {}}])
    r = G.gravar_caso(d, fabrica=lambda cad: obs)
    assert r["ok"] and not r["pulado"]
    g = json.loads((d / "golden_app.json").read_text(encoding="utf-8"))
    assert g["versao"] == 1 and g["fonte"] == "app"
    assert [{k: v for k, v in p.items() if k != "t_parede_ms"} for p in g["passos"]] == [
        {"i": 0, "t_ms": 0, "bobinas": ["KM1"], "lampadas": ["H1"], "motores": [], "saidas_clp": []}]
    assert g["gravado_em"] and g["caso"] == "partida_direta"
    assert not obs.aberto                      # fecha o app sempre


def test_nao_sobrescreve_golden_do_app_sem_forcar(tmp_path):
    d = _caso(tmp_path, {"acoes": [{"acao": "reiniciar"}]})
    (d / "golden_app.json").write_text(json.dumps({"versao": 1, "fonte": "app", "passos": []}), encoding="utf-8")
    r = G.gravar_caso(d, fabrica=lambda cad: ObsFalso())
    assert r["pulado"]
    assert json.loads((d / "golden_app.json").read_text(encoding="utf-8"))["passos"] == []


def test_forcar_sobrescreve(tmp_path):
    d = _caso(tmp_path, {"acoes": [{"acao": "reiniciar"}]})
    (d / "golden_app.json").write_text(json.dumps({"versao": 1, "fonte": "app", "passos": []}), encoding="utf-8")
    r = G.gravar_caso(d, fabrica=lambda cad: ObsFalso([{"bobinas": {"KM1": True}}]), forcar=True)
    assert r["ok"]
    assert json.loads((d / "golden_app.json").read_text(encoding="utf-8"))["passos"][0]["bobinas"] == ["KM1"]


def test_golden_provisorio_e_sobrescrito_sem_forcar(tmp_path):
    d = _caso(tmp_path, {"acoes": [{"acao": "reiniciar"}]})
    (d / "golden_app.json").write_text(json.dumps({"versao": 1, "fonte": "oraculo_python", "passos": []}),
                                      encoding="utf-8")
    r = G.gravar_caso(d, fabrica=lambda cad: ObsFalso([{"bobinas": {}}]))
    assert r["ok"] and not r["pulado"]
    assert json.loads((d / "golden_app.json").read_text(encoding="utf-8"))["fonte"] == "app"


def test_caso_sem_cenario_da_erro(tmp_path):
    d = tmp_path / "x"
    d.mkdir()
    with pytest.raises(G.GoldenErro, match="cenario.json"):
        G.gravar_caso(d, fabrica=lambda cad: ObsFalso())


def test_lista_casos_so_com_cenario(tmp_path):
    for nome in ("a", "b"):
        _caso(tmp_path, nome=nome)
    assert [p.name for p in G.casos_com_cenario(tmp_path)] == ["a", "b"]


class _AppFalso:
    def __init__(self):
        self.cliques = []

    class _Cad:
        simbolos = []

    cad = _Cad()

    def reiniciar(self):
        self.cliques.append(("reiniciar",))

    def pressionar(self, alvo, segurar_s=None):
        self.cliques.append(("down", alvo))

    def soltar(self):
        self.cliques.append(("up",))

    def alternar(self, alvo, espera=0.0):
        self.cliques.append(("click", alvo))


def test_observador_recusa_segurar_dois_atuadores(tmp_path):
    obs = G.ObservadorApp(tmp_path / "x.cad", espera_acao=0)
    obs.app = _AppFalso()
    obs.pressionar("S1")
    with pytest.raises(G.GoldenErro, match="um atuador"):
        obs.pressionar("S0")
    with pytest.raises(G.GoldenErro, match="um atuador"):
        obs.alternar("RT1")
    obs.soltar()
    obs.pressionar("S0")                       # depois de soltar, pode
    assert obs.app.cliques == [("down", "S1"), ("up",), ("down", "S0")]


def test_reiniciar_solta_o_atuador(tmp_path):
    obs = G.ObservadorApp(tmp_path / "x.cad", espera_acao=0)
    obs.app = _AppFalso()
    obs.pressionar("S1")
    obs.reiniciar()
    obs.pressionar("S0")                       # reiniciar zera o ponteiro


def test_montar_golden_registra_disjuntores(tmp_path):
    g = G.montar_golden(tmp_path / "c", {"descricao": "d"}, [{"i": 0}], ["Q1"])
    assert g["disjuntores_fechados"] == ["Q1"]
    assert "disjuntores_fechados" not in G.montar_golden(tmp_path / "c", {}, [])


def test_cenarios_de_conformidade_respeitam_o_ponteiro():
    """Invariante do app: no maximo um atuador segurado por vez (senao o clique seguinte se perde)."""
    base = Path(__file__).resolve().parent.parent / "tests" / "conformidade"
    casos = sorted(base.glob("*/cenario.json"))
    assert casos, "nenhum cenario de conformidade encontrado"
    for p in casos:
        segurando = None
        for i, a in enumerate(json.loads(p.read_text(encoding="utf-8"))["acoes"]):
            acao = a["acao"]
            if acao in ("reiniciar", "soltar"):
                segurando = None
            elif acao in ("pressionar", "alternar"):
                assert segurando is None, f"{p.parent.name} acao {i}: {acao} {a.get('alvo')} com {segurando} segurado"
                segurando = a.get("alvo") if acao == "pressionar" else None
