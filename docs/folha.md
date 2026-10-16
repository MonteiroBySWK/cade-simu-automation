> **CORREÇÃO (2026-10-15, após `tools/app_sim.py`):** os números abaixo (≈975x705) foram medidos
> na unidade da **barra de status** do app (~3,3x a unidade do `.cad`). Em unidades do `.cad` a
> moldura é **x 20..467, y -1..332** (legenda em y≈311..329) — ver `tools/sheet.json` e
> `docs/app-sim.md`. Área segura para layout: **x ≤ 455, y ≤ 305**. Itens do gabarito do curso
> em y=440 ficam fora da moldura.

# Area de desenho da folha — achados 15/10/2026

## Resposta
O layout assume 455x295 e e **muito conservador**. Na pratica a folha (moldura verde com
colunas A..G e linhas 1..5 + legenda no rodape) vai de **x ~10 a ~985** e **y ~70 a ~775**
(unidades das coordenadas X,Y das entidades; 975x705, proporcao ~A4 paisagem).
Uso seguro recomendado: **x 60..960, y 80..750**. `tools/sheet.json`: x_max=980, y_max=770.
Nao ha limite rigido (nao verificado): o editor aceita entidades alem da moldura (so rola a area).

## Evidencia
1. **Empirico (Wine, Aula1.cad)**: cursor sobre cantos da moldura, status `X=,Y=` (grade 10,
   zoom exibido "89"): canto inf-dir = (980,770); canto sup-esq = (10,70); linha de baixo da
   moldura ~Y=778. Escala tela->coord = 1,114 por pixel (zoom 0,9).
2. **Corpus (118 .cad, 11949 entidades)**: max X=432 (x1/x2 de fios 444 com caixa),
   max Y=440 (Intercalar_atv, vv_tmp); texto id 20000 chega a Y=486 (YD_1). Ids 8
   (retangulos) tem campos diferentes (x,y em n8..n11 nao sao origem). Ou seja, os autores
   usam so ~metade esquerda/superior da folha: o gabarito y<=440 cabe com folga.
3. **Campos `*210*279` / `*279*210`**: `config.cfg` e rodape `*%3d*%3d` — 279x210 sao as
   dimensoes de papel de impressao (mm), NAO a area de desenho. A maioria dos arquivos traz
   `*333*3332..3333` (provavelmente lixo/estado do dialogo). Sem relacao direta com a moldura.
4. **Moldura depende do arquivo**: em Pratica5_Complementar.cad (rodape 279*210) a moldura
   tracejada comeca ~45 unidades mais a direita/baixo do que em Aula1.cad. Logo origem e
   tamanho variam com a configuracao da legenda (Cajetin); nao deduzidos do binario.

## Confianca
- Limites de Aula1 (padrao do curso): media-alta (medidos, +-10 de grade).
- "Sem clamp": media — nao foi feita varredura Ghidra de Cajetin/clip (nao necessaria
  para o objetivo; o Wine abriu entidades fora da moldura sem erro).
- Origem da moldura em outros arquivos: baixa (so 2 amostras).

## Pendente
Ghidra: rotina de desenho da moldura (Cajetin.cpp) para saber o tamanho em funcao do
rodape. Sondagem alem da moldura: out/probe_folha.cad (textos em x ate 1500, y ate 1500)
foi aberto mas o wine_mgr copia para wv_tmp e o resultado nao foi lido.
