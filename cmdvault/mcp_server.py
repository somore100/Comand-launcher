"""mcp_server -- let AI assistants use Command Vault through the Model Context Protocol.

Start it with `command-vault --mcp` (an MCP client launches this itself, talking
JSON-RPC over stdin/stdout). Nothing is exposed by default: an entry is only
visible and runnable here when you tick "Let AI assistants run this entry" in
its Edit dialog. Tools:

  list_entries  the entries you allowed, with the inputs ({{placeholders}}) each takes
  run_entry     run one of them (no window) and return its exit code and output
  get_last_run  the last result of a scheduled entry (same data as the Last run button)

Deliberately NOT possible: creating, editing or deleting entries, running entries
that need administrator rights, or running anything you haven't allowed. Input
values from the AI are rejected if they contain shell syntax, so they can't change
what the command does. Every AI run is appended to mcp-log.txt in Command Vault's
settings folder.
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from .config import APP_NAME, APP_VERSION
from .data import app_config_dir, load_data
from .execution import is_program_path, program_command, resolve_exec_command
from .placeholders import extract_placeholders, fill_placeholders
from .runstatus import read_run_log_tail, read_run_status

PROTOCOL_VERSION = "2024-11-05"
MAX_OUTPUT = 16 * 1024
DEFAULT_TIMEOUT = 60
MAX_TIMEOUT = 600
UNSAFE_VALUE_CHARS = set("`$;&|<>(){}\\\"'\n\r\x00")

TOOLS = [
    {
        "name": "list_entries",
        "description": "List the Command Vault entries the user has allowed AI assistants to run, with the "
                       "inputs each one takes.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_entry",
        "description": "Run one allowed Command Vault entry (no window) and return its exit code and output. "
                       "Use list_entries first to see names and inputs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entry": {"type": "string", "description": "Entry name (or id)."},
                "inputs": {"type": "object", "description": "Values for the entry's inputs, by name.",
                           "additionalProperties": {"type": "string"}},
                "timeout_seconds": {"type": "integer", "description": f"Stop after this long (default "
                                    f"{DEFAULT_TIMEOUT}, max {MAX_TIMEOUT})."},
            },
            "required": ["entry"],
        },
    },
    {
        "name": "get_last_run",
        "description": "Result (exit code, time, output) of the last scheduled run of an allowed entry.",
        "inputSchema": {"type": "object", "properties": {"entry": {"type": "string"}}, "required": ["entry"]},
    },
]


class ToolError(Exception):
    """A problem to report back to the AI as a tool error (not a protocol error)."""


# ---------------------------------------------------------------------------
# Which entries are exposed
# ---------------------------------------------------------------------------
def allowed_entries(data):
    """Entries the user opted in. Entries that need admin rights are never exposed."""
    return [e for e in data.get("commands", [])
            if e.get("ai_allowed") and e.get("admin_mode", "off") == "off"]


def find_entry(entries, ref):
    ref = (ref or "").strip()
    for e in entries:
        if e["id"] == ref:
            return e
    matches = [e for e in entries if e["name"].strip().lower() == ref.lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ToolError(f"More than one allowed entry is called '{ref}'; use its id.")
    raise ToolError(f"No allowed entry called '{ref}'. Use list_entries to see what is available.")


def describe_entry(entry):
    inputs = extract_placeholders(entry.get("command", "")) if entry.get("entry_type") != "routine" else []
    return {
        "id": entry["id"],
        "name": entry["name"],
        "category": entry.get("category", ""),
        "type": entry.get("entry_type", "command"),
        "inputs": [{"name": n, "default": d} for n, d in inputs],
        "scheduled": bool(entry.get("schedule_enabled")),
    }


def check_inputs(entry, inputs):
    """Validated {name: value} for the entry's placeholders, or ToolError."""
    inputs = inputs or {}
    if not isinstance(inputs, dict):
        raise ToolError("'inputs' must be an object of name: value.")
    wanted = extract_placeholders(entry.get("command", "")) if entry.get("entry_type") != "routine" else []
    names = {n for n, _d in wanted}
    unknown = set(inputs) - names
    if unknown:
        raise ToolError(f"Unknown input(s): {', '.join(sorted(unknown))}. This entry takes: "
                        f"{', '.join(sorted(names)) or 'no inputs'}.")
    values = {}
    for name, default in wanted:
        value = str(inputs.get(name, default))
        bad = sorted({c for c in value if c in UNSAFE_VALUE_CHARS})
        if bad:
            raise ToolError(f"The value for '{name}' contains characters that could change what the command "
                            f"does ({' '.join(repr(c) for c in bad)}); use plain text.")
        values[name] = value
    return values


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------
def _clean_env():
    env = os.environ.copy()
    for var in ("APPIMAGE", "APPDIR", "ARGV0", "OWD"):
        env.pop(var, None)
    return env


def build_command(entry, values):
    command = entry["command"]
    if entry.get("entry_type") == "appimage":
        if not is_program_path(command):
            raise ToolError(f"Program not found: {command}")
        exec_cmd = program_command(command)
    else:
        exec_cmd = resolve_exec_command(fill_placeholders(command, values))
    from .browser import prefix_exec_cmd
    return prefix_exec_cmd(entry, exec_cmd)


def log_ai_run(entry, values, result):
    try:
        with open(os.path.join(app_config_dir(), "mcp-log.txt"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')}  {entry['name']}  inputs={json.dumps(values)}  "
                    f"-> {result}\n")
    except OSError:
        pass


def run_entry_headless(entry, values, timeout):
    working_dir = entry.get("working_dir") or None
    if working_dir and not os.path.isdir(working_dir):
        raise ToolError(f"Working directory not found: {working_dir}")
    cmd = build_command(entry, values)
    started = time.time()
    try:
        proc = subprocess.run(cmd, shell=True, cwd=working_dir, env=_clean_env(), stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, errors="replace", timeout=timeout)
        out = (proc.stdout or "") + (proc.stderr or "")
        code, timed_out = proc.returncode, False
    except subprocess.TimeoutExpired as e:
        out = ((e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""))
        code, timed_out = None, True
    tail = out[-MAX_OUTPUT:]
    return {"exit_code": code, "timed_out": timed_out, "seconds": round(time.time() - started, 1),
            "output": tail, "output_truncated": len(out) > MAX_OUTPUT}


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------
def call_tool(name, arguments, data=None):
    """Runs a tool; returns a JSON-able result or raises ToolError."""
    data = data if data is not None else load_data()
    entries = allowed_entries(data)
    arguments = arguments or {}
    if name == "list_entries":
        return {"entries": [describe_entry(e) for e in entries]}
    if name == "run_entry":
        entry = find_entry(entries, arguments.get("entry"))
        values = check_inputs(entry, arguments.get("inputs"))
        try:
            timeout = int(arguments.get("timeout_seconds") or DEFAULT_TIMEOUT)
        except (TypeError, ValueError):
            raise ToolError("timeout_seconds must be a whole number.")
        timeout = max(1, min(timeout, MAX_TIMEOUT))
        result = run_entry_headless(entry, values, timeout)
        log_ai_run(entry, values, f"exit {result['exit_code']}" + (" (timed out)" if result["timed_out"] else ""))
        return result
    if name == "get_last_run":
        entry = find_entry(entries, arguments.get("entry"))
        status = read_run_status(entry["id"])
        if status is None:
            raise ToolError("This entry has no recorded scheduled run yet.")
        return {"exit_code": status["exit_code"], "when": status["when"],
                "output": read_run_log_tail(entry["id"], MAX_OUTPUT)}
    raise ToolError(f"Unknown tool: {name}")


def handle_message(msg, data=None):
    """One JSON-RPC message in, response dict out (None for notifications)."""
    method, msg_id, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
    if method is None:
        return None  # a response to something we never sent
    if msg_id is None:
        return None  # notification (e.g. notifications/initialized)
    if method == "initialize":
        result = {"protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
                  "capabilities": {"tools": {}},
                  "serverInfo": {"name": APP_NAME.lower().replace(" ", "-"), "version": APP_VERSION}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        try:
            payload = call_tool(params.get("name"), params.get("arguments"), data)
            result = {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}], "isError": False}
        except ToolError as e:
            result = {"content": [{"type": "text", "text": str(e)}], "isError": True}
    else:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _redirect_dialogs_to_stderr():
    """Library code (e.g. corrupt-vault recovery) may call tkinter message boxes; there is no
    window in MCP mode and stdout carries the protocol, so send them to stderr instead."""
    from tkinter import messagebox

    def to_stderr(title=None, message=None, *a, **k):
        print(f"[{title}] {message}", file=sys.stderr, flush=True)
        return True
    for name in ("showinfo", "showwarning", "showerror", "askyesno", "askokcancel"):
        setattr(messagebox, name, to_stderr)


def serve(stdin=None, stdout=None):
    """Blocking stdio loop: one JSON message per line."""
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    _redirect_dialogs_to_stderr()
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            if not isinstance(msg, dict):
                raise ValueError("not an object")
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            try:
                reply = handle_message(msg)
            except Exception as e:  # noqa: BLE001 - never crash the loop on a bad request
                reply = {"jsonrpc": "2.0", "id": msg.get("id"),
                         "error": {"code": -32603, "message": f"Internal error: {e}"}}
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()
    return 0


def client_config_snippet():
    """JSON an MCP client (Claude Desktop, Claude Code, ...) needs to start this server."""
    if getattr(sys, "frozen", False) and not os.environ.get("APPIMAGE"):
        command, args = sys.executable, ["--mcp"]
    elif os.environ.get("APPIMAGE"):
        command, args = os.environ["APPIMAGE"], ["--mcp"]
    else:
        command, args = sys.executable, [os.path.abspath(sys.argv[0]), "--mcp"]
    return json.dumps({"mcpServers": {"command-vault": {"command": command, "args": args}}}, indent=2)
