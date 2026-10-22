# TODO — 100% funcional (entregas) e ≥80% autônomo (agente)

Dois objetivos diferentes, com critérios diferentes:

- **Eixo A — 100% funcional (tipo entregas A/B)**: qualquer circuito dos padrões da disciplina
  (partida direta, reversão, intercalação, sequencial, emergência, sinalização, CLP/ladder e os
  clássicos de aula) sai do MCP, passa no gate e é **validado no app real** com evidência.
- **Eixo B — ≥80% autônomo**: um agente, recebendo só o MCP + skill (mais um exemplo de referência
  quando o caso permitir), resolve um pedido novo **do zero**, atinge ≥ 80 no `run_eval` e não
  inventa circuito inválido nem classe sem modelo.

Status: `feito` · `andamento` · `todo` · `bloqueado`. Esforço: S (horas) · M (1–2 dias) · L (3+ dias).

## Eixo A — 100% funcional

- [ ] **A1. Ladder/CLP no `cade_sim`** (andamento) — port do `tools/clp_sim.py`: por tick, entradas
  10204, saídas 10205, contatos 10050/10051, bobinas 10060/10061/10062, TON 10066, `bits` e estado.
  - Aceite: `cade gate` num `.cad` de ladder produz o **mesmo texto** do Python nos 5 exemplos
    (`partida_direta`, `reversao`, `intercalada`, `pratica5_complementar`, `partida_sequencial_3`);
    gate de ladder **não** aplica `geo_check` de relé (pino direito aberto por desenho); `saidas_clp`
    preenchido no estado. Custo M.
- [ ] **A2. Conformidade de ladder** — casos `tests/conformidade/ladder_*` com `cenario.json` derivado
  dos T1–T7; gravar `golden_app.json` no app (saídas 10205 + bobinas ladder + lâmpadas).
  - Aceite: `cade conformidade` verde nesses casos; evidência de `Q0.1`/`Q0.2` no app. Custo M.
- [ ] **A3. Instruções de ladder que faltam** — borda 10052/10053, TOF 10067, contador 10063/10075,
  RS 10064, INV/EXOR 10040/10041 (roadmap em `docs/ladder.md` §2.6).
  - Aceite: DSL + modelo lógico + modelo geométrico + caso no app por instrução; teste unitário e
    exemplo em `tools/examples`. Custo L.
- [ ] **A4. Temporizadores elétricos 9007/9015** (intermitente/pulso) + contatos associados.
  - Aceite: caso no app com 9007 (pisca) e 9015 (pulso), lido por imagem; exemplo no gate. Custo M.
- [ ] **A5. Sensores 3 fios (PNP/NPN)** — 56 classes do catálogo (`7501/7502/7504/7505`…); hoje só
  contato de 2 fios.
  - Aceite: modelo de sensor alimentado (pino de alimentação + saída), caso no app com objeto
    detectado, exemplo de partida com sensor. Custo M.
- [ ] **A6. Robustez do app/gravador** — detectar e **fechar o diálogo de CURTO** (hoje o app fica
  bloqueado), registrar `curto:true` no golden; confirmar estado inicial de `6002`/`6003`; medir os
  caracteres do secundário do `3012`.
  - Aceite: cenário com curto grava golden com `curto:true` e segue; 6002/6003 documentados em
    `docs/re-engenharia.md`. Custo S.
- [ ] **A7. Estrela-triângulo** (fora da DSL hoje) — 3 contatores (principal, estrela, triângulo),
  intertravamento e temporizador.
  - Aceite: layout no DSL (ou `cad_build` documentado), exemplo + app. Custo L.
- [ ] **A8. Reversão monofásica** — motor `1008` (`U1 V1 PE U2 V2`), contatores `2002` (4 polos),
  disjuntor `6004`, cruzamento do enrolamento auxiliar.
  - Aceite: modo de ligação no `potencia` (ou `conexoes` de alto nível), exemplo + app. Custo L.
- [ ] **A9. Dispositivos de 4 polos** (`6004`/`2002`) nos exemplos de reversão trifásica — opção
  `polos: 4` no `potencia` (o 4º polo no N), fidelidade ao desenho do professor.
  - Aceite: exemplo `reversao` gera com 6004/2002 e passa no app. Custo S.
- [ ] **A10. GRAFCET (10100+) e pneumática (10500+)** — **bloqueado**: classes sem pinos no binário.
  - Aceite (quando desbloquear): geometria/pinos via Ghidra, modelo, exemplo. Custo L.
- [ ] **A11. Recusa explícita de classe sem modelo** — em vez de simular silenciosamente errado
  (70 classes com `papel:"outro"`, pneumática, GRAFCET, CLPs com imagem).
  - Aceite: `cad_design`/`cade gate` erra com “classe X sem modelo; use …” e lista o que é suportado.
    Custo S.
- [ ] **A12. Regressão das entregas A/B** — manter os `.ladder.json` das entregas como exemplos e
  rodar a validação no app a cada mudança de modelo (roteiro T1–T7).
  - Aceite: `python3 scripts/dev.py gate` + roteiro no app verdes; tempos registrados. Custo S.
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

1. **A1 → A2** (fechar ladder no Rust e a conformidade de ladder) — é o que destrava as entregas.
2. **A6** (curto/6002/3012) — barato e evita golden mentiroso.
3. **A3 → A4** (borda/TOF/contador; 9007/9015) — maior valor didático.
4. **B1 → B2 → B6** (benchmark + `run_eval` ladder + baseline) — mede o 80% desde já.
5. **A5** (sensores 3 fios) → **A7/A8/A9** (clássicos que faltam na DSL).
6. **A11** (recusa explícita) e **B3/B4/B5** (skill, erros, exemplos) em paralelo.
7. **A13** (port restante) e **A10** (Ghidra) por último.

## Definição de pronto

- **A (100%)**: 11/11 relé + 5/5 ladder verdes e conferidos no app; entregas A/B reproduzíveis por
  roteiro; nenhuma classe sem modelo aceita em silêncio; alvos A1–A9 e A11–A12 fechados (A10 só se o
  curso exigir).
- **B (≥80%)**: média ≥ 80 nos 12 held-out, 0 falha dura, tempo ≤ 15 min/caso com o MCP; skill e
  exemplos cobrindo todos os padrões usados no benchmark.

## Riscos

- **Wine/WM**: janela menor que a folha (zoom ~2 px/unidade), diálogos modais e timing de 100 ms —
  sempre gravar com settle e tratar modal.
- **Ghidra**: pneumática/GRAFCET/CLPs com imagem dependem de extrair pinos (um Ghidra por vez, 3 GB).
- **Escopo**: 100% funcional ≠ 100% do catálogo (366 classes). O critério é “os padrões da disciplina
  + tudo que o agente pode pedir”; o resto é recusa explícita.
