#!/usr/bin/env python3
"""Relatorio de cobertura da bancada: docs/cobertura.md (+ verificado_app em docs/classes-papeis.json).

Entrada: os arquivos da bancada (bancada.construir) e docs/bancada-resultados.json (app/netlist por arquivo).
Saida deterministica: so depende do JSON do RE, da definicao da bancada e dos resultados gravados.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import bancada as B  # noqa: E402

NA_ABAS = {"Desenho (formas)"}
CABOS = {"4000", "4001", "4002", "4003", "4004", "4009", "4010", "4012", "4015", "4016", "4017", "4018", "4019"}
FAMILIAS_NAO_VERIFICAVEIS = {"pneumatica", "plc", "grafcet", "logica", "outro", "sensor"}


def _classes_credito(arq, row, cel_por_id):
    """Classes que ganham credito com a linha: a do elemento + bobina/botao que o comanda + fontes."""
    out = []
    c = cel_por_id.get(row["celula"])
    if c is None:
        return out
    out.append(c["classe"])
    out.append("9008") if c["tipo"] not in ("carga", "motor") else None
    if c["tipo"] == "fonte":
        out += c.get("fontes", [])
    if c["tipo"] == "motor":
        out.append(c["fonte"])
    if c["tipo"] in ("contato",) and c.get("ctrl"):
        for k in arq.celulas:
            if k["tipo"] == "comando" and k["ctrl"] == c["ctrl"]:
                out += [k["classe"], arq.d.ids[k["botao"]].classe]
    return [x for x in out if x]


def rollup(arqs, res):
    """{classe: {'app': {...}, 'netlist': {...}}} com contagens e evidencias."""
    R = defaultdict(lambda: {"app": {"ok": [], "falha": [], "obs": []},
                             "nl": {"ok": [], "falha": []}, "div_app_nl": []})
    obsoletos = []
    for arq in arqs:
        r = res["arquivos"].get(arq.nome)
        if not r:
            continue
        if r.get("assinatura") != B._assinatura(arq):
            obsoletos.append(arq.nome)
            continue
        cel = {c["id"]: c for c in arq.celulas}
        for chave in ("app", "netlist"):
            e = r.get(chave)
            if not e or not e.get("executado"):
                continue
            rows = B.avaliar(arq, e)
            for row in rows:
                for cls in set(_classes_credito(arq, row, cel)):
                    ev = f"{arq.nome}: {row['caso']} / {row['leitura']}"
                    if chave == "app":
                        ok = B.linha_ok(row)
                        d = R[cls]["app"]
                        (d["obs"] if ok is None else d["ok" if ok else "falha"]).append((ev, row))
                    else:
                        ok = B.linha_ok(row)
                        if ok is not None:
                            R[cls]["nl"]["ok" if ok else "falha"].append((ev, row))
    return R, obsoletos


def veredito_app(d):
    if d["falha"]:
        return "divergente"
    if d["ok"]:
        return "sim"
    if d["obs"]:
        return "observado"
    return "nao"


def veredito_nl(d):
    if not d["ok"] and not d["falha"]:
        return None
    if not d["falha"]:
        return "sim"
    return "parcial" if d["ok"] else "nao"


def status_classe(cid, v, R):
    """Texto final da coluna 'verificado no app?' respeitando as exclusoes."""
    aba = v.get("aba", "")
    ver = veredito_app(R[cid]["app"]) if cid in R else "nao"
    if ver != "nao":
        return {"sim": "sim", "divergente": "DIVERGENTE", "observado": "observado"}[ver]
    if aba in NA_ABAS:
        return "n/a (desenho)"
    if cid in CABOS:
        return "indireto" if cid == "4000" else "n/a (cabo)"
    return "nao"


def _modelo_sim(cid, R, tabela):
    nl = veredito_nl(R[cid]["nl"]) if cid in R else None
    if nl == "sim":
        return "sim"
    if nl == "parcial":
        return "parcial"
    if nl == "nao":
        return "nao (diverge)" if cid in tabela else "nao"
    return "so tabela" if cid in tabela else "-"


def gerar(arqs, escrever_json=True):
    cat = B.catalogo()["papeis"]
    res = B.carregar_resultados()
    R, obsoletos = rollup(arqs, res)
    import netlist_sim as N
    tabela = set(N.carregar_papeis())
    protos = B.classes_geraveis()
    pins_dsl = set(json.loads((TOOLS / "symbol_pins.json").read_text()))
    sint = set()
    for a in arqs:
        sint |= a.sinteticas

    def gerador(cid):
        if B.tem_prototipo(cid):
            return "G+D" if cid in pins_dsl else "G"
        if cid in sint:
            return "clone"
        return "-"

    linhas = {}
    por_aba = defaultdict(lambda: defaultdict(int))
    for cid in sorted(cat, key=int):
        v = cat[cid]
        st = status_classe(cid, v, R)
        linhas[cid] = st
        por_aba[v["aba"]]["total"] += 1
        chave = {"sim": "ok", "DIVERGENTE": "div", "observado": "obs", "nao": "nao"}.get(st, "na")
        por_aba[v["aba"]][chave] += 1

    L = []
    w = L.append
    w("# Cobertura da paleta — bancada de teste por classe")
    w("")
    w(f"_Gerado por `python3 tools/bancada.py --relatorio` em {B.DATA}. Fonte dos esperados: "
      "`docs/classes-papeis.json` (RE do binario); medidas no app: `docs/bancada-resultados.json`; "
      "circuitos: `out/bancada/*.cad` (`python3 tools/bancada.py --gerar`)._")
    w("")
    w("Como ler: cada item da paleta e posto em um micro-circuito `fonte -> elemento -> lampada 9008 -> N`; "
      "a lampada acesa prova que o elemento conduz. Contatos sao comandados por bobina/temporizador de mesmo "
      "rotulo; botoes/sensores sao segurados; interruptores/disjuntores/fusiveis/seletores sao clicados. "
      "O esperado e derivado do RE, **nunca** do `netlist_sim`.")
    w("")
    w("Legenda de **app**: `sim` = todas as leituras com esperado do RE bateram; `DIVERGENTE` = ao menos uma "
      "leitura difere do RE (ver secao Divergencias); `observado` = rodou, mas o RE nao da expectativa "
      "(ou a leitura por cor nao e confiavel) — vale como sonda, nao como prova; `nao` = nao testado; "
      "`n/a` = sem comportamento a testar. **gerador**: `G` = cad_build aceita (prototipo no acervo), "
      "`D` = tambem na DSL (symbol_pins), `clone` = so a bancada emite (entidade clonada da familia).")
    w("")
    if obsoletos:
        w(f"> Resultados obsoletos (a bancada mudou desde a execucao; rode `--app`): {', '.join(obsoletos)}")
        w("")
    # resumo por aba
    w("## Resumo por aba")
    w("")
    w("| aba | classes | verificadas (sim) | divergentes | observadas | nao verificadas | n/a ou indireto |")
    w("|---|---:|---:|---:|---:|---:|---:|")
    tot = defaultdict(int)
    for aba in sorted(por_aba):
        d = por_aba[aba]
        w(f"| {aba} | {d['total']} | {d['ok']} | {d['div']} | {d['obs']} | {d['nao']} | {d['na']} |")
        for k in ("total", "ok", "div", "obs", "nao", "na"):
            tot[k] += d[k]
    w(f"| **total** | **{tot['total']}** | **{tot['ok']}** | **{tot['div']}** | **{tot['obs']}** | "
      f"**{tot['nao']}** | **{tot['na']}** |")
    w("")
    # divergencias
    w("## Divergencias (app x RE x simulador)")
    w("")
    div_app = []
    for cid, d in R.items():
        for ev, row in d["app"]["falha"]:
            div_app.append((cid, ev, row))
    corrigidas = _correcoes_registradas()
    if div_app:
        w("### App x RE (correcao do campo semantico: ver `docs/re-engenharia.md` §11.7)")
        w("")
        w("| classe | evidencia | lampada | esperado (RE) | obtido (app) |")
        w("|---|---|---|---|---|")
        vistos = set()
        for cid, ev, row in sorted(div_app, key=lambda t: (int(t[0]), t[1], t[2]["lampada"])):
            k = (cid, ev, row["lampada"])
            if k in vistos:
                continue
            vistos.add(k)
            w(f"| {cid} | {ev} | {row['lampada']} | {row['esperado']} | {row['obtido']} |")
        w("")
    else:
        w("- **App x RE:** nenhuma divergencia nas leituras com esperado "
          f"({sum(len(d['app']['ok']) for d in R.values())} credito(s) classe-leitura conferidos).")
        w("")
    if corrigidas:
        w("### Correcoes ja aplicadas apos teste no app")
        w("")
        for t in corrigidas:
            w(f"- {t}")
        w("")
    w("### Simulador (`netlist_sim`) x RE")
    w("")
    nl_div = sorted((cid for cid, d in R.items() if veredito_nl(d["nl"]) in ("nao", "parcial")), key=int)
    if nl_div:
        w("Classes em que o `netlist_sim` NAO reproduz o esperado do RE (e o app confirma o RE quando "
          "a coluna app diz `sim`):")
        w("")
        w("| classe | nome | app | simulador | exemplo |")
        w("|---|---|---|---|---|")
        for cid in nl_div:
            ex = R[cid]["nl"]["falha"][0]
            w(f"| {cid} | {cat[cid].get('nome')} | {linhas[cid]} | {veredito_nl(R[cid]['nl'])} | "
              f"{ex[0]} ({ex[1]['lampada']}: esperado {ex[1]['esperado']}, simulador {ex[1]['obtido']}) |")
    else:
        w("Sem divergencias (ou `--netlist` ainda nao rodado).")
    w("")
    # matriz
    w("## Matriz por classe")
    w("")
    por_aba_cls = defaultdict(list)
    for cid in sorted(cat, key=int):
        por_aba_cls[cat[cid]["aba"]].append(cid)
    for aba in sorted(por_aba_cls):
        w(f"### {aba}")
        w("")
        w("| classe | nome | pinos (RE) | papel (RE) | conf. RE | simulador | gerador | app | evidencia |")
        w("|---|---|---|---|---|---|---|---|---|")
        for cid in por_aba_cls[aba]:
            v = cat[cid]
            pinos = ",".join(v.get("pinos") or [])
            if len(pinos) > 28:
                pinos = pinos[:26] + "…"
            ev = ""
            if cid in R:
                d = R[cid]["app"]
                pool = d["falha"] or d["ok"] or d["obs"]
                if pool:
                    ev = pool[0][0]
                    if len(pool) > 1:
                        ev += f" (+{len(pool) - 1} leituras)"
            nome = (v.get("nome") or "?").replace("|", "/")
            w(f"| {cid} | {nome} | {pinos or '-'} | {v['papel']} | {v['confianca']} | "
              f"{_modelo_sim(cid, R, tabela)} | {gerador(cid)} | {linhas[cid]} | {ev or '-'} |")
        w("")
    # o que falta
    w("## O que falta (priorizado)")
    w("")
    falta = {"P1": [], "P2": [], "P3": [], "P4": []}
    for cid in sorted(cat, key=int):
        v = cat[cid]
        if linhas[cid] not in ("nao", "observado"):
            continue
        fam = v["papel"]
        if linhas[cid] == "observado":
            falta["P2"].append(cid)
        elif fam in FAMILIAS_NAO_VERIFICAVEIS or v["aba"] in ("PLC (LOGO/S7/ET200/Arduino)", "GRAFCET",
                                                              "Pneumática / atuadores"):
            falta["P4"].append(cid)
        elif v["confianca"] in ("alta", "media"):
            falta["P1"].append(cid)
        else:
            falta["P3"].append(cid)

    def lista(ids):
        return ", ".join(f"{c} ({(cat[c].get('nome') or '?')[:28]})" for c in ids) or "(nenhuma)"
    w("1. **P1 — eletricas de confianca alta/media ainda nao provadas no app:** " + lista(falta["P1"]))
    w("")
    w("2. **P2 — observadas (rodaram, mas o RE nao da expectativa ou a leitura por cor nao e prova; "
      "fechar com expectativa derivada do RE ou leitura funcional):** " + lista(falta["P2"]))
    w("")
    w("3. **P3 — eletricas de baixa confianca (so nome+pinos): sensores 3 fios PNP/NPN, barreiras, "
      "variadores, reles de zocalo, medidores:** " + lista(falta["P3"]))
    w("")
    w("4. **P4 — fora do caminho eletrico do gerador (pneumatica, PLC, GRAFCET, logica/ladder, formas "
      "sem classe definida):** " + lista(falta["P4"]))
    w("")
    w("## Limites da leitura (honestidade)")
    w("")
    w("- Leitura por imagem: so ha vermelho puro (255,0,0) para \"estado ON\"; **contato aberto x fechado** "
      "so aparece via lampada em serie (e por isso o desenho dos testes), nunca pelo contato em si.")
    w("- Motores: \"energizado\" = enchimento cinza 192 do disco (ou vermelho); nao distingue sentido de giro.")
    w("- Cargas diferentes de 9000/9008 (sinalizadores, 8101/8103, temporizadores como carga): a cor de "
      "\"ativo\" nao foi calibrada para elas — entram como **observado**.")
    w("- Temporizadores: tempos medidos com T=4 s e leituras com folga de 4 s; nao e metrologia.")
    w("- Multi-polo: cada polo tem a propria lampada; `6013/6014` e `6017..6020` sem tabela de contatos no RE "
      "viram sonda.")
    text = "\n".join(L) + "\n"
    B.COBERTURA.write_text(text)
    print(f"escrito {B.COBERTURA} ({len(text.splitlines())} linhas); "
          f"sim={tot['ok']} div={tot['div']} obs={tot['obs']} nao={tot['nao']} na={tot['na']} de {tot['total']}")
    if escrever_json:
        atualizar_json(cat, R, linhas)
    return {"linhas": linhas, "R": R}


def _correcoes_registradas():
    """Linhas da secao 11.7 de re-engenharia.md (mantida a mao): so listadas aqui."""
    p = B.ROOT / "docs" / "re-engenharia.md"
    if not p.is_file():
        return []
    out, on = [], False
    for ln in p.read_text().splitlines():
        if ln.startswith("### 11.7"):
            on = True
            continue
        if on and ln.startswith("#"):
            break
        if on and ln.startswith("- "):
            out.append(ln[2:].strip())
    return out


def atualizar_json(cat, R, linhas):
    """Escreve `verificado_app` por classe (so quem foi medido) e sobe confianca p/ alta quando 'sim'."""
    raw = json.loads(B.PAPEIS_JSON.read_text())
    mudou = 0
    for cid, v in raw.items():
        if cid.startswith("_"):
            continue
        st = linhas.get(cid)
        novo = None
        if cid in R and st in ("sim", "DIVERGENTE", "observado"):
            d = R[cid]["app"]
            if st == "sim":
                novo = {"ok": True, "data": B.DATA, "caso": d["ok"][0][0]}
            elif st == "DIVERGENTE":
                ev, row = d["falha"][0]
                novo = {"ok": False, "data": B.DATA, "caso": ev,
                        "detalhe": f"{row['lampada']}: esperado {row['esperado']}, obtido {row['obtido']}"}
            else:
                novo = {"ok": None, "estado": "observado", "data": B.DATA, "caso": d["obs"][0][0]}
        elif st == "indireto":
            novo = {"ok": True, "estado": "indireto", "data": B.DATA, "caso": "usado em todos os micro-circuitos"}
        if novo is None:
            if "verificado_app" in v:
                del v["verificado_app"]
                mudou += 1
            continue
        if v.get("verificado_app") != novo:
            v["verificado_app"] = novo
            mudou += 1
        if novo["ok"] is True and v.get("confianca") != "alta":
            v["confianca"] = "alta"
            mudou += 1
    B.PAPEIS_JSON.write_text(json.dumps(raw, indent=1, ensure_ascii=False) + "\n")
    print(f"classes-papeis.json: {mudou} campo(s) atualizados")
