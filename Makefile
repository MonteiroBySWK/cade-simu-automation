.PHONY: setup doctor test gate clean
PY := $(shell [ -x tools/.venv-mcp/bin/python ] && echo tools/.venv-mcp/bin/python || echo python3)

setup:   ## instala o nucleo (cargo + venv + deps); nao usa Wine
	./scripts/setup.sh
doctor:  ## mostra o que funciona/falta (nucleo x opcional)
	$(PY) tools/doctor.py
test:    ## testes (os de Wine/app sao pulados sozinhos se faltar o ambiente)
	$(PY) -m pytest tools -q
gate:    ## gera e valida todos os exemplos + nota do harness de avaliacao
	@mkdir -p out
	@for f in tools/examples/*.layout.json; do n=$$(basename $$f .layout.json); \
	  printf "%-34s" $$n; $(PY) tools/build_spec.py $$f out/$$n.cad | tail -1; done
	$(PY) tools/eval/run_eval.py --golden | tail -2
clean:
	rm -rf out
