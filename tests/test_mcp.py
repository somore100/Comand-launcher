"""Tests for the MCP server (cmdvault.mcp_server): what is exposed, input safety,
the JSON-RPC handling and a real headless run."""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cmdvault import mcp_server as mcp
from cmdvault.data import _blank_entry


def _entry(name, command, **kw):
    e = _blank_entry(name, command)
    e.update(kw)
    return e


def _vault():
    return {"commands": [
        _entry("Hello", "echo hello", ai_allowed=True),
        _entry("Greet", "echo hi {{who:world}}", ai_allowed=True),
        _entry("Secret", "echo secret"),                                    # not allowed
        _entry("Admin", "sudo true", ai_allowed=True, admin_mode="remember"),  # never exposed
    ]}


def test_only_opted_in_non_admin_entries_are_exposed():
    names = [e["name"] for e in mcp.allowed_entries(_vault())]
    assert names == ["Hello", "Greet"]
    listing = mcp.call_tool("list_entries", {}, _vault())["entries"]
    assert [e["name"] for e in listing] == ["Hello", "Greet"]
    assert listing[1]["inputs"] == [{"name": "who", "default": "world"}]


def test_find_entry_by_name_or_id_and_errors():
    entries = mcp.allowed_entries(_vault())
    assert mcp.find_entry(entries, "hello")["name"] == "Hello"
    assert mcp.find_entry(entries, entries[1]["id"])["name"] == "Greet"
    for bad in ("Secret", "Admin", "nope"):
        try:
            mcp.find_entry(entries, bad)
            assert False
        except mcp.ToolError:
            pass


def test_input_values_cannot_inject_shell_syntax():
    entry = mcp.allowed_entries(_vault())[1]
    assert mcp.check_inputs(entry, {"who": "Alice-B2"}) == {"who": "Alice-B2"}
    assert mcp.check_inputs(entry, {}) == {"who": "world"}
    for bad in ("x; rm -rf ~", "$(id)", "`id`", "a && b", "a\nb", 'q"q', "a|b", "a>b"):
        try:
            mcp.check_inputs(entry, {"who": bad})
            assert False, bad
        except mcp.ToolError:
            pass
    try:
        mcp.check_inputs(entry, {"other": "x"})
        assert False
    except mcp.ToolError:
        pass


def test_run_entry_headless_returns_output_and_exit_code():
    result = mcp.call_tool("run_entry", {"entry": "Greet", "inputs": {"who": "bot"}}, _vault())
    assert result["exit_code"] == 0 and "hi bot" in result["output"] and not result["timed_out"]
    failing = {"commands": [_entry("Fail", f'"{sys.executable}" -c "import sys; sys.exit(3)"', ai_allowed=True)]}
    assert mcp.call_tool("run_entry", {"entry": "Fail"}, failing)["exit_code"] == 3


def test_run_entry_timeout_is_enforced():
    slow = {"commands": [_entry("Slow", f'"{sys.executable}" -c "import time; time.sleep(5)"', ai_allowed=True)]}
    result = mcp.call_tool("run_entry", {"entry": "Slow", "timeout_seconds": 1}, slow)
    assert result["timed_out"] is True and result["exit_code"] is None


def test_json_rpc_flow():
    init = mcp.handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                               "params": {"protocolVersion": "2025-03-26"}}, _vault())
    assert init["result"]["protocolVersion"] == "2025-03-26" and "tools" in init["result"]["capabilities"]
    assert mcp.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    tools = mcp.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, _vault())
    assert {t["name"] for t in tools["result"]["tools"]} == {"list_entries", "run_entry", "get_last_run"}
    call = mcp.handle_message({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                               "params": {"name": "run_entry", "arguments": {"entry": "Secret"}}}, _vault())
    assert call["result"]["isError"] is True
    unknown = mcp.handle_message({"jsonrpc": "2.0", "id": 4, "method": "bogus"}, _vault())
    assert unknown["error"]["code"] == -32601


def test_serve_loop_handles_garbage_and_requests():
    stdin = io.StringIO("not json\n" + json.dumps({"jsonrpc": "2.0", "id": 7, "method": "ping"}) + "\n\n")
    stdout = io.StringIO()
    assert mcp.serve(stdin, stdout) == 0
    lines = [json.loads(l) for l in stdout.getvalue().splitlines()]
    assert lines[0]["error"]["code"] == -32700 and lines[1] == {"jsonrpc": "2.0", "id": 7, "result": {}}


def test_client_config_snippet_is_valid_json():
    cfg = json.loads(mcp.client_config_snippet())
    server = cfg["mcpServers"]["command-vault"]
    assert server["args"][-1] == "--mcp" and server["command"]
