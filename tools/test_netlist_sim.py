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
    return json.loads((EX / f"{nome}.layout.json").read_text())


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


def test_papeis_json_sobrepoe_e_ignora_lixo(tmp_path):
    f = tmp_path / "classes-papeis.json"
    f.write_text(json.dumps({"classes": {"7004": {"papel": "contato", "modo": "NF"},
                                         "9004": {"papel": "bobina"}, "9999": {"papel": "inventado"},
                                         "8000": {"papel": "contato", "modo": "NC"}}}))
    t = ns.carregar_papeis(f)
    assert t["7004"] == {"papel": "contato", "modo": "NC"}
    assert t["9004"]["papel"] == "bobina" and "9999" not in t
    assert t["8000"]["modo"] == "NC"                     # JSON do RE tem precedencia
    f.write_text("{nao e json")
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
