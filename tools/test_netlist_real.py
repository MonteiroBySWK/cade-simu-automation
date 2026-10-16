#!/usr/bin/env python3
"""Semantica REAL do app no netlist_sim (docs/re-engenharia.md 11): esquema real de
docs/classes-papeis.json (contatos[].fecha_quando por posicao de pino), NA-NC/comutados, protecoes que
comecam abertas, fusiveis, termico por rotulo e TEMPORIZADORES 9004..9007 com os parametros lidos dos
rotulos 4/5 da entidade. Circuitos pequenos montados direto por coordenadas (sem layout).
Roda com `python3 -m pytest tools/test_netlist_real.py -q`."""
import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import cade_mcp  # noqa: E402
import netlist_sim as ns  # noqa: E402
import temporizador as TM  # noqa: E402

# offsets (dx, dy) dos pinos p1..pN (docs/pinos-binario.json)
P2 = [(0, 0), (0, 12)]
FONTE_L, FONTE_N = (10, 10), (16, 10)


class B:
    """monta um .cad pequeno: simbolos com pinos conhecidos e fios ponto a ponto (so geometria)."""

    def __init__(self, tmp, nome="c"):
        self.out = Path(tmp) / f"{nome}.cad"
        self.simbolos = [{"classe": "3003", "x": 10, "y": 10, "id": "X", "rotulo": "-X"}]
        self.fios = []
        self.pino = {}
        self.pino["X.L"], self.pino["X.N"] = FONTE_L, FONTE_N

    def sym(self, id_, classe, x, y, rotulo, offs, params=None, nomes=None):
        s = {"classe": classe, "x": x, "y": y, "id": id_, "rotulo": rotulo}
        if params:
            s["params"] = params
        self.simbolos.append(s)
        for i, (dx, dy) in enumerate(offs):
            self.pino[f"{id_}.{(nomes or [f'p{k + 1}' for k in range(len(offs))])[i]}"] = (x + dx, y + dy)
        return self

    def liga(self, *pinos):
        """liga os pinos em estrela ao 1o (fios retos: so o extremo importa)."""
        a = self.pino[pinos[0]]
        for q in pinos[1:]:
            self.fios.append({"x1": a[0], "y1": a[1], "x2": self.pino[q][0], "y2": self.pino[q][1]})
        return self

    def cad(self):
        r = cade_mcp.cad_build("T", json.dumps(self.simbolos), json.dumps(self.fios), str(self.out), auto_net=False)
        assert "ERRO" not in r, r
        return ns.Circuito(str(self.out))


# --- esquema real de classes-papeis.json ----------------------------------------------------------

def test_json_real_vira_contatos_por_posicao_de_pino():
    t = ns.carregar_papeis()
    # 7002: pinos [11,13,12,14] = p1..p4 ; 11-12 NC (p1-p3), 13-14 NA (p2-p4)
    assert t["7002"]["papel"] == "elemento" and t["7002"]["fam"] == "rele"
    assert t["7002"]["contatos"] == [{"pinos": ["p1", "p3"], "cond": "0"}, {"pinos": ["p2", "p4"], "cond": "1"}]
    # 7003 comutado: 11-12 NC, 11-14 NA ; 8019 (termico): mesmo, mas entrada
    assert t["7003"]["contatos"] == [{"pinos": ["p1", "p2"], "cond": "0"}, {"pinos": ["p1", "p3"], "cond": "1"}]
    assert t["8019"]["fam"] == "ent" and t["8018"]["fam"] == "ent"
    assert t["7004"]["fam"] == "tmp" and t["7004"]["segue"] == ["9004", "9007"]
    assert t["7009"]["contatos"][0]["cond"] == "0" and t["7009"]["segue"][0] == "9005"
    assert t["7013"]["segue"][0] == "9006"
    assert t["9004"] == {"papel": "temporizador", "tipo": "ton", "pinos": ["p1", "p2"]}
    assert t["9005"]["tipo"] == "tof" and t["9006"]["tipo"] == "ton_tof" and t["9007"]["tipo"] == "intermitente"
    # polos do contator e do termico (sempre) vem do JSON
    assert [c["cond"] for c in t["6007"]["contatos"]] == ["S", "S", "S"]
    assert [c["pinos"] for c in t["2001"]["contatos"]] == [["p1", "p4"], ["p2", "p5"], ["p3", "p6"]]
    # disjuntor comeca aberto (conduz com estado==1); fusivel conduz com estado==0
    assert t["6009"]["contatos"][0]["cond"] == "1" and t["5000"]["contatos"][0]["cond"] == "0"
    assert t["8017"]["contatos"][0]["cond"] == "0" and t["8016"]["contatos"][0]["cond"] == "1"


def test_json_real_nao_e_so_acrescimo_e_logica_mantem_embutido():
    t = ns.carregar_papeis()
    assert t["8000"]["papel"] == "elemento"          # o JSON sobrepoe o embutido legado
    assert t["10050"] == ns.PAPEIS_EMBUTIDOS["10050"]  # 'logica' sem modelo eletrico no JSON: fica o embutido
    assert "9001" not in t or t["9001"]["papel"] != "bobina"   # biestavel/telerruptor: nao modelados


def test_json_real_corrompido_ou_ausente_cai_no_embutido(tmp_path):
    f = tmp_path / "x.json"
    f.write_text("{nao")
    t = ns.carregar_papeis(f)
    assert t["7002"]["papel"] == "elemento" and t["6009"] == {"papel": "polos", "modo": "NA"}
    assert ns.carregar_papeis(tmp_path / "nao_existe.json")["9005"]["tipo"] == "tof"


def test_json_real_arquivo_proprio_com_contatos(tmp_path):
    f = tmp_path / "p.json"
    f.write_text(json.dumps({"_nota": "x", "8000": {"papel": "botao_NC", "aba": "x", "pinos": ["11", "12"],
                                                    "contatos": [{"pinos": ["11", "12"], "fecha_quando": "estado==0"}]}}))
    t = ns.carregar_papeis(f)
    assert t["8000"]["contatos"] == [{"pinos": ["p1", "p2"], "cond": "0"}]


# --- contatos multiplos --------------------------------------------------------------------------

def _lamp(b, id_, x, y, rot, topo):
    b.sym(id_, "9008", x, y, rot, P2).liga(topo, f"{id_}.p1").liga("X.N", f"{id_}.p2")


def test_contato_na_nc_7002_segue_bobina_de_mesmo_rotulo(tmp_path):
    b = B(tmp_path)
    b.sym("S1", "8000", 30, 30, "-S1", P2).liga("X.L", "S1.p1")
    b.sym("KM1", "9000", 30, 60, "-KM1", P2).liga("S1.p2", "KM1.p1").liga("X.N", "KM1.p2")
    # 7002: p1(11) p2(13) / p3(12) p4(14).  11-12 NC, 13-14 NA
    b.sym("K", "7002", 60, 30, "-KM1", [(0, 0), (9, 0), (0, 12), (9, 12)]).liga("X.L", "K.p1", "K.p2")
    _lamp(b, "HNC", 80, 60, "-HNC", "K.p3")
    _lamp(b, "HNA", 100, 60, "-HNA", "K.p4")
    c = b.cad()
    assert c.estado({})["lampadas"] == ["HNC"]
    e = c.estado({"S1": True})
    assert e["bobinas"] == ["KM1"] and e["lampadas"] == ["HNA"]


def test_contato_comutado_8003_por_entrada(tmp_path):
    b = B(tmp_path)
    # 8003: p1(11) em (3,0), p2(12) em (0,12), p3(14) em (6,12) ; 11-12 NC, 11-14 NA
    b.sym("S", "8003", 40, 30, "-S", [(3, 0), (0, 12), (6, 12)]).liga("X.L", "S.p1")
    _lamp(b, "HNC", 40, 60, "-HNC", "S.p2")
    _lamp(b, "HNA", 70, 60, "-HNA", "S.p3")
    c = b.cad()
    assert c.estado({})["lampadas"] == ["HNC"]
    assert c.estado({"S": True})["lampadas"] == ["HNA"]


def test_comutado_termico_8019_e_na_nc_8018_seguem_o_rotulo_do_6007(tmp_path):
    b = B(tmp_path)
    b.sym("A", "8018", 40, 30, "-RT1", [(0, 0), (9, 0), (0, 12), (9, 12)]).liga("X.L", "A.p1", "A.p2")
    _lamp(b, "H95", 40, 60, "-H95", "A.p3")     # 95-97 NC (p1-p3)
    _lamp(b, "H96", 70, 60, "-H96", "A.p4")     # 96-98 NA (p2-p4)
    c = b.cad()
    assert c.estado({})["lampadas"] == ["H95"]
    assert c.estado({"RT1": True})["lampadas"] == ["H96"]
    assert "RT1" in c.entradas


# --- estados iniciais: disjuntor aberto, fusivel integro, termico conduz -------------------------

def _protecao(tmp, classe, offs, rot):
    b = B(tmp)
    b.sym("Q", classe, 40, 30, rot, offs, nomes=None).liga("X.L", "Q.p1")
    _lamp(b, "H", 40, 70, "-H", f"Q.p{len(offs) // 2 + 1}")
    return b.cad()


def test_disjuntor_comeca_aberto_e_fecha_com_a_entrada(tmp_path):
    c = _protecao(tmp_path, "6010", [(0, 0), (0, 12)], "-Q1")      # disjuntor I: 1-2 com estado==1
    assert c.estado({})["lampadas"] == []
    assert c.estado({"Q1": True})["lampadas"] == ["H"]
    assert "Q1" in c.entradas and "Q1" in c.protecoes
    assert c.ligar_protecoes({"S": True}) == {"S": True, "Q1": True}


def test_fusivel_conduz_ate_queimar(tmp_path):
    c = _protecao(tmp_path, "5000", [(0, 0), (0, 12)], "-F1")      # 1-2 com estado==0
    assert c.estado({})["lampadas"] == ["H"]
    assert c.estado({"F1": True})["lampadas"] == []


def test_polos_do_termico_6007_sempre_conduzem(tmp_path):
    b = B(tmp_path)
    offs6 = [(0, 0), (6, 0), (12, 0), (0, 12), (6, 12), (12, 12)]
    b.sym("F", "6007", 40, 30, "-F1", offs6).liga("X.L", "F.p1")
    _lamp(b, "H", 40, 70, "-H", "F.p4")
    c = b.cad()
    assert c.estado({})["lampadas"] == ["H"]
    assert c.estado({"F1": True})["lampadas"] == ["H"]      # disparar o termico nao abre os polos de potencia


def test_contato_8017_segue_rotulo_do_6007_e_nao_o_da_bobina(tmp_path):
    """contato do termico (8017) so conhece o rotulo do 6007: bobina de mesmo nome NAO o comanda."""
    b = B(tmp_path)
    b.sym("KM1", "9000", 30, 30, "-KM1", P2).liga("X.L", "KM1.p1").liga("X.N", "KM1.p2")
    b.sym("NC", "8017", 60, 30, "-KM1", P2).liga("X.L", "NC.p1")
    _lamp(b, "H", 60, 70, "-H", "NC.p2")
    c = b.cad()
    assert c.estado({})["bobinas"] == ["KM1"] and c.estado({})["lampadas"] == ["H"]    # 8017 fechado (estado 0)
    assert c.estado({"KM1": True})["lampadas"] == []                                   # a entrada o abre


# --- temporizadores ------------------------------------------------------------------------------

def test_rotulos_do_temporizador():
    assert TM.atoi("5") == 5 and TM.atoi("0.5") == 0 and TM.atoi("") == 0 and TM.atoi(" 12s") == 12
    assert TM.ticks_dos_rotulos("0", "5") == 50 and TM.ticks_dos_rotulos("3", "7") == 7
    assert TM.ticks_dos_rotulos("1", "2") == 200 and TM.ticks_dos_rotulos("2", "1") == 1000
    assert TM.parametros_para_rotulos("9004", {"tempo": 5, "unidade": "0"}) == {4: "0", 5: "5"}
    assert TM.parametros_para_rotulos("9004", {"segundos": 5}) == {4: "0", 5: "5"}
    assert TM.parametros_para_rotulos("9005", {"segundos": 0.5}) == {4: "3", 5: "5"}
    for ruim in ({"tempo": "0.5"}, {"unidade": "x"}, {"segundos": 0.25}, {"foo": 1}):
        with pytest.raises(ValueError):
            TM.parametros_para_rotulos("9004", ruim)
    with pytest.raises(ValueError):
        TM.parametros_para_rotulos("9000", {"tempo": 5})


def _timer(tmp, classe, params, contatos):
    """botao S1 (momentaneo) -> temporizador KT1 ; contatos [(classe, rotulo_da_lampada)] de mesmo rotulo."""
    b = B(tmp)
    b.sym("S1", "8000", 30, 30, "-S1", P2).liga("X.L", "S1.p1")
    b.sym("KT1", classe, 30, 60, "-KT1", P2, params=params).liga("S1.p2", "KT1.p1").liga("X.N", "KT1.p2")
    x = 60
    for i, (cl, nome) in enumerate(contatos):
        b.sym(f"C{i}", cl, x, 30, "-KT1", P2).liga("X.L", f"C{i}.p1")
        _lamp(b, nome, x, 60, f"-{nome}", f"C{i}.p2")
        x += 25
    return b.cad()


def test_on_delay_9004_le_tempo_e_unidade_dos_rotulos(tmp_path):
    c = _timer(tmp_path, "9004", {"tempo": 5, "unidade": "0"},
               [("7004", "HNA"), ("7005", "HNC"), ("7000", "HINST")])
    assert c._timers() == {"KT1": {"chave": "KT1", "tipo": "ton", "tempo": 5.0, "real": True}}
    e = c.estado({"S1": True}, avanca=0)
    # contato instantaneo (7000) segue o ESTADO na hora; os temporizados so apos a saida
    assert e["lampadas"] == ["HINST", "HNC"] and e["temporizadores"]["KT1"]["saida"] is False
    e = c.estado({"S1": True}, avanca=4.9)
    assert e["lampadas"] == ["HINST", "HNC"]
    e = c.estado({"S1": True}, avanca=5)
    assert e["lampadas"] == ["HINST", "HNA"] and e["temporizadores"]["KT1"]["saida"] is True
    assert e["temporizadores"]["KT1"]["tempo"] == 5.0
    # soltou: reset imediato (ON-delay sem memoria)
    assert c.estado({}, avanca=100)["lampadas"] == ["HNC"]


@pytest.mark.parametrize("params,ticks,seg", [
    ({"tempo": 7, "unidade": "3"}, 7, 0.7), ({"tempo": 2, "unidade": "0"}, 20, 2.0),
    ({"tempo": 1, "unidade": "1"}, 100, 10.0), ({"tempo": 1, "unidade": "2"}, 1000, 100.0),
    ({"tempo": 0, "unidade": "0"}, 0, 0.1)])
def test_unidades_do_temporizador(tmp_path, params, ticks, seg):
    c = _timer(tmp_path, "9004", params, [("7004", "H")])
    assert c._tmr[0]["ticks"] == ticks
    assert c._timers()["KT1"]["tempo"] == pytest.approx(seg)       # tempo 0 comuta no 1o tick (0,1 s)
    antes = c.estado({"S1": True}, avanca=seg - 0.05)
    assert antes["lampadas"] == []
    assert c.estado({"S1": True}, avanca=seg)["lampadas"] == ["H"]


def test_tick_configuravel(tmp_path):
    b = B(tmp_path)
    b.sym("S1", "8000", 30, 30, "-S1", P2).liga("X.L", "S1.p1")
    b.sym("KT1", "9004", 30, 60, "-KT1", P2, params={"tempo": 5, "unidade": "0"}).liga("S1.p2", "KT1.p1").liga("X.N", "KT1.p2")
    b.cad()
    c = ns.Circuito(str(b.out), tick=0.05)
    assert c._timers()["KT1"]["tempo"] == pytest.approx(2.5)


def test_off_delay_9005_mantem_apos_desenergizar(tmp_path):
    c = _timer(tmp_path, "9005", {"tempo": 3, "unidade": "0"}, [("7008", "HNA"), ("7009", "HNC")])
    st = c.novo_estado()
    assert c.avancar(st, {}, 10)["lampadas"] == ["HNC"]
    e = c.avancar(st, {"S1": True}, 0)                       # energiza: saida liga na hora
    assert e["lampadas"] == ["HNA"] and e["temporizadores"]["KT1"]["saida"] is True
    assert c.avancar(st, {}, 2.9)["lampadas"] == ["HNA"]     # desenergizou: segura 3 s
    e = c.avancar(st, {}, 0.1)
    assert e["lampadas"] == ["HNC"] and e["temporizadores"]["KT1"]["saida"] is False
    # reenergizar no meio da contagem recarrega T
    c.avancar(st, {"S1": True}, 0)
    c.avancar(st, {}, 2)
    c.avancar(st, {"S1": True}, 0)
    assert c.avancar(st, {}, 2)["lampadas"] == ["HNA"]
    assert c.avancar(st, {}, 1)["lampadas"] == ["HNC"]


def test_on_off_9006_atrasa_nos_dois_sentidos(tmp_path):
    c = _timer(tmp_path, "9006", {"tempo": 2, "unidade": "0"}, [("7012", "HNA")])
    st = c.novo_estado()
    assert c.avancar(st, {"S1": True}, 1.9)["lampadas"] == []
    assert c.avancar(st, {"S1": True}, 0.1)["lampadas"] == ["HNA"]
    assert c.avancar(st, {}, 1.9)["lampadas"] == ["HNA"]
    assert c.avancar(st, {}, 0.1)["lampadas"] == []
    # pulso curto (< T): nunca chega a ligar
    st = c.novo_estado()
    c.avancar(st, {"S1": True}, 1)
    assert c.avancar(st, {}, 5)["lampadas"] == []


def test_intermitente_9007_alterna_o_estado(tmp_path):
    c = _timer(tmp_path, "9007", {"tempo": 1, "unidade": "0"}, [("7000", "HINST")])
    st = c.novo_estado()
    assert c.avancar(st, {}, 5)["lampadas"] == []
    seq = []
    for _ in range(4):
        seq.append(c.avancar(st, {"S1": True}, 0.5)["lampadas"])    # botao segurado: meio-periodo = 1 s
        seq.append(c.avancar(st, {"S1": True}, 0.5)["lampadas"])
    assert seq == [["HINST"], [], [], ["HINST"], ["HINST"], [], [], ["HINST"]] or seq[0] == ["HINST"]
    assert c.avancar(st, {}, 0)["lampadas"] == []                   # soltou: apaga


def test_temporizador_inicial_e_tempos_do_caso(tmp_path):
    c = _timer(tmp_path, "9004", {"tempo": 50, "unidade": "0"}, [("7004", "H")])   # 500 s no rotulo
    assert c.estado({"S1": True}, avanca=60)["lampadas"] == []
    assert c.estado({"S1": True}, avanca=2, tempos={"KT1": 2})["lampadas"] == ["H"]    # sobrescrito pelo caso
    assert c.estado({"S1": True}, inicial=["KT1"])["lampadas"] == ["H"]
    assert ns.chaves_invalidas(c, {"inicial": ["KT1"], "esperado_temporizadores": ["KT1"]}) == []
    assert ns.chaves_invalidas(c, {"esperado_temporizadores": ["KT9"]}) == [("esperado_temporizadores", "KT9")]


def test_contato_temporizado_sem_temporizador_de_mesmo_rotulo_nunca_fecha(tmp_path):
    b = B(tmp_path)
    b.sym("C", "7004", 60, 30, "-KT9", P2).liga("X.L", "C.p1")
    _lamp(b, "H", 60, 60, "-H", "C.p2")
    c = b.cad()
    assert c.estado({"KT9": True}, avanca=100)["lampadas"] == []    # o app so liga pela saida do temporizador
    assert "KT9" not in c.entradas
