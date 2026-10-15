# cade-simu-automation

Automação de projetos elétricos do **CADe_SIMU 4.0** por código: parser round-trip
do formato `.cad`, CLI para agentes de IA, verificação lógica de rungs Ladder e
validação visual via Wine. Sem Ghidra, sem chute — engenharia reversa barata e
determinística a partir do corpus.

> **EN:** Code-driven automation for CADe_SIMU 4.0 `.cad` files: byte-exact
> round-trip parser, agent-friendly CLI, Ladder rung checker and Wine-based
> visual validation.

## Por que existe

O `.cad` do CADe_SIMU é um formato proprietário sem especificação pública —
mas **não é binário**: é texto ISO-8859 com delimitadores `*`/`#` e seções `$$$`.
Este projeto transforma esse formato em algo que código (e IA) consegue manipular
com segurança: parse → edita → emite, byte-idêntico quando nada muda.

## O que faz

| Componente | O quê | Estado |
|---|---|---|
| `src/cade_core` (Rust) | `parse()` + `emit()` byte-fiéis do `.cad` | ✅ round-trip 114/114 arquivos |
| `src/cade_cli` (Rust) | `validate\|parse\|emit\|new-from-json` — a ferramenta que o agente chama | ✅ e2e OK |
| `tools/extract_ids.py` | dicionário de símbolos `NNNN#SUB` do corpus → `docs/dicionario-simbolos.md` | ✅ 56 IDs |
| `tools/dissect.py` | disseca entidades (seq, ID, flags, X/Y/W/H, nets A/B) | ✅ |
| `tools/cad_preview.py` | render esquemático p/ conferência geométrica | ✅ |
| `tools/ladder_sim.py` | solver de rungs (NA=10050#, NF=10051#) p/ testes T1–T7 | ✅ |
| `tools/img2json.py` | baseline imagem → `cade.json` + preview (PIL+numpy) | ✅ baseline |
| `tools/validate_wine.sh` | smoke test: abre gerados no CADe_SIMU via Wine+Xvfb | ✅ |
| `skills/automacao-industrial` | skill reutilizável: formato, nets, roteiro Wine, padrão de proteção | ✅ |

## Quickstart

```bash
# 1. validar um .cad
cargo build --manifest-path src/cade_cli/Cargo.toml
./src/cade_cli/target/debug/cade_cli validate meu.circuito.cad

# 2. .cad -> JSON -> .cad (round-trip)
./src/cade_cli/target/debug/cade_cli parse meu.circuito.cad -o out/a.json
./src/cade_cli/target/debug/cade_cli emit out/a.json -o out/b.cad
cmp meu.circuito.cad out/b.cad && echo BYTE-IDENTICO

# 3. testes do núcleo
cargo test --manifest-path src/cade_core/Cargo.toml

# 4. dicionário de símbolos do seu corpus
python3 tools/extract_ids.py /caminho/*.cad > docs/dicionario-simbolos.md
```

## Formato `.cad` em 30 segundos

```
CADe_SIMU*0*3005#220V#########*0*0*...   <- header (modo, versão, título)
*1*6017#DJ##N#1#3#5#2#4#6#*1*...*48*63*...  <- entidade: SEQ*ID#SUB#labels#flags*X*Y...
*5*4000##########*0*...*39*57*45*75*...     <- fio (X1*Y1*X2*Y2)
...$$$&&&                                     <- fim de seção
```

Detalhes em [`docs/formato-cad.md`](docs/formato-cad.md),
[`docs/dicionario-simbolos.md`](docs/dicionario-simbolos.md) e
[`spec/spec-v1.md`](spec/spec-v1.md).

## Validação

- `cargo test`: 4 testes (round-trip no corpus + rejeições).
- Round-trip byte-idêntico em **114/114** `.cad` do acervo + `validate` no CLI.
- Abertura real no CADe_SIMU 4.0 via Wine sem erro (roteiro em `tools/validate_wine.sh`).

## Aviso

Projeto independente, sem afiliação com o autor do CADe_SIMU (shareware de
Juan Luis Villanueva Montoto) nem com o "Ensinando Elétrica". Uso didático.
Atividades acadêmicas resolvidas com estas ferramentas **não** são publicadas
aqui (`pratica5/` e `*.pdf` estão no `.gitignore`) — publique seu próprio
aprendizado, não a resposta pronta.

## Licença

GPLv3 — pode usar e modificar; obras derivadas precisam continuar abertas
([LICENSE](LICENSE)).
