#!/usr/bin/env bash
# Atalho Unix para scripts/mcp_server.py (o launcher portavel).
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/mcp_server.py" "$@"
