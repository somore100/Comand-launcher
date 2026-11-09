"""Tests for: Add-many options, macOS startup (LaunchAgents), and the import re-apply helpers."""
import os
import plistlib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cmdvault import autostart as cv_auto
from cmdvault import bulk as cv_bulk


def test_build_entries_applies_startup_schedule_and_admin():
    rows = cv_bulk.parse_bulk_lines("echo one\necho two")
    plain = cv_bulk.build_entries(rows, "Cat", "silent", False)
    assert plain[0]["autostart"] is False and plain[0]["schedule_enabled"] is False and plain[0]["admin_mode"] == "off"
    full = cv_bulk.build_entries(rows, "Cat", "silent", False, autostart=True, schedule_time="08:30",
                                 admin_mode="ask")
    assert all(e["autostart"] and e["schedule_enabled"] and e["schedule_time"] == "08:30"
               and e["schedule_days"] == [] and e["admin_mode"] == "ask" for e in full)


def test_mac_launch_agent_files(tmp_path, monkeypatch):
    monkeypatch.setattr(cv_auto, "is_mac", lambda: True)
    monkeypatch.setattr(cv_auto, "is_linux", lambda: False)
    monkeypatch.setattr(cv_auto, "is_windows", lambda: False)
    real = os.path.expanduser
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)) if p.startswith("~") else real(p))
    entry = {"id": "abc-123", "name": "Job", "command": "echo hi", "working_dir": "", "entry_type": "command",
             "browser_profile": False, "admin_mode": "off"}
    cv_auto.set_entry_autostart(entry, True)
    plist = tmp_path / "Library" / "LaunchAgents" / "com.commandvault.entry.abc-123.plist"
    assert plist.is_file()
    data = plistlib.loads(plist.read_bytes())
    assert data["Label"] == "com.commandvault.entry.abc-123" and data["RunAtLoad"] is True
    script = data["ProgramArguments"][1]
    assert data["ProgramArguments"][0] == "/bin/bash" and "echo hi" in open(script).read()
    assert cv_auto.entry_autostart_enabled("abc-123")
    cv_auto.set_entry_autostart(entry, False)
    assert not plist.exists() and not os.path.exists(script)
    cv_auto.set_app_autostart(True)
    assert cv_auto.app_autostart_enabled()
    cv_auto.set_app_autostart(False)
    assert not cv_auto.app_autostart_enabled()
