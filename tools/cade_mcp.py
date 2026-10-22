#!/usr/bin/env python3
import os
"""Servidor MCP do cade-simu-automation (stdio).

Expõe o .cad para qualquer agente (Claude Code, OpenCode, etc.):
  validate, parse, emit/new, inspect, rungs, preview (imagem), text_to_cad.

Setup:  uv venv tools/.venv-mcp && uv pip install --python tools/.venv-mcp/bin/python mcp pillow numpy
Uso no cliente MCP (ex. claude mcp add):  tools/.venv-mcp/bin/python tools/cade_mcp.py
"""
import base64
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dissect import parse_ent, split_entities  # noqa: E402

try:
    from mcp.server.fastmcp import FastMCP  # noqa: E402
except ImportError:  # sem o pacote `mcp` (ex.: pytest no python do sistema): ferramentas viram funcoes comuns
    class FastMCP:  # type: ignore[no-redef]
        def __init__(self, *_a, **_k):
            pass

        def tool(self, *_a, **_k):
            return lambda fn: fn

        def run(self):
            raise SystemExit("pacote 'mcp' ausente: use tools/.venv-mcp/bin/python tools/cade_mcp.py")

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "src" / "cade_cli" / "target" / "debug" / "cade_cli"

mcp = FastMCP("cade-simu")


def _run(*args):
    r = subprocess.run([str(CLI), *args], capture_output=True, text=True, timeout=60)
    return r.returncode, (r.stdout.strip() or r.stderr.strip())


@mcp.tool()
def cad_validate(path: str) -> str:
    """Valida um .cad (header + seção $$$). Retorna modo/versão ou o erro."""
    code, out = _run("validate", path)
    return ("OK " if code == 0 else "ERRO ") + out


@mcp.tool()
def cad_parse(path: str) -> str:
    """Converte .cad em cade.json (meta + tokens byte-fiéis). Retorna o JSON."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as t:
        tmp = t.name
    code, out = _run("parse", path, "-o", tmp)
    if code != 0:
        return "ERRO " + out
    return Path(tmp).read_text(encoding="utf-8")


@mcp.tool()
def cad_emit(cade_json: str, out_path: str) -> str:
    """Gera .cad válido a partir de cade.json (texto JSON inline). Valida o resultado."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w", encoding="utf-8") as t:
        t.write(cade_json)
        tmp = t.name
    try:
        json.loads(cade_json)
    except json.JSONDecodeError as e:
        return f"ERRO json inválido: {e}"
    code, out = _run("emit", tmp, "-o", out_path)
    if code != 0:
        return "ERRO " + out
    code2, out2 = _run("validate", out_path)
    return (out + " | revalidação: " + out2) if code2 == 0 else "ERRO pós-emit: " + out2


@mcp.tool()
def cad_new(titulo: str, out_path: str, modo: str = "0", versao: str = "3000") -> str:
    """Cria .cad mínimo válido (template) a partir de título/modo/versão."""
    doc = json.dumps({"meta": {"titulo": titulo[:24], "modo": modo, "versao": versao}})
    return cad_emit(doc, out_path)


@mcp.tool()
def cad_inspect(path: str) -> str:
    """Resume entidades do .cad: contagem, IDs únicos, rungs ladder, nets por símbolo. Para planejar/verificar."""
    d = Path(path).read_bytes().decode("latin1")
    _, ents, _ = split_entities(d)
    ps = [p for p in map(parse_ent, ents) if p]
    from collections import Counter
    ids = Counter(f"{p['id']}#{(p['labels'] + [''])[0]}" for p in ps)
    rungs = [(p['seq'], p['id'], (p['labels'] + [''])[0], p['nums'][21], p['nums'][22])
             for p in ps if p['id'] in ('10050', '10051', '10060') and len(p['nums']) > 22]
    nets = sorted({n for p in ps if len(p['nums']) > 22 for n in (p['nums'][21], p['nums'][22]) if n.isdigit()}, key=int)
    simbolos = [{"id": p['id'], "sub": (p['labels'] + [''])[0], "x": p['nums'][8], "y": p['nums'][9],
                 "A": p['nums'][21], "B": p['nums'][22]}
                for p in ps if p['id'] not in ("4000", "4018", "4009", "4001") and len(p['nums']) > 22]
    return json.dumps({"bytes": len(d), "entidades": len(ps),
                       "ids": dict(ids.most_common(25)),
                       "ladder": [{"seq": s, "id": i, "sub": l, "A": a, "B": b} for s, i, l, a, b in rungs],
                       "simbolos": simbolos,
                       "nets_max": nets[-1] if nets else None}, indent=1, ensure_ascii=False)


@mcp.tool()
def cad_preview(path: str, scale: int = 3, png_path: str = "") -> str:
    """VER o circuito: renderiza o .cad como PNG (data URI base64; com png_path tambem grava o arquivo).

    Quando usar: SEMPRE depois do cad_design/cad_gate verde e antes de entregar.
    O desenho mostra o que o simulador vai ver (conectividade por geometria):
      - fios coloridos pela FASE da rede: L1 laranja, L2 roxo, L3 azul, N ciano, PE verde
        (cinza = rede do comando, sem fonte direta);
      - circulo VERMELHO cheio com '?' = pino SOLTO (nenhum fio termina nele);
      - fio vermelho grosso com X = CURTO (duas fases/N/PE na mesma rede);
      - nome de cada pino ao lado (1/3/5, 2/4/6, U1/V1/W1/PE, L1..PE) e rotulo+classe do simbolo.
    Erro comum: achar que 'abriu' basta — pino vermelho ou fio vermelho = reprovado."""
    import cad_render
    img = cad_render.renderizar(path, max(1, int(scale)))
    if png_path:
        Path(png_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(png_path)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@mcp.tool()
def cad_from_image(path: str, out_json: str = "/tmp/cade_from_img.json") -> str:
    """Detecta símbolos numa imagem (kNN sobre dataset minerado) e inventaria em cade.json."""
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "img2cad.py"), path, "-o", out_json],
                       capture_output=True, text=True, timeout=180)
    return (r.stdout or r.stderr).strip()[:4000]


@mcp.tool()
def cad_simulate(path: str, entradas_json: str = "{}", inicial_json: str = "[]") -> str:
    """Simula a LÓGICA do circuito pelo netlist (sem GUI) e devolve as bobinas energizadas.

    entradas_json: {"S1":true,...} — chaves acionadas (True = pressionado/desligado/trip).
    inicial_json: ["KM1"] — bobinas já energizadas no estado inicial (para selo/memória).
    status ∈ {OK, RACE (corrida), INSTAVEL}. Use para TESTAR de verdade o comando."""
    sys.path.insert(0, str(ROOT / "tools"))
    import netlist_sim as ns
    c = ns.Circuito(path)
    try:
        ent = json.loads(entradas_json)
        ini = set(json.loads(inicial_json))
    except json.JSONDecodeError as e:
        return f"ERRO json: {e}"
    status, bob = c.resolve(ent, ini)
    return json.dumps({"status": status, "bobinas_energizadas": sorted(bob),
                       "supply": c.supply, "retorno": c.ret,
                       "entradas": c.entradas, "bobinas": sorted(c.bobinas)},
                      ensure_ascii=False)


@mcp.tool()
def cad_test(path: str, casos_json: str = "[]") -> str:
    """Verificação funcional (tabela-verdade) do comando via netlist.
    casos_json: [{"nome","entradas":{"S1":true},"inicial":["KM1"],"esperado":["KM1"],"status":"OK|RACE"}].
    Sem casos: usa a suite embutida SÓ se o circuito tiver bobinas KM1 e KM2 (intercalada);
    senão retorna SEM_TESTES (o gate reprova — declare "testes" na spec)."""
    sys.path.insert(0, str(ROOT / "tools"))
    import netlist_sim as ns
    import io
    import contextlib
    try:
        casos = json.loads(casos_json)
    except json.JSONDecodeError as e:
        return f"ERRO json: {e}"
    buf = io.StringIO()
    if not casos:
        c = ns.Circuito(path)
        if not {"KM1", "KM2"} <= set(c.bobinas):
            return "SEM_TESTES: declare casos (chave \"testes\" na spec)"
        with contextlib.redirect_stdout(buf):
            ok = ns.teste(path)
    else:
        with contextlib.redirect_stdout(buf):
            ok = ns.teste_casos(path, casos)
    return ("PASSOU\n" if ok else "FALHOU\n") + buf.getvalue()


# --- autoria do zero (símbolos + fios) --------------------------------------

_LIB = None
ACERVO = Path(os.environ.get("CADE_ACERVO", "/home/monteiro/Downloads/CADe_SIMU 4.0 [BR]/CADe_SIMU 4.0 [BR]/Atividades para Simular/115 arquivos CADe_SIMU/Arquivos .cad"))


def _lib():
    """(header, protos, footer, wire): catálogo de entidades doadoras do corpus+acervo."""
    global _LIB
    if _LIB is None:
        import mk_dataset as M
        header, protos, footer, wire = M.load_donor()
        fontes = sorted((ROOT / "corpus").glob("*.cad"))
        if ACERVO.is_dir():
            fontes += sorted(ACERVO.glob("*.cad"))
        for f in fontes:
            try:
                _, ents, _ = split_entities(f.read_bytes().decode("latin1"))
            except Exception:
                continue
            for e in ents:
                p = parse_ent(e)
                if p and p["id"] not in protos:
                    protos[p["id"]] = p
        _LIB = (header, protos, footer, wire)
    return _LIB


def _json_tools(nome, padrao=None):
    try:
        return json.loads((ROOT / "tools" / nome).read_text())
    except Exception:
        return {} if padrao is None else padrao


def _nomes():
    d = _json_tools("symbol_names.json")
    return {k: v for k, v in d.items() if not k.startswith("_")}


@mcp.tool()
def cad_symbols() -> str:
    """Lista as classes de simbolo (ID, nome/descricao quando conhecidos, tamanho, pinos nomeados).

    Quando usar: para ESCOLHER classes antes de montar o layout. Para detalhes de uma classe
    (offsets de pino, para que serve) use cad_pins(classe). Campos: classe, nome, uso,
    exemplo_rotulo, largura, altura, pinos. 'nome' vem de tools/symbol_names.json
    (so o que esta documentado; ausente = desconhecido, nao presuma).
    Erro comum: usar classe que nao esta aqui — cad_build/cad_design recusam."""
    _, protos, _, _ = _lib()
    nomes, dims, pins = _nomes(), _json_tools("symbol_dims.json"), _json_tools("symbol_pins.json")
    itens = []
    for cid, p in sorted(protos.items()):
        if cid in ("4000", "4001", "4002", "4009", "4010", "4011", "4003", "4004"):
            continue  # conectores/cabos: use `fios`
        lab = [x for x in p["labels"] if x]
        n = nomes.get(cid, {})
        w, h = (dims.get(cid) or [None, None])[:2]
        pn = (pins.get(cid, {}).get("pins") or {})
        itens.append({"classe": cid, "nome": n.get("nome"), "uso": n.get("uso"),
                      "exemplo_rotulo": lab[0] if lab else "",
                      "largura": w, "altura": h, "pinos": sorted(pn) or None})
    return json.dumps({"simbolos": itens, "n": len(itens)}, ensure_ascii=False)


@mcp.tool()
def cad_pins(classe: str) -> str:
    """Pinos e geometria de UMA classe: nomes, offsets (dx,dy) a partir de (x,y), largura/altura e 'para que serve'.

    Quando usar: antes de ligar um simbolo desconhecido, ou ao receber 'pino X da classe Y nao existe'.
    Retorno: {classe, nome, uso, largura, altura, pinos:{nome:[dx,dy]}, pinos_ab, pinos_binario, fonte_nome}.
      pinos      = nomeados (1/3/5/2/4/6, U1/V1/W1/PE, L1..PE) — USE ESTES em conexoes/DSL;
      pinos_ab   = A (topo/entrada) e B (base/saida) dos contatos e bobinas;
      pinos_binario = p1..pN extraidos do executavel (verdade geometrica; ordem de desenho).
    Erro comum: ligar so A/B de simbolo multi-terminal e deixar U1/V1/W1/PE ou 3/5/4/6 soltos."""
    _, protos, _, _ = _lib()
    cid = str(classe).strip()
    pins, dims = _json_tools("symbol_pins.json"), _json_tools("symbol_dims.json")
    try:
        binario = json.loads((ROOT / "docs" / "pinos-binario.json").read_text()).get("classes", {})
    except Exception:
        binario = {}
    if cid not in protos and cid not in pins and cid not in binario:
        return json.dumps({"erro": f"classe {cid} desconhecida. Use cad_symbols."}, ensure_ascii=False)
    n = _nomes().get(cid, {})
    pe = pins.get(cid, {})
    w, h = (dims.get(cid) or [None, None])[:2]
    lab = [x for x in (protos.get(cid, {}).get("labels") or []) if x]
    out = {"classe": cid, "nome": n.get("nome"), "uso": n.get("uso"),
           "fonte_nome": n.get("fonte"),
           "largura": w, "altura": h,
           "exemplo_rotulo": lab[0] if lab else "",
           "pinos": pe.get("pins") or {},
           "pinos_ab": {k: pe[k] for k in ("A", "B") if k in pe},
           "pinos_binario": (binario.get(cid) or {}).get("pins", {})}
    if not n:
        out["aviso"] = "nome desconhecido (nao documentado); use exemplo_rotulo e os pinos como guia"
    return json.dumps(out, ensure_ascii=False)


EXEMPLOS = ROOT / "tools" / "examples"


@mcp.tool()
def cad_examples() -> str:
    """Lista os layouts de exemplo (few-shot): nome, titulo, resumo e n de testes.

    Quando usar: PRIMEIRO passo de qualquer pedido de circuito — ache o exemplo mais proximo do
    enunciado e leia com cad_example(nome). Copiar a estrutura de um exemplo que passa o gate e o
    caminho de menor erro. Todos passam o gate (cad_design) por construcao."""
    itens = []
    for f in sorted(EXEMPLOS.glob("*.layout.json")):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        lay = d.get("layout", d)
        cmd = lay.get("comando", [])
        ramos = sum(len(b.get("ramos", [])) for b in cmd)
        pot = lay.get("potencia", [])
        itens.append({"nome": f.name[:-len(".layout.json")],
                      "titulo": d.get("titulo") or lay.get("titulo"),
                      "descricao": d.get("descricao") or f"{ramos} degrau(s) de comando, {len(pot)} grupo(s) de potencia",
                      "n_testes": len(d.get("testes") or lay.get("testes") or [])})
    return json.dumps({"exemplos": itens, "n": len(itens),
                       "uso": "cad_example(nome) devolve o layout.json completo; adapte e envie a cad_design"},
                      ensure_ascii=False, indent=1)


@mcp.tool()
def cad_example(nome: str) -> str:
    """Devolve o layout.json (DSL topologica + testes) do exemplo `nome` (veja cad_examples).

    Quando usar: como modelo para o seu cad_design. O JSON retornado pode ser enviado
    inalterado a cad_design(layout_json=..., out_path=...) e passa o gate."""
    base = Path(str(nome)).name
    for cand in (EXEMPLOS / f"{base}.layout.json", EXEMPLOS / base):
        if cand.is_file() and cand.name.endswith(".layout.json"):
            return cand.read_text()
    disp = [f.name[:-len(".layout.json")] for f in sorted(EXEMPLOS.glob("*.layout.json"))]
    return json.dumps({"erro": f"exemplo '{nome}' nao existe", "disponiveis": disp}, ensure_ascii=False)


def _proximo_passo(r, path):
    if r["ok"] and r["fios"]["ok"] is not False:
        return (f"Gate verde. Chame cad_preview(path='{path}') e confira: nenhuma fase misturada, "
                f"nenhum pino vermelho. Se estiver certo, entregue o .cad e resuma os testes que passaram.")
    if r["ok"]:
        return (f"Gate verde, mas {len(r['fios']['atravessam'])} fio(s) atravessam simbolo (estetico). "
                f"Veja cad_preview; se o desenho estiver legivel, entregue; senao reordene serie/ramos.")
    if r["erros"]:
        e = r["erros"][0]
        if e.startswith("layout invalido"):
            return f"Corrija o layout_json: {e}. Use cad_example('partida_direta') como molde e tente de novo."
        if e.startswith("CURTO"):
            return f"Corrija o curto de fase: {e}. Depois chame cad_design de novo."
        if "solto" in e:
            return f"Ligue o pino solto: {e}. Depois chame cad_design de novo."
        if e.startswith("sem testes") or e.startswith("teste"):
            return f"Ajuste os testes ou o circuito: {e}. Depois chame cad_design de novo."
        return f"Corrija: {e}. Depois chame cad_design de novo."
    return "Revise o relatorio do gate."


def _relatorio(r, path):
    return {"ok": r["ok"], "path": str(path),
            "gate": {"build": r["build"], "testes": {k: r["testes"][k] for k in
                                                     ("ok", "passaram", "total", "falhas")},
                     "geo": {"curtos": r["geo"]["curtos_msg"], "soltos": r["geo"]["soltos_msg"]},
                     "fios": r["fios"]},
            "avisos": r["avisos"], "erros": r["erros"],
            "proximo_passo": _proximo_passo(r, path)}


@mcp.tool()
def cad_design(layout_json: str, out_path: str) -> str:
    """FERRAMENTA PRINCIPAL: layout TOPOLOGICO (sem x/y) -> .cad pronto + gate completo, numa chamada.

    layout_json = string JSON no formato de cad_examples/cad_example (DSL de docs/dsl-layout.md):
      {"titulo","layout":{"trilhos","fontes","comando","potencia"},"testes":[...]}
      (aceita tambem o layout 'puro' com "testes" dentro; ou spec baixa com "simbolos").
    O motor posiciona tudo, roteia os fios, calcula os nets e roda: build+validate, testes
    funcionais (cad_test), geo_check (curto de fase / pino solto) e wires_check (estetica).
    Retorno JSON: {ok, path, gate:{build,testes,geo:{curtos,soltos},fios}, avisos, erros, proximo_passo}.
    ok=false -> leia 'erros' (acionaveis) e 'proximo_passo', corrija o layout e chame de novo.

    Erros comuns que o gate pega: fonte 3004 por fase (use UMA 3007 com pinos), PE ligado ao
    neutro (use trilho "PE" + "pe":"PE"), pino de motor/contator solto, circuito SEM "testes",
    chave de teste que nao existe (a chave e o rotulo sem '-': '-S1' -> 'S1')."""
    try:
        spec = json.loads(layout_json)
    except json.JSONDecodeError as e:
        return json.dumps({"ok": False, "path": out_path, "erros": [f"layout invalido: JSON malformado: {e}"],
                           "proximo_passo": "Envie um JSON valido (string). Veja cad_example."},
                          ensure_ascii=False, indent=1)
    import build_spec
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    try:
        r = build_spec.construir(spec, out_path)
    except Exception as e:  # layout fora da folha, classe sem pino etc. chegam aqui como ValueError
        r = {"ok": False, "path": out_path, "build": {"ok": False, "mensagem": ""},
             "testes": {"ok": False, "passaram": None, "total": None, "falhas": []},
             "geo": {"curtos_msg": [], "soltos_msg": []}, "fios": {"ok": None, "atravessam": []},
             "avisos": [], "erros": [f"layout invalido: {type(e).__name__}: {e}"]}
    return json.dumps(_relatorio(r, out_path), ensure_ascii=False, indent=1)


@mcp.tool()
def cad_gate(path: str, testes_json: str = "[]") -> str:
    """Gate completo de um .cad EXISTENTE: validate + testes funcionais + geo_check + wires_check.

    Quando usar: depois de editar/gerar um .cad por outro caminho (cad_build manual, cad_emit,
    arquivo de terceiros), ou para reconferir. Para criar do zero prefira cad_design (ja inclui).
    testes_json: [{"nome","entradas":{"S1":true},"inicial":["KM1"],"esperado":["KM1"],"status":"OK"}].
      Sem casos o gate so tem suite embutida p/ circuito com KM1+KM2; senao reprova (SEM_TESTES).
    Retorno: mesmo JSON de cad_design, com mensagens acionaveis, p.ex.
      'pino L3 da fonte -X (3007) solto em (42,55): ligue-o ao trilho L3'."""
    import build_spec
    try:
        testes = json.loads(testes_json)
    except json.JSONDecodeError as e:
        return json.dumps({"ok": False, "path": path, "erros": [f"testes_json invalido: {e}"]}, ensure_ascii=False)
    if not Path(path).is_file():
        return json.dumps({"ok": False, "path": path, "erros": [f"arquivo nao existe: {path}"]}, ensure_ascii=False)
    code, out = _run("validate", path)
    r = {"ok": False, "path": path, "build": {"ok": code == 0, "mensagem": out},
         "testes": {}, "geo": {}, "fios": {}, "avisos": [], "erros": [], "_teste_raw": ""}
    if code != 0:
        r["erros"].append(f"arquivo invalido: {out}")
        r["testes"] = {"ok": False, "passaram": None, "total": None, "falhas": []}
        r["geo"] = {"curtos_msg": [], "soltos_msg": []}
        r["fios"] = {"ok": None, "atravessam": []}
        return json.dumps(_relatorio(r, path), ensure_ascii=False, indent=1)
    build_spec.gate(path, testes, r)
    r["ok"] = bool(r["testes"]["ok"] and not r["geo"]["curtos"] and not r["geo"]["soltos"])
    return json.dumps(_relatorio(r, path), ensure_ascii=False, indent=1)


@mcp.tool()
def cad_build(titulo: str, simbolos_json: str, fios_json: str = "[]", out_path: str = "/tmp/novo.cad",
              auto_net: bool = True, conexoes_json: str = "[]", rails_json: str = "[]",
              textos_json: str = "[]") -> str:
    """CRIA UM .CAD DO ZERO (sem reusar arquivo).
    simbolos_json: [{"classe","x","y","rotulo"?,"id"?}]
    conexoes_json: [{"de":["<id>","A|B"],"para":["<id>","A|B"]}] — liga pinos por NOME
      (recomendado; o build roteia o fio e calcula os NETs automaticamente).
    fios_json: [{"x1","y1","x2","y2"}] — segmentos manuais (opcional).
    textos_json: [{"texto","x","y","altura"?}] — texto livre na folha (classe 8; altura em unidades, padrao 4).
    Com auto_net=True os NETs saem calculados por geometria (pinos×fios).
    Ex.: conexoes_json='[{"de":["B1","B"],"para":["K1","A"]}]'."""
    header, protos, footer, wire = _lib()
    try:
        simbolos = json.loads(simbolos_json)
        fios = json.loads(fios_json)
        conexoes = json.loads(conexoes_json)
        rails = json.loads(rails_json)
        textos = json.loads(textos_json)
    except json.JSONDecodeError as e:
        return f"ERRO json: {e}"
    if not isinstance(simbolos, list):
        return "ERRO: simbolos_json deve ser uma lista"
    faltando = [s.get("classe") for s in simbolos if s.get("classe") not in protos]
    if faltando:
        return f"ERRO classe(s) inexistente(s): {faltando}. Use cad_symbols."
    ents = []   # (id, labels, nums)
    for f in fios:
        n = list(wire["nums"])
        n[8], n[9], n[10], n[11] = str(int(f["x1"])), str(int(f["y1"])), str(int(f["x2"])), str(int(f["y2"]))
        ents.append({"id": str(f.get("classe", "4000")), "labels": wire["labels"], "nums": n})
    for s in simbolos:
        p = protos[s["classe"]]
        n = list(p["nums"])
        n[0] = n[1] = "1"
        n[8], n[9] = str(int(s["x"])), str(int(s["y"]))
        labs = list(p["labels"])
        if s.get("rotulo") and labs:
            labs[0] = s["rotulo"]
        for i, v in enumerate(s.get("rotulos") or []):   # sobrescreve labels[i] (ex.: unidade/tempo do 10066)
            if v is not None:
                labs[i] = str(v)
        ents.append({"id": s["classe"], "labels": labs, "nums": n})
    if not ents:
        ents = [{"id": "8000", "labels": protos["8000"]["labels"], "nums": list(protos["8000"]["nums"])}]
    if conexoes or rails:
        err = _rotear(ents, simbolos, conexoes, wire, rails)
        if err:
            return err
    if auto_net:
        _assign_nets(ents)
    avisos = _shorts(ents)
    for t in textos:   # depois dos nets (n21 e altura aqui, net nos simbolos); texto = classe 8: caixa em n8..n11, altura LOGFONT (negativa) em n21, string no '#%s' final
        x, y, h = int(t["x"]), int(t["y"]), int(t.get("altura", 4))
        n = ["0"] * 23
        n[8], n[9], n[10], n[11] = str(x), str(y), str(x + len(t["texto"]) * h // 2), str(y + h)
        n[20], n[21] = "400", str(-round(h * 21 / 4))   # 400 = peso normal; -21 <-> altura 4 (medido no acervo)
        ents.append({"id": "8", "labels": ["", ""] + [" 0"] * 7, "nums": n, "texto": t["texto"]})
    # A entidade 0 vive colada ao "CADe_SIMU" (seq 0). NAO reaproveite a do doador: ela era
    # uma fonte 3004 solta em (93,45) em todo arquivo gerado (lixo). A 1a entidade nossa e a 0.
    # texto (classe 8) traz um campo ' 0' sem '*' entre os rotulos e os numeros: '...# 0# 0*0*0...'
    body = "".join(f"*{i}*{e['id']}#" + "#".join(e["labels"]) + ("# 0*" if "texto" in e else "#*")
                   + "*".join(e["nums"]) + "#" + e.get("texto", "") for i, e in enumerate(ents))
    cad = "CADe_SIMU" + body + footer
    Path(out_path).write_bytes(cad.encode("latin1"))
    code, out = _run("validate", out_path)
    msg = (f"{len(ents)} entidades -> {out_path} | {out}" if code == 0
           else f"ERRO ao validar: {out}")
    if avisos:
        msg += " | AVISO curto A==B em: " + ", ".join(avisos)
    return msg


def _shorts(ents):
    """Símbolos com o mesmo net em A e B (curto) — o autor deve corrigir o layout."""
    bad = []
    for e in ents:
        if e["id"] in ("4000", "4018", "4009", "4001"):
            continue
        n = e["nums"]
        if len(n) > 22 and n[21] == n[22] and n[21] not in ("0", ""):
            lab = e["labels"][0] if e["labels"] else e["id"]
            bad.append(f"{lab or e['id']}")
    return bad


def _pin_coord(sym, pino):
    """Coordenada do pino (nomeado U1/V1/1/3... ou A/B) aprendida dos exemplos."""
    pins = _pins().get(sym["classe"])
    if not pins:
        return None
    nomeados = pins.get("pins", {})
    off = nomeados.get(pino) or (pins.get(pino) if pino in ("A", "B") else None)
    if off is None:
        return None
    return (int(sym["x"]) + off[0], int(sym["y"]) + off[1])


def _symboxes(ents):
    """Caixas dos corpos dos símbolos (inset 2) p/ o keep-out."""
    out = []
    for e in ents:
        if e["id"] in ("4000", "4018", "4009", "4001", "8", "4010"):
            continue
        try:
            x, y, w, h = int(e["nums"][8]), int(e["nums"][9]), int(e["nums"][14]), int(e["nums"][15])
        except (ValueError, IndexError):
            continue
        if w > 4 and h > 4:
            out.append((x + 2, y + 2, x + w - 2, y + h - 2))
    return out


def _cruza(seg, boxes, skip=()):
    (x1, y1), (x2, y2) = seg
    L = max(abs(x2 - x1), abs(y2 - y1)) or 1
    for i in range(L + 1):
        px, py = x1 + (x2 - x1) * i // L, y1 + (y2 - y1) * i // L
        if any(abs(px - a) <= 4 and abs(py - b) <= 4 for a, b in skip):
            continue          # vizinhança do pino: o fio encosta/sai dele
        for b in boxes:
            if b[0] < px < b[2] and b[1] < py < b[3]:
                return True
    return False


def _rotear(ents, simbolos, conexoes, wire, rails=None):
    """Liga pinos por nome. Suporta TRILHOS (barramentos): um pino liga a um
    trilho por fio vertical curto; o trilho sai em segmentos com vértice em cada
    conexão (para os nets fecharem por coordenada)."""
    rails = rails or []
    rail_map = {r["nome"]: {"y": int(r["y"]), "x0": int(r["x0"]), "x1": int(r["x1"])} for r in rails}
    vert = {n: {v["x0"], v["x1"]} for n, v in rail_map.items()}
    byid = {}
    for i, s in enumerate(simbolos):
        key = str(s.get("id") or s.get("rotulo") or f"#{i}")
        byid[key] = s

    def emit(a, b):
        if a == b:
            return
        n = list(wire["nums"])
        n[8], n[9], n[10], n[11] = str(a[0]), str(a[1]), str(b[0]), str(b[1])
        for k in range(8):
            n[k] = "0"
        ents.append({"id": "4000", "labels": wire["labels"], "nums": n})

    for idx, c in enumerate(conexoes):
        de, para = c.get("de"), c.get("para")
        if not de or not para:
            return f"ERRO conexão inválida: {c}"
        # 1) ligação a TRILHO
        feito = False
        for lado_v, outro_v in ((de, para), (para, de)):
            if lado_v[0] in rail_map and outro_v[0] in byid:
                s = byid[outro_v[0]]
                p1 = _pin_coord(s, outro_v[1])
                if p1 is None:
                    return f"ERRO: sem geometria p/ {outro_v[0]}.{outro_v[1]}"
                r = rail_map[lado_v[0]]
                info = _pins().get(s["classe"], {})
                off = (info.get("pins") or {}).get(outro_v[1]) or info.get(outro_v[1], [0, 0])
                s_esc = -1 if off[1] <= 0 else 1     # sai do corpo antes de virar
                e1 = (p1[0], p1[1] + s_esc * 7)
                emit(p1, e1)
                # RETO: se a coluna do pino estiver livre até o trilho, desce direto
                boxes0 = _symboxes(ents)
                if not _cruza((e1, (e1[0], r["y"])), boxes0, skip=(p1, e1)):
                    emit(e1, (e1[0], r["y"]))
                    vert[lado_v[0]].add(e1[0])
                    feito = True
                    break
                via = c.get("via")
                if via is None:
                    # escolhe uma coluna livre (fora de qualquer corpo) até o trilho
                    boxes = _symboxes(ents)
                    xm = e1[0] + 8
                    for _ in range(24):
                        if not any(b[0] - 2 <= xm <= b[2] + 2 and
                                   min(e1[1], r["y"]) - 2 <= (b[1] + b[3]) / 2 <= max(e1[1], r["y"]) + 2
                                   for b in boxes):
                            break
                        xm += 6
                    via = xm
                emit(e1, (int(via), e1[1]))
                emit((int(via), e1[1]), (int(via), r["y"]))
                vert[lado_v[0]].add(int(via))
                feito = True
                break
        if feito:
            continue
        if de[0] not in byid or para[0] not in byid:
            return f"ERRO conexão inválida: {c} (confira os ids)"
        p1 = _pin_coord(byid[de[0]], de[1])
        p2 = _pin_coord(byid[para[0]], para[1])
        if p1 is None or p2 is None:
            cls = byid[de[0]]["classe"]
            return (f"ERRO: sem geometria de pino p/ classe {cls} (ou pino '{de[1]}'). "
                    f"Use fios_json manual ou outra classe.")
        (x1, y1), (x2, y2) = p1, p2
        pins = _pins()
        d1 = pins.get(byid[de[0]]["classe"], {}).get(de[1], [0, 0])[1]
        d2 = pins.get(byid[para[0]]["classe"], {}).get(para[1], [0, 0])[1]
        s1 = -1 if d1 <= 0 else 1     # pino na borda de cima escapa p/ CIMA
        s2 = -1 if d2 <= 0 else 1
        g = 7
        # pinos no MESMO x: fio reto, se o trecho não atravessar símbolo
        if x1 == x2 and not _cruza((p1, p2), _symboxes(ents), skip=(p1, p2)):
            pts = [p1, p2]
        else:
            a1 = (x1, y1 + s1 * g)
            b1 = (x2, y2 + s2 * g)
            pts = [(x1, y1), a1]
            if s1 == s2:
                # mesmo lado: pivota no x do destino (não cruza o símbolo)
                if a1[1] != b1[1]:
                    pts.append((x2, a1[1]))
            else:
                # lados opostos: COLUNA DE DESVIO única por conexão e FORA de
                # qualquer corpo de símbolo (senão o fio atravessa o desenho)
                boxes = _symboxes(ents)
                passo = 1 if x2 >= x1 else -1
                xm = x2 + (10 + 3 * (idx % 4)) * passo
                for _ in range(12):
                    if not any(b[0] - 2 <= xm <= b[2] + 2 and
                               min(a1[1], b1[1]) - 2 <= (b[1] + b[3]) / 2 <= max(a1[1], b1[1]) + 2
                               for b in boxes):
                        break
                    xm += 6 * passo
                pts += [(xm, a1[1]), (xm, b1[1])]
            pts += [b1, (x2, y2)]
        for a, b in zip(pts, pts[1:]):
            emit(a, b)
    # 2) emite os trilhos em segmentos (vértice em cada conexão -> nets fecham)
    for nome, r in rail_map.items():
        xs = sorted(vert[nome])
        for a, b in zip(xs, xs[1:]):
            emit((a, r["y"]), (b, r["y"]))
    return None


PINS_FILE = ROOT / "tools" / "symbol_pins.json"


def _pins():
    try:
        return json.loads(PINS_FILE.read_text())
    except Exception:
        return {}


def _assign_nets(ents):
    """Calcula NETs por geometria: une pinos de símbolo e endpoints de fio que
    coincidem, e propaga por cada fio. Escreve nums[21]/[22] (A/B ou net do fio)."""
    pins = _pins()
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    def pin_pts(e):
        if e["id"] == "4000" or e["id"] in ("4018", "4009", "4001"):
            return [("wire", (int(e["nums"][8]), int(e["nums"][9]))), ("wire", (int(e["nums"][10]), int(e["nums"][11])))]
        x, y = int(e["nums"][8]), int(e["nums"][9])
        m = pins.get(e["id"], {})
        out = []
        if "A" in m:
            out.append(("A", (x + m["A"][0], y + m["A"][1])))
        if "B" in m:
            out.append(("B", (x + m["B"][0], y + m["B"][1])))
        return out

    # registra nós e une points coincidentes
    bycoord = {}
    for e in ents:
        for _, pt in pin_pts(e):
            bycoord.setdefault(pt, []).append(pt)
            find(pt)
    # fios unem seus dois endpoints
    for e in ents:
        if e["id"] == "4000":
            p1 = (int(e["nums"][8]), int(e["nums"][9]))
            p2 = (int(e["nums"][10]), int(e["nums"][11]))
            union(p1, p2)
    # atribui número por raiz
    raizes = {}
    nxt = [20]
    for pt in list(bycoord):
        r = find(pt)
        if r not in raizes:
            nxt[0] += 1
            raizes[r] = nxt[0]
    for e in ents:
        pts = pin_pts(e)
        if e["id"] == "4000":
            net = raizes[find((int(e["nums"][8]), int(e["nums"][9])))]
            if len(e["nums"]) > 21:
                e["nums"][21] = str(net)
            continue
        for pin, pt in pts:
            net = raizes[find(pt)]
            idx = 21 if pin == "A" else 22
            if len(e["nums"]) > idx:
                e["nums"][idx] = str(net)


@mcp.tool()
def cad_simular_no_app(path: str, casos_json: str = "[]", entradas_alias_json: str = "{}") -> str:
    """CONFIRMACAO FINAL na VERDADE do app: abre o .cad no CADe_SIMU (Wine), da Play, aciona as entradas
    e le bobinas/lampadas acesas por analise de imagem. Roda os mesmos casos de cad_test/cad_gate.

    Quando usar: SO no fim, com cad_design/cad_gate verde e o cad_preview conferido. Custa ~30-90 s
    (subir o Wine ~20 s + ~4-6 s por caso), exige Wine + DISPLAY (X11) e usa UM Wine por vez; nao use em
    loop de iteracao (o netlist/cad_test e instantaneo). Sempre derruba o Wine ao terminar.
    casos_json: [{"nome","entradas":{"S1":true},"inicial":["KM1"],"esperado":["KM1"],
                  "esperado_lampadas":["H1"]}]  (mesmo formato dos "testes"; botoeira True = segurar;
      termico/disjuntor True = clique; "inicial" e obtido apertando a sequencia de botoes ate as bobinas
      chegarem la). Vazio = so confere o estado de repouso. status 'RACE' vira 'ignorado'.
    entradas_alias_json: {"RT1":"F1"} (raro): aciona a entrada pelo rotulo de outro simbolo.
    Retorno JSON: {ok, repouso, casos:[{nome, resultado: ok|falha|indeterminado|nao_acionavel|erro|ignorado,
      esperado, obtido, obtido_lampadas, screenshot, motivo}], screenshots (diretorio), tempo_s, avisos}.
    Divergencia app x netlist = bug do modelo/RE ou do circuito, NAO do teste: leia 'motivo' e o screenshot.
    Ja sabido: o contato do rele termico (8016/8017) so acompanha o disparo do 6007 de MESMO ROTULO
    (ex.: ambos '-F1'); com rotulos diferentes (-RT1 x -F1) o app nao permite disparar o termico."""
    try:
        casos = json.loads(casos_json)
        aliases = json.loads(entradas_alias_json)
    except json.JSONDecodeError as e:
        return json.dumps({"ok": False, "erro": f"JSON invalido: {e}"}, ensure_ascii=False)
    if not Path(path).is_file():
        return json.dumps({"ok": False, "erro": f"arquivo nao existe: {path}"}, ensure_ascii=False)
    if not os.environ.get("DISPLAY") and not os.path.exists("/tmp/.X11-unix"):
        return json.dumps({"ok": False, "erro": "sem DISPLAY/X11: o simulador do app precisa de uma tela (DISPLAY=:1)"},
                          ensure_ascii=False)
    import app_sim
    try:
        r = app_sim.executar_casos(path, casos, aliases=aliases)
    except Exception as e:  # nao deixa o MCP cair; o app_sim ja da down no finally
        return json.dumps({"ok": False, "erro": f"{type(e).__name__}: {e}"}, ensure_ascii=False)
    r.pop("log", None)
    div = [c for c in r["casos"] if c.get("resultado") in ("falha", "nao_acionavel", "indeterminado", "erro")]
    r["proximo_passo"] = ("app == modelo nos casos avaliados" if not div and r.get("ok") else
                          f"{len(div)} caso(s) divergem do esperado: confira os screenshots e o 'motivo'; "
                          "se o netlist passa mas o app nao, o circuito/RE esta errado, nao o teste")
    return json.dumps(r, ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
    mcp.run()
