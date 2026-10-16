#!/usr/bin/env python3
"""Parametros de temporizador do CADe_SIMU (RE: docs/re-engenharia.md 11.4), compartilhado entre o
simulador (netlist_sim), o motor de layout e o cad_build.

No .cad o temporizador 9004..9007/9015 guarda: rotulo 4 = UNIDADE, rotulo 5 = TEMPO
(`#-KT1##A1#A2#0#5#` -> unidade '0', tempo 5). O app le o tempo com atoi() e conta TICKS
(1 tick = 100 ms no padrao). Unidade -> ticks por unidade de tempo:
    '3' = x0,1 s (1 tick)   '0' = x1 s (10 ticks)   '1' = x10 s (100)   '2' = x1000 ticks (100 s)
Fracao nao vale: '0.5' vira 0 (comuta no 1o tick).

DSL (campo `params`/4o elemento da folha): {"tempo": 5, "unidade": "0"}  ou  {"segundos": 5}
(o `segundos` escolhe a unidade: inteiro -> '0'; multiplo de 0,1 -> '3'), ou {"rotulos": {"4":"0","5":"5"}}.
"""
import re

CLASSES_TEMPORIZADOR = {"9004", "9005", "9006", "9007", "9015"}
IDX_UNIDADE, IDX_TEMPO = 4, 5               # posicao em labels[] da entidade (0 = rotulo/designacao)
TICK_PADRAO = 0.1                           # s (velocidade de simulacao padrao do app = 50 -> 100 ms)
TICKS_POR_UNIDADE = {"3": 1, "0": 10, "1": 100, "2": 1000}
SEGUNDOS_POR_UNIDADE = {"3": 0.1, "0": 1.0, "1": 10.0, "2": 100.0}
_ALIAS_UNIDADE = {"0,1s": "3", "0.1s": "3", "100ms": "3", "s": "0", "seg": "0", "1s": "0",
                  "10s": "1", "100s": "2", "x60": "2"}


def atoi(v):
    """C atoi: inteiro inicial do texto; resto/nao-numerico -> 0 ('0.5' -> 0, '5s' -> 5, '' -> 0)."""
    m = re.match(r"\s*([+-]?\d+)", str(v if v is not None else ""))
    return int(m.group(1)) if m else 0


def ticks_dos_rotulos(unidade, tempo):
    """(rotulo unidade, rotulo tempo) -> numero de ticks. Unidade desconhecida/vazia: x10 (como '0')."""
    mult = TICKS_POR_UNIDADE.get(str(unidade).strip(), TICKS_POR_UNIDADE["0"])
    return max(atoi(tempo), 0) * mult


def segundos_dos_rotulos(unidade, tempo, tick=TICK_PADRAO):
    return ticks_dos_rotulos(unidade, tempo) * tick


def _unidade(v):
    s = str(v).strip().lower().replace(" ", "")
    if s in TICKS_POR_UNIDADE:
        return s
    if s in _ALIAS_UNIDADE:
        return _ALIAS_UNIDADE[s]
    raise ValueError(f"unidade '{v}' invalida: use '3' (0,1 s), '0' (1 s), '1' (10 s) ou '2' (100 s)")


def parametros_para_rotulos(classe, params):
    """params da DSL -> {indice_do_rotulo: texto}. ValueError com mensagem acionavel."""
    if not isinstance(params, dict):
        raise ValueError(f"params deve ser um objeto JSON, veio {params!r}")
    out = {}
    ch = set(params)
    if "rotulos" in params:
        for k, v in dict(params["rotulos"]).items():
            out[int(k)] = str(v)
        ch.discard("rotulos")
    tempo_like = ch & {"tempo", "unidade", "segundos"}
    if tempo_like and str(classe) not in CLASSES_TEMPORIZADOR:
        raise ValueError(f"params tempo/unidade/segundos so valem em temporizadores "
                         f"({sorted(CLASSES_TEMPORIZADOR)}), nao na classe {classe}")
    if "segundos" in params:
        if {"tempo", "unidade"} & ch:
            raise ValueError("use 'segundos' OU 'tempo'+'unidade', nao os dois")
        s = float(str(params["segundos"]).replace(",", "."))
        if s < 0:
            raise ValueError("segundos deve ser >= 0")
        if abs(s - round(s)) < 1e-9:
            out[IDX_UNIDADE], out[IDX_TEMPO] = "0", str(int(round(s)))
        elif abs(s * 10 - round(s * 10)) < 1e-9:
            out[IDX_UNIDADE], out[IDX_TEMPO] = "3", str(int(round(s * 10)))
        else:
            raise ValueError(f"segundos={s}: o app so conta multiplos de 0,1 s (fracao vira 0)")
        ch.discard("segundos")
    if "unidade" in params:
        out[IDX_UNIDADE] = _unidade(params["unidade"])
        ch.discard("unidade")
    if "tempo" in params:
        t = str(params["tempo"]).strip()
        if not re.fullmatch(r"\d+", t):
            raise ValueError(f"tempo '{params['tempo']}' invalido: o app usa atoi(), so inteiro >= 0 "
                             f"(use unidade '3' para 0,1 s)")
        out[IDX_TEMPO] = t
        ch.discard("tempo")
    if ch:
        raise ValueError(f"params desconhecidos {sorted(ch)}: use tempo, unidade, segundos ou rotulos")
    return out
