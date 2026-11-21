#!/usr/bin/env python3
"""Talks to Command Vault's MCP server exactly like an AI assistant would (JSON lines over stdin/stdout)
and checks the answers. Uses a throw-away home folder with a small test vault, so your real vault is
never read or changed.

    python3 scripts/mcp_check.py          # prints a report, exit code 0 when everything is fine
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _entry(name, command, **extra):
    e = {"id": name.lower(), "name": name, "command": command, "category": "Test", "run_mode": "silent",
         "entry_type": "command", "working_dir": "", "ai_allowed": False, "admin_mode": "off"}
    e.update(extra)
    return e


def _write_vault(home):
    """Puts a test vault where Command Vault looks for it on this OS (home is also used as APPDATA)."""
    vault = {"categories": ["Test"], "settings": {}, "commands": [
        _entry("Hello", "echo hello from the vault", ai_allowed=True),
        _entry("Greet", "echo hi {{who:world|Who to greet?}}", ai_allowed=True),
        _entry("Secret", "echo you-should-not-see-this"),
        _entry("Admin", "sudo true", ai_allowed=True, admin_mode="remember"),
    ]}
    if sys.platform.startswith("win"):
        data_dir = os.path.join(home, "CommandVault", "data")
    elif sys.platform == "darwin":
        data_dir = os.path.join(home, "Library", "Application Support", "CommandVault", "data")
    else:
        data_dir = os.path.join(home, ".local", "share", "command-vault")
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, "commands.json"), "w", encoding="utf-8") as f:
        json.dump(vault, f)


def run_check():
    """Returns [(description, ok, detail), ...]."""
    results = []
    with tempfile.TemporaryDirectory() as home:
        _write_vault(home)
        env = dict(os.environ, HOME=home, USERPROFILE=home, APPDATA=home, LOCALAPPDATA=home,
                   XDG_CONFIG_HOME=os.path.join(home, ".config"))
        proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "main.py"), "--mcp"], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, cwd=ROOT)
        counter = [0]

        def ask(method, params=None):
            counter[0] += 1
            msg = {"jsonrpc": "2.0", "id": counter[0], "method": method, "params": params or {}}
            proc.stdin.write(json.dumps(msg) + "\n")
            proc.stdin.flush()
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError("the server closed without answering: " + proc.stderr.read())
            return json.loads(line)

        def call(name, arguments):
            reply = ask("tools/call", {"name": name, "arguments": arguments})
            result = reply["result"]
            text = result["content"][0]["text"]
            return result["isError"], (json.loads(text) if not result["isError"] else text)

        def check(description, ok, detail=""):
            results.append((description, bool(ok), detail))

        try:
            init = ask("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                      "clientInfo": {"name": "mcp_check", "version": "1"}})
            check("initialize answers with server info", init["result"]["serverInfo"]["name"] == "command-vault")
            tools = [t["name"] for t in ask("tools/list")["result"]["tools"]]
            check("exposes list_entries, run_entry and get_last_run",
                  tools == ["list_entries", "run_entry", "get_last_run"], str(tools))

            err, listing = call("list_entries", {})
            names = [e["name"] for e in listing["entries"]] if not err else []
            check("lists only the entries marked for AI use (not Secret, not Admin)", names == ["Hello", "Greet"],
                  str(names))
            greet = next((e for e in listing["entries"] if e["name"] == "Greet"), {})
            check("shows each input with its default and question",
                  greet.get("inputs") == [{"name": "who", "default": "world", "label": "Who to greet?"}],
                  str(greet.get("inputs")))

            err, run = call("run_entry", {"entry": "Hello"})
            check("runs an allowed entry and returns its output",
                  not err and run["exit_code"] == 0 and "hello from the vault" in run["output"], str(run))
            err, run = call("run_entry", {"entry": "Greet", "inputs": {"who": "Alice"}})
            check("fills in an input value", not err and "hi Alice" in run["output"], str(run))
            err, text = call("run_entry", {"entry": "Secret"})
            check("refuses an entry that is not allowed", err, str(text))
            err, text = call("run_entry", {"entry": "Admin"})
            check("refuses an entry that needs administrator rights", err, str(text))
            err, text = call("run_entry", {"entry": "Greet", "inputs": {"who": "x; echo pwned"}})
            check("refuses an input value with shell syntax", err, str(text))
            err, text = call("run_entry", {"entry": "Greet", "inputs": {"who": "-o /tmp/x"}})
            check("refuses an input value that would add options", err, str(text))
            err, text = call("get_last_run", {"entry": "Hello"})
            check("get_last_run says there is no scheduled run yet", err and "no recorded" in text, str(text))
            check("every AI run is logged",
                  os.path.exists(os.path.join(home, ".config", "command-vault", "mcp-log.txt"))
                  or os.path.exists(os.path.join(home, "CommandVault", "mcp-log.txt"))
                  or os.path.exists(os.path.join(home, "Library", "Application Support", "CommandVault",
                                                 "mcp-log.txt")))
        except Exception as e:  # noqa: BLE001 - report instead of crashing
            check("the conversation completed", False, repr(e))
        finally:
            try:
                proc.stdin.close()
                proc.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                proc.kill()
    return results


def main():
    results = run_check()
    for description, ok, detail in results:
        print(("  ok    " if ok else "  FAIL  ") + description)
        if not ok and detail:
            print("        " + detail[:300].replace("\n", "\n        "))
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
