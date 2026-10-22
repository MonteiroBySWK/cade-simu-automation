# Verificador E2E no app (`tools/app_sim.py`) — 15/10/2026

Fecha o laço com a **verdade do app**: abre o `.cad` no CADe_SIMU (Wine), dá Play, aciona as
entradas e **lê o estado por imagem**. O `netlist_sim`/`cad_test` é um *modelo*; aqui é o próprio
simulador do CADe_SIMU que responde.

```bash
python3 tools/app_sim.py out/x.cad                                   # abre, Play, estado de repouso
python3 tools/app_sim.py out/x.cad --layout tools/examples/x.layout.json   # roda os "testes" da spec
python3 tools/app_sim.py out/x.cad --layout spec.json --saida out/app_sim/x -v --json
```
Biblioteca: `app_sim.executar_casos(cad, casos, aliases=None)` → `{ok, repouso, casos[], tempo_s, ...}`;
classe `AppSim` com `abrir()/play()/stop()/zoom_todo()/pressionar(rotulo, segurar_s)/soltar()/
alternar(rotulo)/screenshot()/estado()/fechar()`. MCP: `cad_simular_no_app(path, casos_json)`.
Screenshots por caso em `out/app_sim/<nome>/` (gitignored). Sempre dá `down` ao terminar — mas **só
no Wine que ele mesmo subiu** (se já há CADe_SIMU rodando de outro agente, espera até 120 s e desiste).

## Como funciona

1. **Abertura robusta** (`AppSim.abrir`): copia o `.cad` como `app_sim.cad` no diretório do EXE, sobe
   o Wine, digita a senha 4962 **uma vez por aparição do teclado** e só considera "pronto" quando a
   toolbar está ativa (botão Play verde; diálogo modal deixa tudo cinza). Se o app morrer
   ("Erro de acesso Key") ou estourar 70 s: `down` + nova tentativa (até 3). ~20 s.
2. **Vista**: depois do Play usa *Ver > Zoom Todo* (folha inteira a 1 px/unidade). A vista pode
   variar (o app abre a 2 px/unid. com scroll; janela pode ter 523 ou 1052 px de altura), então
3. **Calibração coordenada→pixel a cada screenshot**: os fios (`4000`) do próprio `.cad` são
   rasterizados em escalas candidatas (1, 2, 1,5, 0,5, ...) e correlacionados por FFT com os pixels
   de tinta da imagem (ignorando o cinza sólido do fundo MDI): `px = ox + s·(x − xmin)`. Aceita com
   ≥ 85 % dos fios sobre tinta; salva `out/app_sim/calibracao.json`. Medido: **escala 1 → ox=32, oy=102**
   (Zoom Todo) e **escala 2 → ox=31, oy=102** (zoom normal). ~0,2–0,4 s por screenshot.
   A barra de status (`X=…,Y=…`) **não** serve: está em outra unidade (≈ 3,3 × a unidade do `.cad`).
4. **Leitura** (`ler_estado`): região do símbolo = caixa dos pinos (± 5 unidades; motor + disco).
   Cores medidas (sem antialias, valores exatos):

   | cor | significado |
   |---|---|
   | vermelho puro `(255,0,0)` | **símbolo ATIVO**: contato acionado (NA fechado / NF aberto), bobina energizada, lâmpada acesa, botoeira pressionada, disjuntor ligado, térmico disparado |
   | cinza `(192,192,192)` sólido | enchimento de **bobina energizada** e de **motor energizado** (os pontos da grade também são 192: conta só pixels com 8 vizinhos iguais) |
   | cinza `(128,128,128)` | fio/símbolo sem tensão (em simulação tudo é cinza) |
   | vinho `(128,0,0)` | fio ligado à fase L1/L2/L3 (as três são iguais) |
   | azul `(0,0,255)` / verde `(0,128,0)` | fio no neutro N / no PE |

   Observação-chave: **vermelho = "estado ON" do símbolo, não "tem tensão"** (um contato NF fechado
   em repouso fica cinza; o contator de potência fica vermelho com o disjuntor aberto e sem tensão a
   montante). Por isso o verificador reporta *bobinas ativas* e *lâmpadas acesas* (o que os
   `esperado` descrevem) e não "contato fechado".
5. **Acionamento**: botoeira (`8000/8001`) = `mousedown` no centro do corpo, segura, lê, `mouseup`
   (um ponteiro só: com 2 botoeiras só a última fica segurada, a outra leva um pulso). Disjuntor
   (`6009/6010`) e relé térmico (`6007`) = clique alterna. Entre casos: `stop`+`play` (zera
   bobinas, disjuntores, térmico).
6. **`inicial`** (selo): BFS no app — pulsa as botoeiras (profundidade ≤ 2, ≤ 24 probes) até as
   bobinas chegarem ao estado pedido; a sequência é reaplicada antes das entradas do caso.

## Achados sobre o app (verificados)

- **Relé térmico**: o contato `8017` (NF) / `8016` (NA) é ligado ao `6007` **pelo mesmo rótulo**.
  O disparo é um clique no `6007`; o contato de mesmo rótulo acompanha (vermelho = disparado).
  Com rótulos diferentes (`-RT1` no contato, `-F1` no `6007`, como nos exemplos atuais) **o app não
  tem como disparar o térmico** — clicar no contato não faz nada (testado: clique, segurar, botão
  direito, duplo-clique) e clicar no `6007` não afeta o `-RT1`. Confirmado trocando `-RT1` por `-F1`
  no contato: F1 disparado → `S1` não liga KM1; F1 de novo → liga. (No acervo, `Arranque_1.cad` usa
  `-F2` nos três.) O `netlist_sim` trata `RT1` como entrada livre, então **não vê** esse defeito.
- **Disjuntor `6009`**: começa aberto a cada Play; sem ligá-lo (clique) a potência fica sem tensão
  (fios cinza, motor parado). Os testes das specs não o exercitam (só comando).
- **Motor** energizado = disco cinza sólido (192) + `Q1`/contator vermelhos.
- **Folha**: com a calibração por fios deu para medir a moldura verde em unidades do `.cad`:
  externa x∈[20,467], y∈[−1,332] (≈ 447 × 333), interna x∈[23,464], y∈[2,329]; legenda em
  y ≈ 311–329. `tools/sheet.json` (960×750) está em **outra unidade** (status do app ≈ 3,3×) e
  superestima a folha em ~2,2×: ver nota em "Divergências".
- Zoom do app: *Ver > Zoom Todo* → 1 px/unid.; *Zoom Normal* → 2 px/unid. O botão de lupa da
  toolbar (703,32) liga uma vista "3D" do motor; o scroll é pela roda do mouse.

## Resultados (app × netlist)

Netlist = o `esperado` dos `testes` (o gate `build_spec` passou 6/6, 6/6 e 13/13 antes desta
rodada). App = leitura por imagem, Wine real. Tempo total por circuito: **partida_direta ~50 s**,
**partida_sinalizacao ~50 s**, **reversao ~85 s** (≈ 20 s de abertura + 3–6 s por caso; casos com
`inicial` custam mais por causa do replay).

| circuito | caso | netlist | app | resultado |
|---|---|---|---|---|
| partida_direta | repouso desligado | — | — | ok |
| partida_direta | S1 liga KM1 | KM1 | KM1 (+H1) | ok |
| partida_direta | selo mantem KM1 | KM1 | KM1 (+H1) | ok |
| partida_direta | S0 desliga | — | — | ok |
| partida_direta | sem auto-religamento | — | — | ok |
| partida_direta | RT1 aberto bloqueia | — | **não acionável** | divergência (circuito, ver §Divergências 1) |
| partida_sinalizacao | repouso / S1 / selo / S0 / sem auto-religamento | = | = (H1 acompanha KM1) | ok (5/5) |
| partida_sinalizacao | RT1 aberto bloqueia | — | **não acionável** | divergência (idem) |
| reversao | repouso | — | — | ok |
| reversao | S1 liga KM1 / S2 liga KM2 | KM1 / KM2 | KM1+H1 / KM2+H2 | ok |
| reversao | selo KM1 / selo KM2 | KM1 / KM2 | KM1 / KM2 | ok |
| reversao | intertravamento S2 com KM1 / S1 com KM2 | KM1 / KM2 | KM1 / KM2 | ok |
| reversao | S0 desliga KM1 / KM2 | — | — | ok |
| reversao | sem auto-religamento | — | — | ok |
| reversao | RT1 aberto bloqueia S1 / S2; RT1 aberto desliga KM1 | — | **não acionável** | divergência (idem) |
| partida_direta com `-RT1`→`-F1` no contato (`out/app_sim/pd_f1.cad`) | os 6 (RT1→F1) | = | = (6/6) | ok — térmico dispara de verdade |

**Placar**: 10/10 casos não-térmicos coincidem em partida_direta + sinalização; 10/10 em reversao
(incluindo selo, intertravamento e estados `inicial` obtidos apertando botões no app). Os 5 casos de
térmico não são avaliáveis nos exemplos como estão.

Também confirmado: remover a entidade 0 herdada do doador (fonte `3004 -X` solta em x=93,y=45, os
"4 pinhos soltos") — região x∈[88,112], y∈[38,68] tinha 64 px de tinta no `.cad` antigo e **0** nos
`.cad` regenerados; simulação idêntica (mesmos casos, mesmos resultados).

## Divergências e candidatos a bug

1. **Térmico `-RT1` (8017) × `-F1` (6007) — bug do circuito/DSL, invisível ao netlist.** O app só
   liga o contato ao `6007` de mesmo rótulo; nos exemplos (`partida_direta`, `partida_sinalizacao`,
   `reversao`, e provavelmente `intercalada`/`emergencia`/`dois_motores`) o rótulo difere, então o
   térmico **nunca dispara** no app. Correção sugerida (em `layout.py`/skill/DSL, fora do meu
   escopo): usar o MESMO rótulo no contato e no `6007` (e a chave de teste passa a ser esse rótulo,
   ex.: `F1`), ou o motor emitir o contato com o rótulo do térmico de potência. Verificado em
   `out/app_sim/pd_f1.cad`: 6/6 no app. O verificador reporta `nao_acionavel` com o motivo.
2. **`tools/sheet.json` / `docs/folha.md` em unidade errada.** A barra de status do app mostra
   ≈ 3,3 × a unidade das entidades; os "980 × 770" são unidades de status. A moldura medida em
   unidades do `.cad` (Zoom Todo, `reversao`): x∈[20,467], y∈[−1,332]; legenda y ≈ 311–329. Um
   layout com y>330 ou x>465 sai da folha (o app abre, mas fora da moldura). Candidato a correção
   de `sheet.json` (e do clamp em `layout.py`) — **precisa confirmar com a moldura de outro
   arquivo** (folha.md: a moldura depende do rodapé/legenda).
3. **Botoeiras simultâneas** (`S1`+`S2` juntas, status `RACE`): não reproduzível (ponteiro único);
   o verificador pulsa as anteriores e segura só a última, e marca `RACE` como `ignorado`.
4. **Sem divergência de lógica** (app × netlist) nos 20 casos avaliáveis (+6 do `pd_f1`): bobinas e lâmpadas
   coincidem exatamente.

## O que lê com confiança e o que não

- **Confiança alta**: bobina energizada, lâmpada acesa, contato/botoeira/disjuntor/térmico ativos
  (vermelho puro), motor energizado (enchimento cinza + vermelho) — cores exatas, sem antialias,
  calibração por fios (cobertura ≥ 99 %).
- **Não lê / limitações**: *contato aberto vs fechado* em si (só "acionado" vs repouso: NF fechado
  em repouso e NA aberto são ambos cinza); *tensão* num ponto (só a fase do fio por cor, não
  exposta); temporizadores, contadores e outras classes ainda não calibradas (`tipo: outro`:
  lido só por vermelho); circuitos com símbolos fora da folha (reportados em `fora_da_janela`);
  duas botoeiras realmente simultâneas; classes de CLP/ladder (10050…) não testadas.
- **Fragilidades**: depende de Wine+X11 (xdotool move o ponteiro real do usuário); o popup do menu
  *Ver* é clicado por posição fixa (+197,+19 da janela); posições dos botões Play/Stop são fixas
  em px à esquerda da toolbar; `inicial` inalcançável por botões → `indeterminado`.

### Calibracao em circuitos com poucos fios (22/10/2026)
A correlacao de fios sozinha pode escolher um **pico falso** (`fios_sobre_tinta` > 1 = mais acertos
que pixels da mascara). O `calibrar` agora **rejeita `cob > 1.05`** e exige que >= 60% dos simbolos
tenham tinta na posicao prevista (`_confere_simbolos`). Caso real: `9004+7004+lampada` calibrava em
(ox=30, oy=50) e lia tudo apagado; com a correcao acha (31,102) e le 9004/7004/H1 vermelhos (112/75/109 px).

