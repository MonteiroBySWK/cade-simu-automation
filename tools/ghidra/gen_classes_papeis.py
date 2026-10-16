#!/usr/bin/env python3
"""Gera docs/classes-papeis.json a partir das extrações do binário (srv.java).

Entradas (geradas no scratch, NÃO versionadas — derivam do EXE):
  libnames.json  {classe: [nome, opções do diálogo...]}  (FUN_0087aca0, diálogo de propriedades)
  cmpnames.json  {classe: nome}   (srv `cmpstr 00bd95cc`: CMP [classe_editada],imm + PUSH string)
  sem.json       {classe: {desig, pins, conds, classes, L, W}} (srv `sem` sobre a rotina de desenho)
Uso: python3 tools/ghidra/gen_classes_papeis.py <dir_scratch> > docs/classes-papeis.json
Ver docs/re-engenharia.md §11.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
D = Path(sys.argv[1])
PINOS = json.load(open(ROOT / "docs/pinos-binario.json"))["classes"]
LIB = json.load(open(D / "libnames.json"))
CMP = json.load(open(D / "cmpnames.json"))
SEM = json.load(open(D / "sem.json"))
DISP = sorted(set(int(l.split()[1]) for l in open(D / "disp.txt", encoding="latin1") if l.startswith("  C ")))

TEMPO = {"rotulo_tempo": "label5 (+0x4c3a4; 6o rótulo da entidade) — inteiro via atoi()",
         "rotulo_unidade": "label4 (+0x4a464): '3'=x0,1 s (x1 tick) | '0'=x1 s (x10) | '1'=x10 s (x100) | '2'='x60 Seg' no diálogo mas o código usa x1000 ticks (=100 s)",
         "tick": "1 tick = passada 7 do OnDraw disparada pelo WM_TIMER 1; periodo = 1000-18*velocidade ms (velocidade = DAT_00b80804, opção do app gravada pelo diálogo de opções FUN_00878080 no registro de configuração 'CADe_SIMU*...*%4d$$$' — NÃO está no .cad; padrão 50 => 100 ms)",
         "nota": "atoi: '0.5' vira 0 => comuta no 1o tick. No .cad: '#A1#A2#0#5#' = unidade '0' (s), tempo 5"}


def aba(c):
    if c < 1000: return "Desenho (formas)"
    if 8016 <= c <= 8019: return "Contatos auxiliares, temporizados e relés"
    if c < 1100: return "Motores e cargas de potência"
    if c < 2100: return "Contactores e interruptores (polos de potência)"
    if c < 3100: return "Alimentações"
    if c < 4100: return "Cabos e conexões"
    if c < 5100: return "Fusíveis e seccionadores"
    if c < 6100: return "Proteções (disjuntores, térmico, DR)"
    if c < 7100: return "Contatos auxiliares, temporizados e relés"
    if c < 7700: return "Sensores / detectores"
    if c < 8100: return "Botões, interruptores, fins de curso"
    if c < 8200: return "Painel (botoeira/piloto/LED)"
    if c < 9100: return "Bobinas e sinalização"
    if c < 10100: return "Lógica / Ladder / CLP"
    if c < 10200: return "GRAFCET"
    if c < 10300: return "PLC (LOGO/S7/ET200/Arduino)"
    if c < 10600: return "Pneumática / atuadores"
    return "outro"


def contatos_de(pins, conds, campo="0x78a9c"):
    """Pares (entrada, saída) e condição de fechamento, deduzidos da ordem dos pinos e dos
    testes de estado na etapa de propagação (K campo v)."""
    cs = [int(x.split()[1]) for x in conds if x.split()[0] == campo]
    if len(pins) == 2 and cs:
        return [{"pinos": pins, "fecha_quando": f"estado=={cs[0]}"}]
    if len(pins) == 4 and len(cs) >= 2:  # NA-NC: (11,13,12,14) => 11-12 NC, 13-14 NA
        return [{"pinos": [pins[0], pins[2]], "fecha_quando": f"estado=={cs[0]}"},
                {"pinos": [pins[1], pins[3]], "fecha_quando": f"estado=={cs[1]}"}]
    if len(pins) == 3 and len(cs) >= 2:  # comutado: comum + NC + NA
        return [{"pinos": [pins[0], pins[1]], "fecha_quando": f"estado=={cs[0]}"},
                {"pinos": [pins[0], pins[2]], "fecha_quando": f"estado=={cs[1]}"}]
    if len(pins) in (4, 6, 8) and len(cs) == 1:  # polos: topo i <-> base i
        h = len(pins) // 2
        return [{"pinos": [pins[i], pins[i + h]], "fecha_quando": f"estado=={cs[0]}"} for i in range(h)]
    return None


def classify(c, s):
    """(papel, aciona_por, nota, confianca). Regras por faixa + semântica extraída."""
    pins = s.get("pins", []) if s else []
    conds = s.get("conds", []) if s else []
    cs = [x for x in conds if x.startswith("0x78a9c")]
    na = cs[:1] == ["0x78a9c 1"]
    if c in (1, 2, 3, 4, 5, 6, 8, 9) or c < 1000: return "outro", None, "forma gráfica/figura (sem elétrica)", "alta"
    if 1000 <= c < 1050: return "motor", None, "carga trifásica/mono: gira se fases distintas nos pinos de fase (campo 0x7a9dc = estado de giro)", "media"
    if 1050 <= c < 1100: return "outro", None, "carga/acionamento de potência (resistência, variador, soft-starter, controle)", "baixa"
    if c in (2000, 2001, 2002, 2006, 2008): return ("contato_NA", "label igual ao da bobina (9000/9001/9002/9004..9007/9014/9015/1070..)", "polos principais do contator: conduz topo->base quando estado==1", "alta")
    if c in (2003, 2004, 2005, 2007): return "interruptor", "clique (alterna; propaga a mesmo rótulo)", "interruptor manual de potência", "media"
    if c == 2009: return "outro", None, "sem nome no binário", "baixa"
    if 3000 <= c < 3015: return "fonte", None, "estampa o char de fase no fio do pino: L1->'1', L2->'2', L3->'3', N->'N', PE->'P', +->'+', -->'-'", "alta" if c in (3003, 3004, 3006, 3007, 3011) else "media"
    if 3015 <= c < 3021: return "outro", None, "fonte/conversor especial (transformador, retificador, variador)", "baixa"
    if 4000 <= c < 4100: return "outro", None, "cabo/conexão: 4000/4009/4010/4018/4019 = fios (nó por geometria); 4001/4012 = junção; 4003/4004 = marcador", "alta"
    if 5000 <= c < 5005: return "fusivel", "clique (alterna = queima)", "conduz quando estado==0 (estado inicial 0 => íntegro)", "media"
    if 5005 <= c < 5010: return "interruptor", "clique (alterna)", "seccionador: conduz quando estado==1 (inicial 0 => ABERTO)", "media"
    if c == 6007: return "termico", "clique (dispara; propaga estado aos contatos 8016..8019 de mesmo rótulo)", "polos de potência 1-2/3-4/5-6 SEMPRE conduzem (sem teste de estado)", "alta"
    if 6000 <= c < 6021: return "disjuntor", "clique (alterna; propaga a mesmo rótulo)", "conduz quando estado==1; estado inicial 0 => ABERTO até clicar", "media"
    if c in (7000, 7001, 7002, 7003):
        return ("contato_NA" if c == 7000 else "contato_NC" if c == 7001 else "contato_NA_NC" if c == 7002 else "contato_comutado",
                "label igual ao da bobina (cópia instantânea do estado 0x78a9c)", "contato auxiliar instantâneo", "alta")
    if 7004 <= c < 7016:
        fam = "ON" if c < 7008 else ("OFF" if c < 7012 else "ON_OFF")
        k = (c - 7004) % 4
        tipo = ["NA", "NC", "NA_NC", "comutado"][k]
        return (f"contato_temporizado_{tipo}", f"label igual ao do temporizador (9004 ON / 9005 OFF / 9006 ON-OFF); estado = saída temporizada 0x30e24 do temporizador",
                f"contato temporizado {fam}-delay", "alta" if c in (7004, 7005, 7008, 7009) else "media")
    if 7016 <= c < 7022: return "outro", "label (relé de base/zócalo; 7018 contator com 7019..7021 blocos aditivos)", "relé/contator compacto com blocos de contatos auxiliares ou temporizados", "baixa"
    if 7500 <= c < 7700: return ("sensor_NA" if " NA" in (CMP.get(str(c)) or "") else "sensor_NC" if " NC" in (CMP.get(str(c)) or "") else "sensor"), "clique (momentâneo, estado=1 ao pressionar)", "detector 2/3 fios; contato NA/NC", "baixa"
    if c in (8000, 8004): return "botao_NA", "entrada externa (clique momentâneo: estado=1 enquanto pressionado)", "pulsador NA", "alta" if c == 8000 else "media"
    if c in (8001, 8005): return "botao_NC", "entrada externa (clique momentâneo)", "pulsador NC", "alta" if c == 8001 else "media"
    if c in (8002, 8003, 8006, 8007): return "botao_NA_NC" if c in (8002, 8006) else "botao_comutado", "entrada externa (clique momentâneo)", "pulsador duplo/comutado", "media"
    if c in (8008, 8009, 8010, 8011): return ("interruptor", "clique (alterna, retentivo)", "contato de interruptor/seletor retentivo: " + ["NA", "NC", "NA-NC", "comutado"][c - 8008], "media")
    if 8012 <= c < 8016: return ("fim_de_curso", "entrada externa (clique momentâneo)", "fim de curso " + ["NA", "NC", "NA-NC", "comutado"][c - 8012], "media")
    if c == 8016: return "contato_NA", "label igual ao do relé térmico 6007 (clique no 6007 dispara)", "contato 97-98 do térmico (fecha quando disparado)", "alta"
    if c == 8017: return "contato_NC", "label igual ao do relé térmico 6007 (clique no 6007 dispara)", "contato 95-96 do térmico (abre quando disparado)", "alta"
    if c in (8018, 8019): return ("contato_NA_NC" if c == 8018 else "contato_comutado"), "label igual ao do relé térmico 6007", "contatos 95-96/97-98 do térmico", "media"
    if c == 8020: return "seletor", "clique (alterna)", "seletor 2 posições 11-12/11-14 (estados 1/2)", "baixa"
    if c == 8021: return "seletor", "clique (cicla 0->1->2)", "seletor 3 posições", "media"
    if c in (8022, 8023): return "interruptor", "clique", "chave/botão (8022 alterna; 8023 momentâneo)", "baixa"
    if 8100 <= c < 8104: return ("botao_NA" if c == 8100 else "lampada" if c in (8101, 8103) else "outro"), "clique/painel", "elementos de painel com imagem (pulsador/piloto/LED/botoeira)", "baixa"
    if c in (9000, 9001, 9002, 9014): return "bobina", "energiza com tensão entre os 2 pinos (pares de fase distintos, fase-N ou +/-)", {9000: "bobina monoestável", 9001: "biestável (A1 liga / B1 desliga)", 9002: "telerruptor (alterna a cada pulso)", 9014: "bobina (variante)"}[c], "alta" if c == 9000 else "media"
    if c == 9003: return "bobina", "tensão entre os pinos", "eletroválvula (aciona pneumática por rótulo)", "media"
    if c == 9004: return "temporizador_ON", "tensão entre os pinos", "retardo na energização", "alta"
    if c == 9005: return "temporizador_OFF", "tensão entre os pinos", "OFF-delay (FUN_0062f4e0): borda de energização => estado=1, saida=1, contador=T; desenergizou => estado=0 e, enquanto estado==0 && saida==1, contador-- por tick; <1 => saida=0. Contatos 7008..7011 recebem saida", "alta"
    if c == 9006: return "temporizador_ON_OFF", "tensão entre os pinos", "ON+OFF-delay (FUN_00630d40), mesmo T nos dois sentidos: energizado conta até saida=1; desenergizado conta até saida=0. Contatos 7012..7015 recebem saida", "alta"
    if c == 9007: return "temporizador_intermitente", "tensão entre os pinos", "intermitente (FUN_00632a20): energizado, o ESTADO alterna 1/0 a cada T ticks (meio-período = T); copia estado a polos e a 7000..7015 de mesmo rótulo", "media"
    if c == 9015: return "temporizador_pulso", "tensão entre os pinos", "gerador de pulsos", "baixa"
    if c == 9016: return "outro", "tensão", "contador (A1,C,D,R,A2)", "baixa"
    if c in (9008, 9009): return "lampada", "tensão entre X1 e X2", "sinalização óptica (9009 intermitente)", "alta" if c == 9008 else "media"
    if 9010 <= c < 9014: return "sinalizador", "tensão entre X1 e X2", "sinalização acústica (campainha, buzzer, sirene, buzina)", "media"
    if 9040 <= c < 9046: return "outro", None, "medidores/proteções especiais (L1 L2 L3 N)", "baixa"
    if 10000 <= c < 10100: return "logica", None, "porta lógica / ladder / temporizador CLP (10050 NA, 10051 NC, 10060 bobina)", "baixa" if c not in (10050, 10051, 10060) else "media"
    if 10100 <= c < 10200: return "grafcet", None, "elemento GRAFCET", "baixa"
    if 10200 <= c < 10300: return "plc", None, "CLP/IO", "baixa"
    if 10500 <= c < 10600: return "pneumatica", "eletroválvula 9003 de mesmo rótulo / sensores magnéticos", "atuador pneumático/elétrico", "baixa"
    return "outro", None, "", "baixa"


# classes tocadas pelos handlers Símbolo/2D/3D (FUN_0049fe30/FUN_004a1080/FUN_004a2340); ver docs/3d.md
CLASSES_3D = {1000, 1001, 1076, 4011, 6015, 6016, 6017, 6018, 6019, 6020, 7016, 7017, 7018, 7019, 7020,
              7021, 8100, 8101, 8102, 8103, 10202, 10203, 10204, 10209, 10210, 10211, 10212, 10213,
              10214, 10215, 10220}

FALLBACK = {
    "8016": "Contacto relé térmico NA (97-98)", "8017": "Contacto relé térmico NC (95-96)",
    "8018": "Contacto relé térmico NA-NC (95-96/97-98)", "8019": "Contacto relé térmico conmutado (95-96-98)",
    "8020": "Selector 2 posiciones (11-12-14)", "8021": "Selector 3 posiciones (1-2-3-4)", "8022": "Selector/llave (1-2-3-4)",
    "1008": "Motor (U1 V1 PE U2 V2)", "1009": "Freno (U1 V1 PE)", "1060": "Variador (L1 L2 L3 PE M1 M2 F1 F2)",
    "1063": "Control (I1 I2 A1 A2)", "1065": "Módulo lógico (I1..I4 Q1..Q4)", "1066": "Módulo lógico (I1..I3 Q1..Q4 L+)",
    "1067": "Módulo lógico (I1..I3 Q1..Q4 L+)", "1070": "Relé (A1 A2 1 2)", "1071": "Relé (A1 A2 1 2)",
    "1072": "Contactor compacto con bobina (1-6, A1 A2)", "1073": "Contactor compacto con bobina (1-6, A1 A2)",
    "1074": "Relé con contacto NA (A1 A2 13 14)", "1075": "Relé con contacto conmutado (A1 A2 11 12 14)",
    "2008": "Contactor (1-6)", "3016": "Diodo/dispositivo (13 14)", "3017": "Transformador III (1-6)",
    "3018": "Variador (1-5, PE)", "6011": "Disyuntor II (1 3 / 2 4)", "6012": "Disyuntor IIII (1 3 5 7 / 2 4 6 8)",
    "6013": "Protección (1 2 3)", "6014": "Protección (1-5)", "9014": "Bobina (A1 A2)",
    "9016": "Contador (A1 C D R A2)", "9040": "Medidor (L1 L2 L3 N)", "9041": "Medidor (L1 L2 L3)",
    "9042": "Medidor (L1 L2 L3 N)", "9043": "Medidor (L1 L2 L3)", "9044": "Protección con bobina (1 3 / 2 4, A1 A2)",
    "9045": "Protección IIII (1-8)", "10074": "Decodificador (1 2 4 8 C)",
}

INICIAL ="todos os estados (0x78a9c, 0x7a9dc, 0x2eee4, 0x30e24) = 0 ao iniciar a simulação (FUN_0043d540)"

out = {
    "_nota": ("Semântica de simulação por classe extraída do binário CADe_SIMU 4.0 [BR] "
              "(ver docs/re-engenharia.md §11). Chave = id de classe. pinos = nomes padrão na ordem de "
              "desenho (= p1..pN de docs/pinos-binario.json). contatos[].fecha_quando refere-se ao "
              "estado da PRÓPRIA entidade (+0x78a9c), que é copiado de quem aciona (bobina por rótulo, clique, etc.)."),
    "_modelo": {
        "no": "fios por geometria (§9.2); cada fio carrega 1 char: '0' (sem tensão), '1','2','3' (fases), 'N', 'P' (PE), '+', '-', e marcas de carga em série 'R','S','T','A','B','C','W','Z'",
        "conducao": "elemento fechado copia o char de um lado para o fio do outro lado (se este estiver '0'); duas fases diferentes no mesmo nó = curto",
        "carga_energizada": "bobina/lâmpada/temporizador: par (fase_i, N), (N, fase_i), (fase_i, fase_j i!=j), ('+','-') ou ('-','+') nos 2 pinos; lâmpada aceita também ('+','N') e acende com meia luz em série (pares com 'Z'/'B'...)",
        "acionamento_por_rotulo": "bobina (9000..) na passada 7 copia seu estado a TODAS as entidades com label0 igual (Ordinal_812 = CString ==) e classe em {2000,2001,2002,2006,2008, 7000..7003}; temporizadores também a 7004..7015 (estado temporizado)",
        "relaxacao": "OnDraw percorre todas as entidades 8 vezes (DAT_00bd959c = 0..7); só na passada 7 as bobinas comitam estado e os temporizadores contam",
        "estado_inicial": INICIAL,
        "temporizador": TEMPO,
    },
}

ids = sorted(set(int(k) for k in PINOS) | set(int(k) for k in LIB) | set(int(k) for k in CMP) | set(DISP))
for c in ids:
    k = str(c)
    s = SEM.get(k)
    nome = (LIB.get(k) or [CMP.get(k)])[0]
    papel, aciona, nota, conf = classify(c, s)
    pins = [p for p in (s or {}).get("pins", [])]
    pin_ok = bool(pins) and all(0 < len(p) <= 4 and not p.startswith(("LINE", "+", "-0")) for p in pins)
    e = {"nome": nome, "aba": aba(c), "papel": papel}
    if pin_ok:
        e["pinos"] = pins
    elif k in PINOS:
        e["pinos"] = list(PINOS[k]["pins"].keys())
    if s and s.get("desig"):
        e["designacao_padrao"] = s["desig"]
    if aciona:
        e["aciona_por"] = aciona
    ct = contatos_de(pins, s.get("conds", [])) if (s and pin_ok and papel.startswith(("contato", "botao", "fim", "interruptor", "disjuntor", "fusivel", "seletor", "sensor"))) else None
    if c == 6007:
        ct = [{"pinos": ["1", "2"], "fecha_quando": "sempre"}, {"pinos": ["3", "4"], "fecha_quando": "sempre"}, {"pinos": ["5", "6"], "fecha_quando": "sempre"}]
    if ct:
        e["contatos"] = ct
    e["estado_inicial"] = 0
    if papel.startswith("temporizador") or c in (10066, 10067, 10068, 10069, 10081, 7017):
        e["parametros"] = {"tempo": "label5", "unidade": "label4", "ver": "_modelo.temporizador"}
    if papel in ("lampada", "sinalizador") and c in (9008, 9009):
        e["parametros"] = {"cor": "rótulo comparado com nomes de cor (Ordinal_813) — afeta só o desenho"}
    if c in CLASSES_3D:
        opts = (LIB.get(k) or [None])[1:]
        e["representacao"] = {"campo": "n16 (+0x177e4)", "opcoes_dialogo": opts,
                              "3d": "botão 3D (cmd 33360, FUN_004a2340) troca n16 p/ o índice 'Imagen 3D' da variante; 0 = Símbolo (padrão do gerador)"}
    if nota:
        e["nota"] = nota
    ev = []
    if k in PINOS and PINOS[k].get("func"): ev.append("desenho/sim FUN_00" + PINOS[k]["func"])
    if k in LIB: ev.append("nome FUN_0087aca0")
    elif k in CMP: ev.append("nome cmpstr")
    e["evidencia"] = "; ".join(ev) or "dispatch FUN_0040d2b0"
    if nome is None:
        e["nome"] = FALLBACK.get(k)
        e["nome_ausente_no_binario"] = True  # nome deduzido (pinos/rótulo/resources), não lido de string da classe
    e["confianca"] = conf
    out[k] = e

# evidência pontual (funções decompiladas linha a linha)
PONT = {"9000": "FUN_006292a0", "9004": "FUN_0062dbe0", "9008": "FUN_006367b0", "7000": "FUN_005b00d0",
        "7001": "FUN_005b10e0", "7004": "FUN_005b54d0", "8000": "FUN_005ea9b0", "8001": "FUN_005ec030",
        "8016": "FUN_0061b2a0", "8017": "FUN_0061ca70", "6007": "FUN_005727b0", "2001": "FUN_00516240"}
for k, f in PONT.items():
    out[k]["evidencia"] = f + " (decompilada); " + out[k]["evidencia"]
for k in ("8000", "8001", "8004", "8005", "8012", "8013"):
    out[k]["nota"] += "; clique em FUN_0043ee20 (pressionar => estado=1 e propaga a mesmo rótulo)"
json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
print()
