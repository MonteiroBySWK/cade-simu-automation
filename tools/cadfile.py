#!/usr/bin/env python3
"""Leitura/escrita fiel de .cad como LISTA DE ENTIDADES editavel (edicao programatica controlada).

Entidade = `*seq*id#` + rotulos (separados por '#') + `#` + `*n0*n1...` + terminador. O terminador e `#`,
exceto quando a entidade tem string final (IP do CPU 10206, texto da classe 8): `#<string>` e a proxima
entidade vem colada, sem '#'. A entidade 0 vive colada ao `CADe_SIMU` (docs/formato-cad.md).

    cad = Cad.ler("base.cad")
    cad.ents[i].labels[0] = "Q0.2"           # edita
    cad.adicionar(Ent("4000", [""]*10, nums)) # acrescenta
    cad.salvar("novo.cad")

`serializar(parse(x)) == x` byte a byte nos .cad do corpus/acervo (tools/test_cadfile.py).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dissect import parse_ent, split_all  # noqa: E402


class Ent:
    __slots__ = ("id", "labels", "nums", "extra", "seq")

    def __init__(self, cid, labels, nums, extra="", seq=None):
        self.seq = seq                       # None = o Cad atribui max+1 ao adicionar
        self.id = str(cid)
        self.labels = list(labels)
        self.nums = [str(n) for n in nums]
        self.extra = extra

    @classmethod
    def de_dict(cls, p):
        return cls(p["id"], p["labels"], p["nums"], p.get("extra", ""), seq=p["seq"])

    # n8/n9 = x,y do simbolo; n10/n11 = x2,y2 dos fios
    @property
    def x(self):
        return int(self.nums[8])

    @property
    def y(self):
        return int(self.nums[9])

    @property
    def rotulo(self):
        return (self.labels[:1] or [""])[0]

    def mover(self, dx=0, dy=0):
        """Move simbolo (x,y) ou fio (x1,y1,x2,y2)."""
        n = self.nums
        n[8], n[9] = str(int(n[8]) + dx), str(int(n[9]) + dy)
        if self.id.startswith("40") and len(n) > 11:
            n[10], n[11] = str(int(n[10]) + dx), str(int(n[11]) + dy)
        return self

    def serializar(self):
        if not self.nums:                    # texto (classe 8): os numeros vivem dentro de `labels`
            corpo = f"*{self.seq}*{self.id}#" + "#".join(self.labels)
            return corpo if self.labels and self.labels[-1] == "" else corpo + "#"   # ultima entidade ja traz o '#' 
        corpo = f"*{self.seq}*{self.id}#" + "#".join(self.labels) + "#*" + "*".join(self.nums)
        return corpo + ("#" + self.extra if self.extra else "#")

    def __repr__(self):
        return f"Ent({self.id}, {self.rotulo!r}, @{self.nums[8:10]})"


class Cad:
    def __init__(self, ents, footer):
        self.ents = ents
        self.footer = footer

    @classmethod
    def parse(cls, texto):
        _, ents, footer = split_all(texto)
        out = []
        for e in ents:
            p = parse_ent(e)
            if p is None:
                raise ValueError(f"entidade ilegivel: {e[:60]!r}")
            out.append(Ent.de_dict(p))
        return cls(out, footer)

    @classmethod
    def ler(cls, path):
        return cls.parse(Path(path).read_bytes().decode("latin1"))

    def serializar(self):
        corpo = "".join(e.serializar() for e in self.ents)
        return "CADe_SIMU" + corpo + self.footer

    def salvar(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(self.serializar().encode("latin1"))
        return str(path)

    def achar(self, cid=None, rotulo=None):
        return [e for e in self.ents if (cid is None or e.id == str(cid)) and (rotulo is None or e.rotulo == rotulo)]

    def adicionar(self, ent):
        if ent.seq is None:
            ent.seq = 1 + max((int(e.seq) for e in self.ents), default=0)
        self.ents.append(ent)
        return ent

    def remover(self, ent):
        self.ents = [e for e in self.ents if e is not ent]


if __name__ == "__main__":
    for f in sys.argv[1:]:
        t = Path(f).read_bytes().decode("latin1")
        print(("OK  " if Cad.parse(t).serializar() == t else "DIFF"), f)
