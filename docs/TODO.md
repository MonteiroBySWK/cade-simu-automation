# TODO — 100% funcional (entregas) e ≥80% autônomo (agente)

Dois objetivos diferentes, com critérios diferentes:

- **Eixo A — 100% funcional (tipo entregas A/B)**: qualquer circuito dos padrões da disciplina
  (partida direta, reversão, intercalação, sequencial, emergência, sinalização, CLP/ladder e os
  clássicos de aula) sai do MCP, passa no gate e é **validado no app real** com evidência.
- **Eixo B — ≥80% autônomo**: um agente, recebendo só o MCP + skill (mais um exemplo de referência
  quando o caso permitir), resolve um pedido novo **do zero**, atinge ≥ 80 no `run_eval` e não
  inventa circuito inválido nem classe sem modelo.

Status: `feito` · `andamento` · `todo` · `bloqueado`. Esforço: S (horas) · M (1–2 dias) · L (3+ dias).
Escopo: `núcleo` (obrigatório para as entregas) · `recomendado` (livro/IEC) · `opcional` (fora das refs).

## Escopo adequado (decisão pelas referências da disciplina)

Evidência nos 7 PDFs que você baixou (`out/bibliografia/`, texto extraído):

- **Núcleo (obrigatório)** — aparece explicitamente no material:
  - partida direta; **reversão trifásica** (o desenho do professor usa `6004`/`2002`, 4 polos);
  - **reversão monofásica** (documento próprio de 6 páginas + desenho CADe, motor `1008`);
  - **intercalação com CLP** + RT1/RT2 + H1–H4 + intertravamento geral + T1–T7 (atividade da UEMA);
  - partida sequencial com TON (entrega B, 3 motores);
  - emergência e sinalização; ladder NA/NF + OUT/SET/RST + TON.
- **Recomendado** — está no livro (LD/IEC) ou é padrão de curso, mas **não** nas atividades dadas:
  contato de borda, contador, TOF; sensores 3 fios (o material só cita “sensor” como realimentação).
- **Fora do escopo da disciplina** (não exigir para o “100% funcional”):
  - **estrela-triângulo**: **zero menções** nos 7 documentos;
  - **GRAFCET/pneumática**: só teoria no Miyagi (apêndice SFC), nenhuma atividade;
  - **simular inversor de frequência**: o material explica (5 páginas), mas o CADe_SIMU **não tem
    classe de inversor** — o adequado é a explicação teórica (já na skill), não o desenho;
  - as 70 classes com `papel:"outro"` e os CLPs “com imagem”.

Consequência: A7 (estrela-triângulo) e A10 (GRAFCET/pneumática) saem do caminho crítico; A8/A9
(monofásico/4 polos) entram no núcleo por evidência direta; A3/A4/A5 ficam como recomendados.

## Eixo A — 100% funcional

- [ ] **A1. Ladder/CLP no `cade_sim`** (andamento) — port do `tools/clp_sim.py`: por tick, entradas
  10204, saídas 10205, contatos 10050/10051, bobinas 10060/10061/10062, TON 10066, `bits` e estado.
  - Aceite: `cade gate` num `.cad` de ladder produz o **mesmo texto** do Python nos 5 exemplos
    (`partida_direta`, `reversao`, `intercalada`, `pratica5_complementar`, `partida_sequencial_3`);
    gate de ladder **não** aplica `geo_check` de relé (pino direito aberto por desenho); `saidas_clp`
    preenchido no estado. Custo M.
- [parcial] **A2. Conformidade de ladder** — casos `tests/conformidade/ladder_*` gerados por
  `tools/ladder_conformance.py`; golden do app com `--leituras 5 --settle 0.8 --sem-motores`.
  **Feito**: `ladder_partida_direta` e `ladder_reversao` (combinacionais) verdes em `cade conformidade`.
  **Pendente**: casos com temporizador/oscilação (`intercalada`, `partida_sequencial_3`,
  `pratica5_complementar`) — a comparação instantânea não serve (o app repinta em ticks e o relógio
  real não bate tick a tick); precisa de comparação por **janela** (conjunto de saídas ao longo de N
  ticks). Os goldens desses casos foram removidos para não gerar divergente falso.
- [parcial] **A3. Instruções de ladder que faltam** (`recomendado`) — borda 10052/10053 (`SUBIDA`/`DESCIDA`),
  TOF 10067 e contador 10063: DSL (`ladder/1`) + modelo lógico + modelo geométrico + port Rust
  (`cade_sim::ladder`), 3 exemplos em `tools/examples` com testes por tick, paridade Rust×Python e
  `GATE: OK` (Python e `cade gate`). Falta: caso no **app** por instrução (modelo segue o RE §13,
  ainda não medido no app); RS 10064, INV/EXOR 10040/10041, TOF/TP 10068/10069/10081 e up-down 10075
  continuam sem modelo (recusados com erro claro pela A11).
  - Aceite: DSL + modelo lógico + modelo geométrico + caso no app por instrução; teste unitário e
    exemplo em `tools/examples`. Custo M (era L; o layout de 4 pinos do 10063 saiu com o R ligado
    via contato a partir do trilho e o D sem fio).
- [ ] **A4. Temporizadores elétricos 9007/9015** (`recomendado`) (intermitente/pulso) + contatos associados.
  - Aceite: caso no app com 9007 (pisca) e 9015 (pulso), lido por imagem; exemplo no gate. Custo M.
- [ ] **A5. Sensores 3 fios (PNP/NPN)** (`recomendado`) — 56 classes do catálogo (`7501/7502/7504/7505`…); hoje só
  contato de 2 fios.
  - Aceite: modelo de sensor alimentado (pino de alimentação + saída), caso no app com objeto
    detectado, exemplo de partida com sensor. Custo M.
- [x] **A6a. Diálogo de CURTO** — o aviso é uma **janela separada** ('Erro', ~150x82); `AppSim`
  detecta (`janela_dialogo`), fecha (Return e, se preciso, clique no OK) e o gravador marca
  `curto:true` no passo. Testado no app (modal detectado/fechado) + teste unitário.
- [x] **A6b. 6002/6003 e caracteres do `3012`** — `6002`/`6003` confirmados ABERTOS no app (22/10/2026);
  chars do secundário do `3012` seguem assumidos L/N (funciona; medir exige instrumentar o app).
- [ ] **A7. Estrela-triângulo** (`opcional` — fora das refs) — 3 contatores (principal, estrela, triângulo),
  intertravamento e temporizador.
  - Aceite: layout no DSL (ou `cad_build` documentado), exemplo + app. Custo L.
- [x] **A8. Reversão monofásica** (`núcleo`) — motor `1008` (`U1 V1 PE U2 V2`), contatores `2002` (4 polos),
  disjuntor `6002`, cruzamento do enrolamento auxiliar.
  - Aceite: modo de ligação no `potencia` (`tipo:"monofasico"`, ou `conexoes` de alto nível), exemplo + app. Custo L.
  - Entregue (22/10/2026, sem Wine): `potencia` com `tipo:"monofasico"` (`tools/layout.py:_potencia_mono`;
    Q1 `6002` + 2×`2002` em paralelo + `1008`; KM1 referência, KM2 cruza V1/V2), exemplo
    `tools/examples/reversao_monofasica.layout.json` (GATE OK, 10 testes, FIOS/GEO ok, nets conferidas por
    geometria); `2002`/`6002`/`6004` com protótipo em `tools/symbol_lib.json` e modelo no `netlist_sim`.
    Pendente: validar sentido de giro no app (Wine).
- [x] **A9. Dispositivos de 4 polos** (`núcleo`) — opção `polos: 4` (`6004`/`2002`, 4º polo no N).
  **Validado no app** (`reversao_4polos`: S1→KM1+M1, S2→KM2, intertravamento). Pendente: port Rust (A13).
  - Entregue (22/10/2026, sem Wine): `polos: 4` no `potencia` (`tools/layout.py`; linhas = fases+[neutro];
    `6004`+`2002`; `ordem` com N reto; bypass do N em estágio simples de 3 polos; erro claro sem 4 polos);
    exemplo `tools/examples/reversao_4polos.layout.json` (GATE OK, 13 testes; `reversao` original intacto).
    Pendente: validar no app (Wine).
- [ ] **A10. GRAFCET (10100+) e pneumática (10500+)** (`opcional`) — **bloqueado**: classes sem pinos no binário.
  - Aceite (quando desbloquear): geometria/pinos via Ghidra, modelo, exemplo. Custo L.
- [ ] **A11. Recusa explícita de classe sem modelo** — em vez de simular silenciosamente errado
  (70 classes com `papel:"outro"`, pneumática, GRAFCET, CLPs com imagem).
  - Aceite: `cad_design`/`cade gate` erra com “classe X sem modelo; use …” e lista o que é suportado.
    Custo S.
- [x] **A12. Regressão das entregas A/B** — `pratica5_complementar` e `partida_sequencial_3` são exemplos do
  repo e o `dev.py gate` roda os T1–T7 a cada mudança; as entregas foram validadas no app antes (handoff).
  Pendente: re-rodar o roteiro no app se o modelo mudar de propósito.
- [ ] **A13. Port restante (100% Rust)** — `cade_render` (preview PNG), `cade_mcp` (stdio +
  `cade install-mcp`), `cade_app` (Wine), `cade_vision` (detector), `cade_maint`.
  - Aceite: MCP roda sem Python; depois PR apagando `tools/*.py`. Custo L.

## Eixo B — ≥80% autônomo

- [ ] **B1. Benchmark held-out (12 casos)** — `tools/eval/heldout/` com enunciados em PT-BR, sem
  solução no repo; cobrir: direta, reversão, intercalação, sequencial, emergência, sinalização,
  térmico, ladder simples, ladder com TON, sensor, monofásico, estrela-triângulo.
  - Aceite: 12 casos congelados; nenhum “golden” visível ao agente. Custo M.
- [ ] **B2. `run_eval` pontuar ladder** — hoje os `.ladder.json` de `tools/eval/casos/ladder/`
  ficam fora (o scorer só entende relé).
  - Aceite: `run_eval --golden` inclui os 5 ladder com 100; caso held-out de ladder scoreia. Custo M.
- [ ] **B3. Protocolo do agente na skill** — fluxo obrigatório: tabela de I/O → layout → `cad_design`
  → `cad_preview` → (opcional) app; fatos do app (disjuntor aberto, um ponteiro), reversão
  monofásica × trifásica, inversor fora de escopo, limites do gate.
  - Aceite: skill revisada + `cad_examples` com 1 molde por padrão. Custo S.
- [ ] **B4. Erros acionáveis** — toda falha do gate com “o que fazer” (pino solto, curto, sem testes,
  classe sem modelo, teste com chave inexistente). Custo S.
- [ ] **B5. Biblioteca de exemplos (few-shot)** — 7 relé + 5 ladder + monofásico + estrela-triângulo,
  todos `GATE: OK` e validados no app; `cad_examples` lista com resumo de 1 linha.
  - Aceite: `dev.py gate` 100% e nenhum exemplo “só no papel”. Custo M.
- [ ] **B6. Medição do baseline** — rodar 12 held-out com o agente atual, registrar score, falhas e
  tempo; repetir após cada melhoria.
  - Aceite: planilha/markdown com antes/depois; meta ≥ 80 (média) e 0 falha dura (arquivo inválido,
    crash, classe inventada). Custo M.
- [ ] **B7. Loop de melhoria** — cada falha do benchmark vira: correção na skill, mensagem de erro,
  exemplo novo ou feature de DSL; re-medir.
  - Aceite: 2 ciclos completos; score sobe monotonicamente. Custo contínuo.
- [ ] **B8. Determinismo e custo** — mesma entrada ⇒ mesmo `.cad`; gate < 1 s; sem GUI no caminho
  crítico; Docker 3,18 MB roda `conformidade`/`gate`.
  - Aceite: teste de determinismo; benchmark de tempo no CI. Custo S.

## Mapa das lacunas de RE → itens

| lacuna (confiança) | item |
|---|---|
| ladder: borda/TOF/contador/RS/INV-XOR (alta semântica, falta modelo) | A3 |
| 9007 intermitente / 9015 pulso (média) | A4 |
| sensores 3 fios PNP/NPN (56 classes, baixa) | A5 |
| curto bloqueia o app; 6002/6003; chars do `3012` (média) | A6 |
| estrela-triângulo (fora da DSL) | A7 |
| reversão monofásica `1008`+`2002`+`6004` (fora da DSL) | A8 |
| 4 polos `6004`/`2002` (cosmético/estilo) | A9 |
| pneumática `10500+` e GRAFCET `10100+` (sem pinos) | A10 |
| 70 classes `papel:"outro"` / CLPs com imagem (sem modelo) | A11 |
| leitura por imagem: texto/valor de timer, display 7 seg, seletor, sentido de rotação | A2/A6 (evidência) |
| acervo de 115 `.cad` não é golden | A12/B1 |

## Ordem sugerida (agora)

1. **A1 → A2** (fechar ladder no Rust e a conformidade de ladder) — destrava as entregas.
2. **A6** (curto/6002/3012) — barato e evita golden mentiroso.
3. **A8 → A9** (reversão monofásica e 4 polos) — núcleo por evidência no material.
4. **B1 → B2 → B6** (benchmark + `run_eval` ladder + baseline) — mede o 80% desde já.
5. **A3 → A5** (borda/TOF/contador; sensores 3 fios) — recomendados.
6. **A11** (recusa explícita) e **B3/B4/B5** (skill, erros, exemplos) em paralelo.
7. **A13** (port restante); **A7/A10** só se o professor pedir (opcionais).

## Definição de pronto

- **A (100% funcional, núcleo)**: 11/11 relé + 5/5 ladder verdes e conferidos no app; entregas A/B
  reproduzíveis por roteiro; **A8 (monofásico)** e **A9 (4 polos)** entregues; nenhuma classe sem
  modelo aceita em silêncio. A3/A4/A5 são “recomendados” (não bloqueiam); A7/A10 ficam fora.
- **B (≥80%)**: média ≥ 80 nos 12 held-out, 0 falha dura, tempo ≤ 15 min/caso com o MCP; skill e
  exemplos cobrindo todos os padrões usados no benchmark.

## Riscos

- **Wine/WM**: janela menor que a folha (zoom ~2 px/unidade), diálogos modais e timing de 100 ms —
  sempre gravar com settle e tratar modal.
- **Ghidra**: pneumática/GRAFCET/CLPs com imagem dependem de extrair pinos (um Ghidra por vez, 3 GB).
- **Escopo**: 100% funcional ≠ 100% do catálogo (366 classes). O critério é “os padrões da disciplina
  + tudo que o agente pode pedir”; o resto é recusa explícita.
