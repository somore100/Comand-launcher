"""Starts the real MCP server in a subprocess and talks to it over stdin/stdout, like an AI assistant."""
import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_mcp_server_over_stdio():
    spec = importlib.util.spec_from_file_location("mcp_check", os.path.join(ROOT, "scripts", "mcp_check.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    failed = [(d, detail) for d, ok, detail in module.run_check() if not ok]
    assert not failed, failed
