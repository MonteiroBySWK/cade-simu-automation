#!/usr/bin/env python3
"""Testes das ferramentas MCP de alto nivel (cad_design, cad_gate, cad_pins, cad_examples, cad_preview)
e do harness tools/eval. Chamam as funcoes Python direto (sem subir servidor)."""
import base64
import copy
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "eval"))
import cade_mcp as C  # noqa: E402
import cad_render  # noqa: E402
import run_eval  # noqa: E402

EX = TOOLS / "examples"
NOMES = sorted(f.name[:-len(".layout.json")] for f in EX.glob("*.layout.json"))


def _ex(nome):
    return json.loads(C.cad_example(nome))


def _design(spec, out):
    return json.loads(C.cad_design(json.dumps(spec), str(out)))


# --- exemplos -------------------------------------------------------------

def test_cad_examples_lista_os_layouts():
    r = json.loads(C.cad_examples())
    nomes = {e["nome"] for e in r["exemplos"]}
    assert {"partida_direta", "intercalada"} <= nomes
    assert r["n"] == len(NOMES) + len(list(EX.glob("*.ladder.json")))
    assert {"intercalada.ladder", "partida_sequencial_3.ladder"} <= nomes
    assert all(e["titulo"] for e in r["exemplos"])


def test_cad_example_devolve_json_valido_e_erro_claro():
    d = _ex("partida_direta")
    assert "layout" in d and d["testes"]
    r = json.loads(C.cad_example("nao_existe"))
    assert "erro" in r and "partida_direta" in r["disponiveis"]
    r = json.loads(C.cad_example("../../etc/passwd"))      # path traversal neutralizado
    assert "erro" in r


# --- pinos / simbolos -------------------------------------------------------

def test_cad_pins_contator():
    r = json.loads(C.cad_pins("2001"))
    assert set(r["pinos"]) >= {"1", "2", "3", "4", "5", "6"}
    assert r["pinos"]["3"] == [6, 0]
    assert r["largura"] and r["altura"]
    assert "Contator" in r["nome"]
    assert r["pinos_binario"]          # verdade do binario presente


def test_cad_pins_fonte_3007_e_motor():
    f = json.loads(C.cad_pins("3007"))
    assert list(f["pinos"]) == ["L1", "L2", "L3", "N", "PE"]
    m = json.loads(C.cad_pins("1000"))
    assert set(m["pinos"]) >= {"U1", "V1", "W1", "PE"}


def test_cad_pins_classe_desconhecida_nao_inventa():
    assert "erro" in json.loads(C.cad_pins("99999"))


def test_cad_symbols_traz_nome_quando_documentado():
    itens = {s["classe"]: s for s in json.loads(C.cad_symbols())["simbolos"]}
    assert itens["1000"]["nome"] == "Motor trifasico"
    assert itens["1000"]["largura"] == 24
    outras = [s for s in itens.values() if s["nome"] is None]
    assert outras, "classes sem nome documentado devem vir com nome=null (nao inventado)"


# --- cad_design ---------------------------------------------------------------

@pytest.mark.parametrize("nome", NOMES)
def test_cad_design_passa_o_gate_em_todos_os_exemplos(nome, tmp_path):
    r = _design(_ex(nome), tmp_path / f"{nome}.cad")
    assert r["ok"], r["erros"]
    assert r["gate"]["geo"] == {"curtos": [], "soltos": []}
    assert r["gate"]["testes"]["ok"] and r["gate"]["testes"]["total"]
    assert r["gate"]["fios"]["ok"]
    assert "cad_preview" in r["proximo_passo"]
    assert Path(r["path"]).is_file()


def test_cad_design_aceita_layout_puro_com_testes_dentro(tmp_path):
    d = _ex("partida_direta")
    puro = d["layout"]
    puro["testes"] = d["testes"]
    r = _design(puro, tmp_path / "p.cad")
    assert r["ok"], r["erros"]


def test_cad_design_pe_no_neutro_reprova_com_msg_acionavel(tmp_path):
    d = _ex("partida_direta")
    d["layout"]["fontes"][0]["pinos"]["PE"] = "N"
    r = _design(d, tmp_path / "x.cad")
    assert not r["ok"]
    assert r["gate"]["geo"]["curtos"] and "PE" in r["gate"]["geo"]["curtos"][0]
    assert "trilho PE" in r["gate"]["geo"]["curtos"][0]
    assert r["proximo_passo"].startswith("Corrija o curto")


def test_cad_design_pino_solto_mensagem_acionavel(tmp_path):
    d = _ex("partida_direta")
    del d["layout"]["fontes"][0]["pinos"]["L3"]
    r = _design(d, tmp_path / "x.cad")
    assert not r["ok"]
    msgs = r["gate"]["geo"]["soltos"]
    assert any("pino L3" in m and "fonte" in m and "trilho L3" in m for m in msgs), msgs
    assert "Ligue o pino solto" in r["proximo_passo"]


def test_cad_design_sem_testes_reprova(tmp_path):
    d = _ex("partida_direta")
    d["testes"] = []
    r = _design(d, tmp_path / "x.cad")
    assert not r["ok"]
    assert any("sem testes" in e for e in r["erros"])


def test_cad_design_teste_com_chave_inexistente_nao_e_falso_verde(tmp_path):
    d = _ex("partida_direta")
    d["testes"] = [{"nome": "x", "entradas": {"BOTAO_FANTASMA": True}, "esperado": [], "status": "OK"}]
    r = _design(d, tmp_path / "x.cad")
    assert not r["ok"]
    assert any("BOTAO_FANTASMA" in e and "ROTULO" in e for e in r["erros"])


def test_cad_design_teste_que_falha_aponta_o_caso(tmp_path):
    d = _ex("partida_direta")
    d["testes"][1]["esperado"] = []
    r = _design(d, tmp_path / "x.cad")
    assert not r["ok"]
    assert r["gate"]["testes"]["falhas"][0]["nome"] == "S1 liga KM1"


def test_cad_design_aviso_de_fonte_legada_3004_por_fase(tmp_path):
    d = _ex("partida_direta")
    d["layout"]["fontes"] = [{"id": "X1", "classe": "3004", "rotulo": "-X", "fases": ["L1", "L2", "L3"], "neutro": "N"}]
    r = _design(d, tmp_path / "x.cad")
    assert any("3007" in a for a in r["avisos"]), r["avisos"]
    assert not r["ok"]            # e o gate geometrico pega o desenho legado


def test_cad_design_pe_do_motor_sem_trilho_pe_avisa(tmp_path):
    d = _ex("partida_direta")
    d["layout"]["potencia"][0].pop("pe")
    r = _design(d, tmp_path / "x.cad")
    assert any("PE do motor vai ao neutro" in a for a in r["avisos"]), r["avisos"]


def test_cad_design_layout_invalido_e_json_malformado(tmp_path):
    r = json.loads(C.cad_design("{nao e json", str(tmp_path / "x.cad")))
    assert not r["ok"] and "JSON malformado" in r["erros"][0]
    r = _design({"titulo": "x", "layout": {"fontes": []}}, tmp_path / "y.cad")      # sem 'trilhos'
    assert not r["ok"] and r["erros"][0].startswith("layout invalido")
    assert "layout_json" in r["proximo_passo"]


def test_cad_design_classe_inexistente(tmp_path):
    d = _ex("partida_direta")
    d["layout"]["comando"][0]["serie"][0][1] = "99999"
    r = _design(d, tmp_path / "x.cad")
    assert not r["ok"] and r["erros"]


# --- A11: recusa de classe sem modelo -------------------------------------------------

def _spec_com_classe(classe):
    d = _ex("partida_direta")
    d["layout"]["comando"][0]["serie"].append(["X9", classe, "-X9"])
    return d


def test_cad_design_recusa_pneumatica_10500(tmp_path):
    r = _design(_spec_com_classe("10500"), tmp_path / "p.cad")
    assert not r["ok"]
    assert any("classe 10500" in e and "sem modelo" in e for e in r["erros"]), r["erros"]
    assert any("10500-10599" in e for e in r["erros"])
    assert r["proximo_passo"].startswith("Troque")


def test_cad_design_recusa_9007_e_sensor_7501(tmp_path):
    r = _design(_spec_com_classe("9007"), tmp_path / "t.cad")
    assert not r["ok"]
    assert any("classe 9007" in e and "sem modelo" in e for e in r["erros"]), r["erros"]
    r = _design(_spec_com_classe("7501"), tmp_path / "s.cad")
    assert not r["ok"]
    assert any("classe 7501" in e and "3 fios" in e for e in r["erros"]), r["erros"]


def test_cad_design_recusa_grafcet_ladder_plc_protecao(tmp_path):
    for classe, trecho in (("10100", "GRAFCET"), ("10052", "ladder"),
                           ("10202", "CLP"), ("6015", "protecao")):
        r = _design(_spec_com_classe(classe), tmp_path / f"{classe}.cad")
        assert not r["ok"], classe
        assert any(f"classe {classe}" in e and "sem modelo" in e and trecho in e
                   for e in r["erros"]), (classe, r["erros"])


def test_cad_design_outro_gera_aviso_nao_erro(tmp_path):
    import build_spec
    ev, av = build_spec.conferir_classes_em_spec({"layout": {"comando": [{"serie": [["X", "1072", "-X"]]}]}})
    assert not ev and any("classe 1072" in a for a in av), (ev, av)
    r = _design(_spec_com_classe("1050"), tmp_path / "o.cad")  # resistencia: 2 pinos, compila
    assert any("classe 1050" in a for a in r["avisos"]), (r["avisos"], r["erros"])
    assert not any("classe 1050" in e and "sem modelo" in e for e in r["erros"])


def test_cad_gate_recusa_classe_sem_modelo_mesmo_com_testes_ok(tmp_path):
    d = _ex("partida_direta")
    out = tmp_path / "g.cad"
    assert _design(d, out)["ok"]
    raw = out.read_text(encoding="latin1")
    assert "*9008#-H1" in raw
    ruim = tmp_path / "g9007.cad"
    ruim.write_text(raw.replace("*9008#-H1", "*9007#-H1"), encoding="latin1")
    testes = [{"nome": "S1 liga KM1", "entradas": {"S1": True}, "esperado": ["KM1"], "status": "OK"}]
    r = json.loads(C.cad_gate(str(ruim), json.dumps(testes)))
    assert r["gate"]["testes"]["ok"], r  # o teste funcional passa: o 9007 e ignorado (falso verde)
    assert not r["ok"], r
    assert any("classe 9007" in e and "sem modelo" in e for e in r["erros"]), r["erros"]


def test_cad_design_partida_direta_e_ladder_continuam_verdes(tmp_path):
    assert _design(_ex("partida_direta"), tmp_path / "p.cad")["ok"]
    for nome in ("partida_direta", "reversao", "intercalada",
                 "pratica5_complementar", "partida_sequencial_3"):
        r = _design(_ex(f"{nome}.ladder"), tmp_path / f"{nome}.cad")
        assert r["ok"], (nome, r["erros"])


# --- cad_gate -----------------------------------------------------------------

def test_cad_gate_em_cad_existente(tmp_path):
    d = _ex("partida_direta")
    out = tmp_path / "g.cad"
    assert _design(d, out)["ok"]
    r = json.loads(C.cad_gate(str(out), json.dumps(d["testes"])))
    assert r["ok"] and r["gate"]["testes"]["passaram"] == len(d["testes"])
    # sem casos e sem KM1+KM2: reprova pedindo testes
    r = json.loads(C.cad_gate(str(out)))
    assert not r["ok"] and any("sem testes" in e for e in r["erros"])


def test_cad_gate_pega_pino_solto_e_arquivo_inexistente(tmp_path):
    d = _ex("partida_direta")
    del d["layout"]["fontes"][0]["pinos"]["L2"]
    out = tmp_path / "s.cad"
    _design(d, out)
    r = json.loads(C.cad_gate(str(out), json.dumps(d["testes"])))
    assert not r["ok"] and any("pino L2" in m for m in r["gate"]["geo"]["soltos"])
    r = json.loads(C.cad_gate(str(tmp_path / "nao.cad")))
    assert not r["ok"] and "nao existe" in r["erros"][0]


# --- preview --------------------------------------------------------------------

def _png(uri):
    from PIL import Image
    assert uri.startswith("data:image/png;base64,")
    return Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))).convert("RGB")


def test_cad_preview_png_e_cores_de_fase(tmp_path):
    out = tmp_path / "p.cad"
    assert _design(_ex("partida_direta"), out)["ok"]
    png = tmp_path / "p.png"
    img = _png(C.cad_preview(str(out), 2, str(png)))
    assert png.is_file() and img.size[0] > 400
    cores = {c for _, c in img.getcolors(maxcolors=1 << 20)}
    for fase in ("1", "2", "3", "N", "P"):
        assert cad_render.FASE_COR[fase] in cores, fase
    g = cad_render.analisar_geometria(str(out))
    assert g["n_curtos"] == 0 and not g["soltos"]
    nomes = {p["nome"] for p in g["pinos"] if p["rotulo"] == "-KM1"}
    assert {"1", "3", "5", "2", "4", "6"} <= nomes     # pinos nomeados (nao p1..p6)


def test_cad_preview_sinaliza_solto_e_curto_em_vermelho(tmp_path):
    d = _ex("partida_direta")
    del d["layout"]["fontes"][0]["pinos"]["L3"]
    d["layout"]["fontes"][0]["pinos"]["PE"] = "N"
    out = tmp_path / "r.cad"
    _design(d, out)
    g = cad_render.analisar_geometria(str(out))
    assert g["soltos"] and g["n_curtos"] == 1
    img = _png(C.cad_preview(str(out), 2))
    cores = {c for _, c in img.getcolors(maxcolors=1 << 20)}
    assert cad_render.VERMELHO in cores


def test_exemplos_da_skill_passam_o_gate(tmp_path):
    pasta = TOOLS.parent / "skills" / "automacao-industrial" / "exemplos"
    pares = sorted(pasta.glob("*.layout.json"))
    assert len(pares) >= 2
    for f in pares:
        assert f.with_name(f.name.replace(".layout.json", ".enunciado.txt")).is_file(), f
        r = json.loads(C.cad_design(f.read_text(encoding="utf-8"), str(tmp_path / (f.stem + ".cad"))))
        assert r["ok"], (f.name, r["erros"])


def test_preview_propaga_fase_pelo_contator_e_mostra_inversao(tmp_path):
    out = tmp_path / "r.cad"
    assert _design(_ex("reversao"), out)["ok"]
    g = cad_render.analisar_geometria(str(out))
    assert g["n_curtos"] == 0 and not g["soltos"]
    fases = {f["fase"] for f in g["fios"]}
    assert {"1", "2", "3", "N", "P", None} <= fases     # None = rede com 2 fases propagadas (reversao no motor)


# --- build_spec CLI e eval --------------------------------------------------------

def test_build_spec_cli_continua_funcionando(tmp_path):
    r = subprocess.run([sys.executable, str(TOOLS / "build_spec.py"), str(EX / "partida_direta.layout.json"),
                        str(tmp_path / "c.cad")], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    assert r.returncode == 0 and "GATE: OK" in r.stdout and "RESULTADO: 6/6 OK" in r.stdout


def test_eval_casos_bem_formados():
    casos = run_eval.todos_os_casos()
    assert len(casos) >= 6
    for c in casos:
        assert c["id"] and c["enunciado"] and c["obrigatorios"]
        assert c["golden"] is None or isinstance(c["golden"], str)


def test_eval_golden_pontua_100(tmp_path):
    nada = 0
    for caso in run_eval.todos_os_casos():
        cad = run_eval.construir_golden(caso, tmp_path)
        if cad is None:
            continue
        nada += 1
        r = run_eval.pontuar(cad, caso)
        assert r["total"] == 100.0, (caso["id"], r["detalhes"])
    assert nada >= 5


def test_eval_penaliza_circuito_errado(tmp_path):
    caso = run_eval.carregar_caso("partida_direta")
    d = _ex("partida_direta")
    d["layout"]["fontes"][0]["pinos"]["PE"] = "N"      # curto N x PE
    out = tmp_path / "e.cad"
    _design(d, out)
    r = run_eval.pontuar(out, caso)
    assert r["criterios"]["geometria"] == 0.0 and r["total"] < 100
    assert any("CURTO" in x for x in r["detalhes"]["geometria"])
    # arquivo inexistente / rotulo obrigatorio ausente
    assert run_eval.pontuar(tmp_path / "nao.cad", caso)["total"] == 0.0
    d = _ex("partida_direta")
    d["layout"]["comando"][0]["ramos"][0]["indica"][2] = "-L9"
    out2 = tmp_path / "e2.cad"
    _design(d, out2)
    r2 = run_eval.pontuar(out2, caso)
    assert r2["total"] < 100 and any("-H1" in x for x in r2["detalhes"]["obrigatorios"])


def test_eval_cli_golden(tmp_path):
    r = subprocess.run([sys.executable, str(TOOLS / "eval" / "run_eval.py"), "--golden"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    assert r.returncode == 0, r.stdout[-800:]
    assert "MEDIA" in r.stdout and "partida_direta" in r.stdout


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
