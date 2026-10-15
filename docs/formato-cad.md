# Formato `.cad` — achados 14/10/2026

## Fatos

- Encoding: ISO-8859 (latin1), **sem terminadores de linha**, linhas lógicas muito longas (3k–20k chars).
- Delimitadores: `*` separa campos, `#` separa subcampos/blocos, `$$$` termina seções, `,` decimal em config (`1,0000`).
- Header: literal `CADe_SIMU*<n>*...`. Exemplos reais:
  - `CADe_S1.cad`: `CADe_SIMU*0*3005#220V#########*0*0*...`
  - `CADe_S1` (sem ext): `CADe_SIMU*3*6017#DJ...`
  - `config.cfg`: `CADe_SIMU*1*1*0*1*0*0*1*0*  0*  0*1,0000*2*1*210*279*1*2*  50$$$`
- Contagens (`CADe_S1.cad` 7132b): 2316 `*`, 1001 `#`. Tokens via split `*`: 2317.
- Primeiros 40 tokens de `CADe_S1.cad`:
  `CADe_SIMU | 0 | 3005#220V######### | 0×8 | 57 | 33 | 0 | 0 | -12 | -9 | 24 | 3 | 0 | 0 | 0 | 1 | 0 | 0 | 0# | 1 | 6017#DJ##N#1#3#5#2#4#6# | 1×7 | 0 | 48 | 63 | ...`
- IDs de símbolo observados: `6017#DJ` (disjuntor?), `7018#C1` (contator?), `8100#D`, `4000#` (fio/cabo? aparece muito com coordenadas). Padrão `NNNN#...` = catálogo.
- Coordenadas negativas (`-12*-9`, `-12*-3`) + pares `X*Y` (ex: `48*63`, `39*57`, `150*99`) = grade de desenho.
- Sequências tipo `5-1- 6-1-13-1-14-1-21-1-22-1-` = fiação/conexões entre pinos.

## String de formato no EXE

```
CADe_SIMU*%1d*%1d*%1d*%1d*%1d*%1d*%1d*%1d*%3d*%3d*%0.4f*%1d*%1d*%3d*%3d*%1d*%1d*%4d$$$
```

→ cabeçalho fixo com 17 campos. Localizar em `CADe_SIMUDoc.cpp` / `Cdib.cpp` via Ghidra depois para mapear cada `%d`.

## Módulos (via strings `E:\C++\CADe_SIMU\*.cpp`)

`ACCION_GRAFCET, ARR_ELE, CADe_SIMU, CADe_SIMUDoc, CADe_SIMUView, Cajetin (legenda), Cdib, ChildFrm, Clave, Configuracion, Dibujo, Editar, Editar1, EDITAR_ARDUINO, Editar_Cable, Editar_CNT_BIN, Editar_contador, Editar_DI_DO, Editar_IN, Editar_Logo, Editar_MPP1, Editar_NA_NC, Editar_Neuma, Editar_OUT, EDITAR_PLC, Editar_var1/2, Interruptor_horario, Librerias, MainFrm, Numerico, Pilotos, Presenta, Simbolo, Sim_Texto, Temporiza, Texto, TRANSICION_GRAFCET, Var_con1/2`

→ taxonomia pronta para tabela de símbolos: cabo, NA/NC, contador, DI/DO, IN/OUT, Logo, pneumática, temporizadores, pilotos, texto, Grafcet, PLC/Arduino.

## Hipótese de gramática (a confirmar)

```
arquivo := "CADe_SIMU" "*" modo "*" cabecalho "#" titulo "#"* ... (entidades "*")... ["$$$"]
entidade := tipo "#" subtipo ("#" rotulo)* "#" "*" params "*"+ coords "*"+
fio := "4000#" ... coordenadas...
```

## Próximos passos RE (baratos, sem Ghidra)

1. Copiar 10–15 `.cad` variados e comparar headers (`*0*` vs `*3*`, `3005` vs `6017`).
2. Extrair todos os IDs `NNNN#` únicos do corpus → dicionário inicial.
3. Cruzar com `Manual CADe_SIMU.pdf` (tabela de símbolos) + `Exemplos/*.png` (visão).
4. Fuzzing diferencial: alterar 1 campo, abrir no Wine, observar erro/posição → inferir semântica.
5. Só então Ghidra headless nos `Serialize()` de `CADe_SIMUDoc.cpp` se restar ambiguidade.
