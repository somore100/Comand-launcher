"""Unit tests for cmdvault.privilege: sudo parsing, sudoers rule building, and
the run-time `sudo` rewriting. Nothing here touches the real system."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cmdvault import data as cv_data
from cmdvault import privilege as cv_priv


def test_find_sudo_calls_basic_shapes():
    text = "echo hi\nsudo apt update && sudo -n systemctl restart nginx\nif sudo -u bob ls /root; then x; fi\nFOO=1 sudo true"
    calls, problems = cv_priv.find_sudo_calls(text)
    assert problems == []
    assert calls == [
        ("root", ["apt", "update"]),
        ("root", ["systemctl", "restart", "nginx"]),
        ("bob", ["ls", "/root"]),
        ("root", ["true"]),
    ]


def test_find_sudo_calls_ignores_comments_and_plain_text():
    calls, problems = cv_priv.find_sudo_calls("# sudo rm -rf /\necho 'no sudo here'\n")
    assert calls == [] and problems == []


def test_find_sudo_calls_reports_unsupported_things():
    _, problems = cv_priv.find_sudo_calls("sudo -s")
    assert problems
    _, problems = cv_priv.find_sudo_calls("sudo")
    assert problems
    _, problems = cv_priv.find_sudo_calls("sudo apt install {{pkg}}")
    assert any("placeholder" in p for p in problems)


def test_pipeline_after_sudo_is_not_part_of_the_rule():
    calls, _ = cv_priv.find_sudo_calls("sudo apt update | tee /tmp/x")
    assert calls == [("root", ["apt", "update"])]


def test_build_rule_specs_exact_and_no_args(monkeypatch):
    monkeypatch.setattr(cv_priv, "_resolve_binary", lambda n: "/usr/bin/" + n)
    monkeypatch.setattr(cv_priv, "_user_controlled", lambda p: None)
    specs, problems = cv_priv.build_rule_specs([("root", ["apt", "update"]), ("root", ["apt", "update"]),
                                                ("root", ["true"])])
    assert problems == []
    assert specs == [("root", "/usr/bin/apt update"), ("root", '/usr/bin/true ""')]


def test_build_rule_specs_rejects_wildcards_and_quotes(monkeypatch):
    monkeypatch.setattr(cv_priv, "_resolve_binary", lambda n: "/usr/bin/" + n)
    monkeypatch.setattr(cv_priv, "_user_controlled", lambda p: None)
    for bad in ("/tmp/*", "a;b", "$HOME", "x\\y"):
        specs, problems = cv_priv.build_rule_specs([("root", ["rm", bad])])
        assert specs == [] and problems


def test_build_rule_specs_rejects_user_writable_files(monkeypatch, tmp_path):
    script = tmp_path / "evil.sh"
    script.write_text("echo hi\n")
    monkeypatch.setattr(cv_priv, "_resolve_binary", lambda n: str(script))
    specs, problems = cv_priv.build_rule_specs([("root", ["evil.sh"])])
    assert specs == []
    assert problems and "modified by your user" in problems[0]


def test_build_rule_specs_missing_command(monkeypatch):
    monkeypatch.setattr(cv_priv, "_resolve_binary", lambda n: None)
    specs, problems = cv_priv.build_rule_specs([("root", ["nosuchcmd"])])
    assert specs == [] and problems


def test_sudoers_text_and_escaping():
    assert cv_priv._escape_sudoers("a b,c:d=e\\f") == "a\\ b\\,c\\:d\\=e\\\\f"
    text = cv_priv.build_sudoers_text("me", [("root", "/usr/bin/apt update")])
    assert "me ALL=(root) NOPASSWD: /usr/bin/apt update\n" in text
    assert text.endswith("\n")


def test_rule_filename_has_no_dots_or_slashes():
    name = cv_priv.rule_filename("../ab.c/1234-5")
    assert "/" not in name and "." not in name
    assert name.startswith("command-vault-")


def test_entry_sudo_text_includes_script_contents(tmp_path):
    script = tmp_path / "up.sh"
    script.write_text("#!/bin/bash\nsudo apt update\n")
    assert "sudo apt update" in cv_priv.entry_sudo_text(str(script))
    assert cv_priv.entry_sudo_text("echo hi") == "echo hi"


def test_plan_admin_no_sudo_is_a_problem():
    plan = cv_priv.plan_admin({"command": "echo hi"})
    assert plan["problems"] and plan["specs"] == []


def test_admin_prefix_modes(monkeypatch, tmp_path):
    monkeypatch.setattr(cv_priv, "supports_admin", lambda: True)
    monkeypatch.setattr(cv_priv, "ensure_askpass", lambda: "/tmp/askpass.sh")
    assert cv_priv.admin_prefix({"admin_mode": "off"}) == ""
    assert "sudo -n" in cv_priv.admin_prefix({"admin_mode": "remember"})
    assert cv_priv.admin_prefix({"admin_mode": "ask"}) == ""  # terminal: sudo's own prompt
    silent = cv_priv.admin_prefix({"admin_mode": "ask"}, silent=True)
    assert "SUDO_ASKPASS" in silent and "sudo -A" in silent
    assert cv_priv.admin_prefix({"admin_mode": "ask"}, silent=True, unattended=True) == ""
    assert cv_priv.apply_admin({"admin_mode": "off"}, "cmd") == "cmd"
    assert cv_priv.apply_admin({"admin_mode": "remember"}, "cmd").endswith("\ncmd")


def test_admin_prefix_disabled_where_unsupported(monkeypatch):
    monkeypatch.setattr(cv_priv, "supports_admin", lambda: False)
    assert cv_priv.admin_prefix({"admin_mode": "remember"}) == ""


def test_install_script_is_valid_shell_and_quotes_content():
    script = cv_priv._install_script("me ALL=(root) NOPASSWD: /usr/bin/x 'y'\n", "/etc/sudoers.d/command-vault-1")
    import subprocess
    assert subprocess.run(["sh", "-n", "-c", script]).returncode == 0
    assert "visudo -cf" in script and "install -m 0440" in script


def test_normalize_adds_admin_defaults():
    data = cv_data._normalize_vault_data({"categories": [], "commands": [{"name": "a", "command": "b"}]})
    entry = data["commands"][0]
    assert entry["admin_mode"] == "off" and entry["admin_rule_hash"] == ""
