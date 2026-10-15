# Handoff — Atividade "Partida Intercalar" (CADe_SIMU)

## Objetivo
Gerar, do zero e por agente, um `.cad` de **partida intercalar de 2 motores** que
(i) abra no CADe_SIMU, (ii) **cabe na folha**, (iii) passe o gate de lógica e
(iv) tenha fiação limpa (sem curto, sem atravessar símbolo).

## Artefato final
- Especificação: `tools/examples/intercalada.spec.json` (símbolos + conexões + trilhos).
- Saída: `out/intercalada.cad` (gitignored).
- **Regenerar SEMPRE com o gate:**
  ```bash
  python3 tools/build_spec.py tools/examples/intercalada.spec.json out/intercalada.cad
  # tem de imprimir: GATE: OK
  python3 tools/wires_check.py out/intercalada.cad   # tem de imprimir: FIOS: ok
  ```

## Como o circuito é montado (MCP)
`tools/cade_mcp.py` (servidor MCP `cade-simu`) expõe `cad_build` com:
- `simbolos_json`: `[{"classe","x","y","rotulo","id"}]`
- `conexoes_json`: ligação **por nome de pino** — `{"de":["KM1p","2"],"para":["M1","U1"]}`
  ou a trilho — `{"de":["RT1","A"],"para":["L","rail"]}`
- `rails_json`: `[{"nome":"L","y":18,"x0":25,"x1":395}]`
- `auto_net=true` calcula os NETs por geometria (o que faz **simular**).

CLI: `python3 tools/mcp_call.py cad_symbols | cad_inspect | cad_test | cad_preview`.

## Estado atual (verde)
- `GATE: OK` (validate + sem `AVISO curto` + `cad_test` **15/15**).
- `tools/wires_check.py` → **`FIOS: ok`** (nenhum trecho atravessa símbolo).
- Conteúdo dentro da folha (folha fixa ~460×300).
- Potência **trifásica** (3 fases paralelas L→Q→F→Térmico→Contator→Motor) com **PE ao neutro**.
- Fonte `3004#-X` e neutro `3002#TERRA` presentes.
- Abre e **simula** no app (Play ▶; clicar S1 energiza KM1).

## Ferramentas
| ferramenta | para que |
|---|---|
| `tools/build_spec.py` | **gate**: build + validate + test (reprova em curto/teste) |
| `tools/wires_check.py` | mede trechos que atravessam símbolo (estética) |
| `tools/wine_mgr.py` | `up`/`down`/`max`/`shot`/`ws N`/`logs` (abre no Wine, digita a senha 4962) |
| `tools/symbol_pins.json` | geometria dos pinos por classe (nome→offset) |
| `tools/learn_pins2.py` | mede pinos a partir dos 108 `.cad` do acervo |
| `tools/netlist_sim.py` | simulador de netlist (usado pelo `cad_test`) |

## Regras de ouro (aprendidas)
0. **Cabo = entidade `4000`.** É exatamente o que o app grava para fios/cabos
   (4.979 usos no acervo). `4001` = ponto de junção; `4009`/`4018` = **pontos de
   conexão** (do menu "Cabos e conexões") — o app **não exige** esses marcadores:
   abrir nosso arquivo e salvar acrescenta só a entidade de texto `20000`. A
   condução funciona com `4000` + NET.
1. **Pinos nomeados**: motor `1000` tem `U1/V1/W1/PE`; contator `2001`/térmico `6007`
   têm `1-3-5` (topo) e `2-4-6` (base); DJ `6009` idem. **Ligue TODOS os terminais.**
2. **Fase ≠ fase**: um trilho único **curto-circuita as fases**. Use **3 trilhos**
   (`L1/L2/L3` em y=14/20/26) + `N` (y=290); cada coluna de fase liga no seu trilho.
3. **Símbolos de potência têm pinos do mesmo lado** → empilhe em **fileiras/colunas
   alinhadas**, nunca em cascata vertical aleatória.
3. **Folha fixa**: conteúdo em `x≲455`, `y≲295`.
4. **Roteador**: escape do pino para fora; fio reto quando o x coincide e a coluna
   é livre; coluna de desvio fora de qualquer corpo.
5. **Fonte**: `3004#-X` por fase (pino B → N); neutro `3002#TERRA` no N.
6. **Nunca** altere o roteador/pinos sem rodar o **gate** antes e depois (foi a
   fonte de idas-e-vindas).

## Pendências (menores)
- Comando (lado esquerdo): ainda há alguns **degraus** nos fios dos rungs
  (selo/bobina/piloto). A potência já está reta.
- Campos da **legenda** (título/autor/data) não preenchidos (fora de escopo até ser pedido).
- `learn_pins.py` (versão antiga, por moda) foi **substituído** por `learn_pins2.py`
  para contagem por endpoint; manter só o segundo.

## Ver no app
```bash
python3 tools/wine_mgr.py up out/intercalada.cad   # senha 4962 automática
python3 tools/wine_mgr.py max && python3 tools/wine_mgr.py ws 10
python3 tools/wine_mgr.py shot /tmp/x.png
```
