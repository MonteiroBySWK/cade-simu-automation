# Contribuindo

1. `make setup && make doctor` — nada além do núcleo é necessário (sem Wine/CADe_SIMU).
2. Mudou código? `make test` (143+ testes) e `make gate` (exemplos + eval golden = 100).
3. Novo circuito de exemplo: `tools/examples/<nome>.layout.json` **sem coordenadas**, com `"testes"`;
   adicione um caso em `tools/eval/casos/`.
4. Mudou algo que depende do app (RE/pinos/semântica)? Registre a evidência em `docs/` e, se possível, rode
   `tools/app_sim.py` (opcional; Wine) ou `CADE_E2E=1 make test` — veja `docs/DEPENDENCIAS.md`.
5. Não commite arquivos do CADe_SIMU/acervo do curso nem resoluções de atividades (`pratica5/`, `*.pdf`).
6. Commits pequenos em PT-BR. Licença GPLv3.
