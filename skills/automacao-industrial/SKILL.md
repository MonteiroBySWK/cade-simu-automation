# Skill: automacao-industrial

name: automacao-industrial
description: Projetar, editar e validar circuitos CADe_SIMU 4.0 (.cad) por código — parser round-trip, transplante de entidades, simulação lógica de rungs Ladder e validação visual via Wine. Use quando o pedido envolver .cad, CADe_SIMU, CLP/Ladder, partida de motores, relés térmicos, intertravamentos ou quadros de comando.

## Quando usar

- Editar `.cad` existente (adicionar símbolos, fiação, textos) sem quebrar o arquivo.
- Criar `.cad` do zero ou a partir de imagem (via `cade.json` + `cade_cli`).
- Verificar lógica de comando (permissões, selos, intertravamentos) com `ladder_sim.py`.
- Resolver questões de Automação Industrial (partidas, proteções, sinalização).

## Regras de ouro

1. **Nunca escreva `*`/`#` na mão.** Use `cade_cli` (`parse|emit|validate|new-from-json`) ou scripts que clonam entidades doadoras (`tools/pratica5_build.py` como modelo).
2. **Round-trip byte-idêntico é o gate.** Toda modificação: `parse → emit → cmp` + `cade_cli validate`. Se divergir, pare.
3. **Clone doadores do próprio acervo** (115 `.cad` em Downloads): símbolo novo = entidade doadora com seq/X/Y/labels/nets trocados. Nunca invente flags/tamanhos.
4. **`.cad` original nunca in-place**; saída em `out/` ou `pratica5/`. Commits em PT-BR, pequenos.

## Formato `.cad` (resumo operacional)

- Texto ISO-8859 (latin1), sem newlines. `CADe_SIMU*modo*versao#titulo#...`, seções terminam `$$$`, metadados após (`&&&`).
- Entidade: `*SEQ*ID#SUB#labels...#*f0..f7*X*Y*P2x*P2y*OX*OY*W*H*0*0*0*1*0*A*B`
  - `f0..f7` flags; `X*Y` posição; `W*H` tamanho; `A*B` = nets elétricos (ladder/fios) ou pinos.
- Fios: `4000#` (segmento X1Y1X2Y2, A=índice), `4018#`/`4019#` (mesmo, A=net compartilhado), `4001#` (dot de junção, X1==X2).
- Texto: `*SEQ*8### 0#...# 0*...*X1*Y1*X2*Y2*...#TEXTO`.
- Splitter canônico: header até `#(?=\*\d+\*\d+#)`; body split nesse padrão; footer em `$$$`. Validado round-trip em 113/113 arquivos — reuse `tools/dissect.py`.
- IDs úteis: `2001#` contator potência, `6007#` relé térmico (pins 1-3-5/2-4-6), `8017#` NF 95-96, `8016#` NA 97-98, `9008#` piloto X1/X2, `9000#` bobina A1/A2, `8000#/8001#` botoeiras, `10050#` contato Ladder NA, `10051#` NF, `10060#` bobina Ladder, `10204#/10205#` módulos I/O, `10206#` CPU.

## Ladder: convenção de nets

- Contato carrega nets `A` (esq) e `B` (dir): `A` do vizinho esq = `B` do anterior. Bobina `10060#` tem A=B=0 (fecha por geometria).
- Rung = cadeia de nets do trilho esq (net 25) até a bobina. Selo = contato NA da própria saída em ramo paralelo (ver `tools/ladder_sim.py`).
- Novos contatos em série: quebrar net `N` em `N-fresh1-fresh2-...-N` (fresh > maxA do arquivo), deslocar bobina p/ direita, estender fio final. Checar netlist antes/depois com assert.

## Validação Wine (roteiro que funciona)

1. Copie o `.cad` p/ o dir do EXE com nome ASCII curto; rode com cwd = dir do EXE e nome relativo (argv com `Z:\...` longo dá "No se puede abrir el archivo").
2. `xvfb-run -a -s "-screen 0 1280x1024x24"`, aguarde janela `SENHA`, digite `4962` + Return.
3. Duplo-clique na barra de título do filho MDI = maximiza. Menu `Ver` tem Zoom +/−/Janela/Todo.
4. `import -window root shot.png` (ImageMagick) para evidências. Scrollbars MDI não respondem a xdotool — prefira Zoom Janela e maximizar.
5. `tools/validate_wine.sh` faz o smoke test (sobe sem erro fatal). Simulação interativa (play) é manual.

## Lógica de proteção padrão (copie o padrão Pratica5)

```
PERMISSÃO = RT1_OK E RT2_OK        (NF 95-96 em série, ladder + riser comum)
H_funcionamento em paralelo com a bobina do contator
H_falha em série com o NA 97-98 do térmico, alimentado de barra viva
Sem auto-religamento: selo cai com Q; retomada exige novo comando
```

## Entregáveis de atividade (checklist)

- [ ] `.cad` final + base preservada; `validate` + round-trip OK
- [ ] `tools/ladder_sim.py` com T1–T7 ALL PASS + equivalência base==final (RT sadio)
- [ ] `TABELA-IO.md` (função + endereço de cada sinal novo)
- [ ] `RELATORIO-TESTES.md` com limites honestos (o que foi provado × roteiro manual)
- [ ] `evidencias/*.png` (folha geral + detalhes; abrir no CADe sem erro)
