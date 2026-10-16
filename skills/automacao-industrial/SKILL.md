---
name: automacao-industrial
description: Projetar, montar e validar circuitos CADe_SIMU 4.0 (.cad) por agente via MCP — partidas de motores (direta, reversao, intercalar), selo, intertravamento, protecao termica, sinalizacao e emergencia. Use quando o pedido envolver .cad, CADe_SIMU, quadro de comando, partida de motor, rele termico, contator ou intertravamento. Caminho curto - cad_examples, layout topologico, cad_design, relatorio do gate, cad_preview.
---

# Skill: Automação Industrial × CADe_SIMU

Duas disciplinas juntas: **Automação** diz *o que* o circuito faz; **CADe** diz *como*
desenhá-lo para abrir **e simular**. Você descreve a **topologia** (o que liga em quê);
o motor de layout posiciona, roteia e o **gate** prova. **Nunca** escreva `*`/`#` nem
coordenadas x/y à mão.

## Fluxo curto (siga nesta ordem)

1. **`cad_examples`** → escolha o exemplo mais próximo do enunciado → **`cad_example(nome)`**
   (é o seu molde; todos passam o gate). Pares enunciado → layout em `exemplos/`.
2. **Monte o layout topológico** (DSL abaixo) adaptando o exemplo: rótulos do enunciado,
   nº de motores, intertravamentos, sinalização. Escreva também os **`testes`** (obrigatórios).
3. **`cad_design(layout_json, out_path)`** → build + validação + testes funcionais + geometria + fios.
4. **Leia o relatório**: `ok`, `erros` (acionáveis, em ordem), `avisos`, `proximo_passo`.
   Corrija **o primeiro erro** e chame `cad_design` de novo (loop curto).
5. **`cad_preview(path)`** → veja o desenho: fases coloridas, nenhum pino vermelho (solto),
   nenhum fio vermelho com X (curto). Gate verde sem olhar o preview não é "pronto".
6. **Entregue**: caminho do `.cad`, topologia em 3-5 linhas, testes que passaram e **limites honestos**
   (o que o gate não prova — ver seção própria).

Sem MCP nativo: `python3 tools/mcp_call.py cad_design '{"layout_json":"<json>","out_path":"out/x.cad"}'`
ou `python3 tools/build_spec.py meu.layout.json out/x.cad` (imprime `GATE: OK`/`REPROVADO`).

## A DSL em 1 minuto (`docs/dsl-layout.md` tem o detalhe)

```jsonc
{ "titulo": "PARTIDA DIRETA",
  "layout": {
    "trilhos": {"L1":14,"L2":20,"L3":26,"N":282,"PE":291,"x0":25,"x1":395},   // fases em cima; N e PE embaixo
    "fontes":  [{"id":"X1","classe":"3007","rotulo":"-X",                      // UMA fonte multi-terminal
                 "pinos":{"L1":"L1","L2":"L2","L3":"L3","N":"N","PE":"PE"}}],  // pino -> trilho
    "comando": [{"id":"m1","de":"L1","para":"N",
      "serie": [["RT1","8017","-RT1"], ["S0","8001","-S0"]],                   // [id, classe, rotulo], desce em coluna
      "ramos": [{"via":["S1","8000","-S1"], "selo":["selo1","7000","-KM1"],    // via || selo
                 "serie":[["nkm2","7001","-KM2"]],                             // opcional (intertravamento)
                 "carga":["KM1","9000","-KM1"], "indica":["H1","9008","-H1"]}]}], // carga || indica
    "potencia":[{"id":"m1","fases":["L1","L2","L3"],"neutro":"N","pe":"PE",
      "colunas":[["Q1","6009","-Q1"],["F1","6007","-F1"],["KM1p","2001","-KM1"],["M1","1000","-M1"]]}]
  },
  "testes": [{"nome":"S1 liga KM1","entradas":{"S1":true},"esperado":["KM1"],"status":"OK"}] }
```

- **ids únicos** (`selo1`, `nkm2`, `KM1p`); o **rótulo** pode repetir (selo `-KM1` = bobina `-KM1`).
- Cada **ramo** é uma fileira = um degrau do comando; vários ramos = vários degraus (poucos: o motor levanta erro explícito se não couber na folha).
- `potencia.colunas` desce L→Q→F→(contator)→motor, 3 colunas por fase, todos os terminais ligados.
  Contatores em paralelo no mesmo motor (reversão): `{"paralelo":[[...KM1p...],[...KM2p...,{"ordem":["L3","L2","L1"]}]]}`.
- **`testes`**: `entradas` = acionados (`true` = botão pressionado / térmico atuou), `inicial` = bobinas já
  ligadas, `esperado` = conjunto **exato** de bobinas energizadas, `status` = `OK` ou `RACE`.
  **A chave é o rótulo sem o `-`**: `-S1` → `"S1"`, `-RT1` → `"RT1"`.
- Quer conferir um símbolo? `cad_pins(classe)` (pinos, tamanho, para que serve) e `cad_symbols`.

## Tabela de blocos de automação

| Função | Como montar (DSL) | Classes |
|---|---|---|
| Liga / desliga | `via` = NA (liga); `serie` = NF (desliga), **antes** do ramo | `8000` NA, `8001` NF |
| **Selo** (retenção) | `selo` = NA do **mesmo** contator, em paralelo com `via` (rótulo = da bobina) | `7000` |
| **Intertravamento** | em `ramo.serie`: NF do **outro** contator (`-KM2` no degrau de `-KM1`) | `7001` |
| **Proteção térmica** | `serie` do comando: NF do térmico; na potência: térmico antes do contator | `8017` (NF 95-96), `6007` |
| **Parada de emergência** | NF **primeiro** da `serie` (antes de térmico e S0), só desliga e impede partida | `8001` |
| Sinalização de funcionamento | `indica` = lâmpada em paralelo com a bobina | `9008` |
| Sinalização de falha | bloco `comando` próprio: NA do térmico em série com lâmpada | `8016` + `9008` |
| Proteção de potência | disjuntor `Q` no topo da coluna de cada motor | `6009` / `6010` |
| Reversão | 2 contatores em `paralelo`, o 2º com `ordem` invertida L1↔L3 + NF cruzado | `2001` ×2, `7001` ×2 |
| Intercalar | como reversão no comando (NF cruzado) mas 2 motores, 1 contator cada | `exemplos` `intercalada` |
| Sem auto-religamento | selo cai ao desligar; teste `esperado: []` após soltar | — |
| Partida estrela-triângulo / temporizador | **fora da DSL v1** (sem blocos T): avise o limite; veja "esclarecimento" | — |

Regra de ouro do comando: `trilho_L → [proteções NF em série] → [liga ∥ selo] → [intertravamentos NF] → bobina → trilho_N`.
Série só passa se fechada; paralelo liga se *qualquer* ramo fechar.

## Erros comuns (e o que o gate diz)

| Erro | Sintoma no relatório | Correção |
|---|---|---|
| **Fonte `3004` ×3** (um `3004` por fase) | aviso "fonte 3004 por fase" + `CURTO` + pino `L3` solto | **uma** fonte `3007` com `pinos` L1/L2/L3/N/PE |
| **PE no neutro** | `CURTO N+P na mesma net` / aviso "PE do motor vai ao neutro" | trilho `"PE"` em `trilhos` e `"pe":"PE"` na potência |
| **Térmico com rótulo diferente do contato** (`-F1` no 6007 e `-RT1` no 8017) | gate: "contato termico ... nao segue nenhum rele termico 6007 de mesmo rotulo" — no app o térmico NUNCA dispara. Use o **mesmo rótulo** (ex.: `-RT1`) no 6007 e no contato 95-96; o mesmo vale para contatos auxiliares 7000/7001 e polos 2001 (rótulo da bobina 9000). |
| **Pino solto** (V1/W1/PE do motor, pino 3/5 do contator, pino da fonte) | `pino L3 da fonte -X (3007) solto em (x,y): ligue-o ao trilho L3` | ligar todos os terminais (DSL já faz; solto = pino omitido em `fontes.pinos` ou classe sem pino) |
| **Fases cruzadas** (dois trilhos de fase no mesmo nó) | `CURTO 1+2 na mesma net` | cada coluna de fase no seu trilho; reversão só via `ordem` |
| **Sem `testes`** ou chave errada | `sem testes: declare "testes"` / `entrada 'S9' nao existe no circuito` | declare casos; chave = rótulo sem `-` |
| **Teste vacuamente verde** | gate reprova chave inexistente (não finge passar) | use as chaves listadas em "entradas validas" |
| **Nets inúteis** (calcular/escrever `nums[21]/[22]` à mão) | — o app **descarta** nets do arquivo ao simular; só vale a **geometria** | não toque em nets; `cad_design` roteia por geometria |
| Fonte "L1 só" ou sem fonte | circuito "não simula" no app | fonte `3007` (ou `3006`/`3003`) ligada aos trilhos |
| Contato da bobina com rótulo diferente | selo/intertravamento não fecha nos testes | rótulo do contato = rótulo da bobina (`-KM1`) |
| Série longa / muitos ramos | `layout invalido: ... fora da folha` | menos elementos por série; dividir em blocos `comando` |

## Quando pedir esclarecimento (pontos de parada)

Pare e pergunte (em vez de chutar) quando:

- **O tipo de partida é ambíguo**: "intercalar" (2 motores, um por vez) ≠ "reversão" (1 motor, 2 sentidos) ≠ "sequencial".
- **Faltam rótulos/nomes** que os testes precisam (botões `-S0/-S1`, contatores, térmicos) — proponha o padrão
  `-S0` desliga, `-S1/-S2` ligam, `-KMn`, `-RTn`, `-Hn`, `-Qn`, `-Fn`, e peça confirmação se o enunciado tiver outro.
- **O enunciado pede algo fora da DSL v1**: temporizador/estrela-triângulo, CLP/ladder, inversor, soft-starter,
  ramos aninhados, comando em 2 pontos de liga. Diga o limite e ofereça a alternativa (`cad_build` com `conexoes`,
  ou simplificar) — não entregue um circuito "parecido" como se fosse o pedido.
- **Número de motores/fases/tensão** não estão claros, ou há **sinalização/emergência** só insinuada.
- **O gate falhou 3 vezes seguidas com o mesmo erro**: pare, leia `cad_pins`/`docs/dsl-layout.md`, e relate o
  bloqueio ao usuário com o erro literal em vez de contornar o gate.

Nunca: declarar pronto com `ok:false`; desligar testes para passar; ignorar pino vermelho no preview.

## O que o gate prova — e o que não prova

- **Prova**: arquivo válido (abre), lógica de comando pelos testes (selo, intertravamento, térmico, emergência,
  sem auto-religamento), **geometria** sem curto de fase e sem pino solto, fios sem atravessar símbolo.
- **Não prova**: lâmpadas/sinalização (o simulador de netlist só observa bobinas — verifique pela topologia e preview),
  temporizadores, e a simulação **real** no app (validada em amostra via Wine: `tools/cade_open.py`).
- A folha tem área segura ~960×750 (`tools/sheet.json`); layouts típicos ficam bem dentro.

## Ferramentas MCP

| Ferramenta | Para quê |
|---|---|
| `cad_examples` / `cad_example(nome)` | few-shot: lista e devolve layouts que passam o gate |
| **`cad_design(layout_json, out_path)`** | **principal**: layout → `.cad` + gate completo + `proximo_passo` |
| `cad_gate(path, testes_json)` | gate de um `.cad` existente (testes + geometria + fios) |
| `cad_pins(classe)` / `cad_symbols` | nome, uso, tamanho e pinos de uma classe / catálogo |
| `cad_preview(path)` | PNG com pinos nomeados, fase por cor, soltos/curtos em vermelho |
| `cad_test` / `cad_simulate` | tabela-verdade avulsa / simulação de uma combinação |
| `cad_validate` / `cad_inspect` | abre? / resumo de entidades e nets |
| `cad_build` / `cad_emit` / `cad_parse` / `cad_new` | baixo nível (coordenadas, round-trip) — só quando a DSL não cobre |

Avaliação offline de saídas de agentes: `python3 tools/eval/run_eval.py --golden` (baseline) ou
`run_eval.py <caso> <arquivo.cad>` (casos em `tools/eval/casos/`).

## Referência CADe_SIMU (por baixo do capô)

- **Conectividade = GEOMETRIA** (binário, `docs/re-engenharia.md` §9): fio liga a fio só por **extremo**; pino liga
  a fio só no **extremo**; T/cruzamento só com `4001`. Nets em `nums[21/22]` são descartados ao simular.
- **Fases**: cada pino de fonte estampa uma fase (L1→1, L2→2, L3→3, N→N, PE→P); duas estampas diferentes na mesma
  rede = **curto**. Fonte `3007` = L1,L2,L3,N,PE (offsets 0,6,12,18,24); `3006` = L1,L2,L3,N; `3003` = L,N.
- **Pinos nomeados**: motor `1000` `U1/V1/W1/PE` (topo); contator `2001`/térmico `6007` `1-3-5` topo, `2-4-6` base;
  disjuntor `6009` idem (base em y=21); contatos/bobinas `A` (topo) e `B` (base). Ligue **todos**.
- **Layout**: comando à esquerda, potência à direita; símbolos de potência têm pinos do mesmo lado → empilham em
  **coluna por fase**, nunca em cascata aleatória. O roteador sai do pino para fora do corpo e usa coluna livre.
- IDs úteis: `2001` contator · `6007` térmico · `6009/6010` disjuntor · `8017` NF 95-96 · `8016` NA 97-98 ·
  `8001` botoeira NF · `8000` botoeira NA · `7000` aux NA · `7001` aux NF · `9000` bobina · `9008` piloto · `1000` motor.
- Baixo nível (`cad_build`): recebe **strings** JSON (`simbolos_json`, `conexoes_json`, `rails_json`); `id` único por
  símbolo; `AVISO curto A==B` = os dois pinos do símbolo no mesmo nó.
- Ver no app: `python3 tools/cade_open.py out/x.cad --display :1` (copia, abre no Wine e digita a senha sozinho).

## Entregáveis

- `out/<nome>.cad` com `ok: true` no `cad_design`, conferido no `cad_preview`.
- Descrição da topologia (o que cada degrau faz), testes que passaram e **limites honestos** do que não foi provado.
