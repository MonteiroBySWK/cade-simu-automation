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

from mcp.server.fastmcp import FastMCP  # noqa: E402

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
def cad_preview(path: str, scale: int = 2) -> str:
    """Renderiza o esquema como PNG (base64, imagem MCP). Canvas ajustado ao conteúdo."""
    from PIL import Image, ImageDraw
    d = Path(path).read_bytes().decode("latin1")
    _, ents, _ = split_entities(d)
    ps = [p for p in map(parse_ent, ents) if p]
    xs, ys = [], []
    for p in ps:
        n = p["nums"]
        if len(n) < 16:
            continue
        try:
            ints = [int(v) for v in (n[8], n[9], n[10], n[11], n[14], n[15])]
        except ValueError:
            continue
        xs += [ints[0], ints[2], ints[0] + ints[4]]
        ys += [ints[1], ints[3], ints[1] + ints[5]]
    mx, my = (max(xs) if xs else 440), (max(ys) if ys else 220)
    W, H = max(200, mx + 20), max(160, my + 20)
    img = Image.new("RGB", (W * scale, H * scale), "white")
    dr = ImageDraw.Draw(img)
    S = lambda v: int(v) * scale
    for p in ps:
        n = p["nums"]
        if len(n) < 16:
            continue
        x, y = int(n[8]), int(n[9])
        if p["id"] in ("4000", "4001", "4009", "4010", "4018", "4019"):
            x2, y2 = int(n[10]), int(n[11])
            if x == x2 and y == y2:
                dr.ellipse([S(x) - 2, S(y) - 2, S(x) + 2, S(y) + 2], fill="red")
            else:
                dr.line([S(x), S(y), S(x2), S(y2)], fill="red" if p["id"] in ("4000", "4001") else "green")
        elif p["id"] == "8":
            dr.text((S(x), S(y)), p["raw"].split("#")[-1][:30], fill="black")
        else:
            w, h = int(n[14]), int(n[15])
            dr.rectangle([S(x), S(y), S(x + w), S(y + h)], outline="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


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
def cad_test(path: str) -> str:
    """Roda a verificação funcional embutida (tabela-verdade) de um circuito de comando
    com selo/intertravamento/térmico. Retorna OK/FALHA por caso."""
    sys.path.insert(0, str(ROOT / "tools"))
    import netlist_sim as ns
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ok = ns.teste(path)
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


@mcp.tool()
def cad_symbols() -> str:
    """Lista as classes de símbolo disponíveis (ID + exemplo de rótulo) para montar do zero."""
    _, protos, _, _ = _lib()
    itens = []
    for cid, p in sorted(protos.items()):
        if cid in ("4000", "4001", "4002", "4009", "4010", "4011", "4003", "4004"):
            continue  # conectores/cabos: use `fios`
        lab = [x for x in p["labels"] if x]
        itens.append({"classe": cid, "exemplo_rotulo": lab[0] if lab else ""})
    return json.dumps({"simbolos": itens, "n": len(itens)}, ensure_ascii=False)


@mcp.tool()
def cad_build(titulo: str, simbolos_json: str, fios_json: str = "[]", out_path: str = "/tmp/novo.cad",
              auto_net: bool = True, conexoes_json: str = "[]", rails_json: str = "[]") -> str:
    """CRIA UM .CAD DO ZERO (sem reusar arquivo).
    simbolos_json: [{"classe","x","y","rotulo"?,"id"?}]
    conexoes_json: [{"de":["<id>","A|B"],"para":["<id>","A|B"]}] — liga pinos por NOME
      (recomendado; o build roteia o fio e calcula os NETs automaticamente).
    fios_json: [{"x1","y1","x2","y2"}] — segmentos manuais (opcional).
    Com auto_net=True os NETs saem calculados por geometria (pinos×fios).
    Ex.: conexoes_json='[{"de":["B1","B"],"para":["K1","A"]}]'."""
    header, protos, footer, wire = _lib()
    try:
        simbolos = json.loads(simbolos_json)
        fios = json.loads(fios_json)
        conexoes = json.loads(conexoes_json)
        rails = json.loads(rails_json)
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
        ents.append({"id": "4000", "labels": wire["labels"], "nums": n})
    for s in simbolos:
        p = protos[s["classe"]]
        n = list(p["nums"])
        n[0] = n[1] = "1"
        n[8], n[9] = str(int(s["x"])), str(int(s["y"]))
        labs = list(p["labels"])
        if s.get("rotulo") and labs:
            labs[0] = s["rotulo"]
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
    base = (ROOT / "corpus" / "Arranque_1.cad").read_bytes().decode("latin1")
    import re
    m = re.search(r"#(?=\*\d+\*\d+#)", base)
    hdr = base[:m.start() + 1] if m else header
    body = "#".join(f"*{i+1}*{e['id']}#" + "#".join(e["labels"]) + "#*" + "*".join(e["nums"])
                    for i, e in enumerate(ents))
    cad = hdr + body + "#" + footer
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


if __name__ == "__main__":
    mcp.run()
