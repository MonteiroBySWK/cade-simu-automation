#!/usr/bin/env python3
"""Testes da bancada de classes (tools/bancada.py) — geracao e esperados, SEM Wine.

O teste no app (Wine) e opcional: BANCADA_WINE=1 pytest tools/test_bancada.py -k wine
"""
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import bancada as B  # noqa: E402
import geo_check  # noqa: E402

CLI = TOOLS.parent / "src" / "cade_cli" / "target" / "debug" / "cade_cli"


@pytest.fixture(scope="module")
def arqs(tmp_path_factory):
    old = B.SAIDA
    B.SAIDA = tmp_path_factory.mktemp("bancada")
    try:
        yield B.construir(gerar=True)
    finally:
        B.SAIDA = old


# --- catalogo / expectativas derivadas do RE -------------------------------------------------------

def test_acende_par_segue_o_re():
    assert B.acende_par("1", "N") and B.acende_par("N", "1")
    assert B.acende_par("1", "2") and B.acende_par("3", "1")
    assert B.acende_par("+", "-") and B.acende_par("-", "+") and B.acende_par("+", "N")
    assert not B.acende_par("1", "1")
    assert not B.acende_par("1", "P") and not B.acende_par("N", "P")
    assert not B.acende_par("-", "N") and not B.acende_par(None, "N")


def test_contatos_pelo_json_do_re():
    # NA fecha em estado 1; NC em 0; comutado 11-12 em 0 e 11-14 em 1; 6007 sempre conduz
    assert B.lampadas_acesas("7000", 0) == set() and B.lampadas_acesas("7000", 1) == {"p2"}
    assert B.lampadas_acesas("7001", 0) == {"p2"} and B.lampadas_acesas("7001", 1) == set()
    pins = B.pinos_bin("7003")
    assert len(pins) == 3
    nomes = list(pins)
    assert B.lampadas_acesas("7003", 0) == {nomes[1]}      # 11-12
    assert B.lampadas_acesas("7003", 1) == {nomes[2]}      # 11-14
    assert len(B.lampadas_acesas("6007", 0)) == 3 == len(B.lampadas_acesas("6007", 1))
    assert B.lampadas_acesas("2001", 0) == set() and len(B.lampadas_acesas("2001", 1)) == 3
    assert B.lampadas_acesas("5000", 0) and not B.lampadas_acesas("5000", 1)      # fusivel integro conduz


def test_mapa_pinos_usa_ordem_de_desenho():
    mp = B.mapa_pinos("3005")
    assert mp == {"L1": "L1", "L2": "L2", "L3": "L3", "PE": "PE"} or list(mp) == ["L1", "L2", "L3", "PE"]
    assert B.mapa_pinos("6015") is None                    # nomes duplicados: sem mapa


def test_temporizado_le_a_saida():
    assert B.eh_temporizado("7004") and not B.eh_temporizado("7000")


# --- geracao ----------------------------------------------------------------------------------------

def test_todos_os_arquivos_gerados_e_sem_curto(arqs):
    assert len(arqs) >= 15
    for a in arqs:
        assert a.cad_path().is_file(), a.nome
        curtos, _ = geo_check.analisar(str(a.cad_path()))
        assert curtos == [], f"{a.nome}: {curtos}"


def test_pinos_de_lampada_e_comando_nao_ficam_soltos(arqs):
    obrig = {"9008", "9000", "8000"}
    for a in arqs:
        _, soltos = geo_check.analisar(str(a.cad_path()))
        for s in soltos:
            classe = s.split("(")[1].split(")")[0]
            assert classe not in obrig, f"{a.nome}: {s}"


def test_celulas_dut_tem_todos_os_pinos_ligados(arqs):
    """Contatos/botoes/interruptores: topo em L e cada base numa lampada => nenhum pino solto."""
    for a in arqs:
        _, soltos = geo_check.analisar(str(a.cad_path()))
        ids = {c["rotulo"] for c in a.celulas if c["tipo"] in ("contato", "momentaneo", "alterna", "termico")}
        for s in soltos:
            assert s.split("(")[0] not in ids, f"{a.nome}: {s}"


def test_geracao_deterministica(arqs, tmp_path):
    a = arqs[0]
    antes = a.cad_path().read_bytes()
    b = B.Arquivo(a.nome)
    assert antes == a.cad_path().read_bytes()
    assert b.nome == a.nome


def test_rotulos_de_lampada_unicos_e_casos_referenciam_ids(arqs):
    for a in arqs:
        rots = [s.rotulo for s in a.d.simbolos if s.classe == "9008" and s.id.startswith("H")]
        assert len(rots) == len(set(rots))
        for c in a.casos:
            for p in c.passos:
                if p[0] in ("segurar", "clicar"):
                    assert p[1] in a.d.ids, f"{a.nome}: {p}"
                assert p[0] in ("segurar", "soltar", "clicar", "esperar", "ler")
        assert a.casos, a.nome


def test_esperado_referencia_lampadas_existentes(arqs):
    for a in arqs:
        for caso in a.casos:
            for p in caso.passos:
                if p[0] != "ler":
                    continue
                esp = B.esperado_leitura(a, p[2])
                assert set(esp) <= set(a.lampadas), (a.nome, set(esp) - set(a.lampadas))


def test_contato_comandado_segue_a_bobina_no_esperado(arqs):
    a = next(x for x in arqs if x.nome == "contatos_01")
    on = B.esperado_leitura(a, {"-K1": 1})
    off = B.esperado_leitura(a, {"-K1": 0})
    cel = {c["classe"]: c for c in a.celulas if c["tipo"] == "contato"}
    na = cel["7000"]["lamps"]["p2"]
    nc = cel["7001"]["lamps"]["p2"]
    assert (off[na], on[na]) == (False, True)
    assert (off[nc], on[nc]) == (True, False)
    for lab in cel["2001"]["lamps"].values():          # polos do contator
        assert (off[lab], on[lab]) == (False, True)


def test_termico_outro_rotulo_nao_acompanha(arqs):
    a = next(x for x in arqs if x.nome == "termico_01")
    esp = B.esperado_leitura(a, {"-F1": 1, "-F9": 0})
    f9 = next(c for c in a.celulas if c["rotulo"] == "-F9")
    f1_nc = next(c for c in a.celulas if c["classe"] == "8017" and c["rotulo"] == "-F1")
    assert esp[f9["lamps"]["p2"]] is True              # 8017 de outro rotulo segue fechado
    assert esp[f1_nc["lamps"]["p2"]] is False          # disparado abre o NC


def test_temporizador_on_delay_usa_saida(arqs):
    a = next(x for x in arqs if x.nome.startswith("temporizadores") and
             any(c["classe"] == "9004" for c in a.celulas))
    k = next(c for c in a.celulas if c["tipo"] == "comando" and c["classe"] == "9004")["ctrl"]
    t = next(c for c in a.celulas if c["classe"] == "7004")
    lab = t["lamps"]["p2"]
    assert B.esperado_leitura(a, {k: 1, f"{k}.saida": 0})[lab] is False
    assert B.esperado_leitura(a, {k: 1, f"{k}.saida": 1})[lab] is True
    inst = next(c for c in a.celulas if c["classe"] == "7000" and c["ctrl"] == k)
    assert B.esperado_leitura(a, {k: 1, f"{k}.saida": 0})[inst["lamps"]["p2"]] is True


def test_alternadores_ciclo_de_estados(arqs):
    assert [B.estado_apos("8008", n) for n in (0, 1, 2, 3)] == [0, 1, 0, 1]
    assert [B.estado_apos("8021", n) for n in (0, 1, 2, 3)] == [0, 1, 2, 0]


def test_fontes_esperam_so_pares_validos(arqs):
    fs = [c for a in arqs for c in a.celulas if c["tipo"] == "fonte"]
    assert fs
    for c in fs:
        assert c["fixo"] == B.acende_par(*c["chars"])
    assert any(not c["fixo"] for c in fs) and any(c["fixo"] for c in fs)   # ha controle negativo


def test_cobertura_minima_da_bancada(arqs):
    todas = set().union(*(a.classes for a in arqs))
    essenciais = {"9000", "9008", "8000", "8001", "7000", "7001", "7002", "7003", "2001", "6007", "6009",
                  "9004", "9005", "9006", "9007", "3000", "3001", "3003", "3004", "3010", "1000",
                  "5000", "8016", "8017", "7004", "7008", "7012"}
    assert essenciais <= todas, essenciais - todas
    assert len(todas) >= 100


def test_cad_valido_no_cli(arqs):
    if not CLI.is_file():
        pytest.skip("cade_cli nao compilado")
    import subprocess
    for a in arqs[:3]:
        r = subprocess.run([str(CLI), "validate", str(a.cad_path())], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr


# --- netlist e relatorio (sem Wine) -----------------------------------------------------------------

def test_netlist_executa_nos_mesmos_casos(arqs):
    a = next(x for x in arqs if x.nome == "fontes_01")
    r = B.executar_netlist(a)
    assert r["executado"], r["erro"]
    assert len(r["casos"]) == len(a.casos)


def test_avaliar_e_linha_ok(arqs):
    a = next(x for x in arqs if x.nome == "contatos_01")
    # resultado "perfeito" sintetico: lampadas = esperado -> nenhuma falha
    casos = []
    for c in a.casos:
        lei = []
        for p in c.passos:
            if p[0] == "ler":
                esp = B.esperado_leitura(a, p[2])
                lei.append({"nome": p[1], "obtido": [k for k, v in esp.items() if v]})
        casos.append({"nome": c.nome, "leituras": lei})
    rows = B.avaliar(a, {"casos": casos})
    assert rows and all(B.linha_ok(r) is True for r in rows)
    casos[1]["leituras"][0]["obtido"] = []          # app "nao acendeu nada" com a bobina ligada
    rows = B.avaliar(a, {"casos": casos})
    assert any(B.linha_ok(r) is False for r in rows)


def test_relatorio_gera_markdown_e_json_sem_tocar_nos_reais(arqs, tmp_path, monkeypatch):
    import bancada_relatorio as R
    cob = tmp_path / "cobertura.md"
    pj = tmp_path / "classes-papeis.json"
    pj.write_text(B.PAPEIS_JSON.read_text())
    res = tmp_path / "res.json"
    monkeypatch.setattr(B, "COBERTURA", cob)
    monkeypatch.setattr(B, "PAPEIS_JSON", pj)
    monkeypatch.setattr(B, "RESULTADOS", res)
    B._CAT.clear()
    try:
        # resultado perfeito para o arquivo de contatos
        a = next(x for x in arqs if x.nome == "contatos_01")
        casos = []
        for c in a.casos:
            lei = []
            for p in c.passos:
                if p[0] == "ler":
                    esp = B.esperado_leitura(a, p[2])
                    lei.append({"nome": p[1], "obtido": [k for k, v in esp.items() if v]})
            casos.append({"nome": c.nome, "leituras": lei})
        r = {"data": B.DATA, "arquivos": {}}
        B.registrar(r, a, "app", {"executado": True, "casos": casos, "tempo_s": 1})
        B.salvar_resultados(r)
        out = R.gerar(arqs, escrever_json=True)
        texto = cob.read_text()
        assert "## Resumo por aba" in texto and "## Matriz por classe" in texto and "## O que falta" in texto
        assert out["linhas"]["7000"] == "sim" and out["linhas"]["2001"] == "sim"
        assert out["linhas"]["9000"] == "sim"          # bobina creditada pelo contato que ela comanda
        assert out["linhas"]["10500"] == "nao"
        d = json.loads(pj.read_text())
        assert d["7000"]["verificado_app"]["ok"] is True and d["7000"]["confianca"] == "alta"
        assert "verificado_app" not in d["10500"]
    finally:
        B._CAT.clear()


# --- opcional: Wine ---------------------------------------------------------------------------------

@pytest.mark.skipif(not os.environ.get("BANCADA_WINE") or not shutil.which("xdotool"),
                    reason="defina BANCADA_WINE=1 (precisa de DISPLAY, wine e CADe_SIMU)")
def test_wine_fontes_no_app(arqs):
    a = next(x for x in arqs if x.nome == "fontes_01")
    ex = B.executar_app(a)
    assert ex["executado"], ex["erro"]
    assert all(B.linha_ok(r) is True for r in B.avaliar(a, ex))
