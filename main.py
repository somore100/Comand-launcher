import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import os
import sys
import glob
import re
import platform
import subprocess
import uuid
import shutil
import threading
import queue
import shlex
import socket
import base64
import io
import time
import urllib.request
import urllib.error
from datetime import datetime

try:
    from pynput import keyboard as pynput_keyboard
    HAVE_PYNPUT = True
except Exception:
    HAVE_PYNPUT = False

try:
    from PIL import Image as PILImage, ImageDraw as PILImageDraw
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False

try:
    import pystray
    HAVE_PYSTRAY = HAVE_PIL
except Exception:
    HAVE_PYSTRAY = False

APP_NAME = "Command Vault"
APP_VERSION = "1.5.0"
GITHUB_REPO = "somore100/Comand-launcher"  # typo in repo name is intentional, cosmetic only


# ---------------------------------------------------------------------------
# Theme (Catppuccin Mocha inspired)
# ---------------------------------------------------------------------------
COLOR_BG = "#1e1e2e"
COLOR_SIDEBAR = "#181825"
COLOR_PANEL = "#242438"
COLOR_TEXT = "#cdd6f4"
COLOR_SUBTEXT = "#a6adc8"
COLOR_ACCENT = "#89b4fa"
COLOR_ACCENT_DIM = "#5876a8"
COLOR_GREEN = "#a6e3a1"
COLOR_RED = "#f38ba8"
COLOR_YELLOW = "#f9e2af"
COLOR_ROW_ALT = "#28283f"
COLOR_SELECT = "#33344d"
FONT_TITLE = ("Segoe UI", 18, "bold")
FONT_HEADING = ("Segoe UI", 11, "bold")
FONT_NORMAL = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)
FONT_MONO = ("Consolas", 10) if platform.system() == "Windows" else ("DejaVu Sans Mono", 10)

DEFAULT_ICON = "\U0001F4E6"  # package
ALL_CATEGORY = "All"
UNCATEGORIZED = "Uncategorized"

EMOJI_CHOICES = [
    "\U0001F680", "\u2699\uFE0F", "\U0001F527", "\U0001F6E0\uFE0F", "\U0001F4BB", "\U0001F5A5\uFE0F",
    "\U0001F4E6", "\U0001F40D", "\U0001F916", "\U0001F3A8", "\U0001F4CA", "\U0001F525",
    "\u2B50", "\u2705", "\u274C", "\U0001F310", "\U0001F4C1", "\U0001F5C2\uFE0F",
    "\U0001F579\uFE0F", "\U0001F3AE", "\U0001F3B5", "\U0001F3AC", "\U0001F4F7", "\u26A1",
    "\U0001F9E9", "\U0001F512", "\U0001F511", "\U0001F4DD", "\u270F\uFE0F", "\U0001F4CC",
    "\U0001F9E0", "\U0001F433", "\u2601\uFE0F", "\U0001F5C4\uFE0F", "\U0001F4E1", "\U0001F9EA",
    "\U0001F578\uFE0F", "\U0001F50C", "\U0001F5B1\uFE0F", "\u2328\uFE0F", "\U0001F4DC", "\U0001F50D",
    "\U0001F9F0", "\U0001F3AF", "\u23F0", "\U0001F514",
]


# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------
def is_windows():
    return platform.system() == "Windows"


def is_linux():
    return platform.system() == "Linux"


def is_mac():
    return platform.system() == "Darwin"


# ---------------------------------------------------------------------------
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
# Auto-update check
# ---------------------------------------------------------------------------
UPDATE_CHECK_COOLDOWN_SECONDS = 20 * 60 * 60  # don't hit the API more than ~once/day
UPDATE_CHECK_TIMEOUT_SECONDS = 5


def _parse_version(v):
    """'v1.5.0' or '1.5.0-beta' -> (1, 5, 0). Non-numeric trailing parts
    (pre-release suffixes) are dropped rather than raising, so an odd tag
    name degrades to "can't tell, treat as not newer" instead of crashing
    the check."""
    v = v.strip().lstrip("vV")
    parts = []
    for chunk in v.split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _version_is_newer(candidate, current):
    return _parse_version(candidate) > _parse_version(current)


def fetch_latest_release():
    """Hits the GitHub Releases API for the latest release. Returns
    (tag_name, html_url) or None on any failure (no network, rate limit,
    repo has no releases yet, etc.) -- this is a best-effort background
    check and must never raise into the caller."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    req = urllib.request.Request(url, headers={
        "User-Agent": f"{APP_NAME.replace(' ', '-')}/{APP_VERSION}",
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=UPDATE_CHECK_TIMEOUT_SECONDS) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        tag = payload.get("tag_name", "")
        html_url = payload.get("html_url", f"https://github.com/{GITHUB_REPO}/releases")
        if not tag:
            return None
        return tag, html_url
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            json.JSONDecodeError, OSError, ValueError):
        return None


def check_for_update(force=False, on_result=None):
    """Runs the update check in a background daemon thread and calls
    on_result(tag, html_url) on the SAME (background) thread if an update
    is found -- callers that touch Tk must hop back to the main thread
    themselves (see CommandVault._check_for_update_startup for the
    pattern). Respects the cooldown and the "check automatically" setting
    unless force=True (manual "Check for Updates" button)."""
    cfg = _load_config()
    if not force:
        if not cfg.get("auto_update_check", True):
            return
        last_check = cfg.get("last_update_check", 0)
        if time.time() - last_check < UPDATE_CHECK_COOLDOWN_SECONDS:
            return

    def _run():
        result = fetch_latest_release()
        cfg2 = _load_config()
        cfg2["last_update_check"] = time.time()
        _save_config(cfg2)
        if result is None:
            return
        tag, html_url = result
        if _version_is_newer(tag, APP_VERSION) and on_result:
            on_result(tag, html_url)

    threading.Thread(target=_run, daemon=True).start()


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
# Autostart handling
# ---------------------------------------------------------------------------
def linux_autostart_dir():
    d = os.path.expanduser("~/.config/autostart")
    os.makedirs(d, exist_ok=True)
    return d


def windows_startup_dir():
    appdata = os.getenv("APPDATA", "")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def app_relaunch_command():
    """Command used to relaunch Command Vault itself. Has to handle three
    very different cases correctly, or autostart silently does nothing:

    1. Running inside an AppImage: sys.executable points at a path inside
       a temporary mount (/tmp/.mount_XXXXXX/...) that AppImage creates
       fresh on every launch and deletes on exit -- that path is gone by
       the next boot. AppImage's runtime sets $APPIMAGE to the *actual*,
       stable path of the .AppImage file itself, so we use that instead.
    2. Running as any other frozen PyInstaller binary (Windows .exe, a
       plain Linux binary, a macOS .app) -- sys.executable IS the program,
       so it should be run directly, not wrapped as a script argument.
    3. Running from source via `python main.py` -- the original behavior.
    """
    appimage_path = os.environ.get("APPIMAGE")
    if appimage_path:
        return f'"{appimage_path}"'

    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'

    script = os.path.abspath(sys.argv[0])
    py = sys.executable
    if is_windows():
        pyw = py.replace("python.exe", "pythonw.exe")
        if os.path.exists(pyw):
            py = pyw
    return f'"{py}" "{script}"'


def app_autostart_path():
    if is_linux():
        return os.path.join(linux_autostart_dir(), "command-vault.desktop")
    if is_windows():
        return os.path.join(windows_startup_dir(), "CommandVault.bat")
    return None


def app_autostart_enabled():
    path = app_autostart_path()
    return bool(path and os.path.exists(path))


def app_autostart_script_path():
    return os.path.join(linux_autostart_scripts_dir(), "command-vault-autostart.sh")


def set_app_autostart(enabled):
    path = app_autostart_path()
    if not path:
        raise NotImplementedError("Autostart isn't supported on this OS yet.")
    if not enabled:
        if os.path.exists(path):
            os.remove(path)
        if is_linux():
            script_path = app_autostart_script_path()
            if os.path.exists(script_path):
                os.remove(script_path)
        return
    if is_linux():
        # Route through a real wrapper script instead of inlining into
        # Exec=, for two reasons:
        #  1. It sidesteps any quoting quirks in whichever Exec= parser the
        #     user's session (GNOME/KDE/XFCE/etc.) happens to use.
        #  2. When running as an AppImage, launching the AppImage directly
        #     from Exec= relies on FUSE-mounting it, which races against the
        #     desktop session's own startup (DBus / XDG_RUNTIME_DIR aren't
        #     always up yet at the point autostart entries fire). This is a
        #     well-documented class of "works fine double-clicked, silently
        #     does nothing on autostart" AppImage bug. --appimage-extract-
        #     and-run sidesteps FUSE for this one launch (slower, but it
        #     actually starts), and a short `sleep` up front is a portable
        #     stand-in for X-GNOME-Autostart-Delay on non-GNOME sessions.
        appimage_path = os.environ.get("APPIMAGE")
        script_path = app_autostart_script_path()
        lines = ["#!/bin/bash", "sleep 3"]
        if appimage_path:
            lines.append(f'chmod +x "{appimage_path}" 2>/dev/null || true')
            lines.append(f'"{appimage_path}" --appimage-extract-and-run')
        else:
            lines.append(app_relaunch_command())
        with open(script_path, "w") as f:
            f.write("\n".join(lines) + "\n")
        os.chmod(script_path, 0o755)

        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Command Vault\n"
            f'Exec=bash "{script_path}"\n'
            "X-GNOME-Autostart-enabled=true\n"
            "X-GNOME-Autostart-Delay=5\n"
        )
        with open(path, "w") as f:
            f.write(content)
    elif is_windows():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(f'@echo off\nstart "" {app_relaunch_command()}\n')


def linux_autostart_scripts_dir():
    d = os.path.expanduser("~/.config/autostart-scripts")
    os.makedirs(d, exist_ok=True)
    return d


def entry_autostart_path(entry_id):
    if is_linux():
        return os.path.join(linux_autostart_dir(), f"cv-{entry_id}.desktop")
    if is_windows():
        return os.path.join(windows_startup_dir(), f"cv-{entry_id}.bat")
    return None


def entry_autostart_enabled(entry_id):
    path = entry_autostart_path(entry_id)
    return bool(path and os.path.exists(path))


def set_entry_autostart(entry, enabled):
    path = entry_autostart_path(entry["id"])
    if not path:
        if enabled:
            raise NotImplementedError("Autostart isn't supported on this OS yet.")
        return

    if not enabled:
        if os.path.exists(path):
            os.remove(path)
        script_path = os.path.join(linux_autostart_scripts_dir(), f"cv-{entry['id']}.sh")
        if os.path.exists(script_path):
            os.remove(script_path)
        return

    command = entry["command"]
    working_dir = entry.get("working_dir") or ""
    is_appimage_entry = entry.get("entry_type") == "appimage"
    if is_appimage_entry and is_linux():
        # See the matching comment in set_app_autostart(): launching an
        # AppImage straight from Exec= races against the desktop session's
        # own startup and can silently fail to mount via FUSE. Extract-and-
        # run avoids that; chmod +x guards against a lost executable bit
        # (e.g. after re-downloading or moving the file).
        exec_cmd = f'chmod +x "{command}" 2>/dev/null || true\n"{command}" --appimage-extract-and-run'
    elif is_appimage_entry:
        exec_cmd = f'"{command}"'
    else:
        exec_cmd = resolve_exec_command(command)

    if is_linux():
        # Write a real wrapper script instead of inlining into Exec=, since
        # squashing multiline commands onto one line breaks as soon as a
        # line has a "#" comment (bash treats the rest of that line as a
        # comment, silently dropping every command after it).
        script_path = os.path.join(linux_autostart_scripts_dir(), f"cv-{entry['id']}.sh")
        lines = ["#!/bin/bash", "sleep 3"]
        if working_dir:
            lines.append(f'cd "{working_dir}" || exit 1')
        lines.append(exec_cmd)
        with open(script_path, "w") as f:
            f.write("\n".join(lines) + "\n")
        os.chmod(script_path, 0o755)

        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={entry['name']}\n"
            f'Exec=bash "{script_path}"\n'
            "X-GNOME-Autostart-enabled=true\n"
        )
        with open(path, "w") as f:
            f.write(content)
    elif is_windows():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        cd_part = f'cd /d "{working_dir}"\n' if working_dir else ""
        with open(path, "w") as f:
            f.write(f"@echo off\n{cd_part}{exec_cmd}\n")


# ---------------------------------------------------------------------------
# Installed-app discovery (for "Pick Installed App")
# ---------------------------------------------------------------------------
def find_linux_apps():
    dirs = ["/usr/share/applications", os.path.expanduser("~/.local/share/applications")]
    apps = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for fname in glob.glob(os.path.join(d, "*.desktop")):
            name, exec_line, no_display = None, None, False
            try:
                with open(fname, "r", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("Name=") and name is None:
                            name = line[len("Name="):]
                        elif line.startswith("Exec=") and exec_line is None:
                            exec_line = line[len("Exec="):]
                        elif line.startswith("NoDisplay=true"):
                            no_display = True
            except OSError:
                continue
            if name and exec_line and not no_display:
                clean = re.sub(r"%[a-zA-Z]", "", exec_line).strip()
                apps.append((name, clean, fname))
    apps.sort(key=lambda a: a[0].lower())
    return apps


def find_windows_apps():
    apps = []
    dirs = []
    appdata = os.getenv("APPDATA")
    programdata = os.getenv("PROGRAMDATA")
    if appdata:
        dirs.append(os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs"))
    if programdata:
        dirs.append(os.path.join(programdata, "Microsoft", "Windows", "Start Menu", "Programs"))
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for fname in files:
                if fname.lower().endswith(".lnk"):
                    full = os.path.join(root, fname)
                    name = os.path.splitext(fname)[0]
                    apps.append((name, f'start "" "{full}"', full))
    apps.sort(key=lambda a: a[0].lower())
    return apps


def find_installed_apps():
    if is_linux():
        return find_linux_apps()
    if is_windows():
        return find_windows_apps()
    return []


# ---------------------------------------------------------------------------
# Single-instance lock
# ---------------------------------------------------------------------------
# Autostart + a global hotkey can each independently launch/wake an
# instance, so nothing previously stopped two copies running at once --
# both trying to register the same OS-level hotkeys, or both writing
# commands.json at overlapping moments, is a real failure mode. A bound
# TCP socket on a fixed localhost port doubles as a mutex (only one
# process can hold the bind) and as a tiny IPC channel (a second launch
# attempt connects, asks the first instance to raise its window, then
# exits). 127.0.0.1-only binding avoids any firewall prompt on Windows.
SINGLE_INSTANCE_PORT = 47812


def notify_running_instance():
    """If another instance already holds the lock, ask it to show its
    window and return True (caller should exit immediately after)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect(("127.0.0.1", SINGLE_INSTANCE_PORT))
        s.sendall(b"SHOW\n")
        s.close()
        return True
    except OSError:
        return False


def acquire_single_instance_lock(on_show):
    """Binds the mutex port and starts a background thread that calls
    on_show() whenever a later launch attempt connects. Returns the
    listening socket -- keep a reference for the app's lifetime and close
    it on quit. Returns None if the port couldn't be bound for some other
    reason (e.g. something else on the machine is using it); in that case
    we simply proceed without the lock rather than blocking startup."""
    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        srv.bind(("127.0.0.1", SINGLE_INSTANCE_PORT))
        srv.listen(5)
    except OSError:
        return None

    def _serve():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return  # socket was closed (app shutting down)
            try:
                conn.recv(16)
            except OSError:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
            on_show()

    threading.Thread(target=_serve, daemon=True).start()
    return srv


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
        # can leave commands.json unparsable. Rather than crashing on every
        # startup from then on, quarantine the bad file and start fresh --
        # the vault is recoverable (existing hotkeys/autostart entries just
        # need re-adding) but a permanently unlaunchable app is not.
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        quarantined = f"{data_file}.corrupted-{timestamp}"
        try:
            shutil.move(data_file, quarantined)
        except OSError:
            quarantined = None
        try:
            messagebox.showwarning(
                "Command Vault",
                "Your commands.json file appears to be corrupted and "
                f"couldn't be read ({e}).\n\n"
                + (f"The bad file has been saved as:\n{quarantined}\n\n"
                   if quarantined else "")
                + "Starting with an empty vault."
            )
        except tk.TclError:
            pass  # no Tk root yet (e.g. called before mainloop is set up)
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
    }


def save_data(data):
    with open(get_data_file(), "w") as f:
        json.dump(data, f, indent=4)


# ---------------------------------------------------------------------------
# Script/command resolution
# ---------------------------------------------------------------------------
SCRIPT_EXTENSIONS = (".sh", ".bash", ".bat", ".cmd", ".ps1", ".py")


def resolve_exec_command(command):
    """If `command` is (just) a path to a known script type, wrap it with the
    right interpreter so it runs correctly regardless of executable bit or
    shebang. Otherwise, return the command untouched (raw typed command or
    multiline script text)."""
    stripped = command.strip()
    if "\n" in stripped or not os.path.isfile(stripped):
        return command

    ext = os.path.splitext(stripped)[1].lower()

    if ext in (".sh", ".bash"):
        return f'bash "{stripped}"'
    if ext in (".bat", ".cmd"):
        # cmd.exe runs .bat/.cmd natively; on Linux this just won't find an
        # interpreter, which is expected since batch files are Windows-only
        return f'"{stripped}"'
    if ext == ".ps1":
        return f'powershell -ExecutionPolicy Bypass -File "{stripped}"'
    if ext == ".py":
        py = "python" if is_windows() else "python3"
        return f'{py} "{stripped}"'

    # Unknown extension but a real file: try to make it executable and run directly
    try:
        os.chmod(stripped, 0o755)
    except OSError:
        pass
    return f'"{stripped}"'



# ---------------------------------------------------------------------------
# Templated commands: {{name}} or {{name:default}} prompts for a value each run
# ---------------------------------------------------------------------------
PLACEHOLDER_RE = re.compile(r"\{\{(\w+)(?::([^}]*))?\}\}")


def extract_placeholders(command):
    """Returns an ordered list of (name, default) for each unique {{name}}
    or {{name:default}} found in the command."""
    seen = {}
    order = []
    for m in PLACEHOLDER_RE.finditer(command):
        name, default = m.group(1), m.group(2) or ""
        if name not in seen:
            seen[name] = default
            order.append(name)
    return [(name, seen[name]) for name in order]


def fill_placeholders(command, values):
    def repl(m):
        name = m.group(1)
        return values.get(name, m.group(0))
    return PLACEHOLDER_RE.sub(repl, command)


class PlaceholderDialog(tk.Toplevel):
    """Prompts for {{name}} values before running a templated command."""
    def __init__(self, entry_name, placeholders):
        super().__init__()
        self.result = None
        self.title(f"Run: {entry_name}")
        self.configure(bg=COLOR_BG)
        self.resizable(False, False)
        self.grab_set()

        tk.Label(self, text=f'Fill in values to run "{entry_name}"', bg=COLOR_BG, fg=COLOR_TEXT,
                 font=FONT_HEADING, wraplength=340, justify="left").pack(anchor="w", padx=16, pady=(16, 10))

        self.vars = {}
        first_entry = None
        for name, default in placeholders:
            tk.Label(self, text=name, bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, anchor="w"
                      ).pack(fill="x", padx=16)
            var = tk.StringVar(value=default)
            entry = tk.Entry(self, textvariable=var, width=42, font=FONT_NORMAL, bg=COLOR_PANEL,
                              fg=COLOR_TEXT, insertbackground=COLOR_TEXT, relief="flat")
            entry.pack(fill="x", padx=16, pady=(2, 8))
            entry.bind("<Return>", lambda e: self._confirm())
            self.vars[name] = var
            if first_entry is None:
                first_entry = entry

        btn_frame = tk.Frame(self, bg=COLOR_BG)
        btn_frame.pack(fill="x", padx=16, pady=(4, 16))
        tk.Button(btn_frame, text="Cancel", command=self._cancel, bg=COLOR_PANEL, fg=COLOR_TEXT,
                  relief="flat", padx=14, pady=4).pack(side="right")
        tk.Button(btn_frame, text="Run", command=self._confirm, bg=COLOR_GREEN, fg=COLOR_SIDEBAR,
                  relief="flat", padx=14, pady=4, font=("Segoe UI", 10, "bold")).pack(side="right", padx=(0, 8))

        if first_entry:
            first_entry.focus_set()
            first_entry.select_range(0, tk.END)

    def _confirm(self):
        self.result = {name: var.get() for name, var in self.vars.items()}
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


# ---------------------------------------------------------------------------
# Terminal selection: auto-detect, or a user-chosen/custom preference
# ---------------------------------------------------------------------------
NAMED_LINUX_TERMINALS = {
    "GNOME Terminal": lambda cmd: ["gnome-terminal", "--", "bash", "-c", cmd + "; exec bash"],
    "Konsole": lambda cmd: ["konsole", "-e", "bash", "-c", cmd + "; exec bash"],
    "Xfce Terminal": lambda cmd: ["xfce4-terminal", "-e", "bash", "-c", cmd + "; exec bash"],
    "COSMIC Terminal": lambda cmd: ["cosmic-term", "-e", "bash", "-c", cmd + "; exec bash"],
    "xterm": lambda cmd: ["xterm", "-e", "bash", "-c", cmd + "; exec bash"],
    "Alacritty": lambda cmd: ["alacritty", "-e", "bash", "-c", cmd + "; exec bash"],
    "kitty": lambda cmd: ["kitty", "bash", "-c", cmd + "; exec bash"],
    "Terminator": lambda cmd: ["terminator", "-x", "bash", "-c", cmd + "; exec bash"],
}

TERMINAL_BUILDERS = [
    lambda cmd: ["cosmic-term", "-e", "bash", "-c", cmd + "; exec bash"],
    lambda cmd: ["gnome-terminal", "--", "bash", "-c", cmd + "; exec bash"],
    lambda cmd: ["konsole", "-e", "bash", "-c", cmd + "; exec bash"],
    lambda cmd: ["xfce4-terminal", "-e", "bash", "-c", cmd + "; exec bash"],
    lambda cmd: ["wt", "cmd", "/k", cmd],
    lambda cmd: ["cmd", "/k", cmd],
]


def custom_terminal_builder(template):
    def build(cmd):
        filled = template.replace("%CMD%", cmd)
        return shlex.split(filled)
    return build


def get_terminal_builders():
    """Preferred terminal first (if configured), falling back to the full
    auto-detect list either way, for robustness."""
    cfg = _load_config()
    pref = cfg.get("preferred_terminal", "auto")
    builders = []
    if pref == "custom":
        template = cfg.get("custom_terminal_template", "").strip()
        if template:
            builders.append(custom_terminal_builder(template))
    elif pref in NAMED_LINUX_TERMINALS:
        builders.append(NAMED_LINUX_TERMINALS[pref])
    builders.extend(TERMINAL_BUILDERS)
    return builders


APPIMAGE_RUNTIME_ENV_VARS = ("APPIMAGE", "APPDIR", "ARGV0", "OWD")


def child_process_env():
    """Environment to launch a user's entry with. When Command Vault itself
    is running as an AppImage, the AppImage runtime sets APPIMAGE/APPDIR/
    ARGV0/OWD on our own process, and subprocess.Popen inherits the full
    parent environment by default -- so every script or app we launch would
    otherwise also see (for example) APPIMAGE=/path/to/CommandVault.AppImage,
    regardless of whether it has anything to do with AppImages. A launched
    entry that happens to also check that variable then behaves as if it
    were itself running from inside CommandVault's AppImage -- wrong, and
    genuinely confusing to debug since it only reproduces when launched via
    Command Vault's own AppImage build, not when run standalone. Strip
    Command Vault's own AppImage-runtime variables before handing the
    environment to a child."""
    env = os.environ.copy()
    for var in APPIMAGE_RUNTIME_ENV_VARS:
        env.pop(var, None)
    return env


def run_entry(entry, log=None):
    """Runs an entry. `log`, if given, is called with short status strings
    for the console panel -- e.g. the resolved command, working dir, and
    (for silent mode) live output as it's produced."""
    def emit(msg):
        if log:
            log(msg)

    command = entry["command"]
    working_dir = entry.get("working_dir") or None
    run_mode = entry.get("run_mode", "terminal")
    entry_type = entry.get("entry_type", "command")
    entry_name = entry.get("name", "entry")

    if working_dir and not os.path.isdir(working_dir):
        messagebox.showerror("Working directory not found", working_dir)
        return

    if entry_type != "appimage":
        placeholders = extract_placeholders(command)
        if placeholders:
            dialog = PlaceholderDialog(entry_name, placeholders)
            dialog.wait_window()
            if dialog.result is None:
                emit(f'Cancelled "{entry_name}" (values not filled in)')
                return
            command = fill_placeholders(command, dialog.result)

    if entry_type == "appimage":
        if not os.path.isfile(command):
            messagebox.showerror("AppImage not found", command)
            return
        try:
            os.chmod(command, 0o755)
        except OSError as e:
            messagebox.showwarning("Couldn't set executable bit", str(e))
        exec_cmd = f'"{command}"'
    else:
        exec_cmd = resolve_exec_command(command)

    emit(f'\u25B6 Running "{entry_name}" \u2014 {run_mode} mode' + (f' \u00b7 cwd: {working_dir}' if working_dir else ''))
    emit(f'  $ {exec_cmd}')

    if run_mode == "silent":
        try:
            proc = subprocess.Popen(
                exec_cmd,
                shell=True,
                cwd=working_dir,
                env=child_process_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                text=True,
                bufsize=1,
            )
        except Exception as e:
            emit(f'  \u2717 Failed to launch "{entry_name}": {e}')
            messagebox.showerror("Failed to launch", str(e))
            return

        if log:
            def reader():
                try:
                    for line in proc.stdout:
                        log(f'  [{entry_name}] {line.rstrip()}')
                except Exception:
                    pass
            threading.Thread(target=reader, daemon=True).start()
        return

    for builder in get_terminal_builders():
        try:
            subprocess.Popen(builder(exec_cmd), cwd=working_dir, env=child_process_env())
            emit(f'  \u2192 Opened in terminal')
            return
        except FileNotFoundError:
            continue

    emit(f'  \u2717 No terminal found for "{entry_name}"')
    messagebox.showerror("No terminal found", "No supported terminal emulator was found on this system.")


# ---------------------------------------------------------------------------
# Emoji picker popup
# ---------------------------------------------------------------------------
class EmojiPicker(tk.Toplevel):
    def __init__(self, master, on_pick):
        super().__init__(master)
        self.title("Choose an icon")
        self.configure(bg=COLOR_BG)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        cols = 8
        frame = tk.Frame(self, bg=COLOR_BG)
        frame.pack(padx=10, pady=10)
        for i, emoji in enumerate(EMOJI_CHOICES):
            r, c = divmod(i, cols)
            btn = tk.Button(frame, text=emoji, font=("Segoe UI", 16), width=2,
                             bg=COLOR_PANEL, fg=COLOR_TEXT, relief="flat",
                             command=lambda e=emoji: self._pick(e, on_pick))
            btn.grid(row=r, column=c, padx=2, pady=2)

        if is_windows():
            hint = "Tip: Win + . also opens Windows' built-in emoji panel here."
        else:
            hint = "Pick a symbol below to use as this entry's icon."
        tk.Label(self, text=hint, bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL,
                 wraplength=280, justify="left").pack(padx=10, pady=(0, 10), anchor="w")

    def _pick(self, emoji, callback):
        callback(emoji)
        self.destroy()


# ---------------------------------------------------------------------------
# Installed-app picker popup
# ---------------------------------------------------------------------------
class AppPicker(tk.Toplevel):
    def __init__(self, master, on_pick):
        super().__init__(master)
        self.title("Pick Installed App")
        self.configure(bg=COLOR_BG)
        self.geometry("420x420")
        self.transient(master)
        self.grab_set()

        self.on_pick = on_pick
        self.all_apps = find_installed_apps()

        tk.Label(self, text="Pick Installed App", bg=COLOR_BG, fg=COLOR_TEXT, font=FONT_HEADING
                 ).pack(anchor="w", padx=14, pady=(14, 4))

        if not self.all_apps:
            msg = ("No installed apps were found to scan on this system."
                   if (is_linux() or is_windows())
                   else "App scanning isn't supported on this OS yet.")
            tk.Label(self, text=msg, bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL,
                     wraplength=380, justify="left").pack(padx=14, pady=10, anchor="w")
            tk.Button(self, text="Close", command=self.destroy, bg=COLOR_PANEL, fg=COLOR_TEXT,
                      relief="flat", padx=12, pady=4).pack(pady=10)
            return

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh())
        search_entry = tk.Entry(self, textvariable=self.search_var, font=FONT_NORMAL, bg=COLOR_PANEL,
                                 fg=COLOR_TEXT, insertbackground=COLOR_TEXT, relief="flat")
        search_entry.pack(fill="x", padx=14, pady=(0, 8), ipady=5)
        search_entry.focus_set()

        list_frame = tk.Frame(self, bg=COLOR_BG)
        list_frame.pack(fill="both", expand=True, padx=14)
        self.listbox = tk.Listbox(list_frame, bg=COLOR_PANEL, fg=COLOR_TEXT, relief="flat",
                                   selectbackground=COLOR_SELECT, font=FONT_NORMAL, activestyle="none")
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.listbox.bind("<Double-1>", lambda e: self._confirm())

        btn_frame = tk.Frame(self, bg=COLOR_BG)
        btn_frame.pack(fill="x", padx=14, pady=10)
        tk.Button(btn_frame, text="Cancel", command=self.destroy, bg=COLOR_PANEL, fg=COLOR_TEXT,
                  relief="flat", padx=12, pady=4).pack(side="right")
        tk.Button(btn_frame, text="Use Selected", command=self._confirm, bg=COLOR_ACCENT, fg=COLOR_SIDEBAR,
                  relief="flat", padx=12, pady=4, font=("Segoe UI", 10, "bold")).pack(side="right", padx=(0, 8))

        self._filtered = []
        self._refresh()

    def _refresh(self):
        query = self.search_var.get().strip().lower()
        self.listbox.delete(0, tk.END)
        self._filtered = [a for a in self.all_apps if query in a[0].lower()] if query else self.all_apps
        for name, _, _ in self._filtered:
            self.listbox.insert(tk.END, name)

    def _confirm(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        name, command, _ = self._filtered[sel[0]]
        self.on_pick(name, command)
        self.destroy()


class InsertPlaceholderDialog(tk.Toplevel):
    """Small dialog for naming an input box before inserting {{name}} (or
    {{name:default}}) at the cursor in the command box."""
    def __init__(self, master, suggested_name):
        super().__init__(master)
        self.result = None
        self.title("Add Input Box")
        self.configure(bg=COLOR_BG)
        self.resizable(False, False)
        self.grab_set()

        tk.Label(self, text="Name", bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, anchor="w"
                  ).pack(fill="x", padx=16, pady=(16, 0))
        self.name_var = tk.StringVar(value=suggested_name)
        name_entry = tk.Entry(self, textvariable=self.name_var, width=32, font=FONT_NORMAL, bg=COLOR_PANEL,
                               fg=COLOR_TEXT, insertbackground=COLOR_TEXT, relief="flat")
        name_entry.pack(fill="x", padx=16, pady=(2, 8))
        name_entry.bind("<Return>", lambda e: self._confirm())

        tk.Label(self, text="Default value (optional)", bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL,
                  anchor="w").pack(fill="x", padx=16)
        self.default_var = tk.StringVar()
        default_entry = tk.Entry(self, textvariable=self.default_var, width=32, font=FONT_NORMAL,
                                  bg=COLOR_PANEL, fg=COLOR_TEXT, insertbackground=COLOR_TEXT, relief="flat")
        default_entry.pack(fill="x", padx=16, pady=(2, 12))
        default_entry.bind("<Return>", lambda e: self._confirm())

        btns = tk.Frame(self, bg=COLOR_BG)
        btns.pack(fill="x", padx=16, pady=(0, 16))
        tk.Button(btns, text="Cancel", command=self.destroy, bg=COLOR_PANEL, fg=COLOR_TEXT,
                  relief="flat", padx=12, pady=4).pack(side="right")
        tk.Button(btns, text="Insert", command=self._confirm, bg=COLOR_ACCENT, fg=COLOR_SIDEBAR,
                  relief="flat", font=("Segoe UI", 10, "bold"), padx=12, pady=4).pack(side="right", padx=(0, 8))

        name_entry.focus_set()
        name_entry.select_range(0, tk.END)

    def _confirm(self):
        name = self.name_var.get().strip()
        if not re.fullmatch(r"\w+", name or ""):
            messagebox.showwarning("Invalid name", "Use letters, numbers, and underscores only (no spaces).")
            return
        self.result = (name, self.default_var.get().strip())
        self.destroy()


# ---------------------------------------------------------------------------
# Add / Edit dialog
# ---------------------------------------------------------------------------
class EntryDialog(tk.Toplevel):
    def __init__(self, master, categories, entry=None):
        super().__init__(master)
        self.result = None
        self.categories = categories
        self.entry = entry

        self.title("Edit Entry" if entry else "Add Entry")
        self.configure(bg=COLOR_BG)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        pad = {"padx": 16, "pady": (10, 0)}

        def label(text):
            return tk.Label(self, text=text, bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, anchor="w")

        # Name + icon row
        label("Icon").grid(row=0, column=0, sticky="w", **pad)
        label("Name").grid(row=0, column=1, sticky="w", **pad)

        self.icon_var = tk.StringVar(value=entry["icon"] if entry else DEFAULT_ICON)
        self.name_var = tk.StringVar(value=entry["name"] if entry else "")

        icon_row = tk.Frame(self, bg=COLOR_BG)
        icon_row.grid(row=1, column=0, sticky="w", padx=(16, 6))
        self.icon_label = tk.Label(icon_row, textvariable=self.icon_var, font=("Segoe UI", 16),
                                    bg=COLOR_PANEL, fg=COLOR_TEXT, width=2)
        self.icon_label.pack(side="left")
        tk.Button(icon_row, text="\U0001F600", font=("Segoe UI", 10), command=self._open_emoji_picker,
                  bg=COLOR_ACCENT_DIM, fg=COLOR_TEXT, relief="flat", width=2).pack(side="left", padx=(4, 0))

        name_entry = tk.Entry(self, textvariable=self.name_var, width=32, font=FONT_NORMAL,
                               bg=COLOR_PANEL, fg=COLOR_TEXT, insertbackground=COLOR_TEXT, relief="flat")
        name_entry.grid(row=1, column=1, sticky="we", padx=(0, 16))

        # Type
        self.type_var = tk.StringVar(value=entry["entry_type"] if entry else "command")
        label("Type").grid(row=2, column=0, columnspan=2, sticky="w", **pad)

        type_frame = tk.Frame(self, bg=COLOR_BG)
        type_frame.grid(row=3, column=0, columnspan=2, sticky="w", padx=16)
        tk.Radiobutton(type_frame, text="Command / Script", variable=self.type_var, value="command",
                        bg=COLOR_BG, fg=COLOR_TEXT, selectcolor=COLOR_PANEL, activebackground=COLOR_BG,
                        activeforeground=COLOR_TEXT, font=FONT_SMALL, command=self._sync_command_widget
                        ).pack(side="left")
        tk.Radiobutton(type_frame, text="AppImage", variable=self.type_var, value="appimage",
                        bg=COLOR_BG, fg=COLOR_TEXT, selectcolor=COLOR_PANEL, activebackground=COLOR_BG,
                        activeforeground=COLOR_TEXT, font=FONT_SMALL, command=self._sync_command_widget
                        ).pack(side="left", padx=(12, 0))
        tk.Button(type_frame, text="Pick Installed App", command=self._open_app_picker,
                  bg=COLOR_ACCENT_DIM, fg=COLOR_TEXT, relief="flat", font=FONT_SMALL, padx=8
                  ).pack(side="left", padx=(16, 0))

        # Command (multiline text box)
        self.path_label_var = tk.StringVar(value="Command (supports multiple lines)")
        tk.Label(self, textvariable=self.path_label_var, bg=COLOR_BG, fg=COLOR_SUBTEXT,
                 font=FONT_SMALL, anchor="w").grid(row=4, column=0, columnspan=2, sticky="w", padx=16, pady=(10, 0))

        cmd_frame = tk.Frame(self, bg=COLOR_BG)
        cmd_frame.grid(row=5, column=0, columnspan=2, sticky="we", padx=16)
        self.command_text = tk.Text(cmd_frame, width=46, height=6, font=FONT_MONO, bg=COLOR_PANEL,
                                     fg=COLOR_TEXT, insertbackground=COLOR_TEXT, relief="flat", wrap="none",
                                     undo=True)
        self.command_text.pack(side="left", fill="both", expand=True)
        cmd_scroll = ttk.Scrollbar(cmd_frame, orient="vertical", command=self.command_text.yview)
        self.command_text.configure(yscrollcommand=cmd_scroll.set)
        cmd_scroll.pack(side="left", fill="y")
        if entry:
            self.command_text.insert("1.0", entry["command"])

        cfg = _load_config()
        self._placeholder_shortcut = cfg.get("insert_placeholder_tkbind", "<Control-i>")
        self._placeholder_shortcut_display = cfg.get("insert_placeholder_display", "Ctrl+I")
        self.command_text.bind(self._placeholder_shortcut, self._add_input_box_event)

        browse_frame = tk.Frame(self, bg=COLOR_BG)
        browse_frame.grid(row=6, column=0, columnspan=2, sticky="w", padx=16, pady=(4, 0))
        tk.Button(browse_frame, text="Browse for file...", command=self._browse_command, bg=COLOR_PANEL,
                  fg=COLOR_TEXT, relief="flat", font=FONT_SMALL, padx=8).pack(side="left")
        tk.Button(browse_frame, text="+ Add Input Box", command=self._add_input_box, bg=COLOR_PANEL,
                  fg=COLOR_TEXT, relief="flat", font=FONT_SMALL, padx=8).pack(side="left", padx=(6, 0))
        tk.Label(browse_frame, text=".sh / .bat / .ps1 / .py files auto-run with the right interpreter",
                  bg=COLOR_BG, fg=COLOR_SUBTEXT, font=("Segoe UI", 8)).pack(side="left", padx=(8, 0))

        tk.Label(self, text=f"Tip: type {{{{name}}}} or {{{{name:default}}}} yourself, click \"+ Add Input Box\", "
                             f"or press {self._placeholder_shortcut_display} in the command box \u2014 all three "
                             f"prompt for a value each time you run this (e.g. git commit -m \"{{{{message:update}}}}\")",
                  bg=COLOR_BG, fg=COLOR_SUBTEXT, font=("Segoe UI", 8), wraplength=420, justify="left"
                  ).grid(row=7, column=0, columnspan=2, sticky="w", padx=16, pady=(4, 0))

        # Working directory
        label("Working Directory (optional)").grid(row=8, column=0, columnspan=2, sticky="w", **pad)
        wd_frame = tk.Frame(self, bg=COLOR_BG)
        wd_frame.grid(row=9, column=0, columnspan=2, sticky="we", padx=16)
        self.wd_var = tk.StringVar(value=entry["working_dir"] if entry else "")
        tk.Entry(wd_frame, textvariable=self.wd_var, width=38, font=FONT_NORMAL, bg=COLOR_PANEL, fg=COLOR_TEXT,
                  insertbackground=COLOR_TEXT, relief="flat").pack(side="left", fill="x", expand=True)
        tk.Button(wd_frame, text="Browse", command=self._browse_dir, bg=COLOR_ACCENT_DIM, fg=COLOR_TEXT,
                  relief="flat", font=FONT_SMALL, padx=8).pack(side="left", padx=(6, 0))

        # Category
        label("Category").grid(row=10, column=0, columnspan=2, sticky="w", **pad)
        self.category_var = tk.StringVar(value=entry["category"] if entry else (categories[0] if categories else UNCATEGORIZED))
        cat_values = categories if categories else [UNCATEGORIZED]
        self.category_combo = ttk.Combobox(self, textvariable=self.category_var, values=cat_values, width=34,
                                            font=FONT_NORMAL)
        self.category_combo.grid(row=11, column=0, columnspan=2, sticky="we", padx=16)

        # Run mode
        label("Run Mode").grid(row=12, column=0, columnspan=2, sticky="w", **pad)
        self.mode_var = tk.StringVar(value=entry["run_mode"] if entry else "terminal")
        mode_frame = tk.Frame(self, bg=COLOR_BG)
        mode_frame.grid(row=13, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 4))
        tk.Radiobutton(mode_frame, text="Open in Terminal", variable=self.mode_var, value="terminal",
                        bg=COLOR_BG, fg=COLOR_TEXT, selectcolor=COLOR_PANEL, activebackground=COLOR_BG,
                        activeforeground=COLOR_TEXT, font=FONT_SMALL).pack(side="left")
        tk.Radiobutton(mode_frame, text="Run Silently (no window)", variable=self.mode_var, value="silent",
                        bg=COLOR_BG, fg=COLOR_TEXT, selectcolor=COLOR_PANEL, activebackground=COLOR_BG,
                        activeforeground=COLOR_TEXT, font=FONT_SMALL).pack(side="left", padx=(12, 0))

        # Autostart
        self.autostart_var = tk.BooleanVar(
            value=entry_autostart_enabled(entry["id"]) if entry else False
        )
        autostart_frame = tk.Frame(self, bg=COLOR_BG)
        autostart_frame.grid(row=14, column=0, columnspan=2, sticky="w", padx=16, pady=(4, 10))
        tk.Checkbutton(autostart_frame, text="Run this automatically when the computer starts",
                        variable=self.autostart_var, bg=COLOR_BG, fg=COLOR_TEXT, selectcolor=COLOR_PANEL,
                        activebackground=COLOR_BG, activeforeground=COLOR_TEXT, font=FONT_SMALL
                        ).pack(anchor="w")
        tk.Label(autostart_frame,
                 text="Runs on its own via the OS startup mechanism \u2014 works even if Command Vault isn't set to autostart.",
                 bg=COLOR_BG, fg=COLOR_SUBTEXT, font=("Segoe UI", 8), wraplength=380, justify="left"
                 ).pack(anchor="w")

        # Launch shortcut (optional, needs pynput)
        self.entry_hotkey_pynput = entry.get("hotkey_pynput", "") if entry else ""
        self.entry_hotkey_display_var = tk.StringVar(
            value=(entry.get("hotkey_display") or "Not set") if entry else "Not set"
        )
        if HAVE_PYNPUT:
            hotkey_frame = tk.Frame(self, bg=COLOR_BG)
            hotkey_frame.grid(row=15, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 10))
            tk.Label(hotkey_frame, text="Launch Shortcut (optional)", bg=COLOR_BG, fg=COLOR_SUBTEXT,
                     font=FONT_SMALL, anchor="w").pack(anchor="w")
            row = tk.Frame(hotkey_frame, bg=COLOR_BG)
            row.pack(anchor="w", pady=(2, 0))
            tk.Label(row, textvariable=self.entry_hotkey_display_var, bg=COLOR_PANEL, fg=COLOR_ACCENT,
                     font=("Segoe UI", 10, "bold"), padx=8, pady=3).pack(side="left")
            tk.Button(row, text="Record...", command=self._record_entry_hotkey, bg=COLOR_ACCENT_DIM,
                      fg=COLOR_TEXT, relief="flat", font=FONT_SMALL, padx=8, pady=3).pack(side="left", padx=(6, 0))
            tk.Button(row, text="Clear", command=self._clear_entry_hotkey, bg=COLOR_PANEL, fg=COLOR_RED,
                      relief="flat", font=FONT_SMALL, padx=8, pady=3).pack(side="left", padx=(6, 0))
            tk.Label(hotkey_frame, text="Runs this specific command from anywhere, even with Command Vault "
                                         "closed \u2014 needs an X11 session on Linux.",
                     bg=COLOR_BG, fg=COLOR_SUBTEXT, font=("Segoe UI", 8), wraplength=380, justify="left"
                     ).pack(anchor="w", pady=(2, 0))
            buttons_row = 16
        else:
            buttons_row = 15

        # Buttons
        btn_frame = tk.Frame(self, bg=COLOR_BG)
        btn_frame.grid(row=buttons_row, column=0, columnspan=2, sticky="we", padx=16, pady=(6, 16))
        tk.Button(btn_frame, text="Cancel", command=self._cancel, bg=COLOR_PANEL, fg=COLOR_TEXT,
                  relief="flat", font=FONT_NORMAL, padx=14, pady=4).pack(side="right")
        tk.Button(btn_frame, text="Save", command=self._save, bg=COLOR_ACCENT, fg=COLOR_SIDEBAR,
                  relief="flat", font=("Segoe UI", 10, "bold"), padx=14, pady=4).pack(side="right", padx=(0, 8))

        self._sync_command_widget()
        name_entry.focus_set()

    def _record_entry_hotkey(self):
        dialog = HotkeyRecorderDialog(self)
        self.wait_window(dialog)
        if not dialog.result:
            return
        display_string, pynput_string, _tk_bind_string = dialog.result

        conflicts = self.master._all_used_hotkeys(exclude_pynput=self.entry_hotkey_pynput or None)
        if pynput_string in conflicts:
            messagebox.showwarning("Already in use", f"{display_string} is already assigned to "
                                                        f"{conflicts[pynput_string]}. Pick a different combo.")
            return

        self.entry_hotkey_pynput = pynput_string
        self.entry_hotkey_display_var.set(display_string)

    def _clear_entry_hotkey(self):
        self.entry_hotkey_pynput = ""
        self.entry_hotkey_display_var.set("Not set")

    def _sync_command_widget(self):
        if self.type_var.get() == "appimage":
            self.path_label_var.set("AppImage path")
        else:
            self.path_label_var.set("Command (supports multiple lines)")

    def _open_emoji_picker(self):
        EmojiPicker(self, self._set_icon)

    def _set_icon(self, emoji):
        self.icon_var.set(emoji)

    def _open_app_picker(self):
        AppPicker(self, self._apply_picked_app)

    def _apply_picked_app(self, name, command):
        if not self.name_var.get().strip():
            self.name_var.set(name)
        self.command_text.delete("1.0", tk.END)
        self.command_text.insert("1.0", command)
        self.type_var.set("command")
        self.mode_var.set("silent")
        self._sync_command_widget()

    def _browse_command(self):
        path = filedialog.askopenfilename(title="Select script or AppImage")
        if path:
            self.command_text.delete("1.0", tk.END)
            self.command_text.insert("1.0", path)
            if path.lower().endswith(".appimage"):
                self.type_var.set("appimage")
                self._sync_command_widget()

    def _add_input_box_event(self, event=None):
        self._add_input_box()
        return "break"

    def _add_input_box(self):
        existing_names = {n for n, _ in extract_placeholders(self.command_text.get("1.0", "end-1c"))}
        suggested = "value"
        i = 2
        while suggested in existing_names:
            suggested = f"value{i}"
            i += 1

        dialog = InsertPlaceholderDialog(self, suggested)
        self.wait_window(dialog)
        if not dialog.result:
            return
        name, default = dialog.result
        token = "{{" + name + "}}" if not default else "{{" + name + ":" + default + "}}"
        self.command_text.insert(tk.INSERT, token)
        self.command_text.focus_set()

    def _browse_dir(self):
        path = filedialog.askdirectory(title="Select working directory")
        if path:
            self.wd_var.set(path)

    def _cancel(self):
        self.result = None
        self.destroy()

    def _save(self):
        name = self.name_var.get().strip()
        command = self.command_text.get("1.0", "end-1c").strip("\n")
        if not name or not command.strip():
            messagebox.showwarning("Missing info", "Name and Command/Path are both required.")
            return
        category = self.category_var.get().strip() or UNCATEGORIZED
        icon = self.icon_var.get().strip() or DEFAULT_ICON

        self.result = {
            "id": self.entry["id"] if self.entry else str(uuid.uuid4()),
            "name": name,
            "command": command,
            "working_dir": self.wd_var.get().strip(),
            "run_mode": self.mode_var.get(),
            "entry_type": self.type_var.get(),
            "category": category,
            "icon": icon,
            "autostart": bool(self.autostart_var.get()),
            "hotkey_display": self.entry_hotkey_display_var.get() if self.entry_hotkey_pynput else "",
            "hotkey_pynput": self.entry_hotkey_pynput,
        }
        self.destroy()


# ---------------------------------------------------------------------------
# Settings dialog
# ---------------------------------------------------------------------------
class SettingsDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.master_app = master
        self.title("Settings")
        self.configure(bg=COLOR_BG)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        tk.Label(self, text="Settings", bg=COLOR_BG, fg=COLOR_TEXT, font=FONT_HEADING
                 ).pack(anchor="w", padx=16, pady=(16, 8))

        self.autostart_var = tk.BooleanVar(value=app_autostart_enabled())
        tk.Checkbutton(self, text="Launch Command Vault when the computer starts",
                        variable=self.autostart_var, bg=COLOR_BG, fg=COLOR_TEXT, selectcolor=COLOR_PANEL,
                        activebackground=COLOR_BG, activeforeground=COLOR_TEXT, font=FONT_NORMAL,
                        command=self._toggle_app_autostart).pack(anchor="w", padx=16)

        note = ("Once this is on, you can also flip \u201cRun this automatically when the computer starts\u201d "
                "on individual entries in the Edit dialog.")
        tk.Label(self, text=note, bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, wraplength=340,
                 justify="left").pack(anchor="w", padx=16, pady=(6, 16))

        tk.Frame(self, bg=COLOR_PANEL, height=1).pack(fill="x", padx=16, pady=(0, 14))

        tk.Label(self, text="Data Storage", bg=COLOR_BG, fg=COLOR_TEXT, font=FONT_HEADING
                 ).pack(anchor="w", padx=16)
        tk.Label(self, text="Your commands.json is currently stored in:", bg=COLOR_BG, fg=COLOR_SUBTEXT,
                 font=FONT_SMALL).pack(anchor="w", padx=16, pady=(6, 2))

        self.path_var = tk.StringVar(value=get_data_dir())
        path_entry = tk.Entry(self, textvariable=self.path_var, width=44, font=("Segoe UI", 9),
                               bg=COLOR_PANEL, fg=COLOR_SUBTEXT, relief="flat", state="readonly",
                               readonlybackground=COLOR_PANEL)
        path_entry.pack(fill="x", padx=16)

        tk.Button(self, text="Change Folder...", command=self._change_folder, bg=COLOR_ACCENT_DIM,
                  fg=COLOR_TEXT, relief="flat", font=FONT_SMALL, padx=10, pady=4
                  ).pack(anchor="w", padx=16, pady=(8, 4))

        tk.Label(self, text="Existing data moves automatically to the new folder.", bg=COLOR_BG,
                 fg=COLOR_SUBTEXT, font=("Segoe UI", 8)).pack(anchor="w", padx=16, pady=(0, 12))

        backup_row = tk.Frame(self, bg=COLOR_BG)
        backup_row.pack(anchor="w", padx=16, pady=(0, 4))
        tk.Button(backup_row, text="Export Vault...", command=self._export_vault, bg=COLOR_PANEL,
                  fg=COLOR_TEXT, relief="flat", font=FONT_SMALL, padx=10, pady=4
                  ).pack(side="left")
        tk.Button(backup_row, text="Import Vault...", command=self._import_vault, bg=COLOR_PANEL,
                  fg=COLOR_TEXT, relief="flat", font=FONT_SMALL, padx=10, pady=4
                  ).pack(side="left", padx=(8, 0))

        tk.Label(self, text="Export saves all your categories and commands to a single file \u2014 cheap "
                             "insurance before big edits or moving to a new machine. Import replaces your "
                             "current vault with one from a file.",
                 bg=COLOR_BG, fg=COLOR_SUBTEXT, font=("Segoe UI", 8), wraplength=360, justify="left"
                 ).pack(anchor="w", padx=16, pady=(0, 16))

        if is_linux():
            tk.Frame(self, bg=COLOR_PANEL, height=1).pack(fill="x", padx=16, pady=(0, 14))

            tk.Label(self, text="Terminal", bg=COLOR_BG, fg=COLOR_TEXT, font=FONT_HEADING
                     ).pack(anchor="w", padx=16)
            tk.Label(self, text="Which terminal \"Open in Terminal\" mode uses. Auto-detect tries common "
                                 "terminals in order; pick one directly if you know what you have installed.",
                     bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, wraplength=360, justify="left"
                     ).pack(anchor="w", padx=16, pady=(6, 8))

            cfg = _load_config()
            saved_pref = cfg.get("preferred_terminal", "auto")
            terminal_options = ["Auto-detect"] + list(NAMED_LINUX_TERMINALS.keys()) + ["Custom command..."]
            if saved_pref == "auto":
                initial = "Auto-detect"
            elif saved_pref == "custom":
                initial = "Custom command..."
            elif saved_pref in NAMED_LINUX_TERMINALS:
                initial = saved_pref
            else:
                initial = "Auto-detect"

            self.terminal_var = tk.StringVar(value=initial)
            terminal_combo = ttk.Combobox(self, textvariable=self.terminal_var, values=terminal_options,
                                           state="readonly", width=30, font=FONT_NORMAL)
            terminal_combo.pack(anchor="w", padx=16)
            terminal_combo.bind("<<ComboboxSelected>>", lambda e: self._sync_custom_template_visibility())

            self.custom_template_var = tk.StringVar(value=cfg.get("custom_terminal_template", ""))
            self.custom_template_label = tk.Label(self, text="Custom command (use %CMD% where the command goes):",
                                                    bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, anchor="w")
            self.custom_template_entry = tk.Entry(self, textvariable=self.custom_template_var, width=44,
                                                    font=("Segoe UI", 9), bg=COLOR_PANEL, fg=COLOR_TEXT,
                                                    insertbackground=COLOR_TEXT, relief="flat")
            example = tk.Label(self, text='Example: kitty bash -c "%CMD%; exec bash"',
                                bg=COLOR_BG, fg=COLOR_SUBTEXT, font=("Segoe UI", 8))
            self.custom_template_example = example

            self._sync_custom_template_visibility()

            btn_row = tk.Frame(self, bg=COLOR_BG)
            btn_row.pack(anchor="w", padx=16, pady=(10, 16))
            tk.Button(btn_row, text="Save", command=self._save_terminal_pref, bg=COLOR_ACCENT, fg=COLOR_SIDEBAR,
                      relief="flat", font=("Segoe UI", 10, "bold"), padx=12, pady=4).pack(side="left")
            tk.Button(btn_row, text="Test", command=self._test_terminal, bg=COLOR_PANEL, fg=COLOR_TEXT,
                      relief="flat", font=FONT_SMALL, padx=12, pady=4).pack(side="left", padx=(8, 0))

        tk.Frame(self, bg=COLOR_PANEL, height=1).pack(fill="x", padx=16, pady=(0, 14))

        tk.Label(self, text="Global Hotkey", bg=COLOR_BG, fg=COLOR_TEXT, font=FONT_HEADING
                 ).pack(anchor="w", padx=16)

        if not HAVE_PYNPUT:
            tk.Label(self, text="Install pynput to enable this:\npip install pynput",
                     bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, justify="left"
                     ).pack(anchor="w", padx=16, pady=(6, 16))
        else:
            tray_note = ("with a tray icon to reopen or quit" if HAVE_PYSTRAY else
                         "by minimizing (install pystray too for a proper tray icon instead)")
            tk.Label(self, text=f"Press this combo anytime \u2014 even with Command Vault closed \u2014 to bring "
                                 f"the window back. Closing the window then keeps running in the background "
                                 f"{tray_note}.",
                     bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, wraplength=360, justify="left"
                     ).pack(anchor="w", padx=16, pady=(6, 10))

            cfg = _load_config()
            display = cfg.get("hotkey_display", "Not set")
            self.hotkey_display_var = tk.StringVar(value=display)
            tk.Label(self, textvariable=self.hotkey_display_var, bg=COLOR_PANEL, fg=COLOR_ACCENT,
                     font=("Segoe UI", 11, "bold"), padx=10, pady=6).pack(anchor="w", padx=16, fill="x")

            hk_btn_row = tk.Frame(self, bg=COLOR_BG)
            hk_btn_row.pack(anchor="w", padx=16, pady=(8, 4))
            tk.Button(hk_btn_row, text="Record Shortcut...", command=self._record_hotkey, bg=COLOR_ACCENT,
                      fg=COLOR_SIDEBAR, relief="flat", font=("Segoe UI", 10, "bold"), padx=12, pady=4
                      ).pack(side="left")
            tk.Button(hk_btn_row, text="Clear", command=self._clear_hotkey, bg=COLOR_PANEL, fg=COLOR_RED,
                      relief="flat", font=FONT_SMALL, padx=12, pady=4).pack(side="left", padx=(8, 0))
            tk.Button(hk_btn_row, text="See All Keybinds", command=self._open_all_keybinds, bg=COLOR_PANEL,
                      fg=COLOR_TEXT, relief="flat", font=FONT_SMALL, padx=12, pady=4).pack(side="left", padx=(8, 0))

            if is_linux():
                tk.Label(self, text="Linux note: needs an X11 session. On native Wayland this generally won't "
                                     "trigger even while Command Vault is open and focused, since Wayland blocks "
                                     "cross-app input capture by design.",
                         bg=COLOR_BG, fg=COLOR_SUBTEXT, font=("Segoe UI", 8), wraplength=360, justify="left"
                         ).pack(anchor="w", padx=16, pady=(4, 16))
            else:
                tk.Label(self, text="", bg=COLOR_BG).pack(pady=(0, 4))

        tk.Frame(self, bg=COLOR_PANEL, height=1).pack(fill="x", padx=16, pady=(0, 14))

        tk.Label(self, text="Insert Input Box Shortcut", bg=COLOR_BG, fg=COLOR_TEXT, font=FONT_HEADING
                 ).pack(anchor="w", padx=16)
        tk.Label(self, text="Used inside the command box in Add/Edit Entry to insert a {{name}} placeholder "
                             "at the cursor \u2014 no extra install needed, this works purely within the app.",
                 bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, wraplength=360, justify="left"
                 ).pack(anchor="w", padx=16, pady=(6, 10))

        ph_cfg = _load_config()
        ph_display = ph_cfg.get("insert_placeholder_display", "Ctrl+I (default)")
        self.placeholder_shortcut_display_var = tk.StringVar(value=ph_display)
        tk.Label(self, textvariable=self.placeholder_shortcut_display_var, bg=COLOR_PANEL, fg=COLOR_ACCENT,
                 font=("Segoe UI", 11, "bold"), padx=10, pady=6).pack(anchor="w", padx=16, fill="x")

        ph_btn_row = tk.Frame(self, bg=COLOR_BG)
        ph_btn_row.pack(anchor="w", padx=16, pady=(8, 16))
        tk.Button(ph_btn_row, text="Record Shortcut...", command=self._record_placeholder_shortcut,
                  bg=COLOR_ACCENT, fg=COLOR_SIDEBAR, relief="flat", font=("Segoe UI", 10, "bold"), padx=12, pady=4
                  ).pack(side="left")
        tk.Button(ph_btn_row, text="Reset to Ctrl+I", command=self._clear_placeholder_shortcut, bg=COLOR_PANEL,
                  fg=COLOR_TEXT, relief="flat", font=FONT_SMALL, padx=12, pady=4).pack(side="left", padx=(8, 0))

        tk.Frame(self, bg=COLOR_PANEL, height=1).pack(fill="x", padx=16, pady=(0, 14))

        tk.Label(self, text="Updates", bg=COLOR_BG, fg=COLOR_TEXT, font=FONT_HEADING
                 ).pack(anchor="w", padx=16)
        tk.Label(self, text=f"You're running v{APP_VERSION}.", bg=COLOR_BG, fg=COLOR_SUBTEXT,
                 font=FONT_SMALL).pack(anchor="w", padx=16, pady=(6, 8))

        auto_check_cfg = _load_config()
        self.auto_update_var = tk.BooleanVar(value=auto_check_cfg.get("auto_update_check", True))
        tk.Checkbutton(self, text="Check for updates automatically (about once a day)",
                        variable=self.auto_update_var, bg=COLOR_BG, fg=COLOR_TEXT, selectcolor=COLOR_PANEL,
                        activebackground=COLOR_BG, activeforeground=COLOR_TEXT, font=FONT_NORMAL,
                        command=self._toggle_auto_update_check).pack(anchor="w", padx=16)

        self.update_status_var = tk.StringVar(value="")
        tk.Button(self, text="Check for Updates", command=self._check_for_updates_manual, bg=COLOR_PANEL,
                  fg=COLOR_TEXT, relief="flat", font=FONT_SMALL, padx=10, pady=4
                  ).pack(anchor="w", padx=16, pady=(10, 4))
        tk.Label(self, textvariable=self.update_status_var, bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL,
                 wraplength=360, justify="left").pack(anchor="w", padx=16, pady=(0, 16))

        tk.Button(self, text="Close", command=self.destroy, bg=COLOR_PANEL, fg=COLOR_TEXT,
                  relief="flat", padx=14, pady=4).pack(pady=(0, 16))

    def _toggle_auto_update_check(self):
        cfg = _load_config()
        cfg["auto_update_check"] = self.auto_update_var.get()
        _save_config(cfg)

    def _check_for_updates_manual(self):
        self.update_status_var.set("Checking...")

        def _run():
            result = fetch_latest_release()
            cfg = _load_config()
            cfg["last_update_check"] = time.time()
            _save_config(cfg)

            def _apply():
                if not self.winfo_exists():
                    return  # Settings dialog was closed before the check finished
                if result is None:
                    self.update_status_var.set(
                        "Couldn't check for updates (no network, or GitHub is unreachable right now).")
                    return
                tag, html_url = result
                if _version_is_newer(tag, APP_VERSION):
                    self.update_status_var.set(f"{tag} is available.")
                    if messagebox.askyesno("Update available",
                                            f"Command Vault {tag} is available (you have v{APP_VERSION}).\n\n"
                                            f"Open the release page?"):
                        self.master_app._open_url(html_url)
                else:
                    self.update_status_var.set(f"You're on the latest version (v{APP_VERSION}).")

            self.master_app._post_to_main_thread(_apply)

        threading.Thread(target=_run, daemon=True).start()

    def _record_placeholder_shortcut(self):
        dialog = HotkeyRecorderDialog(self)
        self.wait_window(dialog)
        if not dialog.result:
            return
        display_string, _pynput_string, tk_bind_string = dialog.result
        cfg = _load_config()
        cfg["insert_placeholder_display"] = display_string
        cfg["insert_placeholder_tkbind"] = tk_bind_string
        _save_config(cfg)
        self.placeholder_shortcut_display_var.set(display_string)

    def _clear_placeholder_shortcut(self):
        cfg = _load_config()
        cfg.pop("insert_placeholder_display", None)
        cfg.pop("insert_placeholder_tkbind", None)
        _save_config(cfg)
        self.placeholder_shortcut_display_var.set("Ctrl+I (default)")

    def _record_hotkey(self):
        dialog = HotkeyRecorderDialog(self)
        self.wait_window(dialog)
        if not dialog.result:
            return
        display_string, pynput_string, _tk_bind_string = dialog.result

        current = _load_config().get("hotkey_pynput")
        conflicts = self.master_app._all_used_hotkeys(exclude_pynput=current)
        if pynput_string in conflicts:
            messagebox.showwarning("Already in use", f"{display_string} is already assigned to "
                                                        f"{conflicts[pynput_string]}. Pick a different combo.")
            return

        cfg = _load_config()
        cfg["hotkey_display"] = display_string
        cfg["hotkey_pynput"] = pynput_string
        _save_config(cfg)
        self.hotkey_display_var.set(display_string)
        self.master_app._rebuild_hotkey_listener()
        self.master_app._log(f"Global hotkey set: {display_string}")

    def _clear_hotkey(self):
        cfg = _load_config()
        cfg.pop("hotkey_display", None)
        cfg.pop("hotkey_pynput", None)
        _save_config(cfg)
        self.hotkey_display_var.set("Not set")
        self.master_app._rebuild_hotkey_listener()
        self.master_app._log("Global hotkey cleared.")

    def _open_all_keybinds(self):
        AllKeybindsDialog(self, self.master_app)

    def _sync_custom_template_visibility(self):
        if self.terminal_var.get() == "Custom command...":
            self.custom_template_label.pack(anchor="w", padx=16, pady=(6, 2))
            self.custom_template_entry.pack(fill="x", padx=16)
            self.custom_template_example.pack(anchor="w", padx=16, pady=(2, 0))
        else:
            self.custom_template_label.pack_forget()
            self.custom_template_entry.pack_forget()
            self.custom_template_example.pack_forget()

    def _current_terminal_pref(self):
        choice = self.terminal_var.get()
        if choice == "Auto-detect":
            return "auto", ""
        if choice == "Custom command...":
            return "custom", self.custom_template_var.get().strip()
        return choice, ""

    def _save_terminal_pref(self):
        pref, template = self._current_terminal_pref()
        if pref == "custom" and "%CMD%" not in template:
            messagebox.showwarning("Missing %CMD%", "Your custom command needs a %CMD% placeholder for where "
                                                       "the actual command gets inserted.")
            return
        cfg = _load_config()
        cfg["preferred_terminal"] = pref
        cfg["custom_terminal_template"] = template
        _save_config(cfg)
        messagebox.showinfo("Saved", "Terminal preference saved.")

    def _test_terminal(self):
        pref, template = self._current_terminal_pref()
        cfg = _load_config()
        cfg["preferred_terminal"] = pref
        cfg["custom_terminal_template"] = template
        _save_config(cfg)
        test_entry = {"id": "test", "name": "Terminal Test", "command": 'echo "Command Vault terminal test - it works!"',
                      "working_dir": "", "run_mode": "terminal", "entry_type": "command"}
        run_entry(test_entry, log=self.master_app._log)

    def _toggle_app_autostart(self):
        try:
            set_app_autostart(self.autostart_var.get())
        except NotImplementedError as e:
            messagebox.showwarning("Not supported", str(e))
            self.autostart_var.set(app_autostart_enabled())

    def _change_folder(self):
        new_dir = filedialog.askdirectory(title="Choose folder to store Command Vault's data",
                                           initialdir=get_data_dir())
        if not new_dir:
            return
        try:
            set_data_dir(new_dir)
        except OSError as e:
            messagebox.showerror("Couldn't change folder", str(e))
            return
        self.path_var.set(get_data_dir())
        self.master_app.data = load_data()
        self.master_app._refresh_categories()
        self.master_app._refresh_list()
        messagebox.showinfo("Data folder updated", f"Command Vault now stores its data in:\n{new_dir}")

    def _export_vault(self):
        default_name = f"command-vault-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        path = filedialog.asksaveasfilename(
            title="Export Command Vault", defaultextension=".json", initialfile=default_name,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            # Serialize the in-memory vault rather than copying commands.json
            # off disk -- on a brand-new install with an empty vault, no
            # file has been written yet, and this way Export can never miss
            # a change even if the on-disk copy were somehow stale.
            with open(path, "w") as f:
                json.dump(self.master_app.data, f, indent=4)
        except OSError as e:
            messagebox.showerror("Export failed", str(e))
            return
        n = len(self.master_app.data.get("commands", []))
        messagebox.showinfo("Vault exported", f"Exported {n} command{'s' if n != 1 else ''} to:\n{path}")

    def _import_vault(self):
        path = filedialog.askopenfilename(title="Import Command Vault",
                                           filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "r") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
            messagebox.showerror("Import failed", f"Couldn't read that file as a Command Vault export:\n{e}")
            return

        try:
            imported = _normalize_vault_data(raw)
        except (AttributeError, TypeError):
            # e.g. valid JSON but not an object/list shaped like a vault
            messagebox.showerror("Import failed", "That file doesn't look like a Command Vault export.")
            return

        current_n = len(self.master_app.data.get("commands", []))
        new_n = len(imported.get("commands", []))
        proceed = messagebox.askyesno(
            "Replace current vault?",
            f"This will replace your current vault ({current_n} command{'s' if current_n != 1 else ''}) "
            f"with the {new_n} command{'s' if new_n != 1 else ''} from:\n{path}\n\n"
            "Your current vault will be backed up first. Continue?")
        if not proceed:
            return

        # Cheap insurance against importing the wrong file: back up what's
        # about to be overwritten, same convention as the corrupted-file
        # quarantine in load_data().
        data_file = get_data_file()
        if os.path.exists(data_file):
            backup_path = f"{data_file}.pre-import-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            try:
                shutil.copy2(data_file, backup_path)
            except OSError:
                backup_path = None
        else:
            backup_path = None

        try:
            save_data(imported)
        except OSError as e:
            messagebox.showerror("Import failed", f"Couldn't write the new vault:\n{e}")
            return

        self.master_app.data = imported
        self.master_app._refresh_categories()
        self.master_app._refresh_list()
        # hotkey_pynput on each entry is the live source of truth for global
        # hotkeys, so this actually re-registers any imported entries' hotkeys.
        self.master_app._rebuild_hotkey_listener()
        # autostart's source of truth is an OS-level file per entry, not the
        # JSON field, so imported entries with autostart=True need that file
        # (re)created here or they'd show "on" in the UI without actually
        # running at login on this machine.
        autostart_failures = 0
        for entry in imported.get("commands", []):
            if entry.get("autostart"):
                try:
                    set_entry_autostart(entry, True)
                except (NotImplementedError, OSError):
                    autostart_failures += 1

        msg = f"Imported {new_n} command{'s' if new_n != 1 else ''}."
        if backup_path:
            msg += f"\n\nYour previous vault was backed up to:\n{backup_path}"
        if autostart_failures:
            msg += (f"\n\n{autostart_failures} autostart entr{'y' if autostart_failures == 1 else 'ies'} "
                     "couldn't be registered on this machine/OS and may need re-enabling manually.")
        messagebox.showinfo("Vault imported", msg)


# ---------------------------------------------------------------------------
# Global hotkey: capture (local, dialog-scoped) and tray icon (for background mode)
# ---------------------------------------------------------------------------
MODIFIER_KEYSYMS = {
    "Control_L": "ctrl", "Control_R": "ctrl",
    "Alt_L": "alt", "Alt_R": "alt",
    "Shift_L": "shift", "Shift_R": "shift",
    "Super_L": "cmd", "Super_R": "cmd",
}

MODIFIER_ORDER = ["ctrl", "alt", "shift", "cmd"]

TK_MODIFIER_NAMES = {"ctrl": "Control", "alt": "Alt", "shift": "Shift", "cmd": "Super"}

SPECIAL_KEYSYM_TO_PYNPUT = {
    "space": "<space>", "Return": "<enter>", "Escape": "<esc>", "Tab": "<tab>",
    "BackSpace": "<backspace>", "Delete": "<delete>",
    "Up": "<up>", "Down": "<down>", "Left": "<left>", "Right": "<right>",
    "Home": "<home>", "End": "<end>", "Page_Up": "<page_up>", "Page_Down": "<page_down>",
    "F1": "<f1>", "F2": "<f2>", "F3": "<f3>", "F4": "<f4>", "F5": "<f5>", "F6": "<f6>",
    "F7": "<f7>", "F8": "<f8>", "F9": "<f9>", "F10": "<f10>", "F11": "<f11>", "F12": "<f12>",
}


def tk_keysym_to_pynput(keysym):
    if keysym in SPECIAL_KEYSYM_TO_PYNPUT:
        return SPECIAL_KEYSYM_TO_PYNPUT[keysym]
    if len(keysym) == 1:
        return keysym.lower()
    return None


TRAY_ICON_PNG_B64 = (
    "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"
    "gg=="
)


def build_tray_image(size=64):
    """Decodes the app's packaging/icon.png logo (baked in as base64 below)
    and resizes it to the requested size. Baked in rather than loaded from
    disk because PyInstaller builds never bundle packaging/ as a data file
    -- this keeps the tray icon self-contained the same way the earlier
    procedurally-drawn padlock placeholder was."""
    img = PILImage.open(io.BytesIO(base64.b64decode(TRAY_ICON_PNG_B64))).convert("RGBA")
    if img.size != (size, size):
        img = img.resize((size, size), PILImage.LANCZOS)
    return img


class HotkeyRecorderDialog(tk.Toplevel):
    """Minecraft-style capture: click Record, hold modifiers + press a key,
    it finalizes immediately. Local Tkinter key events are enough here since
    this dialog has focus while recording -- only *triggering* the saved
    hotkey later needs to be global (that's pynput's job, in CommandVault)."""
    def __init__(self, master):
        super().__init__(master)
        self.result = None
        self.title("Record Shortcut")
        self.configure(bg=COLOR_BG)
        self.resizable(False, False)
        self.grab_set()
        self.held_modifiers = set()

        self.status_var = tk.StringVar(value="Press a key combination\u2026")
        tk.Label(self, textvariable=self.status_var, bg=COLOR_BG, fg=COLOR_TEXT, font=("Segoe UI", 14, "bold")
                 ).pack(padx=36, pady=(28, 8))
        tk.Label(self, text="Hold Ctrl/Alt/Shift/Super and press a key. Esc to cancel.",
                 bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL).pack(padx=20, pady=(0, 24))

        self.bind("<KeyPress>", self._on_key_press)
        self.bind("<KeyRelease>", self._on_key_release)
        self.focus_set()

    def _on_key_press(self, event):
        keysym = event.keysym
        if keysym in MODIFIER_KEYSYMS:
            self.held_modifiers.add(MODIFIER_KEYSYMS[keysym])
            self._update_status()
            return
        if keysym == "Escape":
            self.result = None
            self.destroy()
            return

        pynput_key = tk_keysym_to_pynput(keysym)
        if not pynput_key:
            self.status_var.set(f"'{keysym}' isn't supported \u2014 try another key")
            return
        if not self.held_modifiers:
            self.status_var.set("Add at least one modifier (Ctrl/Alt/Shift/Super)")
            return

        mods = [m for m in MODIFIER_ORDER if m in self.held_modifiers]
        pynput_string = "+".join([f"<{m}>" for m in mods] + [pynput_key])
        display_key = keysym if len(keysym) > 1 else keysym.upper()
        display_string = "+".join([m.capitalize() for m in mods] + [display_key])
        tk_bind_string = "<" + "-".join([TK_MODIFIER_NAMES[m] for m in mods] + [keysym]) + ">"
        self.result = (display_string, pynput_string, tk_bind_string)
        self.destroy()

    def _on_key_release(self, event):
        keysym = event.keysym
        if keysym in MODIFIER_KEYSYMS:
            self.held_modifiers.discard(MODIFIER_KEYSYMS[keysym])
            self._update_status()

    def _update_status(self):
        if self.held_modifiers:
            mods = "+".join(m.capitalize() for m in MODIFIER_ORDER if m in self.held_modifiers)
            self.status_var.set(f"{mods}+\u2026 (now press a key)")
        else:
            self.status_var.set("Press a key combination\u2026")


class AllKeybindsDialog(tk.Toplevel):
    """Read-only overview of every configured shortcut: the app-level
    reopen hotkey, the local insert-input-box shortcut, and every entry's
    own launch hotkey. Actual changes happen where each is defined."""
    def __init__(self, master, app):
        super().__init__(master)
        self.title("All Keybinds")
        self.configure(bg=COLOR_BG)
        self.geometry("460x420")
        self.transient(master)
        self.grab_set()

        tk.Label(self, text="All Keybinds", bg=COLOR_BG, fg=COLOR_TEXT, font=FONT_HEADING
                 ).pack(anchor="w", padx=16, pady=(16, 8))

        list_frame = tk.Frame(self, bg=COLOR_BG)
        list_frame.pack(fill="both", expand=True, padx=16)

        columns = ("what", "shortcut")
        tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="none")
        tree.heading("what", text="Command / Action")
        tree.heading("shortcut", text="Shortcut")
        tree.column("what", width=280, anchor="w")
        tree.column("shortcut", width=140, anchor="w")
        tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")

        cfg = _load_config()
        rows = []
        app_hk = cfg.get("hotkey_display")
        rows.append(("App: Show Command Vault", app_hk or "Not set"))
        ph_hk = cfg.get("insert_placeholder_display", "Ctrl+I (default)")
        rows.append(("Insert Input Box (in command editor)", ph_hk))
        for entry in app.data.get("commands", []):
            hk = entry.get("hotkey_display")
            if hk:
                rows.append((f'{entry.get("icon", "")} {entry["name"]} ({entry["category"]})', hk))

        for i, (what, shortcut) in enumerate(rows):
            tag = "even" if i % 2 else "odd"
            tree.insert("", tk.END, values=(what, shortcut), tags=(tag,))
        tree.tag_configure("odd", background=COLOR_PANEL)
        tree.tag_configure("even", background=COLOR_ROW_ALT)

        entry_count = len(rows) - 2
        if entry_count == 0:
            tk.Label(self, text="No per-command shortcuts set yet \u2014 add one from an entry's Edit dialog.",
                     bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, wraplength=420, justify="left"
                     ).pack(anchor="w", padx=16, pady=(8, 0))

        tk.Button(self, text="Close", command=self.destroy, bg=COLOR_PANEL, fg=COLOR_TEXT,
                  relief="flat", padx=14, pady=4).pack(pady=16)


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
class CommandVault(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Command Vault")
        self.geometry("860x680")
        self.minsize(700, 520)
        self.configure(bg=COLOR_BG)
        self._set_window_icon()

        self.data = load_data()
        self.selected_category = ALL_CATEGORY
        self._log_queue = queue.Queue()
        self._main_thread_queue = queue.Queue()
        self._hotkey_listener = None
        self._tray_icon = None
        self._instance_lock_socket = acquire_single_instance_lock(
            lambda: self._post_to_main_thread(self._show_window)
        )

        self._build_style()
        self._build_layout()
        self._refresh_categories()
        self._refresh_list()
        self.after(150, self._drain_log_queue)
        self._log("Command Vault ready.")

        self.protocol("WM_DELETE_WINDOW", self._on_close_request)
        self._rebuild_hotkey_listener()
        self._check_for_update_startup()

    # -- global hotkey / background mode ------------------------------------
    def _rebuild_hotkey_listener(self, retry_count=0):
        """Rebuilds the single combined GlobalHotKeys listener from the
        app-level hotkey (config.json) plus every entry's own hotkey
        (commands.json). Call this after any hotkey is added/changed/removed.

        retry_count > 0 means this call is itself a retry: registration can
        fail right at login/autostart if the X session isn't fully up yet,
        so failures here back off and try again a few times rather than
        giving up silently."""
        if not HAVE_PYNPUT:
            return
        self._stop_hotkey_listener()

        mapping = {}
        cfg = _load_config()
        app_hotkey = cfg.get("hotkey_pynput")
        if app_hotkey:
            mapping[app_hotkey] = self._on_app_hotkey_triggered

        for entry in self.data.get("commands", []):
            hk = entry.get("hotkey_pynput")
            if hk and hk not in mapping:
                mapping[hk] = self._make_entry_hotkey_callback(entry["id"])

        if not mapping:
            return

        try:
            self._hotkey_listener = pynput_keyboard.GlobalHotKeys(mapping)
            self._hotkey_listener.daemon = True
            self._hotkey_listener.start()
            # GlobalHotKeys() and .start() succeed synchronously even when
            # the underlying X connection is broken -- that failure happens
            # *inside* the listener's background thread (e.g. X session not
            # ready yet at login), which then dies silently with no
            # exception we can catch here. So verify shortly after that the
            # thread is actually still alive before declaring success.
            self.after(500, lambda: self._verify_hotkey_listener(retry_count))
        except Exception as e:
            self._hotkey_listener = None
            self._schedule_hotkey_retry(retry_count, e)

    def _verify_hotkey_listener(self, retry_count):
        listener = self._hotkey_listener
        if listener is None:
            return  # already replaced or cleared by something else since
        if not listener.is_alive():
            self._hotkey_listener = None
            self._schedule_hotkey_retry(retry_count, "listener thread died (X session likely wasn't ready)")
        elif retry_count > 0:
            self._log("Global hotkeys registered successfully.")

    def _schedule_hotkey_retry(self, retry_count, error):
        max_retries = 5
        if retry_count < max_retries:
            delay_ms = min(2000 * (retry_count + 1), 10000)
            self._log(f"Hotkey registration failed (attempt {retry_count + 1}/{max_retries}), "
                      f"retrying in {delay_ms // 1000}s: {error}")
            self.after(delay_ms, lambda: self._rebuild_hotkey_listener(retry_count + 1))
        else:
            self._log(f"Couldn't register global hotkey(s) after {max_retries} attempts: {error}")

    def _make_entry_hotkey_callback(self, entry_id):
        def callback():
            self._post_to_main_thread(lambda: self._run_entry_by_id(entry_id))
        return callback

    def _run_entry_by_id(self, entry_id):
        for entry in self.data.get("commands", []):
            if entry["id"] == entry_id:
                run_entry(entry, log=self._log)
                return

    def _all_used_hotkeys(self, exclude_pynput=None):
        """Returns {pynput_string: description} across the app-level hotkey
        and every entry's hotkey, for conflict checking. exclude_pynput lets
        the thing currently being edited not conflict with its own old value."""
        used = {}
        cfg = _load_config()
        app_hotkey = cfg.get("hotkey_pynput")
        if app_hotkey and app_hotkey != exclude_pynput:
            used[app_hotkey] = f"App: Show Command Vault ({cfg.get('hotkey_display', '')})"
        for entry in self.data.get("commands", []):
            hk = entry.get("hotkey_pynput")
            if hk and hk != exclude_pynput:
                used[hk] = f'"{entry["name"]}" ({entry.get("hotkey_display", "")})'
        return used

    def _on_app_hotkey_triggered(self):
        self._post_to_main_thread(self._show_window)

    def _stop_hotkey_listener(self):
        if self._hotkey_listener:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass
            self._hotkey_listener = None

    def _post_to_main_thread(self, fn):
        self._main_thread_queue.put(fn)

    def _show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _set_window_icon(self):
        """Sets the titlebar/taskbar icon from the same baked-in logo the
        tray icon uses. Best-effort: some platforms/WMs ignore iconphoto,
        and PIL might not be present, so failures here are silent."""
        if not HAVE_PIL:
            return
        try:
            from PIL import ImageTk
            self._window_icon_ref = ImageTk.PhotoImage(build_tray_image(64))
            self.iconphoto(True, self._window_icon_ref)
        except Exception:
            pass

    def _check_for_update_startup(self):
        def _on_found(tag, html_url):
            self._post_to_main_thread(lambda: self._notify_update_available(tag, html_url))
        check_for_update(force=False, on_result=_on_found)

    def _notify_update_available(self, tag, html_url):
        # Don't nag about the same version more than once per run/day --
        # once shown, remember it so it doesn't reappear tomorrow's cooldown
        # cycle unless a newer tag shows up.
        cfg = _load_config()
        if cfg.get("dismissed_update_version") == tag:
            return
        self._log(f"Update available: {tag} (you have v{APP_VERSION}) -- {html_url}")
        if messagebox.askyesno(
                "Update available",
                f"Command Vault {tag} is available (you have v{APP_VERSION}).\n\n"
                f"Open the release page?"):
            self._open_url(html_url)
        cfg["dismissed_update_version"] = tag
        _save_config(cfg)

    @staticmethod
    def _open_url(url):
        try:
            if is_windows():
                os.startfile(url)
            elif is_mac():
                subprocess.Popen(["open", url])
            else:
                subprocess.Popen(["xdg-open", url])
        except OSError:
            pass

    def _ensure_tray_icon(self):
        if self._tray_icon:
            return True
        if not HAVE_PYSTRAY:
            return False
        try:
            image = build_tray_image()
            menu = pystray.Menu(
                pystray.MenuItem("Show Command Vault", lambda: self._post_to_main_thread(self._show_window),
                                  default=True),
                pystray.MenuItem("Quit", lambda: self._post_to_main_thread(self._quit_app)),
            )
            self._tray_icon = pystray.Icon("command-vault", image, "Command Vault", menu)
            self._tray_icon.run_detached()
            return True
        except Exception as e:
            self._tray_icon = None
            self._log(f"Tray icon unavailable ({e})")
            return False

    def _stop_tray_icon(self):
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None

    def _on_close_request(self):
        cfg = _load_config()
        if not cfg.get("hotkey_pynput"):
            self._quit_app()
            return
        if self._ensure_tray_icon():
            self.withdraw()
            self._log("Minimized to tray \u2014 press your hotkey or use the tray icon to reopen.")
        else:
            self.iconify()
            self._log("Minimized \u2014 press your hotkey or restore from the taskbar to reopen.")

    def _quit_app(self):
        self._stop_hotkey_listener()
        self._stop_tray_icon()
        if self._instance_lock_socket:
            try:
                self._instance_lock_socket.close()
            except OSError:
                pass
            self._instance_lock_socket = None
        self.destroy()

    # -- styling -----------------------------------------------------------
    def _build_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview",
                         background=COLOR_PANEL,
                         fieldbackground=COLOR_PANEL,
                         foreground=COLOR_TEXT,
                         rowheight=30,
                         borderwidth=0,
                         font=FONT_NORMAL)
        style.configure("Treeview.Heading",
                         background=COLOR_SIDEBAR,
                         foreground=COLOR_SUBTEXT,
                         font=FONT_HEADING,
                         borderwidth=0)
        style.map("Treeview",
                  background=[("selected", COLOR_SELECT)],
                  foreground=[("selected", COLOR_TEXT)])
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

    # -- layout --------------------------------------------------------------
    def _build_layout(self):
        sidebar = tk.Frame(self, bg=COLOR_SIDEBAR, width=190)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(sidebar, text="Command Vault", bg=COLOR_SIDEBAR, fg=COLOR_TEXT, font=FONT_TITLE,
                 anchor="w", justify="left", wraplength=170).pack(fill="x", padx=16, pady=(20, 16))

        tk.Label(sidebar, text="CATEGORIES", bg=COLOR_SIDEBAR, fg=COLOR_SUBTEXT, font=FONT_SMALL,
                 anchor="w").pack(fill="x", padx=16)

        self.category_frame = tk.Frame(sidebar, bg=COLOR_SIDEBAR)
        self.category_frame.pack(fill="both", expand=True, padx=8, pady=(6, 8))

        tk.Button(sidebar, text="+ New Category", command=self._add_category, bg=COLOR_SIDEBAR,
                  fg=COLOR_ACCENT, relief="flat", font=FONT_SMALL, anchor="w", padx=8
                  ).pack(fill="x", padx=8, pady=(0, 4))

        tk.Button(sidebar, text="\u2699 Settings", command=self._open_settings, bg=COLOR_SIDEBAR,
                  fg=COLOR_SUBTEXT, relief="flat", font=FONT_SMALL, anchor="w", padx=8
                  ).pack(fill="x", padx=8, pady=(0, 16), side="bottom")

        main = tk.Frame(self, bg=COLOR_BG)
        main.pack(side="left", fill="both", expand=True)

        top_bar = tk.Frame(main, bg=COLOR_BG)
        top_bar.pack(fill="x", padx=20, pady=(20, 10))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_list())
        search_entry = tk.Entry(top_bar, textvariable=self.search_var, font=FONT_NORMAL, bg=COLOR_PANEL,
                                 fg=COLOR_TEXT, insertbackground=COLOR_TEXT, relief="flat")
        search_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 10))
        self._set_placeholder(search_entry, "Search commands...")

        tk.Button(top_bar, text="+ Add", command=self._add_entry, bg=COLOR_ACCENT, fg=COLOR_SIDEBAR,
                  font=("Segoe UI", 10, "bold"), relief="flat", padx=14, pady=4).pack(side="left")

        list_frame = tk.Frame(main, bg=COLOR_BG)
        list_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        columns = ("icon", "name", "category", "mode", "boot")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("icon", text="")
        self.tree.heading("name", text="Name")
        self.tree.heading("category", text="Category")
        self.tree.heading("mode", text="Mode")
        self.tree.heading("boot", text="Boot")
        self.tree.column("icon", width=40, anchor="center", stretch=False)
        self.tree.column("name", width=300, anchor="w")
        self.tree.column("category", width=130, anchor="w")
        self.tree.column("mode", width=130, anchor="center")
        self.tree.column("boot", width=50, anchor="center", stretch=False)
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self._run_selected())

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        self.tree.tag_configure("odd", background=COLOR_PANEL)
        self.tree.tag_configure("even", background=COLOR_ROW_ALT)

        action_bar = tk.Frame(main, bg=COLOR_BG)
        action_bar.pack(fill="x", padx=20, pady=(0, 10))

        tk.Button(action_bar, text="\u25B6 Run", command=self._run_selected, bg=COLOR_GREEN, fg=COLOR_SIDEBAR,
                  font=("Segoe UI", 10, "bold"), relief="flat", padx=16, pady=6).pack(side="left")
        self.run_all_button = tk.Button(action_bar, text="\u25B6\u25B6 Run All", command=self._run_visible,
                                         bg=COLOR_YELLOW, fg=COLOR_SIDEBAR, font=("Segoe UI", 10, "bold"),
                                         relief="flat", padx=16, pady=6)
        self.run_all_button.pack(side="left", padx=(8, 0))
        tk.Button(action_bar, text="Edit", command=self._edit_selected, bg=COLOR_PANEL, fg=COLOR_TEXT,
                  font=FONT_NORMAL, relief="flat", padx=16, pady=6).pack(side="left", padx=(8, 0))
        tk.Button(action_bar, text="Delete", command=self._delete_selected, bg=COLOR_PANEL, fg=COLOR_RED,
                  font=FONT_NORMAL, relief="flat", padx=16, pady=6).pack(side="left", padx=(8, 0))

        # Console panel: shows exactly what ran and its live output, so
        # silent-mode entries (which show no window) aren't a black box.
        console_header = tk.Frame(main, bg=COLOR_BG)
        console_header.pack(fill="x", padx=20)
        tk.Label(console_header, text="CONSOLE", bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL,
                 anchor="w").pack(side="left")
        tk.Button(console_header, text="Clear", command=self._clear_console, bg=COLOR_BG, fg=COLOR_SUBTEXT,
                  relief="flat", font=FONT_SMALL, padx=6).pack(side="right")

        console_frame = tk.Frame(main, bg=COLOR_PANEL, height=150)
        console_frame.pack(fill="x", padx=20, pady=(4, 20))
        console_frame.pack_propagate(False)

        self.console_text = tk.Text(console_frame, bg=COLOR_PANEL, fg=COLOR_TEXT,
                                     font=("Consolas", 9) if is_windows() else ("DejaVu Sans Mono", 9),
                                     relief="flat", wrap="word", state="disabled", padx=8, pady=6)
        self.console_text.pack(side="left", fill="both", expand=True)
        console_scroll = ttk.Scrollbar(console_frame, orient="vertical", command=self.console_text.yview)
        self.console_text.configure(yscrollcommand=console_scroll.set)
        console_scroll.pack(side="right", fill="y")

    def _clear_console(self):
        self.console_text.configure(state="normal")
        self.console_text.delete("1.0", tk.END)
        self.console_text.configure(state="disabled")

    def _log(self, message):
        """Thread-safe: worker threads (reading silent-mode process output)
        call this too -- it only queues; the widget update happens on the
        main thread via _drain_log_queue."""
        self._log_queue.put(message)

    def _drain_log_queue(self):
        try:
            while True:
                message = self._log_queue.get_nowait()
                self._append_console(message)
        except queue.Empty:
            pass
        try:
            while True:
                fn = self._main_thread_queue.get_nowait()
                fn()
        except queue.Empty:
            pass
        self.after(150, self._drain_log_queue)

    def _append_console(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.console_text.configure(state="normal")
        self.console_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.console_text.see(tk.END)
        self.console_text.configure(state="disabled")

    def _set_placeholder(self, entry, text):
        entry.insert(0, text)
        entry.config(fg=COLOR_SUBTEXT)

        def on_focus_in(_):
            if entry.get() == text:
                entry.delete(0, tk.END)
                entry.config(fg=COLOR_TEXT)

        def on_focus_out(_):
            if not entry.get():
                entry.insert(0, text)
                entry.config(fg=COLOR_SUBTEXT)

        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)

    def _open_settings(self):
        SettingsDialog(self)

    # -- category sidebar ----------------------------------------------------
    def _refresh_categories(self):
        for widget in self.category_frame.winfo_children():
            widget.destroy()

        used = sorted({c["category"] for c in self.data["commands"]} | set(self.data["categories"]))
        all_cats = [ALL_CATEGORY] + used

        for cat in all_cats:
            is_selected = cat == self.selected_category
            btn = tk.Button(
                self.category_frame,
                text=cat,
                anchor="w",
                bg=COLOR_SELECT if is_selected else COLOR_SIDEBAR,
                fg=COLOR_ACCENT if is_selected else COLOR_TEXT,
                relief="flat",
                font=FONT_NORMAL,
                padx=10,
                pady=6,
                command=lambda c=cat: self._select_category(c),
            )
            btn.pack(fill="x", pady=1)

    def _select_category(self, cat):
        self.selected_category = cat
        self._refresh_categories()
        self._refresh_list()

    def _add_category(self):
        top = tk.Toplevel(self, bg=COLOR_BG)
        top.title("New Category")
        top.resizable(False, False)
        top.transient(self)
        top.grab_set()

        tk.Label(top, text="Category name", bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL
                 ).pack(padx=16, pady=(16, 4), anchor="w")
        var = tk.StringVar()
        entry = tk.Entry(top, textvariable=var, width=30, font=FONT_NORMAL, bg=COLOR_PANEL, fg=COLOR_TEXT,
                          insertbackground=COLOR_TEXT, relief="flat")
        entry.pack(padx=16, fill="x")
        entry.focus_set()

        def confirm():
            name = var.get().strip()
            if name and name not in self.data["categories"]:
                self.data["categories"].append(name)
                save_data(self.data)
                self._refresh_categories()
            top.destroy()

        btn_frame = tk.Frame(top, bg=COLOR_BG)
        btn_frame.pack(fill="x", padx=16, pady=16)
        tk.Button(btn_frame, text="Cancel", command=top.destroy, bg=COLOR_PANEL, fg=COLOR_TEXT,
                  relief="flat", padx=12, pady=4).pack(side="right")
        tk.Button(btn_frame, text="Add", command=confirm, bg=COLOR_ACCENT, fg=COLOR_SIDEBAR,
                  relief="flat", padx=12, pady=4, font=("Segoe UI", 10, "bold")).pack(side="right", padx=(0, 8))
        entry.bind("<Return>", lambda e: confirm())

    # -- list ------------------------------------------------------------
    def _visible_commands(self):
        query = self.search_var.get().strip().lower()
        if query == "search commands...":
            query = ""
        result = []
        for cmd in self.data["commands"]:
            if self.selected_category != ALL_CATEGORY and cmd["category"] != self.selected_category:
                continue
            if query and query not in cmd["name"].lower() and query not in cmd["command"].lower():
                continue
            result.append(cmd)
        return result

    @staticmethod
    def _command_preview(cmd):
        lines = cmd["command"].splitlines()
        if not lines:
            return ""
        first = lines[0]
        return first + " \u2026" if len(lines) > 1 else first

    def _refresh_list(self):
        if not hasattr(self, "tree"):
            return
        self.tree.delete(*self.tree.get_children())
        visible = self._visible_commands()
        for i, cmd in enumerate(visible):
            mode_label = "Silent" if cmd.get("run_mode") == "silent" else "Terminal"
            if cmd.get("entry_type") == "appimage":
                mode_label += " \u00b7 AppImage"
            boot_label = "\u2713" if cmd.get("autostart") else ""
            tag = "even" if i % 2 else "odd"
            self.tree.insert("", tk.END, iid=cmd["id"],
                              values=(cmd.get("icon", DEFAULT_ICON), cmd["name"], cmd["category"], mode_label,
                                      boot_label),
                              tags=(tag,))
        self._update_run_all_label(len(visible))

    def _update_run_all_label(self, count):
        if not hasattr(self, "run_all_button"):
            return
        if self.selected_category == ALL_CATEGORY:
            label = f"\u25B6\u25B6 Run All ({count})"
        else:
            label = f"\u25B6\u25B6 Run All in {self.selected_category} ({count})"
        self.run_all_button.config(text=label, state=("normal" if count else "disabled"))

    def _run_visible(self):
        entries = self._visible_commands()
        if not entries:
            messagebox.showinfo("Nothing to run", "There are no entries in the current view.")
            return

        runnable = [e for e in entries if not extract_placeholders(e.get("command", ""))]
        skipped_ids = {e["id"] for e in entries} - {e["id"] for e in runnable}
        skipped = [e for e in entries if e["id"] in skipped_ids]

        scope = "all categories" if self.selected_category == ALL_CATEGORY else f"'{self.selected_category}'"
        query = self.search_var.get().strip()
        if query and query.lower() != "search commands...":
            scope += f" matching \"{query}\""

        msg = f"This will launch {len(runnable)} entries in {scope}."
        if skipped:
            names = ", ".join(e["name"] for e in skipped)
            msg += f"\n\n{len(skipped)} skipped (need values filled in \u2014 run individually): {names}"
        msg += "\n\nContinue?"

        if not runnable:
            messagebox.showinfo("Nothing to run", "Every entry in this view needs values filled in \u2014 run them individually.")
            return

        if not messagebox.askyesno("Run all?", msg):
            return

        for entry in runnable:
            run_entry(entry, log=self._log)

    def _get_selected_entry(self):
        sel = self.tree.selection()
        if not sel:
            return None
        entry_id = sel[0]
        for cmd in self.data["commands"]:
            if cmd["id"] == entry_id:
                return cmd
        return None

    # -- CRUD actions ------------------------------------------------------
    def _known_categories(self):
        used = sorted({c["category"] for c in self.data["commands"]} | set(self.data["categories"]))
        return used or [UNCATEGORIZED]

    def _apply_autostart(self, entry):
        if entry.get("autostart") and extract_placeholders(entry.get("command", "")):
            messagebox.showwarning(
                "Heads up",
                f'"{entry["name"]}" uses {{{{placeholders}}}} that need values filled in each run.\n\n'
                "At boot there's no one to prompt, so it will run with the literal "
                "{{name}} text still in it and likely fail. Consider removing the "
                "placeholders for autostart entries, or leaving autostart off for this one."
            )
        try:
            set_entry_autostart(entry, entry.get("autostart", False))
        except NotImplementedError as e:
            messagebox.showwarning("Not supported", str(e))

    def _add_entry(self):
        dialog = EntryDialog(self, self._known_categories())
        self.wait_window(dialog)
        if dialog.result:
            self.data["commands"].append(dialog.result)
            if dialog.result["category"] not in self.data["categories"]:
                self.data["categories"].append(dialog.result["category"])
            save_data(self.data)
            self._apply_autostart(dialog.result)
            self._rebuild_hotkey_listener()
            self._refresh_categories()
            self._refresh_list()

    def _edit_selected(self):
        entry = self._get_selected_entry()
        if not entry:
            messagebox.showinfo("No selection", "Select an entry to edit first.")
            return
        dialog = EntryDialog(self, self._known_categories(), entry=entry)
        self.wait_window(dialog)
        if dialog.result:
            idx = next(i for i, c in enumerate(self.data["commands"]) if c["id"] == entry["id"])
            self.data["commands"][idx] = dialog.result
            if dialog.result["category"] not in self.data["categories"]:
                self.data["categories"].append(dialog.result["category"])
            save_data(self.data)
            self._apply_autostart(dialog.result)
            self._rebuild_hotkey_listener()
            self._refresh_categories()
            self._refresh_list()

    def _delete_selected(self):
        entry = self._get_selected_entry()
        if not entry:
            messagebox.showinfo("No selection", "Select an entry to delete first.")
            return
        if messagebox.askyesno("Delete entry", f"Delete '{entry['name']}'?"):
            self.data["commands"] = [c for c in self.data["commands"] if c["id"] != entry["id"]]
            save_data(self.data)
            try:
                set_entry_autostart(entry, False)
            except NotImplementedError:
                pass
            self._rebuild_hotkey_listener()
            self._refresh_categories()
            self._refresh_list()

    def _run_selected(self):
        entry = self._get_selected_entry()
        if not entry:
            messagebox.showinfo("No selection", "Select an entry to run first.")
            return
        run_entry(entry, log=self._log)


if __name__ == "__main__":
    if notify_running_instance():
        # Another instance is already running and has been asked to raise
        # its window -- nothing more for this process to do.
        sys.exit(0)
    app = CommandVault()
    app.mainloop()
