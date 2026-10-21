//! `cade_mcp` — ESQUELETO (fase futura).
//!
//! Servidor MCP por stdio (JSON-RPC 2.0, handshake `initialize` + `tools/list` + `tools/call`) que substitui
//! `tools/cade_mcp.py`. Tools a expor (mesmos nomes/descricoes do Python): cad_validate, cad_parse, cad_emit,
//! cad_new, cad_inspect, cad_preview, cad_from_image, cad_simulate, cad_test, cad_symbols, cad_pins, cad_examples,
//! cad_example, cad_design, cad_gate, cad_build, cad_simular_no_app. Subcomando previsto: `cade mcp`.
//! `cad_build`/`cad_design` ja tem implementacao em `cade_build` + `cade_layout`.
//! Smoke de referencia: `tools/mcp_call.py`, `tools/test_mcp.py`.
