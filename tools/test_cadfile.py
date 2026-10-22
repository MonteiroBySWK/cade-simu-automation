"""Testes de tools/cadfile.py (leitura/escrita fiel de .cad) e do dissect com string final (IP do 10206)."""
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import ladder_dsl as L  # noqa: E402
from cadfile import Cad, Ent  # noqa: E402
from dissect import parse_ent, split_all  # noqa: E402


def _gerado(tmp_path):
    import json
    spec = json.loads((TOOLS / "examples" / "partida_sequencial_3.ladder.json").read_text(encoding="utf-8"))
    d, _ = L.compilar(spec, "x.cad")
    p = tmp_path / "x.cad"
    d.cad.salvar(p)
    return p


def test_roundtrip_byte_a_byte(tmp_path):
    p = _gerado(tmp_path)
    t = p.read_bytes().decode("latin1")
    assert Cad.parse(t).serializar() == t


def test_ip_do_10206_nao_engole_a_entrada_seguinte(tmp_path):
    p = _gerado(tmp_path)
    _, ents, _ = split_all(p.read_bytes().decode("latin1"))
    ps = [parse_ent(e) for e in ents]
    cpu = [x for x in ps if x["id"] == "10206"]
    assert len(cpu) == 1 and cpu[0]["extra"] == "192.128.0.1"
    assert len([x for x in ps if x["id"] == "10204"]) == 3


def test_edicao_e_texto(tmp_path):
    p = _gerado(tmp_path)
    c = Cad.ler(p)
    bob = c.achar("10060", "Q0.3")[0]
    bob.labels[0] = "Q0.9"
    n = len(c.ents)
    d = L.Desenho()
    d.cad = c
    d.texto(10, 10, "LEGENDA")
    assert len(c.ents) == n + 1
    c.salvar(tmp_path / "y.cad")
    c2 = Cad.ler(tmp_path / "y.cad")
    assert c2.achar("10060", "Q0.9") and c2.ents[-1].id == "8" and any("LEGENDA" in x for x in c2.ents[-1].labels)
    assert Ent("4000", [""] * 9, [0] * 8 + [1, 2, 3, 4] + [0] * 11).mover(3, 3).nums[8:12] == ["4", "5", "6", "7"]
