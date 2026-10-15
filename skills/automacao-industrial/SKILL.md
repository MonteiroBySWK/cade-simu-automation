---
name: automacao-industrial
description: Projetar, montar e validar circuitos CADe_SIMU 4.0 (.cad) por código/agente — disciplina de Automação Industrial (partidas, selo, intertravamento, proteção térmica, sinalização) + disciplina CADe_SIMU (modelo de NETs, geometria de pinos, layout, autoria via MCP). Use quando o pedido envolver .cad, CADe_SIMU, CLP/Ladder, partida de motores, relé térmico, intertravamento ou quadro de comando.
---

# Skill: Automação Industrial × CADe_SIMU

Duas disciplinas andando juntas. **Automação** diz *o que* o circuito deve fazer;
**CADe** diz *como* representá-lo para abrir **e simular**.

## Quando usar
- Criar/editar `.cad` (do zero, de imagem ou de circuito existente).
- Resolver questões de Automação (partidas direta/reversão/estrela-triângulo/intercalada, proteções, sinalização).
- Verificar lógica de comando (permissões, selos, intertravamentos).

---

## Parte A — Disciplina de Automação Industrial

### Blocos-padrão
| Função | Como montar |
|---|---|
| **Selo (retenção)** | contato **NA** do próprio contator em **paralelo** com o botão de liga |
| **Intertravamento** | contato **NF** do outro contator **em série** no comando |
| **Proteção térmica** | NF do RT (95-96) **em série**; `PERMISSÃO = RT1_OK E RT2_OK` |
| **Sinalização** | piloto de funcionamento em **paralelo** com a bobina; falha em série com NA 97-98 |
| **Sem auto-religamento** | selo cai com o desligamento; retomada exige novo comando |
| **Parada de emergência** | NF dedicado **em série**, à esquerda de tudo (primeiro da cadeia) |

### Regra de ouro do comando
`trilho_L → [proteções NF em série] → [liga ∥ selo] → [intertravamentos NF] → bobina → trilho_N`
Todo elemento em **série** só passa se fechado; todo **paralelo** liga se *qualquer* ramo fechar.

### Checklists
- Partida direta: F2(DJ) + RT + S0(desliga NF) + S1(liga NA) + KM1 + selo + H.
- Reversão: dois contatores com NF cruzado (intertravamento) + botões distintos + selos.
- Intercalada/estrela-triângulo: temporização (blocos `T`) ou lógica de sequência.
- Proteção: RT em cada motor; permissão em série; nunca deixar motor sem térmico.

---

## Parte B — Disciplina CADe_SIMU

### Modelo de conexão (o que faz SIMULAR)
A conectividade é dada por **NETs** (inteiros). Cada símbolo tem pinos `A`/`B`
(campos `nums[21]`,`nums[22]`); fios (`4000`) também carregam um net.
Dois pontos com o **mesmo número de net estão conectados**. Fio avulso não conecta:
o que conecta é o net compartilhado (e a geometria — fio tocando o pino).

**Geometria de pinos aprendida dos exemplos:** `tools/symbol_pins.json`
(105 classes; offsets de `A`/`B` relativos a `X,Y`). Ex.: `7000` A=(0,-6) B=(0,18);
`8017` A=(0,-3) B=(0,15); `9000` (bobina) A=(0,0) B=(0,12); `9008` A=(0,0) B=(0,12).
Regerar: `python3 tools/learn_pins.py` (varre o acervo de 115 `.cad`).

### Layout
- Comando na faixa `x∈[40,320]`, `y∈[20,150]`; **potência abaixo** (`y≥160`).
- **Símbolos de potência** (`6007` térmico, `6009`/`6010` DJ, `2001` contator, `1000` motor)
  têm os pinos A/B no **mesmo lado** → **empilhe na HORIZONTAL** (fileira com
  espaçamento ≥40 em `x`), nunca em cascata vertical (o roteador auto fecharia
  curto). Contatos de comando (`7000`/`7001`/`8000`/`8001`/`8017`) têm A em cima,
  B embaixo (cascata vertical OK).
- `cad_preview` recorta ao conteúdo (canvas automático) — layouts um pouco maiores ok.

### Autoria via MCP (regra de ouro: nunca escrever `*`/`#` na mão)
Atenção: `cad_build` recebe **strings** (JSON escapado) — passe `simbolos_json`,
`conexoes_json` e `fios_json` como *strings*, não arrays.
```bash
python3 tools/mcp_call.py cad_symbols
python3 tools/mcp_call.py cad_build '<json>'
python3 tools/mcp_call.py cad_validate '{"path":"out/x.cad"}'
python3 tools/mcp_call.py cad_inspect  '{"path":"out/x.cad"}'   # traz nets A/B por símbolo
python3 tools/mcp_call.py cad_preview  '{"path":"out/x.cad"}'
```
`cad_build` aceita **conexões lógicas por nome/pino** (rota + net automáticos):
```json
{"titulo":"PARTIDA DIRETA",
 "simbolos_json":[{"classe":"8017","x":160,"y":60,"rotulo":"-F2","id":"RT"},
                  {"classe":"8001","x":160,"y":90,"rotulo":"-S0","id":"S0"},
                  {"classe":"8000","x":160,"y":120,"rotulo":"-S1","id":"S1"},
                  {"classe":"8000","x":215,"y":120,"rotulo":"-KM1","id":"selo"},
                  {"classe":"9000","x":160,"y":160,"rotulo":"-KM1","id":"KM1"}],
 "conexoes_json":[{"de":["RT","B"],"para":["S0","A"]},
                  {"de":["S0","B"],"para":["S1","A"]},
                  {"de":["S1","B"],"para":["KM1","A"]},
                  {"de":["S1","A"],"para":["selo","A"]},
                  {"de":["S1","B"],"para":["selo","B"]}],
 "out_path":"out/partida_direta.cad"}
```
- **`id` único** por símbolo (rótulo pode repetir; o `id` é a chave de ligação).
- Elemento **em paralelo** liga nos **mesmos dois nós** (ex.: selo.A→S1.A e selo.B→S1.B).
- `auto_net=True` (padrão) calcula os nets por geometria.
- Se o retorno trouxer **`AVISO curto A==B`**, o layout ligou os dois pinos no mesmo nó — corrija.

### Loop de trabalho
1. `cad_symbols` → escolher classes.
2. Desenhar a topologia (Parte A) → `cad_build` com `conexoes_json`.
3. `cad_validate` (tem que dar OK) e checar `AVISO curto`.
4. `cad_inspect` → conferir os nets (nós devem bater com a topologia).
5. `cad_preview` → **ver** o esquema.
6. Abrir no CADe (Wine) p/ confirmar; `tools/render_cad.sh out/x.cad out/x.png`.

### IDs úteis
`2001` contator potência · `6007` térmico potência (1-3-5/2-4-6) · `6010`/`6009` disjuntor ·
`8017` NF 95-96 · `8016` NA 97-98 · `8001` botoeira NF · `8000` botoeira NA ·
`7000` contato NA auxiliar · `7001` contato NF auxiliar · `9000` bobina (A1-A2) ·
`9008` piloto · `1000` motor · `10050/10051/10060` ladder NA/NF/bobina.

## Validação Wine
1. Copie o `.cad` p/ o dir do EXE (nome ASCII curto); rode com cwd=dir do EXE.
2. Desbloqueio (senha 4962): **cliques** no teclado do diálogo (a busca por título `SENHA` falha — o diálogo não tem título). `tools/render_cad.sh` já encapsula.
3. `Ver > Zoom Todo` / maximizar o filho; `import -window <id> shot.png`.

## Entregáveis
- `out/<nome>.cad` validado (aceita no app) + nets coerentes (sem aviso de curto).
- Descrição da topologia (o que cada rung faz) + limites honestos do que foi testado.
