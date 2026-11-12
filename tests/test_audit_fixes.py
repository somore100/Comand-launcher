"""Regression tests for the security/quality audit fixes."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cmdvault import data as cv_data
from cmdvault import mcp_server as mcp
from cmdvault import privilege as cv_priv
from cmdvault import routine as rt
from cmdvault import terminals


def _stub(monkeypatch):
    monkeypatch.setattr(cv_priv, "_resolve_binary", lambda n: n if n.startswith("/") else "/usr/bin/" + n)
    monkeypatch.setattr(cv_priv, "_user_controlled", lambda p: None)


def test_wildcard_in_binary_is_rejected(monkeypatch):
    _stub(monkeypatch)
    specs, problems = cv_priv.build_rule_specs([("root", ["/usr/bin/*"])])
    assert specs == [] and problems


def test_relative_or_missing_script_path_is_rejected(monkeypatch):
    _stub(monkeypatch)
    for argv in (["python3", "script.py"], ["bash", "/home/u/does-not-exist-later.sh"], ["bash", "./x"]):
        specs, problems = cv_priv.build_rule_specs([("root", argv)])
        assert specs == [] and problems, argv


def test_sudo_user_must_be_a_real_account(monkeypatch):
    _stub(monkeypatch)
    specs, problems = cv_priv.build_rule_specs([("ALL", ["id"])])
    assert specs == [] and problems


def test_symlink_itself_is_checked(tmp_path):
    target = tmp_path / "real"
    target.write_text("x")
    link = tmp_path / "link"
    link.symlink_to(target)
    assert cv_priv._user_controlled(str(link))  # the folder holding the link is writable by us


def _entry(command):
    return {"id": "a", "name": "n", "command": command, "entry_type": "command", "admin_mode": "off"}


def test_mcp_rejects_option_injection_and_globs():
    entry = _entry("curl {{url}}")
    for bad in ("-o /tmp/x http://e/x", "-v", "a b", "*", "~/x", "a%20b", "#x"):
        with pytest.raises(mcp.ToolError):
            mcp.check_inputs(entry, {"url": bad})
    assert mcp.check_inputs(entry, {"url": "http://example.com/x"}) == {"url": "http://example.com/x"}


def test_mcp_allows_spaces_only_inside_quotes():
    assert mcp.check_inputs(_entry('echo "{{m}}"'), {"m": "hello world"}) == {"m": "hello world"}
    with pytest.raises(mcp.ToolError):
        mcp.check_inputs(_entry("echo {{m}}"), {"m": "hello world"})


def test_normalize_replaces_unsafe_ids_and_bad_times():
    raw = {"commands": [{"id": "a\n* * * * * evil", "name": "x", "command": "y"},
                        {"id": "../../x", "name": "x", "command": "y", "schedule_time": "25:99",
                         "schedule_enabled": True},
                        "junk", {"name": "no id", "command": 5}]}
    data = cv_data._normalize_vault_data(raw)
    assert len(data["commands"]) == 3
    assert all(cv_data.SAFE_ID_RE.match(c["id"]) for c in data["commands"])
    assert len({c["id"] for c in data["commands"]}) == 3
    assert data["commands"][1]["schedule_time"] == "" and not data["commands"][1]["schedule_enabled"]
    assert data["commands"][2]["command"] == "5"


def test_strip_persistence_switches_everything_off():
    data = cv_data._normalize_vault_data({"commands": [
        {"id": "a", "name": "n", "command": "c", "autostart": True, "schedule_enabled": True,
         "schedule_time": "10:00", "hotkey_pynput": "<f1>", "ai_allowed": True, "admin_mode": "remember",
         "browser_profile_dir": "/home/x/Documents"}]})
    cv_data.strip_persistence(data)
    c = data["commands"][0]
    assert not (c["autostart"] or c["schedule_enabled"] or c["hotkey_pynput"] or c["ai_allowed"])
    assert c["admin_mode"] == "off" and c["browser_profile_dir"] == ""


def test_terminal_commands_with_ampersand_and_custom_template():
    argv = terminals.NAMED_LINUX_TERMINALS["GNOME Terminal"]("firefox &")
    assert argv[-1] == "firefox &\nexec bash"
    build = terminals.custom_terminal_builder("myterm -e %CMD%")
    assert build('bash "/home/u/my scripts/a.sh"') == ["myterm", "-e", 'bash "/home/u/my scripts/a.sh"']


def test_routine_script_does_not_substitute_inside_steps():
    routine = {"kind": "web", "steps": [{"type": "wait", "seconds": 1, "note": "__KIND__ __SHOW__"}],
               "show_browser": False}
    src = rt.generate_script("e1", "name", routine)
    compile(src, "routine.py", "exec")
    assert "__KIND__" in src  # still just text inside the JSON string
