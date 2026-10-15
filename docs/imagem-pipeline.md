# Pipeline imagem→JSON — baseline v0.1 (Fase 4)

## Fluxo

```
PNG/JPG/BMP → tools/img2json.py → cade.json (meta + analise) → cade_cli new-from-json → .cad válido → preview PNG
```

## O que o baseline faz

- `tools/img2json.py`: PIL+numpy, threshold 128, densidade de tinta + projeções H/V (>30%).
- Saída `cade.json` em formato template-mínimo (`meta` + `analise`/`simbolos`/`fios`/`textos`).
  `cade_cli new-from-json` aceita esse formato e gera `.cad` mínimo válido.
- Preview: linhas H candidatas em vermelho, V em azul.
- Log de decisões com `confianca` explícita (0.40 projeções, 0.0 classificação — honesto).

## Limites conhecidos (para Fase 4 completa)

- Bordas da imagem (ex: linhas 0–14) poluem as projeções — precisa crop de moldura.
- Sem classificação de símbolos (contatos, bobinas, disjuntores): precisão atual ~0%,
  longe dos 80% do critério F2. Próximo passo: template matching sobre recortes do
  `Manual CADe_SIMU.pdf` ou dataset rotulado dos 115 `.cad` + PNGs de exemplo.
- O `.cad` gerado do baseline **abre** (válido) mas **não simula** o circuito da foto —
  contém só o header/template. Isso é parcial de propósito: a etapa
  `cade.json→.cad` é determinística; falta a etapa `imagem→símbolos`.

## Exemplo verificado

```
python3 tools/img2json.py "<Exemplos>/Comandos Elétricos/exemplo01.png" -o out/exemplo01.json --preview out/exemplo01.preview.png
src/cade_cli/target/debug/cade_cli new-from-json out/exemplo01.json -o out/exemplo01.cad
src/cade_cli/target/debug/cade_cli validate out/exemplo01.cad  # OK modo=0 versao=3000
```
