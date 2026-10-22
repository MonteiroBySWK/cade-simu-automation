#!/usr/bin/env python3
"""Testes do simulador offline fiel ao app (tools/netlist_sim.py): geometria, papeis, lampadas,
curto de fase e temporizadores. Roda com `python3 -m pytest tools/test_netlist_sim.py -q`."""
import copy
import itertools
import json
import re
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import build_spec  # noqa: E402
import geo_check  # noqa: E402
import netlist_sim as ns  # noqa: E402

EX = TOOLS / "examples"
NOMES = sorted(f.name[: -len(".layout.json")] for f in EX.glob("*.layout.json"))


def _spec(nome):
    return json.loads((EX / f"{nome}.layout.json").read_text(encoding="utf-8"))


def _build(spec, out):
    r = build_spec.construir(spec, str(out))
    assert r["build"]["ok"], r["build"]
    return str(out)


@pytest.fixture(scope="module")
def cads(tmp_path_factory):
    base = tmp_path_factory.mktemp("cads")
    return {n: _build(_spec(n), base / f"{n}.cad") for n in NOMES}


def _editar(path, destino, fn):
    """Aplica fn(p_dict_parse, nums) sobre cada entidade (fn pode mudar nums in-place) e regrava."""
    sys.path.insert(0, str(TOOLS))
    from dissect import parse_ent, split_all
    txt = Path(path).read_bytes().decode("latin1")
    _, ents, _ = split_all(txt)
    for e in ents:
        p = parse_ent(e)
        if not p:
            continue
        nums = list(p["nums"])
        antes = list(nums)
        fn(p, nums)
        if nums != antes:
            bloco = "*" + "*".join(antes)
            novo = "*" + "*".join(nums)
            assert bloco in e
            txt = txt.replace(e, e.replace(bloco, novo, 1), 1)
    Path(destino).write_bytes(txt.encode("latin1"))
    return str(destino)


# --- fidelidade: geometria, nao nets gravados ---------------------------------------------------

@pytest.mark.parametrize("nome", NOMES)
def test_exemplos_passam_em_todos_os_casos(nome, cads):
    assert ns.teste_casos(cads[nome], _spec(nome)["testes"])


@pytest.mark.parametrize("nome", NOMES)
def test_ignora_nets_gravados_no_arquivo(nome, cads, tmp_path):
    """Zera nums[21]/[22] de todas as entidades: o resultado nao pode mudar (conectividade = geometria)."""
    zerado = _editar(cads[nome], tmp_path / "z.cad", lambda p, n: n.__setitem__(slice(21, 23), ["0", "0"])
                     if len(n) > 22 else None)
    assert ns.teste_casos(zerado, _spec(nome)["testes"])


def test_nets_gravados_errados_nao_enganam(cads, tmp_path):
    """Nets forjados (todos = 7) nao ligam nada: a simulacao segue so a geometria."""
    forjado = _editar(cads["partida_direta"], tmp_path / "f.cad",
                      lambda p, n: n.__setitem__(slice(21, 23), ["7", "7"]) if len(n) > 22 else None)
    assert ns.teste_casos(forjado, _spec("partida_direta")["testes"])


def test_pino_fora_do_extremo_do_fio_nao_conecta(cads, tmp_path):
    """Move a bobina 1px: nenhum fio termina mais no pino -> nao energiza (mesmo com net no arquivo)."""
    def move(p, n):
        if p["id"] == "9000" and len(n) > 9:
            n[8] = str(int(n[8]) + 1)
    c = ns.Circuito(_editar(cads["partida_direta"], tmp_path / "m.cad", move))
    assert c.estado({"S1": True})["bobinas"] == []
    assert any("9000" in s for s in c.soltos)
    ok = ns.Circuito(cads["partida_direta"])
    assert ok.estado({"S1": True})["bobinas"] == ["KM1"]
    assert not ok.soltos


def test_conectividade_igual_a_do_geo_check(cads):
    """Nenhum pino funcional solto no sim <=> geo_check sem pino solto, nos exemplos."""
    for nome in NOMES:
        curtos, soltos = geo_check.analisar(cads[nome])
        c = ns.Circuito(cads[nome])
        assert not curtos and not soltos and not c.soltos, nome


# --- API ---------------------------------------------------------------------------------------

def test_api_estado_e_resolve_compativeis(cads):
    c = ns.Circuito(cads["partida_direta"])
    e = c.estado({"S1": True})
    assert set(e) >= {"bobinas", "lampadas", "temporizadores", "status"}
    assert e == {"status": "OK", "bobinas": ["KM1"], "lampadas": ["H1"], "temporizadores": {}, "curtos": []}
    assert c.resolve({"S1": True}) == ("OK", {"KM1"})
    assert c.resolve({}, {"KM1"}) == ("OK", {"KM1"})            # selo
    assert c.resolve({"S0": True}, {"KM1"}) == ("OK", set())
    assert c.resolve({"RT1": True, "S1": True}) == ("OK", set())
    assert set(c.entradas) == {"S0", "S1", "RT1"} and set(c.bobinas) == {"KM1"}
    assert set(c.lampadas) == {"H1"}
    assert isinstance(c.supply, int) and isinstance(c.ret, int)   # cad_simulate serializa em JSON


def test_estado_inicial_nao_vaza_entre_chamadas(cads):
    c = ns.Circuito(cads["partida_direta"])
    assert c.estado({}, ["KM1"])["bobinas"] == ["KM1"]
    assert c.estado({})["bobinas"] == []


def test_cli_test_e_tabela(cads, capsys):
    ns.tabela(cads["intercalada"])
    out = capsys.readouterr().out
    assert "lampadas:" in out and "KM2" in out
    assert ns.teste(cads["intercalada"])
    assert "15/15 OK" in capsys.readouterr().out


def test_corrida_continua_detectada(cads):
    c = ns.Circuito(cads["intercalada"])
    assert c.estado({"S1": True, "S2": True})["status"] == "RACE"


# --- lampadas ----------------------------------------------------------------------------------

def test_lampadas_seguem_bobina_e_termico(cads):
    c = ns.Circuito(cads["partida_sinalizacao"])
    assert set(c.lampadas) == {"H1", "H2"}
    assert c.estado({})["lampadas"] == []
    assert c.estado({"S1": True})["lampadas"] == ["H1"]
    assert c.estado({}, ["KM1"])["lampadas"] == ["H1"]
    # termico disparado: abre o comando (KM1 cai) e o NA 97-98 acende H2
    e = c.estado({"RT1": True}, ["KM1"])
    assert e["bobinas"] == [] and e["lampadas"] == ["H2"]
    assert c.estado({"RT1": True, "S1": True})["lampadas"] == ["H2"]


def test_esperado_lampadas_reprova_quando_errado(cads, capsys):
    caso_ok = {"nome": "ok", "entradas": {"S1": True}, "esperado": ["KM1"], "esperado_lampadas": ["H1"], "status": "OK"}
    assert ns.teste_casos(cads["partida_sinalizacao"], [caso_ok])
    for erro in ({"esperado_lampadas": []}, {"esperado_lampadas": ["H1", "H2"]}, {"esperado_lampadas": ["H2"]}):
        assert not ns.teste_casos(cads["partida_sinalizacao"], [{**caso_ok, **erro}])
    out = capsys.readouterr().out
    assert "FALHA" in out and "esperado_lampadas=['H2']" in out


def test_lampadas_nos_exemplos_sao_validadas(cads):
    """Cada exemplo com H1/H2 declara esperado_lampadas e eles batem com o simulador."""
    for nome in NOMES:
        spec = _spec(nome)
        c = ns.Circuito(cads[nome])
        if not c.lampadas:
            continue
        com = [t for t in spec["testes"] if t.get("esperado_lampadas") is not None]
        assert com, f"{nome}: lampadas sem esperado_lampadas"
        for t in com:
            assert c.estado(t["entradas"], t.get("inicial"))["lampadas"] == sorted(t["esperado_lampadas"]), (nome, t["nome"])


def test_chaves_invalidas_sao_apontadas(cads):
    c = ns.Circuito(cads["partida_sinalizacao"])
    cs = {"entradas": {"FANTASMA": True}, "inicial": ["KM9"], "esperado": ["KM1"],
          "esperado_lampadas": ["H1", "H7"], "passos": [{"entradas": {"XX": True}}]}
    assert set(ns.chaves_invalidas(c, cs)) == {("entradas", "FANTASMA"), ("inicial", "KM9"),
                                               ("esperado_lampadas", "H7"), ("entradas", "XX")}
    assert ns.chaves_invalidas(c, {"entradas": {"S1": True}, "esperado": ["KM1"], "esperado_lampadas": ["H1"]}) == []


def test_gate_reprova_lampada_inexistente(tmp_path):
    spec = _spec("partida_sinalizacao")
    spec["testes"][1]["esperado_lampadas"] = ["H9"]
    r = build_spec.construir(spec, str(tmp_path / "g.cad"))
    assert not r["ok"]
    assert any("H9" in e and "lampada" in e for e in r["erros"]), r["erros"]


# --- curto de fase -----------------------------------------------------------------------------

def test_curto_dinamico_por_contatos_fechados(tmp_path):
    spec = _spec("partida_direta")
    spec["layout"]["comando"].append({"id": "mx", "de": "L1", "para": "N", "serie": [["S9", "8000", "-S9"]],
                                      "ramos": [{"carga": ["S8", "8000", "-S8"]}]})
    spec["testes"] = []
    c = ns.Circuito(_build(spec, tmp_path / "c.cad"))
    assert geo_check.analisar(str(tmp_path / "c.cad"))[0] == []          # estaticamente sem curto
    assert c.estado({"S9": True})["status"] == "OK"
    e = c.estado({"S8": True, "S9": True})
    assert e["status"] == "CURTO" and e["curtos"] == ["1+N"]
    assert c.estado({"S1": True})["status"] == "OK"                      # comando normal intacto


def test_curto_estatico_compativel_com_geo_check(tmp_path):
    spec = _spec("partida_direta")
    spec["layout"]["fontes"][0]["pinos"]["PE"] = "N"                    # PE no neutro
    p = _build(spec, tmp_path / "s.cad")
    curtos, _ = geo_check.analisar(p)
    assert curtos and "P" in curtos[0] and "N" in curtos[0]
    e = ns.Circuito(p).estado({})
    assert e["status"] == "CURTO" and any({"N", "P"} <= set(c.split("+")) for c in e["curtos"])


def test_curto_na_potencia_por_inversao_de_fase(cads):
    """Intertravamento NF (7001) contornado -> KM1 e KM2 juntos trocam fases no motor = curto 1+2/2+3."""
    papeis = ns.carregar_papeis()
    papeis["7001"] = {"papel": "polos", "modo": "FECHADO"}               # NF do intertravamento vira fio
    c = ns.Circuito(cads["reversao"], papeis=papeis)
    e = c.estado({"S1": True, "S2": True})
    assert set(e["bobinas"]) == {"KM1", "KM2"}
    assert e["status"] == "CURTO" and e["curtos"], e
    normal = ns.Circuito(cads["reversao"])
    assert normal.estado({"S1": True}, ["KM1"])["status"] == "OK"


def test_reversao_normal_nao_acusa_curto(cads):
    c = ns.Circuito(cads["reversao"])
    for ent, ini in itertools.product(({}, {"S1": True}, {"S2": True}, {"S0": True}), ([], ["KM1"], ["KM2"])):
        assert c.estado(ent, ini)["curtos"] == [], (ent, ini)


# --- temporizadores (ON/OFF-delay) por passos de tempo ------------------------------------------

def _papeis_timer(tipo, tempo):
    p = ns.carregar_papeis()
    p["8016"] = {"papel": "contato_temp", "modo": "NA", "tipo": tipo, "tempo": tempo}   # NA 97-98 temporizado
    return p


# --- temporizadores-carga 9004..9007 + contatos 7004..7015 ----------------------------------------

def _circ_timer(tmp_path, carga, contato, nome, rot="-KT1", rot_carga=None):
    """Circuito de 2 ramos: S1 alimenta a carga; o contato de mesmo rotulo comanda H1."""
    spec = {"titulo": nome, "layout": {
        "trilhos": {"L1": 14, "L2": 20, "L3": 26, "N": 282, "x0": 25, "x1": 395, "PE": 291},
        "fontes": [{"id": "X1", "classe": "3007", "rotulo": "-X",
                    "pinos": {"L1": "L1", "L2": "L2", "L3": "L3", "N": "N", "PE": "PE"}}],
        "comando": [
            {"id": "m1", "de": "L1", "para": "N", "serie": [["S1", "8000", "-S1"]],
             "ramos": [{"carga": ["KT1", carga, rot_carga or rot]}]},
            {"id": "m2", "de": "L1", "para": "N", "serie": [["T1", contato, rot]],
             "ramos": [{"carga": ["H1", "9008", "-H1"]}]},
        ],
        "testes": []}}
    return ns.Circuito(_build(spec, tmp_path / f"{nome}.cad"))


def test_tempo_do_temporizador_labels():
    t = ns.Circuito._tempo_do_temporizador
    base = ["-KT1", "", "A1", "A2"]
    assert t(base + ["0", "5"]) == 5.0      # proto do 9004 no symbol_lib: unidade s, tempo 5
    assert t(base + ["3", "10"]) == 1.0     # x0,1 s: 10 ticks de 100 ms
    assert t(base + ["1", "1"]) == 10.0     # x10 s
    assert t(base + ["2", "1"]) == 100.0    # rotulo x60 s do dialogo = x1000 ticks no codigo
    assert t(base + ["9", "5"]) == 0.5      # unidade desconhecida: x1 tick (0,5 s)
    assert t(base + ["0", "0.5"]) == 0.0    # atoi do C: fracao vira 0 (comuta no 1o tick)
    assert t(base) == 0.0                  # sem labels: 0 s


def test_9004_on_delay_liga_via_7004(tmp_path):
    c = _circ_timer(tmp_path, "9004", "7004", "timer_on")
    assert [t["tipo"] for t in c._tim] == ["ton"]
    assert c._cont and all(x["fonte"] == "timer" for x in c._cont if x["chave"] == "KT1")
    assert c.estado({"S1": True}, avanca=1.9, tempos={"KT1": 2})["lampadas"] == []
    e = c.estado({"S1": True}, avanca=2, tempos={"KT1": 2})
    assert e["lampadas"] == ["H1"] and e["temporizadores"]["KT1"]["saida"] is True
    assert c.estado({}, avanca=0, tempos={"KT1": 2})["lampadas"] == []   # sem S1 o timer nao parte
    st = c.novo_estado(tempos={"KT1": 2})
    c.avancar(st, {"S1": True}, 2)
    assert c.avancar(st, {}, 0)["lampadas"] == []                        # desenergizou: abre na hora


def test_9005_off_delay_segura_via_7008(tmp_path):
    c = _circ_timer(tmp_path, "9005", "7008", "timer_off")
    assert [t["tipo"] for t in c._tim] == ["tof"]
    st = c.novo_estado(tempos={"KT1": 3})
    assert c.avancar(st, {"S1": True}, 0)["lampadas"] == ["H1"]          # fecha na hora
    assert c.avancar(st, {}, 2.9)["lampadas"] == ["H1"]                 # comando caiu: segura 3 s
    assert c.avancar(st, {}, 0.1)["lampadas"] == []                     # 3 s completos: abre


def test_9006_on_off_nos_dois_sentidos(tmp_path):
    c = _circ_timer(tmp_path, "9006", "7012", "timer_onoff")
    assert [t["tipo"] for t in c._tim] == ["tonof"]
    st = c.novo_estado(tempos={"KT1": 2})
    c.avancar(st, {"S1": True}, 1.9)
    assert c.avancar(st, {"S1": True}, 0.1)["lampadas"] == ["H1"]        # ligou apos 2 s
    assert c.avancar(st, {}, 1.9)["lampadas"] == ["H1"]                  # soltou: segura 2 s
    assert c.avancar(st, {}, 0.1)["lampadas"] == []                      # apagou


def test_9007_intermitente_alterna_e_para(tmp_path):
    c = _circ_timer(tmp_path, "9007", "7004", "timer_pisca")
    assert [t["tipo"] for t in c._tim] == ["intermitente"]
    st = c.novo_estado(tempos={"KT1": 1})
    passos = [c.avancar(st, {"S1": True}, 0.5) for _ in range(6)]
    assert [e["temporizadores"]["KT1"]["saida"] for e in passos] == [False, True, True, False, False, True]
    assert passos[1]["lampadas"] == ["H1"] and passos[3]["lampadas"] == []   # lampada segue o pisca
    e = c.avancar(st, {}, 0.5)
    assert e["lampadas"] == [] and e["temporizadores"]["KT1"]["saida"] is False  # parou em 0


def test_contato_NC_temporizado(tmp_path):
    c = _circ_timer(tmp_path, "9004", "7005", "timer_nc")               # NC do ON-delay
    assert c.estado({"S1": True}, avanca=0, tempos={"KT1": 2})["lampadas"] == ["H1"]  # fechado antes de T
    assert c.estado({"S1": True}, avanca=2, tempos={"KT1": 2})["lampadas"] == []      # abre apos T


def test_tipo_vem_do_timer_mesmo_rotulo(tmp_path):
    """7008 e OFF por classe, mas com 9004 (ON) de mesmo rotulo segue o ON."""
    c = _circ_timer(tmp_path, "9004", "7008", "timer_tipo_do_timer")
    assert c.estado({"S1": True}, avanca=1.9, tempos={"KT1": 2})["lampadas"] == []
    assert c.estado({"S1": True}, avanca=2, tempos={"KT1": 2})["lampadas"] == ["H1"]


def test_contato_temp_sem_timer_mesmo_rotulo(tmp_path):
    """7004 sem 9004 de mesmo rotulo: NA abre (NC 7005 fecha); sem contagem propria."""
    c = _circ_timer(tmp_path, "9000", "7004", "timer_sem_timer", rot_carga="-KM1")
    assert not c._tim
    assert c.estado({"S1": True}, avanca=100)["lampadas"] == []
    d = _circ_timer(tmp_path, "9000", "7005", "timer_sem_timer_nc", rot_carga="-KM1")
    assert d.estado({"S1": True}, avanca=0)["lampadas"] == ["H1"]


def test_ligacoes_multipar_por_fecha_quando():
    assert ns._ligacoes_re("7006", {"pinos": ["55", "57", "56", "58"], "contatos": [
        {"pinos": ["55", "56"], "fecha_quando": "estado==0"},
        {"pinos": ["57", "58"], "fecha_quando": "estado==1"}]}) == [(["p1", "p3"], "NC"), (["p2", "p4"], "NA")]
    assert ns._ligacoes_re("7004", {"pinos": ["67", "68"], "contatos": [
        {"pinos": ["67", "68"], "fecha_quando": "estado==1"}]}) == [(["p1", "p2"], "NA")]
    assert ns._ligacoes_re("7004", {"pinos": ["67"], "contatos": [
        {"pinos": ["67", "68"], "fecha_quando": "estado==1"}]}) == []     # pino fora: cai no par padrao
    assert ns._ligacoes_re("7004", {}) == []


def test_7006_dois_pares_seguem_o_timer(tmp_path):
    """7006 NA-NC (55-56 NC, 57-58 NA) com 9004 de mesmo rotulo: os 2 pares seguem a saida."""
    import cade_mcp
    sims = [{"classe": "3007", "x": 50, "y": 20, "rotulo": "-X", "id": "X1"},
            {"classe": "8000", "x": 50, "y": 60, "rotulo": "-S1", "id": "S1"},
            {"classe": "9004", "x": 50, "y": 120, "rotulo": "-KT1", "id": "KT1"},
            {"classe": "7006", "x": 110, "y": 60, "rotulo": "-KT1", "id": "T1"},
            {"classe": "9008", "x": 110, "y": 110, "rotulo": "-H1", "id": "H1"},
            {"classe": "9008", "x": 119, "y": 110, "rotulo": "-H2", "id": "H2"}]
    fios = [{"x1": 50, "y1": 20, "x2": 50, "y2": 60},                     # trilho L1
            {"x1": 68, "y1": 20, "x2": 68, "y2": 122},                   # trilho N (pino N da fonte)
            {"x1": 68, "y1": 122, "x2": 68, "y2": 132},
            {"x1": 50, "y1": 72, "x2": 50, "y2": 120},                   # S1.B -> KT1.A
            {"x1": 50, "y1": 132, "x2": 68, "y2": 132},                  # KT1.B -> N
            {"x1": 50, "y1": 60, "x2": 110, "y2": 60},                   # L1 -> p1 (55)
            {"x1": 50, "y1": 60, "x2": 119, "y2": 60},                   # L1 -> p2 (57)
            {"x1": 110, "y1": 72, "x2": 110, "y2": 110},                 # p3 (56) -> H1.A
            {"x1": 110, "y1": 122, "x2": 68, "y2": 122},                 # H1.B -> N
            {"x1": 119, "y1": 72, "x2": 119, "y2": 110},                 # p4 (58) -> H2.A
            {"x1": 119, "y1": 122, "x2": 68, "y2": 122}]                 # H2.B -> N
    out = str(tmp_path / "timer_7006.cad")
    msg = cade_mcp.cad_build("TIMER_7006", json.dumps(sims), json.dumps(fios), out_path=out)
    assert "ERRO" not in msg, msg
    c = ns.Circuito(out)
    assert not c.soltos, c.soltos
    assert [t["tipo"] for t in c._tim] == ["ton"]
    st = c.novo_estado(tempos={"KT1": 2})
    e = c.avancar(st, {"S1": True}, 0)
    assert e["lampadas"] == ["H1"], e                                     # NC conduz, NA abre
    e = c.avancar(st, {"S1": True}, 2)
    assert e["lampadas"] == ["H2"], e                                     # apos T: inverte



def test_on_delay_fecha_apos_o_tempo(cads):
    c = ns.Circuito(cads["partida_sinalizacao"], papeis=_papeis_timer("ton", 5))
    assert c.estado({"RT1": True}, avanca=0)["lampadas"] == []
    assert c.estado({"RT1": True}, avanca=4.9)["lampadas"] == []
    e = c.estado({"RT1": True}, avanca=5)
    assert e["lampadas"] == ["H2"] and e["temporizadores"]["RT1"]["saida"] is True
    assert e["temporizadores"]["RT1"]["decorrido"] == 5
    # sem acionar nunca fecha, por mais tempo que passe
    assert c.estado({}, avanca=100)["lampadas"] == []


def test_on_delay_zera_se_comando_cai_antes(cads):
    c = ns.Circuito(cads["partida_sinalizacao"], papeis=_papeis_timer("ton", 5))
    st = c.novo_estado()
    c.avancar(st, {"RT1": True}, 3)
    e = c.avancar(st, {}, 1)                        # soltou: contagem zera
    assert e["temporizadores"]["RT1"]["decorrido"] == 0
    assert c.avancar(st, {"RT1": True}, 3)["lampadas"] == []   # 3s (nao 6s) -> ainda aberto
    assert c.avancar(st, {"RT1": True}, 2)["lampadas"] == ["H2"]


def test_off_delay_mantem_e_depois_abre(cads):
    c = ns.Circuito(cads["partida_sinalizacao"], papeis=_papeis_timer("tof", 3))
    st = c.novo_estado()
    assert c.avancar(st, {"RT1": True}, 0)["lampadas"] == ["H2"]        # fecha na hora
    assert c.avancar(st, {}, 2)["lampadas"] == ["H2"]                   # comando caiu: segura 3s
    assert c.avancar(st, {}, 1)["lampadas"] == []                       # 3s completos: abre


def test_timer_em_casos_declarativos(cads, capsys, monkeypatch):
    papeis = _papeis_timer("ton", 5)
    monkeypatch.setattr(ns, "carregar_papeis", lambda path=None: papeis)
    casos = [
        {"nome": "antes do tempo", "entradas": {"RT1": True}, "avanca": 4, "esperado": [],
         "esperado_lampadas": [], "esperado_temporizadores": [], "status": "OK"},
        {"nome": "apos o tempo", "entradas": {"RT1": True}, "tempo": 5, "esperado": [],
         "esperado_lampadas": ["H2"], "esperado_temporizadores": ["RT1"]},
        {"nome": "passos", "passos": [{"entradas": {"RT1": True}, "avanca": 4, "esperado_lampadas": []},
                                      {"entradas": {"RT1": True}, "avanca": 1, "esperado_lampadas": ["H2"]}],
         "esperado_lampadas": ["H2"]},
        {"nome": "tempo sobrescrito por caso", "entradas": {"RT1": True}, "avanca": 2, "tempos": {"RT1": 2},
         "esperado_lampadas": ["H2"]},
    ]
    assert ns.teste_casos(cads["partida_sinalizacao"], casos)
    assert not ns.teste_casos(cads["partida_sinalizacao"],
                              [{"nome": "x", "entradas": {"RT1": True}, "avanca": 4, "esperado_lampadas": ["H2"]}])


def test_timer_selo_com_bobina_comandando_contato_temporizado(cads):
    """Contato temporizado comandado por BOBINA (rotulo -KM1): fecha 2s depois de KM1 ligar."""
    p = ns.carregar_papeis()
    p["7000"] = {"papel": "polos", "modo": "FECHADO"}            # selo vira fio: KM1 so liga com S1 pressionado
    p["8016"] = {"papel": "contato_temp", "modo": "NA", "tipo": "ton", "tempo": 2}
    c = ns.Circuito(cads["partida_sinalizacao"], papeis=p)
    assert c.estado({"S1": True}, avanca=1)["bobinas"] == ["KM1"]


# --- tabela de papeis (docs/classes-papeis.json) ----------------------------------------------------

def test_papeis_embutidos_cobrem_o_modelo_anterior():
    t = ns.carregar_papeis(Path("/nao/existe.json"))
    for c in ("8000", "8016", "7000", "10050"):
        assert t[c] == {"papel": "contato", "modo": "NA"}
    for c in ("8001", "8017", "7001", "10051"):
        assert t[c] == {"papel": "contato", "modo": "NC"}
    assert t["9000"]["papel"] == t["10060"]["papel"] == "bobina"
    assert t["9008"]["papel"] == "lampada"


def test_papeis_embutidos_4polos_e_disjuntor():
    """2002 = polos NA por rotulo (senao viraria contato p1-p2 e daria curto L1-L2);
    6002/6004 = protecao passante (no app, fechar a mao)."""
    t = ns.carregar_papeis(Path("/nao/existe.json"))
    assert t["2002"] == {"papel": "polos", "modo": "NA"}
    assert t["6002"] == {"papel": "polos", "modo": "FECHADO"}
    assert t["6004"] == {"papel": "polos", "modo": "FECHADO"}


def test_papeis_json_sobrepoe_e_ignora_lixo(tmp_path):
    f = tmp_path / "classes-papeis.json"
    f.write_text(json.dumps({"classes": {"7004": {"papel": "contato", "modo": "NF"},
                                         "9004": {"papel": "bobina"}, "9999": {"papel": "inventado"},
                                         "8000": {"papel": "contato", "modo": "NC"}}}), encoding="utf-8")
    t = ns.carregar_papeis(f)
    assert t["7004"] == {"papel": "contato", "modo": "NC"}
    assert t["9004"]["papel"] == "bobina" and "9999" not in t
    assert t["8000"]["modo"] == "NC"                     # JSON do RE tem precedencia
    f.write_text("{nao e json", encoding="utf-8")
    assert ns.carregar_papeis(f)["8000"]["modo"] == "NA"  # arquivo corrompido -> embutida


def test_classe_nova_via_papeis_entra_no_modelo(cads, tmp_path):
    """Troca a classe de um botao por outra do JSON de papeis: o simulador a trata pelo papel, nao pelo id."""
    def troca(p, n):
        pass
    txt = Path(cads["partida_direta"]).read_bytes().decode("latin1")
    novo = re.sub(r"(\*\d+\*)8000(#-S1#)", r"\g<1>8004\g<2>", txt)
    assert novo != txt
    out = tmp_path / "n.cad"
    out.write_bytes(novo.encode("latin1"))
    sem = ns.Circuito(str(out), papeis=ns.carregar_papeis(Path("/nao/existe.json")))
    assert "S1" not in sem.entradas                      # 8004 desconhecida: ignorada
    p = ns.carregar_papeis(Path("/nao/existe.json"))
    p["8004"] = {"papel": "contato", "modo": "NA"}
    com = ns.Circuito(str(out), papeis=p)
    assert com.estado({"S1": True})["bobinas"] == ["KM1"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
