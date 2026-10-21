# Atalhos Unix; no Windows use: python scripts/dev.py <tarefa>
.PHONY: setup doctor test gate mcp-config
setup doctor test gate mcp-config:
	python3 scripts/dev.py $@
