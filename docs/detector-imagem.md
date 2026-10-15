# Detector imagem→símbolos (machine vision)

## Abordagem

Visão computacional **clássica** (sem ML): o `.cad` renderiza traço sintético
limpo, então regras determinísticas são a ferramenta certa.

Pipeline (`tools/detect_symbols.py`):
1. **Máscara de tinta**: pixels escuros, removendo fio vermelho e marca-d'água.
2. **Componentes conexos** (BFS próprio).
3. **Classificação por forma**: número de buracos (Euler), diagonais internas
   (anel do piloto vs dígito), largura/altura, densidade, colunas cheias (polos).
4. **Lâmpadas de painel acesas**: disco vermelho/verde sólido (fora da tinta).
5. **Merge** de fragmentos causados pelo fio vermelho que corta o símbolo.

## Estado atual e limites

- Regras (forma geométrica) nos `Exemplos/*.png`: P≈0,87 / R≈0,46.
- **Medição honesta (leave-one-case-out)** no dataset minerado
  (221 símbolos, 30 casos), `tools/eval_loo.py`:

  | método | P | R |
  |---|---|---|
  | regras geométricas | 1,00 | 0,13 |
  | **kNN (dataset minerado)** | **0,88** | **0,89** |

  Curva de escala: com 76 símbolos → P=0,83/R=0,79; com 221 → **P=0,88/R=0,89**.
  A meta de 80% (critério F2) é atingida e cresce com mais dados.

- **Diagnóstico:** as regras puras atingem o teto por **falta de dados** (cada
  correção de falso positivo custa recall em outro símbolo). Com o dataset
  minerado, o kNN equilibra P/R e chega perto da meta de 80% — e cresce com
  mais dados.

## Desbloqueio: minerar rótulos dos próprios `.cad`

Os **114 `.cad` do acervo são ground-truth perfeito** — cada arquivo diz quais
símbolos existem, onde e de que tipo. Minerando renders rotulados:

- `tools/mk_dataset.py` — gera `.cad` sintéticos com símbolos em coords
  conhecidas (clona entidades doadoras; mesmo render do app) + manifesto JSON.
- `tools/render_cad.sh` — renderiza no CADe_SIMU via Wine (desbloqueio da senha
  4962 por cliques no teclado do diálogo; maximiza MDI; `Ver > Zoom Todo`).
- `tools/label_dataset.py` — transform calibrado `cad→tela`
  (`screen ≈ (50 + 1.995·x, 124 + 2.045·y)`), recorta cada símbolo rotulado
  em `out/dataset/<classe>/`, mede P/R real (`--detect`) e gera contact sheet.

Com esse dataset: (a) medir P/R honesto em centenas de símbolos, (b) treinar um
classificador pequeno (kNN/ONNX) OU calibrar as regras — sem mais chute.

### Classificador kNN (`tools/classifier.py`)

Regras geram **candidatos**; o kNN decide a classe (feature = máscara 20×20 +
aspecto, distância vetorial, k=5 votos). Sem dependências (numpy puro).

```bash
python3 tools/mk_dataset.py gen 10          # .cad sintéticos + manifesto
for c in out/ds/case-*.cad; do tools/render_cad.sh "$c" "${c%.cad}.png"; done
python3 tools/label_dataset.py --sheet      # recorta rotulados + contact sheet
python3 tools/classifier.py train           # treina -> out/model.npz
python3 tools/label_dataset.py --detect --knn   # mede P/R do kNN
python3 tools/label_dataset.py --detect         # mede P/R das regras
python3 tools/eval_loo.py                        # LOO honesto (kNN)
python3 tools/eval_loo.py --regras               # LOO honesto (regras)
```

## Template library

`tools/mk_templates.py` + `tools/crop_templates.py` geram templates limpos
(8 classes) do próprio app, usáveis por template matching (NCC já implementado
em `detect_symbols.ncc`, rápida via FFT) quando o dataset justificar.

## Como o agente usa

`tools/cade_mcp.py` expõe `cad_inspect`/`cad_preview` (o agente vê o circuito)
e o loop texto/imagem→`cade.json`→`cade_cli`→`.cad`→Wine. A detecção por imagem
é a frente em evolução; o `.cad↔json` (Rust) já é determinístico e byte-fiel.
