#!/usr/bin/env python3
"""Gera um .cad a partir de uma especificacao JSON, via cad_build, e roda o GATE.

Uso: python3 tools/build_spec.py tools/examples/intercalada.layout.json out/x.cad
     python3 tools/build_spec.py tools/examples/intercalada.layout.json out/x.cad  # DSL topologica

Como biblioteca (usado por cad_design / eval):
    from build_spec import construir
    r = construir(spec_dict, "out/x.cad")   # -> dict {ok, build, testes, geo, fios, avisos, erros, ...}
"""
import json
import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

_FALHA = re.compile(r"\[FALHA\]\s*(?P<nome>.*?):\s*KM=(?P<obtido>\[.*?\])\s*status=(?P<status>\S+)\s*esperado=(?P<esp>\[[^\]]*\]|None)(?P<resto>.*)$")
_PINO_SOLTO = re.compile(r"^(?P<rot>.*)\((?P<classe>\d+)\)\.(?P<pino>[^@]+)@\((?P<x>-?\d+), (?P<y>-?\d+)\)$")
_FONTES = {"3000", "3001", "3003", "3004", "3005", "3006", "3007", "3011"}

# --- A11: classes sem modelo de simulacao (recusa com erro claro, nao falso verde) ------
_LADDER_SEM_MODELO = {"10064", "10065", "10068", "10069", "10075", "10081"}
_TEMP_SEM_MODELO = {"9007", "9015"}
_PROT_SEM_MODELO = {"6015", "6017"}
_PLC_MODELADO = {"10204", "10205", "10206"}
_FIOS_SEM_AVISO = {"4000", "4001", "4009", "4010", "4018", "4019"}  # fio/juncao: geometria pura
_SUPORTADOS = ("contatos 8000/8001/8016/8017, auxiliares 7000/7001, bobinas 9000/9001/9002/9014, "
               "sinalizacao 9008/9009..9013/8101/8103, polos 2000/2001/2002/2006/2008, "
               "protecao 6007/6009/6010, temporizadores 9004/9005/9006 + contatos 7004..7015, "
               "motores, ladder 10050/10051/10052/10053/10060/10061/10062/10066/10067, contador 10063, "
               "CLP 10204/10205/10206, fontes 3000..3012")
_CATALOGO = None


def _catalogo():
    """docs/classes-papeis.json (nome/papel/pinos por classe), com cache."""
    global _CATALOGO
    if _CATALOGO is None:
        try:
            _CATALOGO = json.loads((TOOLS.parent / "docs" / "classes-papeis.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _CATALOGO = {}
    return _CATALOGO


def _motivo_sem_modelo(cid, cat):
    """(nivel, motivo) da classe: nivel em {"erro", "aviso", None}."""
    try:
        n = int(cid)
    except (TypeError, ValueError):
        return None, ""
    papel = str((cat.get("papel") or ""))
    pinos = cat.get("pinos") or []
    if 10500 <= n <= 10599:
        return "erro", "pneumatica (faixa 10500-10599) nao tem modelo (sem pinos no binario)"
    if 10100 <= n <= 10199:
        return "erro", "GRAFCET (faixa 10100-10199) nao tem modelo (sem pinos no binario)"
    if cid in _TEMP_SEM_MODELO:
        return "erro", "temporizador " + cid + " ainda sem modelo (use 9004/9005/9006 + contatos 7004..7015)"
    if cid in _LADDER_SEM_MODELO:
        return "erro", ("instrucao ladder " + cid + " ainda sem modelo "
                        "(use 10050/10051/10052/10053, 10060/10061/10062, TON 10066, TOF 10067 ou CTU 10063)")
    if papel.startswith("sensor") and len(pinos) >= 3:
        return "erro", ("sensor 3 fios (PNP/NPN) ainda sem modelo: precisa de alimentacao + saida "
                        "(use botoeira 8000/8001 como placeholder da deteccao)")
    if (papel == "plc" or 10200 <= n <= 10299) and cid not in _PLC_MODELADO:
        return "erro", ("CLP com imagem sem modelo: so CPU 10206 + I/O 10204/10205 sao simulados "
                        "(troque por eles ou desenhe a logica em rele)")
    if cid in _PROT_SEM_MODELO:
        return "erro", ("protecao sem modelo "
                        "(use disjuntor 6002/6003/6009/6010, termico 6007 ou fusivel 5000..5004)")
    if papel == "outro" and cid not in _FIOS_SEM_AVISO:
        return "aviso", "sem modelo: ignorada nos testes; confira o comportamento no app (Play) antes de entregar"
    return None, ""


def _msg_sem_modelo(cid, nome, motivo):
    return (f"classe {cid} ({nome}) sem modelo de simulacao: {motivo}. "
            f"O gate simula: {_SUPORTADOS}. "
            f"Alternativas: simplificar para componentes suportados, montar com cad_build "
            f"validando por fora, ou pedir suporte a classe")


def conferir_classes_sem_modelo(path):
    """Classes do .cad sem modelo funcional (A11). Erro no conjunto curado, aviso no resto.
    Retorna (erros, avisos)."""
    from dissect import parse_ent, split_all
    try:
        _, ents, _ = split_all(Path(path).read_bytes().decode("latin1"))
    except (OSError, ValueError):
        return [], []
    cat = _catalogo()
    vistos, erros, avisos = [], [], []
    for p in map(parse_ent, ents):
        if not p:
            continue
        cid = str(p["id"])
        if cid in vistos:
            continue
        vistos.append(cid)
        info = cat.get(cid) or {}
        nivel, motivo = _motivo_sem_modelo(cid, info)
        if not nivel:
            continue
        nome = info.get("nome") or "sem nome no catalogo"
        (erros if nivel == "erro" else avisos).append(_msg_sem_modelo(cid, nome, motivo))
    return erros, avisos


def _classes_da_spec(spec):
    """Todas as classes citadas numa spec (layout topologico OU spec baixa), sem repetir."""
    achadas = []

    def ver(cid):
        cid = str(cid)
        if cid.isdigit() and cid not in achadas:
            achadas.append(cid)

    def varrer(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "classe" and isinstance(v, str) and v.isdigit():
                    ver(v)
                else:
                    varrer(v)
        elif isinstance(o, list):
            if len(o) >= 2 and isinstance(o[0], str) and isinstance(o[1], str) and o[1].isdigit():
                ver(o[1])  # item [id, classe, rotulo?] de serie/coluna/ramo
            for v in o:
                varrer(v)

    varrer(spec)
    return achadas


def conferir_classes_em_spec(spec):
    """A11 sobre a spec ainda nao compilada (pega 10500 etc. mesmo sem geometria)."""
    cat = _catalogo()
    erros, avisos = [], []
    for cid in _classes_da_spec(spec if isinstance(spec, dict) else {}):
        nivel, motivo = _motivo_sem_modelo(cid, cat.get(cid) or {})
        if not nivel:
            continue
        nome = (cat.get(cid) or {}).get("nome") or "sem nome no catalogo"
        (erros if nivel == "erro" else avisos).append(_msg_sem_modelo(cid, nome, motivo))
    return erros, avisos


def normalizar(spec):
    """spec (layout topologico OU spec baixa, com/sem chave "layout") -> (baixa, testes, layout|None)."""
    if not isinstance(spec, dict):
        raise ValueError("a spec deve ser um objeto JSON")
    layout_d = spec.get("layout")
    testes = spec.get("testes") or (layout_d or {}).get("testes") or []
    if layout_d is None and "simbolos" not in spec and "trilhos" in spec:
        layout_d = spec            # layout "puro" (sem o envelope {"layout":...})
        testes = spec.get("testes") or []
    if layout_d is not None:
        import layout  # motor de layout: spec topologica -> spec baixa
        low = layout.compilar(layout_d)
        low.setdefault("titulo", spec.get("titulo") or layout_d.get("titulo") or "NOVO")
        if spec.get("titulo"):
            low["titulo"] = spec["titulo"]
        return low, testes, layout_d
    if "simbolos" not in spec:
        raise ValueError("spec sem 'layout' (DSL topologica) nem 'simbolos' (spec baixa)")
    return spec, testes, None


def _classes_da_coluna(c):
    """Classes de um item de coluna: [id,cls,rot,...] ou {"paralelo":[item,...]} (reversao)."""
    if isinstance(c, dict):
        out = []
        for m in c.get("paralelo", []):
            out += _classes_da_coluna(m)
        return out
    return [str(c[1])] if isinstance(c, (list, tuple)) and len(c) > 1 else []


def lint_layout(layout_d, low=None):
    """Avisos de AUTORIA (erros comuns) sobre o layout topologico, antes do build."""
    av = []
    if not layout_d:
        return av
    pins = json.loads((TOOLS / "symbol_pins.json").read_text(encoding="utf-8"))
    trilhos = {k: v for k, v in layout_d.get("trilhos", {}).items() if k not in ("x0", "x1")}
    for nome in (layout_d.get("trilhos_comando") or {}).get("nomes", []):
        trilhos.setdefault(nome, None)            # trilhos de comando (C1/C2) tambem valem
    for f in layout_d.get("fontes", []):
        if not f.get("pinos") and len(f.get("fases") or []) > 1:
            av.append(f"fonte {f.get('classe', '3004')} por fase ({f.get('id')}): desenho legado que gera "
                      f"curto N x PE e fase solta. Use UMA fonte 3007: "
                      f"{{\"id\":\"X1\",\"classe\":\"3007\",\"rotulo\":\"-X\",\"pinos\":{{\"L1\":\"L1\",\"L2\":\"L2\","
                      f"\"L3\":\"L3\",\"N\":\"N\",\"PE\":\"PE\"}}}}")
    for g in layout_d.get("potencia", []):
        classes = [cl for c in g.get("colunas", []) for cl in _classes_da_coluna(c)]
        tem_pe = any("PE" in ((pins.get(cl, {}).get("pins")) or {}) or cl in ("1002", "1008", "1010")
                    for cl in classes)
        if tem_pe:
            if not g.get("pe") or g.get("pe") == g.get("neutro", "N"):
                av.append(f"potencia '{g.get('id')}': o PE do motor vai ao neutro (curto N x PE). Declare um "
                          f"trilho \"PE\" em 'trilhos' e \"pe\":\"PE\" no grupo.")
            elif g.get("pe") not in trilhos:
                av.append(f"potencia '{g.get('id')}': \"pe\":\"{g['pe']}\" nao existe em 'trilhos'.")
    for b in layout_d.get("comando", []):
        for k in ("de", "para"):
            if b.get(k) not in trilhos:
                av.append(f"comando '{b.get('id')}': '{k}'='{b.get(k)}' nao e um trilho (trilhos: {sorted(trilhos)}).")
    return av


def _parse_testes(saida):
    """Texto do cad_test -> (passaram, total, [falhas estruturadas])."""
    falhas = []
    for ln in saida.splitlines():
        if "[FALHA]" in ln:
            m = _FALHA.search(ln.strip())
            falhas.append(m.groupdict() if m else {"nome": ln.strip()})
    m = re.search(r"RESULTADO:\s*(\d+)/(\d+)", saida)
    return (int(m.group(1)), int(m.group(2))) if m else (None, None), falhas


def conferir_chaves_de_teste(path, testes):
    """Chaves de entradas/inicial/esperado*/passos que nao existem no circuito (teste vacuo = falso verde)."""
    if not testes:
        return []
    import netlist_sim as ns
    c = ns.Circuito(path)
    erros = []
    for cs in testes:
        for campo, k in ns.chaves_invalidas(c, cs):
            nome = cs.get("nome", "?")
            if campo == "entradas":
                erros.append(f"teste '{nome}': entrada '{k}' nao existe no circuito "
                             f"(entradas validas: {sorted(c.entradas)}; bobinas: {sorted(c.bobinas)}). "
                             f"A chave e o ROTULO do simbolo sem o '-' (ex.: '-S1' -> 'S1').")
            elif campo == "esperado_lampadas":
                erros.append(f"teste '{nome}': '{campo}' cita '{k}', que nao e lampada "
                             f"(lampadas: {sorted(c.lampadas)}; use o rotulo sem '-', ex.: '-H1' -> 'H1').")
            elif campo == "esperado_temporizadores":
                erros.append(f"teste '{nome}': '{campo}' cita '{k}', que nao e contato temporizado "
                             f"(temporizadores: {sorted(c._timers())}).")
            else:
                erros.append(f"teste '{nome}': '{campo}' cita '{k}', que nao e bobina "
                             f"(bobinas: {sorted(c.bobinas)}).")
    return erros


def acionavel_solto(s):
    """'-X(3007).L3@(30, 20)' -> mensagem com o que fazer."""
    m = _PINO_SOLTO.match(s)
    if not m:
        return f"pino solto: {s}"
    rot, cid, pino, x, y = m["rot"], m["classe"], m["pino"], m["x"], m["y"]
    if cid in _FONTES:
        return (f"pino {pino} da fonte {rot} ({cid}) solto em ({x},{y}): ligue-o ao trilho "
                f"{pino} (fontes: {{\"pinos\":{{\"{pino}\":\"{pino}\"}}}}; cada pino da fonte vai a um trilho)")
    if cid == "1000":
        return (f"pino {pino} do motor {rot} solto em ({x},{y}): ligue TODOS os terminais "
                f"(U1/V1/W1 as fases, PE ao trilho PE) — use potencia.colunas com fases e \"pe\":\"PE\"")
    return (f"pino {pino} de {rot} ({cid}) solto em ({x},{y}): nenhum fio termina nesse ponto; "
            f"ligue o pino (conexao de/para) ou remova o simbolo")


def acionavel_curto(c):
    """'1+N na mesma net: ...' -> mensagem."""
    dica = ""
    if "N" in c and "P" in c:
        dica = " — PE ligado ao neutro: crie trilho PE separado (\"pe\":\"PE\")"
    elif "1" in c or "2" in c or "3" in c:
        dica = " — duas fases no mesmo no: confira trilhos L1/L2/L3 e a coluna de cada fase"
    return f"CURTO {c}{dica}"


def conferir_vinculos(path):
    """Vinculos por ROTULO que o app usa (achado do app_sim): contato 8016..8019 so segue um 6007
    (termico) de MESMO rotulo; auxiliares 7000/7001 e polos 2001 so seguem bobina 9xxx de mesmo
    rotulo. Retorna (erros, avisos)."""
    from dissect import parse_ent, split_all
    _, ents, _ = split_all(Path(path).read_bytes().decode("latin1"))
    ps = [p for p in map(parse_ent, ents) if p]
    rot = lambda p: ((p["labels"] or [""])[0]).strip()
    termicos = {rot(p) for p in ps if p["id"] in ("6007", "6002", "6003", "6004", "6009", "6010")}   # termico OU disjuntor (DJ1)
    bobinas = {rot(p) for p in ps if p["id"] in ("9000", "9001", "9002", "9004", "9005", "9006", "9007",
                                                  "9014", "9015", "10060")}
    erros, avisos = [], []
    for p in ps:
        r = rot(p)
        if p["id"] in ("8016", "8017", "8018", "8019") and r not in termicos:
            erros.append(f"contato termico {r or p['id']} ({p['id']}) nao segue nenhum rele termico 6007 de "
                         f"mesmo rotulo (6007: {sorted(termicos) or 'nenhum'}): no app o termico NUNCA dispara. "
                         f"Use o MESMO rotulo no 6007 e no contato 95-96.")
        if p["id"] in ("7000", "7001", "2001", "2002") and r and r not in bobinas:
            avisos.append(f"{p['id']} {r}: nenhuma bobina de mesmo rotulo (contato nunca e comandado)")
    return erros, avisos


def gate(path, testes, r=None):
    """Gate sobre um .cad ja gerado: testes funcionais + geo_check + wires_check. Preenche `r`
    (dict no formato de construir) e o devolve. Nao reconstroi o arquivo."""
    import cade_mcp
    import geo_check
    import wires_check
    if r is None:
        r = {"testes": {}, "geo": {}, "fios": {}, "avisos": [], "erros": [], "_teste_raw": ""}
    r.setdefault("sem_modelo", [])
    evm, avm = conferir_classes_sem_modelo(str(path))   # A11: recusa classe sem modelo
    r["erros"] += evm
    r["avisos"] += avm
    r["sem_modelo"] = list(evm)
    import clp_sim
    if clp_sim.tem_clp(str(path)):               # arquivo com CLP/ladder: modelo geometrico por ticks
        import ladder_dsl
        ladder_dsl.gate_clp(path, {"testes": testes}, r)
        r["fios"] = {"ok": True, "n": 0, "atravessam": []}
        return r
    out = path
    res_geo = geo_check.analisar(str(out))      # (curtos, soltos[, ...]) — tolera campos extras
    curtos, soltos = res_geo[0], res_geo[1]
    r["geo"] = {"curtos": curtos, "soltos": soltos,
                "curtos_msg": [acionavel_curto(c) for c in curtos],
                "soltos_msg": [acionavel_solto(s) for s in soltos]}
    r["erros"] += r["geo"]["curtos_msg"] + r["geo"]["soltos_msg"]

    ev, av = conferir_vinculos(str(out))
    r["erros"] += ev
    r["avisos"] += av

    # sem casos declarados, cad_test usa a suite embutida (so vale p/ circuito com KM1 e KM2)
    teste = cade_mcp.cad_test(str(out), json.dumps(testes))
    r["_teste_raw"] = teste
    (pas, tot), falhas = _parse_testes(teste)
    chaves = conferir_chaves_de_teste(str(out), testes) if testes else []
    r["testes"] = {"ok": teste.startswith("PASSOU") and not chaves, "passaram": pas, "total": tot,
                   "falhas": falhas, "saida": teste}
    if teste.startswith("SEM_TESTES"):
        r["erros"].append("sem testes: declare \"testes\" (casos {nome, entradas, inicial, esperado, status}); "
                          "sem eles o circuito nao tem prova funcional")
    for f in falhas:
        r["erros"].append("teste falhou: " + (f"{f.get('nome')} -> obtido {f.get('obtido')} "
                          f"status={f.get('status')}, esperado {f.get('esp')}" if "obtido" in f else f["nome"]))
    for c in chaves:
        r["erros"].append(c)
    if testes and not teste.startswith("PASSOU") and not falhas:
        r["erros"].append(f"testes: {teste.splitlines()[0]}")

    n, ruins = wires_check.analisar(str(out))
    r["fios"] = {"ok": not ruins, "n": n,
                 "atravessam": [f"fio {a}->{b} atravessa o simbolo {nome}" for nome, a, b in ruins]}
    if ruins:
        r["avisos"].append(f"{len(ruins)} trecho(s) de fio atravessam simbolo (estetico): "
                           + "; ".join(r["fios"]["atravessam"][:3]))
    return r


def construir(spec, out):
    """Compila (se for DSL), gera o .cad via cad_build e roda o gate completo.

    Retorno: dict {ok, path, titulo, build:{ok,mensagem}, testes:{ok,passaram,total,falhas,saida},
                   geo:{curtos,soltos,curtos_msg,soltos_msg}, fios:{ok,n,atravessam},
                   avisos:[...], erros:[...], n_simbolos, _build_raw, _teste_raw}.
    `ok` = build ok E testes passam E sem curto/pino solto (fios = aviso estetico, nao bloqueia)."""
    if isinstance(spec, dict) and (spec.get("dsl") == "ladder/1" or ((spec.get("layout") or {}).get("clp"))):
        import ladder_dsl                          # CLP + ladder: gerador/gate proprio
        return ladder_dsl.construir(spec, out)
    import cade_mcp
    r = {"ok": False, "path": str(out), "titulo": None,
         "build": {"ok": False, "mensagem": ""},
         "testes": {"ok": False, "passaram": None, "total": None, "falhas": [], "saida": ""},
         "geo": {"curtos": [], "soltos": [], "curtos_msg": [], "soltos_msg": []},
         "fios": {"ok": None, "n": 0, "atravessam": []},
         "avisos": [], "erros": [], "_build_raw": "", "_teste_raw": "", "sem_modelo": []}
    if isinstance(spec, dict):
        evs, avs = conferir_classes_em_spec(spec)   # A11: barra antes de compilar
        r["erros"] += evs
        r["avisos"] += avs
        r["sem_modelo"] = list(evs)
        if evs:
            r["ok"] = False
            return r
    try:
        low, testes, layout_d = normalizar(spec)
    except (ValueError, KeyError, TypeError) as e:
        msg = f"campo obrigatorio ausente: {e}" if isinstance(e, KeyError) else str(e)
        r["erros"].append(f"layout invalido: {msg}")
        return r
    r["titulo"] = low.get("titulo")
    r["n_simbolos"] = len(low.get("simbolos", []))
    r["avisos"] += lint_layout(layout_d, low)

    res = cade_mcp.cad_build(
        titulo=low.get("titulo", "NOVO"),
        simbolos_json=json.dumps(low["simbolos"]),
        conexoes_json=json.dumps(low.get("conexoes", [])),
        fios_json=json.dumps(low.get("fios", [])),
        rails_json=json.dumps(low.get("rails", [])),
        out_path=str(out))
    r["_build_raw"] = res
    r["build"] = {"ok": ("AVISO" not in res and "ERRO" not in res and "OK" in res), "mensagem": res}
    if "ERRO" in res:
        r["erros"].append(f"build: {res}")
    if "AVISO" in res:
        r["erros"].append(f"build: {res} — um simbolo ficou com os dois pinos no mesmo no (curto); "
                          f"revise as conexoes do simbolo citado")
    if "ERRO" in res:
        return r

    g = gate(str(out), testes, r)
    r["ok"] = bool(r["build"]["ok"] and g["testes"]["ok"] and not r["geo"]["curtos"]
                   and not r["geo"]["soltos"] and not r.get("sem_modelo"))
    return r


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    spec = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    if argv[0].endswith(".layout.json") and "layout" not in spec and "simbolos" not in spec:
        spec = {"layout": spec}
    r = construir(spec, argv[1])
    if r["erros"] and not r["_build_raw"]:
        print("ERRO:", "; ".join(r["erros"]))
        print("GATE: REPROVADO (corrija antes de seguir)")
        return 1
    print(r["_build_raw"])
    print(r["_teste_raw"])
    for c in r["geo"]["curtos"]:
        print("CURTO:", c)
    for sl in r["geo"]["soltos"]:
        print("SOLTO:", sl)
    for e in r["erros"]:
        if e.startswith("teste ") or e.startswith("sem testes") or e.startswith("classe "):
            print("ERRO:", e)
    if not r["ok"]:
        print("GATE: REPROVADO (corrija antes de seguir)")
        return 1
    print("GATE: OK (validado, sem curto/fase cruzada/pino solto, testes passando)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
