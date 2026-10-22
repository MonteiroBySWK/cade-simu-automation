#!/usr/bin/env python3
"""Grava os goldens do APP REAL (Wine) para o teste diferencial de conformidade.

`tests/conformidade/<caso>/cenario.json` -> `golden_app.json` com `"fonte": "app"`.

O cenario e uma sequencia de acoes (ver `docs/conformidade.md`): `reiniciar` (Stop + Play), `esperar`
(ms de parede), `pressionar`/`soltar` (botoeira: mousedown/mouseup) e `alternar` (termico/disjuntor:
um clique). Depois de CADA acao o estado do app e lido por imagem (`app_sim.ler_estado`): bobinas,
lampadas, motores e saidas do CLP. `t_ms` do golden = soma dos `esperar` (contrato do `cade
conformidade`); `t_parede_ms` guarda o tempo real decorrido (diagnostico: no app o relogio anda
tambem durante cliques e screenshots).

Dois fatos do app que o gravador trata (e que custaram caro):

- **um ponteiro so**: nao da para segurar S1 e apertar S0 ao mesmo tempo; o cenario que tenta isso
  e RECUSADO (o clique perdido gerava golden mentiroso: S0 nao desligava nada);
- **disjuntores iniciam ABERTOS** em cada Play (6009/6010...): sem fechar, o motor nunca gira. Depois
  de Play e de cada `reiniciar` o gravador clica cada disjuntor (`--sem-disjuntores` desliga isso e
  grava o app cru).

Uso:
  python3 tools/golden_app.py tests/conformidade/partida_direta     # um caso
  python3 tools/golden_app.py --todos                               # todos os casos
  python3 tools/golden_app.py --todos --json saida.json             # resumo em JSON
  python3 tools/golden_app.py --todos --forcar                      # regrava golden "app"

Um Wine por vez: se ja houver CADe_SIMU rodando (outro agente), espera e desiste (`AGENTS.md`).
Sem Wine, `--seco` so reescreve o golden a partir do `estado` do oraculo Python? NAO: use
`python3 tests/conformidade/gerar.py` para os provisorios.
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent

CAMPOS = ("bobinas", "lampadas", "motores", "saidas_clp")


class GoldenErro(RuntimeError):
    pass


# --------------------------------------------------------------------------- nucleo (sem Wine)

def norm(rot):
    return (rot or "").strip().lstrip("-").upper()


def _ativos(d):
    return sorted(k for k, v in (d or {}).items() if v)


def _extrair(est, campos=CAMPOS):
    """Estado lido -> campos do golden. Campo ausente na leitura NAO entra (nao e comparado)."""
    out = {}
    for c in campos:
        if c in est:
            out[c] = _ativos(est[c])
    if est.get("curto"):
        out["curto"] = True
    return out


def carregar_cenario(caso_dir):
    p = Path(caso_dir) / "cenario.json"
    if not p.exists():
        raise GoldenErro(f"{caso_dir}: sem cenario.json")
    try:
        c = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise GoldenErro(f"{p}: JSON invalido ({e})") from e
    if not isinstance(c.get("acoes"), list) or not c["acoes"]:
        raise GoldenErro(f"{p}: sem `acoes`")
    return c


def executar_cenario(cenario, obs, campos=CAMPOS, progresso=None):
    """Executa as acoes no observador e devolve um passo por acao (estado lido DEPOIS da acao)."""
    passos, t_ms, t0 = [], 0, time.time()
    for i, a in enumerate(cenario["acoes"]):
        nome = a.get("acao")
        if nome == "reiniciar":
            obs.reiniciar()
            t0 = time.time()
            t_ms = 0
        elif nome == "esperar":
            ms = a.get("ms")
            if not isinstance(ms, int) or ms < 0:
                raise GoldenErro(f"acao {i}: `esperar` sem `ms` inteiro >= 0")
            t_ms += ms
            obs.esperar(ms)
        elif nome in ("pressionar", "alternar"):
            alvo = a.get("alvo")
            if not alvo:
                raise GoldenErro(f"acao {i} ({nome}): sem `alvo`")
            getattr(obs, nome)(norm(alvo))
        elif nome == "soltar":
            obs.soltar()
        else:
            raise GoldenErro(f"acao {i}: acao desconhecida {nome!r}")
        est = obs.observar()
        passo = {"i": i, "t_ms": t_ms, "t_parede_ms": int(round((time.time() - t0) * 1000))}
        passo.update(_extrair(est, campos))
        passos.append(passo)
        if progresso:
            progresso(i, len(cenario["acoes"]), passo)
    return passos


def montar_golden(caso_dir, cenario, passos, disjuntores=()):
    g = {
        "versao": 1,
        "fonte": "app",
        "caso": Path(caso_dir).name,
        "descricao": cenario.get("descricao", ""),
        "gravado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
        "passos": passos,
    }
    if disjuntores:
        # o app inicia os disjuntores ABERTOS (docs/classes-papeis.json, estado_inicial 0): o gravador
        # fecha cada um depois de Play/reiniciar. Campo informativo (o Rust ignora chaves extras).
        g["disjuntores_fechados"] = sorted(disjuntores)
    return g


def casos_com_cenario(base):
    base = Path(base)
    return sorted(p for p in base.iterdir() if p.is_dir() and (p / "cenario.json").exists())


def gravar_caso(caso_dir, fabrica=None, forcar=False, verbose=False, campos=CAMPOS,
                fechar_disjuntores=True, manter=False):
    """Grava `golden_app.json` do caso. `fabrica(cad)` devolve o observador (testes injetam um falso)."""
    caso_dir = Path(caso_dir)
    cenario = carregar_cenario(caso_dir)
    cad = caso_dir / "circuito.cad"
    if not cad.exists():
        raise GoldenErro(f"{caso_dir}: sem circuito.cad")
    destino = caso_dir / "golden_app.json"
    if destino.exists() and not forcar:
        atual = {}
        try:
            atual = json.loads(destino.read_text(encoding="utf-8"))
        except ValueError:
            pass
        if atual.get("fonte") == "app":
            return {"caso": caso_dir.name, "ok": False, "pulado": True,
                    "motivo": "golden do app ja existe (use --forcar para regravar)"}

    obs = (fabrica or (lambda cad: ObservadorApp(cad, manter=manter, verbose=verbose,
                                                 fechar_disjuntores=fechar_disjuntores)))(cad)
    t0 = time.time()
    def progresso(i, n, passo):
        if verbose and (i % 10 == 0 or i == n - 1):
            print(f"[golden] {caso_dir.name} {i+1}/{n} t={passo['t_ms']}ms "
                  f"bobinas={passo.get('bobinas')} lampadas={passo.get('lampadas')}", flush=True)
    try:
        obs.abrir()
        passos = executar_cenario(cenario, obs, campos=campos, progresso=progresso)
    finally:
        try:
            obs.fechar()
        except Exception:                                    # noqa: BLE001 - fechar nunca derruba a gravacao
            pass
    golden = montar_golden(caso_dir, cenario, passos, getattr(obs, "disjuntores", ()))
    destino.write_text(json.dumps(golden, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"caso": caso_dir.name, "ok": True, "pulado": False, "passos": len(passos),
            "golden": str(destino), "duracao_s": round(time.time() - t0, 1),
            "bobinas_vistas": sorted({b for p in passos for b in p.get("bobinas", [])}),
            "lampadas_vistas": sorted({b for p in passos for b in p.get("lampadas", [])}),
            "motores_vistos": sorted({b for p in passos for b in p.get("motores", [])})}


# --------------------------------------------------------------------------- observador do app

class ObservadorApp:
    """Observa o CADe_SIMU rodando no Wine. `abrir()` faz Play + zoom; `fechar()` derruba o Wine.

    No app ha **um ponteiro so**: `pressionar` segura (mousedown) e `soltar` larga (mouseup). Tentar
    segurar um segundo atuador com o primeiro pressionado e impossivel (o clique vira o mouseup do
    primeiro) — o gravador recusa o cenario em vez de gravar um estado enganoso.

    Os disjuntores (6009/6010...) iniciam **abertos** em cada Play; por isso, depois de Play e de cada
    `reiniciar`, o gravador fecha todos (clique alterna), como faz o operador no app.
    """

    def __init__(self, cad, manter=False, verbose=False, calibrar_a_cada=20, espera_acao=0.5,
                 fechar_disjuntores=True, settle_leitura=0.25):
        import app_sim
        self.app_sim = app_sim
        self.cad = Path(cad)
        self.manter = manter
        self.verbose = verbose
        self.calibrar_a_cada = int(calibrar_a_cada)
        self.espera_acao = float(espera_acao)
        self.settle_leitura = float(settle_leitura)
        self.fechar_disjuntores = bool(fechar_disjuntores)
        self.disjuntores = []
        self.segurando = None
        self.app = None
        self.n = 0

    def abrir(self):
        self.app = self.app_sim.AppSim(self.cad, verbose=self.verbose)
        self.app.abrir()
        self.app.play()
        self.app.zoom_todo()
        est = self.app.estado("_calibra.png")          # calibra e confere que le o circuito
        if est["fora_da_janela"]:
            raise GoldenErro(f"{self.cad.name}: simbolos fora da janela (nao lidos): {est['fora_da_janela']}")
        self.n = 0
        self._fechar_disjuntores()
        return self

    def fechar(self):
        if self.app is not None and not self.manter:
            self.app.fechar()
            self.app = None

    def __enter__(self):
        return self.abrir()

    def __exit__(self, *a):
        self.fechar()

    def _fechar_disjuntores(self):
        """Clique em cada disjuntor (inicia aberto em cada Play). Registra os rotulos fechados."""
        if not self.fechar_disjuntores:
            return []
        fechados = []
        for s in self.app.cad.simbolos:
            if s["tipo"] == "disjuntor":
                self.app.alternar(s["chave"], espera=0.3)
                fechados.append(s["chave"])
        self.disjuntores = sorted(set(self.disjuntores) | set(fechados))
        return fechados

    # -- acoes (espelham docs/conformidade.md)
    def reiniciar(self):
        self.app.reiniciar()
        time.sleep(self.espera_acao)
        self.segurando = None
        self._fechar_disjuntores()

    def esperar(self, ms):
        time.sleep(ms / 1000.0)

    def pressionar(self, alvo):
        if self.segurando:
            raise GoldenErro(f"{self.cad.name}: `pressionar {alvo}` com {self.segurando} pressionado — "
                             f"no app so um atuador por vez (insira um `soltar` antes no cenario)")
        self.app.pressionar(alvo, segurar_s=None)      # mousedown; `soltar` vem em acao propria
        self.segurando = alvo
        time.sleep(self.espera_acao)

    def soltar(self):
        self.app.soltar()
        self.segurando = None
        time.sleep(self.espera_acao)

    def alternar(self, alvo):
        if self.segurando:
            raise GoldenErro(f"{self.cad.name}: `alternar {alvo}` com {self.segurando} pressionado — "
                             f"no app so um atuador por vez (insira um `soltar` antes no cenario)")
        self.app.alternar(alvo, espera=self.espera_acao)

    def observar(self):
        # settle extra: o app repinta em ticks de 100 ms e a captura pode pegar um quadro parcial
        # (bobina ja vermelha, contato auxiliar/lampada/motor ainda nao) — visto em 22/10/2026.
        if self.settle_leitura:
            time.sleep(self.settle_leitura)
        nome = f"p{self.n:04d}.png"
        self.n += 1
        app = self.app
        if app.cal is None or self.n % self.calibrar_a_cada == 0:
            img, _, cal = app._snap_calibra(nome)
            if cal is None:
                raise GoldenErro(f"{self.cad.name}: calibracao falhou no passo {self.n - 1}")
        else:
            img, _ = app.screenshot(nome)
        est = self.app_sim.ler_estado(img, app.cad, app.cal)
        faltando = sorted({s["rotulo"] for s in est["simbolos"] if not s["visivel"]})
        if faltando:
            raise GoldenErro(f"{self.cad.name}: simbolos fora da janela no passo {self.n - 1}: {faltando}")
        return est


# --------------------------------------------------------------------------- CLI

def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="grava goldens do app para tests/conformidade")
    ap.add_argument("casos", nargs="*", type=Path, help="pastas de caso (com cenario.json)")
    ap.add_argument("--todos", action="store_true", help="todos os casos de tests/conformidade")
    ap.add_argument("--forcar", action="store_true", help="regrava golden que ja e do app")
    ap.add_argument("--manter", action="store_true", help="nao derruba o Wine ao terminar")
    ap.add_argument("--sem-motores", action="store_true", help="nao grava o campo motores")
    ap.add_argument("--sem-disjuntores", action="store_true",
                    help="nao fecha os disjuntores (grava o app cru: eles iniciam abertos, motores nao giram)")
    ap.add_argument("--json", nargs="?", const=Path("out/app_sim/goldens.json"), type=Path,
                    help="grava o resumo em JSON (padrao: out/app_sim/goldens.json)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    alvos = list(args.casos)
    if args.todos:
        alvos = casos_com_cenario(ROOT / "tests" / "conformidade")
    if not alvos:
        ap.error("informe pastas de caso ou --todos")

    campos = tuple(c for c in CAMPOS if not (args.sem_motores and c == "motores"))
    res = []
    for caso in alvos:
        print(f"[golden] === {Path(caso).name} ===", flush=True)
        try:
            r = gravar_caso(caso, forcar=args.forcar, verbose=args.verbose, campos=campos,
                            fechar_disjuntores=not args.sem_disjuntores, manter=args.manter)
        except Exception as e:                                  # noqa: BLE001 - registra e segue
            r = {"caso": Path(caso).name, "ok": False, "erro": f"{type(e).__name__}: {e}"}
        res.append(r)
        print(f"[golden] {r}", flush=True)

    destino = args.json
    if destino:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps({"resultados": res}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"[golden] resumo em {destino}")
    ok = sum(1 for r in res if r.get("ok"))
    print(f"GOLDEN: {ok} gravado(s), {sum(1 for r in res if r.get('pulado'))} pulado(s), "
          f"{sum(1 for r in res if r.get('erro'))} erro(s) de {len(res)}", flush=True)
    return 0 if ok or all(r.get("pulado") for r in res) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
