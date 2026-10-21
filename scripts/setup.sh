#!/usr/bin/env bash
# Atalho Unix para `python scripts/dev.py setup` (no Windows use o comando python direto).
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/dev.py" setup
