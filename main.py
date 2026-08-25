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


def set_app_autostart(enabled):
    path = app_autostart_path()
    if not path:
        raise NotImplementedError("Autostart isn't supported on this OS yet.")
    if not enabled:
        if os.path.exists(path):
            os.remove(path)
        return
    if is_linux():
        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Command Vault\n"
            f"Exec={app_relaunch_command()}\n"
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
    if entry.get("entry_type") == "appimage":
        exec_cmd = f'"{command}"'
    else:
        exec_cmd = resolve_exec_command(command)

    if is_linux():
        # Write a real wrapper script instead of inlining into Exec=, since
        # squashing multiline commands onto one line breaks as soon as a
        # line has a "#" comment (bash treats the rest of that line as a
        # comment, silently dropping every command after it).
        script_path = os.path.join(linux_autostart_scripts_dir(), f"cv-{entry['id']}.sh")
        lines = ["#!/bin/bash"]
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
# Data layer
# ---------------------------------------------------------------------------
def load_data():
    """Load commands.json, migrating the old flat-list format if needed."""
    data_file = get_data_file()
    if not os.path.exists(data_file):
        return {"categories": [], "commands": [], "settings": {}}

    with open(data_file, "r") as f:
        raw = json.load(f)

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
            subprocess.Popen(builder(exec_cmd), cwd=working_dir)
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
                 fg=COLOR_SUBTEXT, font=("Segoe UI", 8)).pack(anchor="w", padx=16, pady=(0, 16))

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

        tk.Button(self, text="Close", command=self.destroy, bg=COLOR_PANEL, fg=COLOR_TEXT,
                  relief="flat", padx=14, pady=4).pack(pady=(0, 16))

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


def build_tray_image(size=64):
    """Draws the same padlock icon as packaging/icon.png, in-memory, so the
    tray icon doesn't depend on bundling a separate asset file."""
    img = PILImage.new("RGBA", (size, size), (0, 0, 0, 0))
    d = PILImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size, size], radius=size // 6, fill=(30, 30, 46, 255))
    cx, cy = size // 2, size // 2 + size // 25
    bw, bh = int(size * 0.5), int(size * 0.38)
    body = [cx - bw // 2, cy - bh // 2, cx + bw // 2, cy + bh // 2]
    d.rounded_rectangle(body, radius=size // 18, fill=(36, 36, 56, 255), outline=(137, 180, 250, 255),
                         width=max(2, size // 26))
    shackle = [cx - size // 6, cy - bh // 2 - size // 4, cx + size // 6, cy - bh // 2 + size // 13]
    d.arc(shackle, start=180, end=360, fill=(137, 180, 250, 255), width=max(2, size // 20))
    d.ellipse([cx - size // 24 - 2, cy - size // 18, cx + size // 24 + 2, cy + size // 18], fill=(137, 180, 250, 255))
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

        self.data = load_data()
        self.selected_category = ALL_CATEGORY
        self._log_queue = queue.Queue()
        self._main_thread_queue = queue.Queue()
        self._hotkey_listener = None
        self._tray_icon = None

        self._build_style()
        self._build_layout()
        self._refresh_categories()
        self._refresh_list()
        self.after(150, self._drain_log_queue)
        self._log("Command Vault ready.")

        self.protocol("WM_DELETE_WINDOW", self._on_close_request)
        self._rebuild_hotkey_listener()

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
    app = CommandVault()
    app.mainloop()
