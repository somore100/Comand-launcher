"""
Unit tests for the pure(-ish) logic in main.py: the parts that don't need a
live Tk event loop to exercise -- the data layer (normalize/load/save,
including atomic-write and corruption-recovery behavior), resolve_exec_command,
placeholder extraction/filling, and update-check version parsing.

Run with:
    pip install pytest
    pytest

These intentionally do NOT touch the real commands.json / app-config dir:
every test that goes through load_data()/save_data() monkeypatches
main.get_data_file() to a path under pytest's tmp_path fixture.
"""
import json
import os
import socket
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main as m


@pytest.fixture(autouse=True)
def no_display_dialogs(monkeypatch):
    """load_data() pops a messagebox.showwarning on a corrupted file. In the
    real app there's always a live Tk root, so this is harmless; under
    pytest (often headless/no DISPLAY) it can raise instead of the
    tk.TclError load_data() catches -- Tk's own _get_temp_root() leaves a
    module-level flag in a bad state after the first failed attempt to spin
    up a throwaway root. That's a test-environment quirk, not something
    load_data() does wrong, so we stub the dialog out rather than test Tk's
    dialog plumbing here."""
    monkeypatch.setattr(m.messagebox, "showwarning", lambda *a, **k: None)


# ---------------------------------------------------------------------------
# _parse_version / _version_is_newer
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("1.5.0", (1, 5, 0)),
    ("v1.5.0", (1, 5, 0)),
    ("V2.0", (2, 0)),
    ("1.5.0-beta", (1, 5, 0)),
    # Quirk in the current implementation: it only stops at the first chunk
    # with NO leading digits. "0-beta" still yields digit "0", so parsing
    # continues into the next dot-separated chunk ("2") instead of stopping
    # at the first suffixed chunk. Documented here so a future change to
    # _parse_version has to consciously decide whether to keep this.
    ("1.5.0-beta.2", (1, 5, 0, 2)),
    ("1.5", (1, 5)),
    ("1", (1,)),
    ("", ()),
    ("beta", ()),
    ("1..0", (1,)),  # empty chunk between dots stops parsing
])
def test_parse_version(raw, expected):
    assert m._parse_version(raw) == expected


@pytest.mark.parametrize("candidate, current, expected", [
    ("1.6.0", "1.5.0", True),
    ("1.5.0", "1.6.0", False),
    ("1.5.0", "1.5.0", False),
    ("v2.0.0", "1.9.9", True),
    ("1.5.0-beta", "1.5.0", False),   # suffix dropped -> equal -> not newer
    ("garbage", "1.0.0", False),       # unparsable candidate -> () is never >
    ("1.0.0", "garbage", True),        # unparsable current -> () -> anything real is newer
])
def test_version_is_newer(candidate, current, expected):
    assert m._version_is_newer(candidate, current) is expected


# ---------------------------------------------------------------------------
# extract_placeholders / fill_placeholders
# ---------------------------------------------------------------------------

def test_extract_placeholders_none():
    assert m.extract_placeholders("echo hello") == []


def test_extract_placeholders_simple():
    assert m.extract_placeholders("echo {{name}}") == [("name", "")]


def test_extract_placeholders_with_default():
    assert m.extract_placeholders("ping {{host:localhost}}") == [("host", "localhost")]


def test_extract_placeholders_dedupes_keeps_first_default_and_order():
    cmd = "cp {{src}} {{dst:/tmp}} && echo {{src}} done"
    assert m.extract_placeholders(cmd) == [("src", ""), ("dst", "/tmp")]


def test_extract_placeholders_default_with_special_chars():
    # default is "everything up to the next }", so punctuation/spaces are fine
    assert m.extract_placeholders("{{msg:hello, world!}}") == [("msg", "hello, world!")]


def test_fill_placeholders_basic():
    result = m.fill_placeholders("ping {{host}}", {"host": "example.com"})
    assert result == "ping example.com"


def test_fill_placeholders_missing_value_left_untouched():
    # if a name isn't in values, the original {{name}} / {{name:default}} text is kept
    result = m.fill_placeholders("echo {{a}} {{b:def}}", {"a": "1"})
    assert result == "echo 1 {{b:def}}"


def test_fill_placeholders_repeated_name_all_replaced():
    result = m.fill_placeholders("{{x}}-{{x}}", {"x": "9"})
    assert result == "9-9"


# ---------------------------------------------------------------------------
# resolve_exec_command
# ---------------------------------------------------------------------------

def test_resolve_exec_command_passthrough_for_raw_command():
    # not a file on disk -> returned untouched
    assert m.resolve_exec_command("echo hello") == "echo hello"


def test_resolve_exec_command_passthrough_for_multiline_script_text():
    multiline = "echo one\necho two"
    assert m.resolve_exec_command(multiline) == multiline


def test_resolve_exec_command_wraps_shell_script(tmp_path):
    script = tmp_path / "deploy.sh"
    script.write_text("#!/bin/bash\necho hi\n")
    assert m.resolve_exec_command(str(script)) == f'bash "{script}"'


def test_resolve_exec_command_wraps_bash_extension(tmp_path):
    script = tmp_path / "deploy.bash"
    script.write_text("echo hi\n")
    assert m.resolve_exec_command(str(script)) == f'bash "{script}"'


def test_resolve_exec_command_wraps_python_script(tmp_path, monkeypatch):
    script = tmp_path / "run.py"
    script.write_text("print('hi')\n")
    monkeypatch.setattr(m, "is_windows", lambda: False)
    assert m.resolve_exec_command(str(script)) == f'python3 "{script}"'


def test_resolve_exec_command_wraps_python_script_on_windows(tmp_path, monkeypatch):
    script = tmp_path / "run.py"
    script.write_text("print('hi')\n")
    monkeypatch.setattr(m, "is_windows", lambda: True)
    assert m.resolve_exec_command(str(script)) == f'python "{script}"'


def test_resolve_exec_command_wraps_powershell():
    # doesn't need to exist on disk to check the .ps1 branch text, but the
    # function requires os.path.isfile -- so use a real temp file.
    pass  # covered together with .bat below to share the tmp_path fixture


def test_resolve_exec_command_wraps_ps1_and_bat(tmp_path):
    ps1 = tmp_path / "script.ps1"
    ps1.write_text("Write-Host hi\n")
    assert m.resolve_exec_command(str(ps1)) == f'powershell -ExecutionPolicy Bypass -File "{ps1}"'

    bat = tmp_path / "script.bat"
    bat.write_text("echo hi\n")
    assert m.resolve_exec_command(str(bat)) == f'"{bat}"'


def test_resolve_exec_command_unknown_extension_quotes_and_chmods(tmp_path):
    script = tmp_path / "run.thing"
    script.write_text("echo hi\n")
    result = m.resolve_exec_command(str(script))
    assert result == f'"{script}"'
    if os.name != "nt":
        assert os.access(str(script), os.X_OK)


def test_resolve_exec_command_strips_surrounding_whitespace_for_isfile_check(tmp_path):
    script = tmp_path / "deploy.sh"
    script.write_text("echo hi\n")
    # leading/trailing whitespace shouldn't stop it from being recognized as a file
    assert m.resolve_exec_command(f"  {script}  ") == f'bash "{script}"'


# ---------------------------------------------------------------------------
# _normalize_vault_data
# ---------------------------------------------------------------------------

def test_normalize_legacy_flat_list():
    legacy = [
        {"name": "hello", "command": "echo hi"},
        {"name": "", "command": ""},  # empty placeholder row, should be dropped
    ]
    result = m._normalize_vault_data(legacy)
    assert result["categories"] == [m.UNCATEGORIZED]
    assert len(result["commands"]) == 1
    entry = result["commands"][0]
    assert entry["name"] == "hello"
    assert entry["command"] == "echo hi"
    assert entry["category"] == m.UNCATEGORIZED
    assert "id" in entry  # _blank_entry assigns a fresh uuid


def test_normalize_legacy_flat_list_all_empty_rows_dropped():
    result = m._normalize_vault_data([{"name": "  ", "command": " "}])
    assert result["commands"] == []


def test_normalize_current_format_fills_missing_fields():
    raw = {
        "categories": ["Dev"],
        "commands": [{"id": "abc", "name": "x", "command": "y"}],
    }
    result = m._normalize_vault_data(raw)
    assert result["settings"] == {}
    entry = result["commands"][0]
    assert entry["working_dir"] == ""
    assert entry["run_mode"] == "terminal"
    assert entry["entry_type"] == "command"
    assert entry["category"] == m.UNCATEGORIZED
    assert entry["icon"] == m.DEFAULT_ICON
    assert entry["autostart"] is False
    assert entry["hotkey_display"] == ""
    assert entry["hotkey_pynput"] == ""


def test_normalize_current_format_preserves_existing_fields():
    raw = {
        "categories": ["Dev"],
        "commands": [{
            "id": "abc", "name": "x", "command": "y",
            "working_dir": "/tmp", "run_mode": "background",
            "category": "Dev", "autostart": True,
        }],
    }
    result = m._normalize_vault_data(raw)
    entry = result["commands"][0]
    assert entry["working_dir"] == "/tmp"
    assert entry["run_mode"] == "background"
    assert entry["category"] == "Dev"
    assert entry["autostart"] is True


def test_normalize_missing_top_level_keys():
    result = m._normalize_vault_data({})
    assert result == {"categories": [], "commands": [], "settings": {}}


# ---------------------------------------------------------------------------
# save_data / load_data: atomic write, .bak rotation, corruption recovery
# ---------------------------------------------------------------------------

@pytest.fixture
def data_file(tmp_path, monkeypatch):
    path = str(tmp_path / "commands.json")
    monkeypatch.setattr(m, "get_data_file", lambda: path)
    return path


def test_save_then_load_roundtrip(data_file):
    data = {"categories": ["A"], "commands": [m._blank_entry("hi", "echo hi")], "settings": {}}
    m.save_data(data)
    loaded = m.load_data()
    assert loaded["categories"] == ["A"]
    assert loaded["commands"][0]["name"] == "hi"


def test_save_data_no_bak_on_first_save(data_file):
    m.save_data({"categories": [], "commands": [], "settings": {}})
    assert not os.path.exists(data_file + ".bak")


def test_save_data_creates_bak_of_previous_version(data_file):
    m.save_data({"categories": ["first"], "commands": [], "settings": {}})
    m.save_data({"categories": ["second"], "commands": [], "settings": {}})
    assert os.path.exists(data_file + ".bak")
    with open(data_file + ".bak") as f:
        bak = json.load(f)
    assert bak["categories"] == ["first"]
    with open(data_file) as f:
        current = json.load(f)
    assert current["categories"] == ["second"]


def test_save_data_no_leftover_temp_files(data_file, tmp_path):
    m.save_data({"categories": [], "commands": [], "settings": {}})
    m.save_data({"categories": ["x"], "commands": [], "settings": {}})
    leftovers = [p for p in os.listdir(str(tmp_path)) if p.startswith(".commands-")]
    assert leftovers == []


def test_load_data_missing_file_returns_empty_vault(data_file):
    assert not os.path.exists(data_file)
    assert m.load_data() == {"categories": [], "commands": [], "settings": {}}


def test_load_data_recovers_from_bak_when_corrupted(data_file):
    m.save_data({"categories": ["good"], "commands": [], "settings": {}})
    m.save_data({"categories": ["good", "second"], "commands": [], "settings": {}})
    # corrupt the live file
    with open(data_file, "w") as f:
        f.write("{not valid json")

    result = m.load_data()
    assert result["categories"] == ["good"]  # recovered from .bak (the first save)

    # the corrupted file should be quarantined, not left in place
    assert not os.path.exists(data_file) or json.loads(open(data_file).read())
    quarantined = [p for p in os.listdir(os.path.dirname(data_file)) if "corrupted" in p]
    assert len(quarantined) == 1


def test_load_data_corrupted_with_no_bak_returns_empty_vault(data_file):
    with open(data_file, "w") as f:
        f.write("not json at all {{{")
    result = m.load_data()
    assert result == {"categories": [], "commands": [], "settings": {}}
    quarantined = [p for p in os.listdir(os.path.dirname(data_file)) if "corrupted" in p]
    assert len(quarantined) == 1


def test_load_data_corrupted_bak_falls_back_to_empty_vault(data_file):
    with open(data_file, "w") as f:
        f.write("also not json {{{")
    with open(data_file + ".bak", "w") as f:
        f.write("still not json {{{")
    result = m.load_data()
    assert result == {"categories": [], "commands": [], "settings": {}}


# ---------------------------------------------------------------------------
# Single-instance lock: mutual exclusion via OS file lock, ephemeral port +
# token auth for the "raise window" IPC channel
# ---------------------------------------------------------------------------

@pytest.fixture
def instance_lock_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "app_config_dir", lambda: str(tmp_path))
    yield str(tmp_path)


def test_acquire_lock_publishes_port_and_token(instance_lock_dir):
    handle = m.acquire_single_instance_lock(lambda: None)
    try:
        assert handle is not None
        lock_path = m._instance_lock_path()
        assert os.path.exists(lock_path)
        with open(lock_path) as f:
            info = json.load(f)
        assert isinstance(info["port"], int)
        assert isinstance(info["token"], str) and len(info["token"]) > 0
    finally:
        m.release_single_instance_lock(handle)


@pytest.mark.skipif(os.name == "nt", reason="POSIX file permissions only")
def test_acquire_lock_file_is_user_only_on_posix(instance_lock_dir):
    handle = m.acquire_single_instance_lock(lambda: None)
    try:
        mode = os.stat(m._instance_lock_path()).st_mode & 0o777
        assert mode == 0o600
    finally:
        m.release_single_instance_lock(handle)


def test_second_acquire_fails_while_first_holds_lock(instance_lock_dir):
    handle1 = m.acquire_single_instance_lock(lambda: None)
    try:
        assert handle1 is not None
        handle2 = m.acquire_single_instance_lock(lambda: None)
        assert handle2 is None
    finally:
        m.release_single_instance_lock(handle1)


def test_notify_running_instance_triggers_on_show(instance_lock_dir):
    shown = []
    handle = m.acquire_single_instance_lock(lambda: shown.append(True))
    try:
        assert m.notify_running_instance() is True
        for _ in range(20):
            if shown:
                break
            time.sleep(0.05)
        assert shown == [True]
    finally:
        m.release_single_instance_lock(handle)


def test_notify_running_instance_false_when_nothing_running(instance_lock_dir):
    assert m.notify_running_instance() is False


def test_wrong_token_does_not_trigger_on_show(instance_lock_dir):
    shown = []
    handle = m.acquire_single_instance_lock(lambda: shown.append(True))
    try:
        with open(m._instance_lock_path()) as f:
            info = json.load(f)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect(("127.0.0.1", info["port"]))
        s.sendall(b"SHOW not-the-right-token\n")
        s.close()
        time.sleep(0.2)
        assert shown == []
    finally:
        m.release_single_instance_lock(handle)


def test_release_removes_lock_file_and_allows_reacquire(instance_lock_dir):
    handle1 = m.acquire_single_instance_lock(lambda: None)
    m.release_single_instance_lock(handle1)
    assert not os.path.exists(m._instance_lock_path())

    handle2 = m.acquire_single_instance_lock(lambda: None)
    assert handle2 is not None
    m.release_single_instance_lock(handle2)


def test_notify_running_instance_stale_lock_file_returns_false(instance_lock_dir):
    # A lock file with garbage content (e.g. left over from an unrelated
    # process, or corrupted) should be treated the same as "no running
    # instance" rather than raising.
    with open(m._instance_lock_path(), "w") as f:
        f.write("not valid json {{{")
    assert m.notify_running_instance() is False


def test_release_single_instance_lock_handles_none():
    m.release_single_instance_lock(None)  # should not raise
