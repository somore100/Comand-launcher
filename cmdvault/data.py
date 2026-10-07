"""data -- split out of the former monolithic main.py."""
from datetime import datetime
import json
from tkinter import messagebox
import os
import shutil
import sys
import tempfile
import tkinter as tk
import uuid
from .platform_utils import is_mac, is_windows
from .theme import DEFAULT_ICON, UNCATEGORIZED


# Data storage location (configurable, auto-organized by default)
# ---------------------------------------------------------------------------
def app_config_dir():
    """Where the small pointer config file lives (this itself is fixed --
    it's just a breadcrumb telling the app where the *real* data folder is)."""
    if is_windows():
        base = os.getenv("APPDATA", os.path.expanduser("~"))
        return os.path.join(base, "CommandVault")
    if is_mac():
        return os.path.expanduser("~/Library/Application Support/CommandVault")
    return os.path.expanduser("~/.config/command-vault")


def app_config_file():
    return os.path.join(app_config_dir(), "config.json")


def default_data_dir():
    """The organized default folder Command Vault stores its data in."""
    if is_windows():
        base = os.getenv("APPDATA", os.path.expanduser("~"))
        return os.path.join(base, "CommandVault", "data")
    if is_mac():
        return os.path.expanduser("~/Library/Application Support/CommandVault/data")
    return os.path.expanduser("~/.local/share/command-vault")


def _load_config():
    path = app_config_file()
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_config(cfg):
    os.makedirs(app_config_dir(), exist_ok=True)
    with open(app_config_file(), "w") as f:
        json.dump(cfg, f, indent=4)


# ---------------------------------------------------------------------------


def get_data_dir():
    """Returns the folder commands.json lives in, creating the organized
    default on first run (and migrating a legacy commands.json that used
    to sit next to the script, if one is found)."""
    cfg = _load_config()
    data_dir = cfg.get("data_dir")

    if not data_dir:
        data_dir = default_data_dir()
        os.makedirs(data_dir, exist_ok=True)

        legacy = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "commands.json")
        target = os.path.join(data_dir, "commands.json")
        if os.path.exists(legacy) and not os.path.exists(target):
            try:
                shutil.copy(legacy, target)
            except OSError:
                pass

        cfg["data_dir"] = data_dir
        _save_config(cfg)
    else:
        os.makedirs(data_dir, exist_ok=True)

    return data_dir


def get_data_file():
    return os.path.join(get_data_dir(), "commands.json")


def set_data_dir(new_dir, move_existing=True):
    """Switch Command Vault's data folder, optionally moving the existing
    commands.json into the new location."""
    old_file = get_data_file()
    os.makedirs(new_dir, exist_ok=True)
    new_file = os.path.join(new_dir, "commands.json")

    if move_existing and os.path.exists(old_file) and not os.path.exists(new_file):
        shutil.move(old_file, new_file)

    cfg = _load_config()
    cfg["data_dir"] = new_dir
    _save_config(cfg)


# ---------------------------------------------------------------------------


# Data layer
# ---------------------------------------------------------------------------
def _normalize_vault_data(raw):
    """Shared normalization for a parsed commands.json payload: migrates the
    old flat-list format and fills in defaults for any fields added since
    an entry was first saved. Used by both load_data() and vault Import."""
    # Old format: a plain list of {"name": ..., "command": ...}
    if isinstance(raw, list):
        commands = []
        categories = set()
        for entry in raw:
            name = entry.get("name", "").strip()
            command = entry.get("command", "").strip()
            if not name and not command:
                continue  # drop empty legacy placeholder rows
            categories.add(UNCATEGORIZED)
            commands.append(_blank_entry(name, command))
        return {"categories": sorted(categories), "commands": commands, "settings": {}}

    raw.setdefault("categories", [])
    raw.setdefault("commands", [])
    raw.setdefault("settings", {})
    for cmd in raw["commands"]:
        cmd.setdefault("working_dir", "")
        cmd.setdefault("run_mode", "terminal")
        cmd.setdefault("entry_type", "command")
        cmd.setdefault("category", UNCATEGORIZED)
        cmd.setdefault("icon", DEFAULT_ICON)
        cmd.setdefault("autostart", False)
        cmd.setdefault("hotkey_display", "")
        cmd.setdefault("hotkey_pynput", "")
        cmd.setdefault("schedule_enabled", False)
        cmd.setdefault("schedule_days", [])  # empty list means "every day"
        cmd.setdefault("schedule_time", "")  # "HH:MM", 24h
        cmd.setdefault("browser_profile", False)
        cmd.setdefault("browser_profile_dir", "")  # "" = default per-entry folder
    return raw


def load_data():
    """Load commands.json, migrating the old flat-list format if needed."""
    data_file = get_data_file()
    if not os.path.exists(data_file):
        return {"categories": [], "commands": [], "settings": {}}

    try:
        with open(data_file, "r") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        # A partial write from a crash, a bad manual edit, or a disk issue
        # can leave commands.json unparsable. Quarantine the bad file, then
        # try the .bak that save_data() keeps (the vault as of the previous
        # save) before giving up and starting empty -- recovering silently
        # from a good recent copy beats losing everything over one bad write.
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        quarantined = f"{data_file}.corrupted-{timestamp}"
        try:
            shutil.move(data_file, quarantined)
        except OSError:
            quarantined = None

        backup_file = data_file + ".bak"
        recovered = None
        if os.path.exists(backup_file):
            try:
                with open(backup_file, "r") as f:
                    recovered = json.load(f)
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                recovered = None

        try:
            if recovered is not None:
                messagebox.showwarning(
                    "Command Vault",
                    "Your commands.json file appears to be corrupted and "
                    f"couldn't be read ({e}).\n\n"
                    + (f"The bad file has been saved as:\n{quarantined}\n\n"
                       if quarantined else "")
                    + "Recovered your vault from the most recent backup instead."
                )
            else:
                messagebox.showwarning(
                    "Command Vault",
                    "Your commands.json file appears to be corrupted and "
                    f"couldn't be read ({e}).\n\n"
                    + (f"The bad file has been saved as:\n{quarantined}\n\n"
                       if quarantined else "")
                    + "No usable backup was found either. Starting with an empty vault."
                )
        except tk.TclError:
            pass  # no Tk root yet (e.g. called before mainloop is set up)

        if recovered is not None:
            return _normalize_vault_data(recovered)
        return {"categories": [], "commands": [], "settings": {}}

    return _normalize_vault_data(raw)


def _blank_entry(name="", command=""):
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "command": command,
        "working_dir": "",
        "run_mode": "terminal",
        "entry_type": "command",
        "category": UNCATEGORIZED,
        "icon": DEFAULT_ICON,
        "autostart": False,
        "hotkey_display": "",
        "hotkey_pynput": "",
        "schedule_enabled": False,
        "schedule_days": [],
        "schedule_time": "",
        "browser_profile": False,
        "browser_profile_dir": "",
    }


def save_data(data):
    """Writes commands.json atomically: serialize to a temp file in the same
    directory, fsync it, then os.replace() it into place. os.replace() is
    atomic on both POSIX and Windows, so a crash or power loss can only ever
    leave the OLD file intact or the NEW file fully written -- never a
    half-written commands.json. Before that swap, the previous good file
    (if any) is copied to commands.json.bak, as a second line of defense
    independent of Export/Import.

    Keep this atomic. Do not go back to a plain open(..., "w") here -- that
    reintroduces the exact corruption case _normalize_vault_data's caller
    (load_data) has to quarantine and recover from."""
    data_file = get_data_file()

    if os.path.exists(data_file):
        try:
            shutil.copy2(data_file, data_file + ".bak")
        except OSError:
            pass  # best-effort; don't block saving over a backup failure

    data_dir = os.path.dirname(data_file) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".commands-", suffix=".json.tmp", dir=data_dir)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, data_file)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
