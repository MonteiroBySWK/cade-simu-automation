# Bibliografia — Automação Industrial (digest e lacunas)

Material da disciplina (UEMA/DECOMP, prof. José Pinheiro de Moura) e livro-texto, baixados em
22/10/2026. Extração: `pdftotext -layout` nos digitais e OCR (`tesseract`, modelo `por`) no livro
escaneado; textos brutos em `out/bibliografia/` (fora do git — `*.pdf` e `out/` são ignorados).
Este arquivo é o que fica: conceitos, o que o projeto **já cobre**, o que **não cobre** e o que fazer.

## 1. Reversão de motor monofásico (2 documentos)

- `Documento_Reversao_Motor_Monofasico.pdf` (6 pág., texto didático)
- `Partida_Reversa_Motor_Monofasico.pdf` (1 pág., desenho CADe_SIMU)

**Conceito central**: motor monofásico = enrolamento principal + auxiliar. A reversão **não** é
trocar fase e neutro: ela inverte a **ligação relativa de um enrolamento** (na prática, os dois
terminais do auxiliar), via contatores. Cada contator estabelece uma configuração; C1 e C2 nunca
podem ficar energizados juntos (intertravamento elétrico NF cruzado; mecanicamente, recomenda-se
intertravamento mecânico). Selo por contato NA do próprio contator; DESLIGA/EMERGÊNCIA NF antes de
tudo; sinalização por sentido (`H1`/`H2`).

**No CADe_SIMU** (do desenho): fonte `3005`/`3007`, disjuntor 2 polos `6001/6002` (ou 4 polos
`6004`), contatores de **4 polos** `2002` (C1/C2) com o cruzamento no enrolamento auxiliar, motor
**`1008`** `U1 V1 PE U2 V2`; comando com B1/B2 (`8000`), selo (`7000`) e NF cruzado (`7001`).

**Projeto**: `potencia` da DSL só monta colunas de 3 fases (`1000`/`2001`/`6007`/`6009`). Reversão
monofásica **não é suportada** hoje — ver Lacunas.

## 2. Reversão trifásica (2 desenhos CADe)

- `Partida_Reversa-1.pdf` / `Partida_Reversa-2.pdf` (1 pág. cada)

Desenho com fonte `3005` (L1,L2,L3,PE), **disjuntor de 4 polos `6004`** (DJ1, pinos 1-3-5-7 /
2-4-6-8), térmico `6007` (RT1), **contatores de 4 polos `2002`** (C1/C2) e motor `1000`
(U1,V1,W1,PE). Comando: DJ2 (`6002`) + RT1 (95-96) + B3 DESLIGA (`8001`) + ramos B1/C1 e B2/C2 com
selo e NF cruzado; lâmpadas `LH`/`LA` por sentido. A inversão é a permuta de duas fases no segundo
contator (nosso `potencia.paralelo` com `ordem: ["L3","L2","L1"]`).

**Projeto**: coberto (exemplo `reversao`), mas com `6009`/`2001` de **3 polos**. O 4º polo é
cosmético para motor trifásico sem neutro; usar `6004`/`2002` fica como opção de fidelidade ao
desenho do professor (ver Lacunas).

## 3. Inversor de frequência

- `Acionamento_Motores_Inversor_Frequencia_Explicacao_Detalhada.pdf` (5 pág.)

Arquitetura: rede → DJ → L1/L2/L3 do INV → U/V/W → motor(es); dois motores na mesma saída não têm
velocidade independente; `n_s = 120 f / P` (30/45/60 Hz → 900/1350/1800 rpm em 4 polos, menos o
escorregamento). Comando por entradas digitais `I1..I4` (função depende da parametrização), `AI`/
`AO`/`0V`, relé `RA/RC`, `R+/R−` (frenagem — conferir manual). Cuidados: não manobrar contator na
saída U/V/W com o inversor comandando; não ligar capacitor de correção na saída.

**Projeto**: **fora de escopo** — o CADe_SIMU não tem classe de inversor (o catálogo tem motor,
contator, disjuntor, térmico, CLP; não INV). A skill deve dizer isso e não inventar circuito.

## 4. Atividade de partidas intercalares com proteção (UEMA)

- `Atividade_Partidas_Intercalares_de_Motores_CadeSimu-1.pdf` (4 pág.)

Enunciado: ampliar a prática 5 (intercalação M1/M2 por CLP) com **RT1/RT2** nos circuitos de
potência, contatos NF na permissão e NA no alarme, **H1/H2** (funcionamento) e **H3/H4** (falha),
**intertravamento geral**: qualquer térmico atuado desliga C1 e C2, bloqueia novo LIGA enquanto a
falha persistir e exige novo comando depois do rearme (sem religamento automático). Testes T1–T7.

**Projeto**: implementado em `tools/examples/pratica5_complementar.ladder.json` (permissão
`I0.4`/`I0.5`, alarmes `I0.6`/`I0.7`, saídas `Q0.4`/`Q0.5`) e os T1–T7 estão nos `testes` do
exemplo. O enunciado é um bom **caso held-out** em linguagem natural (ver Lacunas).

## 5. Controle Programável — Paulo Eigi Miyagi (206 pág., escaneado)

Livro-texto de Sistemas a Eventos Discretos (2ª reimpressão, 2001). Estrutura: 1 Introdução
(história do CLP; adota o termo Controlador Programável), 2 Características do sistema de controle
(operações básicas, CP), 3 Modelagem das tarefas de controle (**diagrama de relés/LD** segundo a
IEC; linguagens LD/IL/SFC), 4 Redes de Petri, 5 PFS/MFG, 6 **Metodologia de projeto**, 8 Apêndice
**SFC**.

O que aproveitamos:

- **LD/IEC (§3.2)**: regras de matriz (bobinas só na última coluna; linhas mãe à esquerda/direita;
  fluxo da esquerda para a direita = **AND**; verticais de cima para baixo = **OR**; processamento
  de cima para baixo); contatos tipo **a** (NA) e **b** (NF); **detector de variação** (borda de
  subida/descida, ON por 1 ciclo de controle); bobinas (comum, inversa, SET/RST, **com memória**,
  de borda); temporizador (entrada, saída, set-point, valor atual); contadores.
- **SFC/GRAFCET (Apêndice)**: etapas e transições — base de um futuro front-end `grafcet/1`; o
  CADe_SIMU já tem a classe `10100 Etapa 0 GRAFCET` (e o catálogo tem a família `10100+`).
- **Metodologia (§6)**: análise de necessidades → estudo do objeto → funções de controle →
  interfaces e **alocação de I/O** → estrutura do programa → software → testes. É o mesmo roteiro da
  skill (listar I/O antes de desenhar), com vocabulário formal.
- **PFS/MFG (§5)**: modelagem formal (redes de Petri) para recursos/deadlock; não entra no
  simulador, mas justifica validar sequências e estados alcançáveis (não implementado).

Lacuna que o livro escancara: nossa DSL `ladder/1` tem só NA/NF, OUT/SET/RST e TON — falta borda,
TOF, contador e GRAFCET. A tabela do roadmap está em `docs/ladder.md` §2.6, com as classes do
CADe_SIMU que já existem no catálogo.

## Lacunas e plano

| # | Lacuna | Impacto | Ação |
|---|---|---|---|
| 1 | Reversão **monofásica** (motor `1008`, contatores `2002`, cruzamento U2/V2) | aluno/professor pede e a DSL não monta | modo de ligação explícito no `potencia` (ou `conexoes` de alto nível) + exemplo + teste no app |
| 2 | Dispositivos de **4 polos** (`6004`/`2002`) nos exemplos de reversão | fidelidade ao desenho do professor | opção `polos: 4` no `potencia` (o 4º polo no N) — validar no app |
| 3 | **Inversor de frequência** | não existe no CADe_SIMU | documentar como fora de escopo na skill (não tentar desenhar) |
| 4 | `run_eval` não pontua casos **ladder** (`tools/eval/casos/ladder/`) | benchmark held-out ignora CLP | estender `run_eval` para `.ladder.json` |
| 5 | Enunciados da disciplina como **held-out** | medir confiabilidade real | criar `tools/eval/casos/pratica5_complementar.json` (T1–T7) e rodar com agentes |
| 6 | Fatos do app fora da skill (disjuntor inicia aberto; um ponteiro só) | agentes gravam/validam errado | seção “No app” da skill + `docs/conformidade.md` |
