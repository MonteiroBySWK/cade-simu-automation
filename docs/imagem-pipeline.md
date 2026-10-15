# Pipeline imagem→JSON

## Fluxo (atual)

```
imagem → tools/img2cad.py (detector kNN) → cade.json (inventário de símbolos)
       → tools/mk_dataset.py (monta .cad) → cade_cli validate → .cad válido
```

O baseline antigo (`tools/img2json.py`, projeções H/V) foi substituído pelo
detector de símbolos em `tools/detect_symbols.py` + classificador
`tools/classifier.py`. Ver `docs/detector-imagem.md` para o método e métricas.

## O detector de símbolos

- Segmenta a tinta (remove fio vermelho e marca-d'água), acha componentes
  conexos e classifica cada candidato por **kNN** sobre um dataset minerado dos
  próprios `.cad` (ground-truth perfeito).
- P/R honestos (leave-one-case-out, 221 símbolos): **P=0,88 / R=0,89** dentro do
  domínio minerado.
- `tools/img2cad.py` gera `cade.json` (inventário) e, se pedido, um `.cad`
  colocando uma entidade doadora por símbolo; `cade_cli validate` confirma.

## Limites conhecidos

- **Domínio:** o modelo é treinado no estilo/zoom do dataset minerado. Nos
  `Exemplos/*.png` (lâmpadas preenchidas, marca-d'água, outro zoom) cai para
  P≈0,2/R≈0,3. Fechar com dataset multi-estilo / augmentation de escala / rejeição
  por novidade.
- O `.cad` gerado tem os símbolos nas posições detectadas, mas ainda **sem a
  fiação** (`fios`) inferida — a etapa `imagem→fios` não está implementada.
- Sem classificação de texto/legenda.

## Exemplo verificado

```
python3 tools/img2json.py "<Exemplos>/Comandos Elétricos/exemplo01.png" -o out/exemplo01.json --preview out/exemplo01.preview.png
src/cade_cli/target/debug/cade_cli new-from-json out/exemplo01.json -o out/exemplo01.cad
src/cade_cli/target/debug/cade_cli validate out/exemplo01.cad  # OK modo=0 versao=3000
```
