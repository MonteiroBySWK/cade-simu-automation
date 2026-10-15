#!/usr/bin/env python3
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
    """Resume entidades do .cad: contagem, IDs únicos, rungs ladder, nets. Para planejar edições."""
    d = Path(path).read_bytes().decode("latin1")
    _, ents, _ = split_entities(d)
    ps = [p for p in map(parse_ent, ents) if p]
    from collections import Counter
    ids = Counter(f"{p['id']}#{(p['labels'] + [''])[0]}" for p in ps)
    rungs = [(p['seq'], p['id'], (p['labels'] + [''])[0], p['nums'][21], p['nums'][22])
             for p in ps if p['id'] in ('10050', '10051', '10060') and len(p['nums']) > 22]
    nets = sorted({n for p in ps if len(p['nums']) > 22 for n in (p['nums'][21], p['nums'][22]) if n.isdigit()}, key=int)
    return json.dumps({"bytes": len(d), "entidades": len(ps),
                       "ids": dict(ids.most_common(25)),
                       "ladder": [{"seq": s, "id": i, "sub": l, "A": a, "B": b} for s, i, l, a, b in rungs],
                       "nets_max": nets[-1] if nets else None}, indent=1, ensure_ascii=False)


@mcp.tool()
def cad_preview(path: str, scale: int = 2) -> str:
    """Renderiza o esquema como PNG (base64, MCP image). Para o agente VER o circuito."""
    from PIL import Image, ImageDraw
    d = Path(path).read_bytes().decode("latin1")
    _, ents, _ = split_entities(d)
    ps = [p for p in map(parse_ent, ents) if p]
    W, H = 440, 220
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


if __name__ == "__main__":
    mcp.run()
