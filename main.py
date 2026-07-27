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
    """Command used to relaunch Command Vault itself."""
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



TERMINAL_BUILDERS = [
    lambda cmd: ["cosmic-term", "-e", "bash", "-c", cmd + "; exec bash"],
    lambda cmd: ["gnome-terminal", "--", "bash", "-c", cmd + "; exec bash"],
    lambda cmd: ["konsole", "-e", "bash", "-c", cmd + "; exec bash"],
    lambda cmd: ["xfce4-terminal", "-e", "bash", "-c", cmd + "; exec bash"],
    lambda cmd: ["wt", "cmd", "/k", cmd],
    lambda cmd: ["cmd", "/k", cmd],
]


def run_entry(entry):
    command = entry["command"]
    working_dir = entry.get("working_dir") or None
    run_mode = entry.get("run_mode", "terminal")
    entry_type = entry.get("entry_type", "command")

    if working_dir and not os.path.isdir(working_dir):
        messagebox.showerror("Working directory not found", working_dir)
        return

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

    if run_mode == "silent":
        try:
            subprocess.Popen(
                exec_cmd,
                shell=True,
                cwd=working_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as e:
            messagebox.showerror("Failed to launch", str(e))
        return

    for builder in TERMINAL_BUILDERS:
        try:
            subprocess.Popen(builder(exec_cmd), cwd=working_dir)
            return
        except FileNotFoundError:
            continue

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

        browse_frame = tk.Frame(self, bg=COLOR_BG)
        browse_frame.grid(row=6, column=0, columnspan=2, sticky="w", padx=16, pady=(4, 0))
        tk.Button(browse_frame, text="Browse for file...", command=self._browse_command, bg=COLOR_PANEL,
                  fg=COLOR_TEXT, relief="flat", font=FONT_SMALL, padx=8).pack(side="left")
        tk.Label(browse_frame, text=".sh / .bat / .ps1 / .py files auto-run with the right interpreter",
                  bg=COLOR_BG, fg=COLOR_SUBTEXT, font=("Segoe UI", 8)).pack(side="left", padx=(8, 0))

        # Working directory
        label("Working Directory (optional)").grid(row=7, column=0, columnspan=2, sticky="w", **pad)
        wd_frame = tk.Frame(self, bg=COLOR_BG)
        wd_frame.grid(row=8, column=0, columnspan=2, sticky="we", padx=16)
        self.wd_var = tk.StringVar(value=entry["working_dir"] if entry else "")
        tk.Entry(wd_frame, textvariable=self.wd_var, width=38, font=FONT_NORMAL, bg=COLOR_PANEL, fg=COLOR_TEXT,
                  insertbackground=COLOR_TEXT, relief="flat").pack(side="left", fill="x", expand=True)
        tk.Button(wd_frame, text="Browse", command=self._browse_dir, bg=COLOR_ACCENT_DIM, fg=COLOR_TEXT,
                  relief="flat", font=FONT_SMALL, padx=8).pack(side="left", padx=(6, 0))

        # Category
        label("Category").grid(row=9, column=0, columnspan=2, sticky="w", **pad)
        self.category_var = tk.StringVar(value=entry["category"] if entry else (categories[0] if categories else UNCATEGORIZED))
        cat_values = categories if categories else [UNCATEGORIZED]
        self.category_combo = ttk.Combobox(self, textvariable=self.category_var, values=cat_values, width=34,
                                            font=FONT_NORMAL)
        self.category_combo.grid(row=10, column=0, columnspan=2, sticky="we", padx=16)

        # Run mode
        label("Run Mode").grid(row=11, column=0, columnspan=2, sticky="w", **pad)
        self.mode_var = tk.StringVar(value=entry["run_mode"] if entry else "terminal")
        mode_frame = tk.Frame(self, bg=COLOR_BG)
        mode_frame.grid(row=12, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 4))
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
        autostart_frame.grid(row=13, column=0, columnspan=2, sticky="w", padx=16, pady=(4, 10))
        tk.Checkbutton(autostart_frame, text="Run this automatically when the computer starts",
                        variable=self.autostart_var, bg=COLOR_BG, fg=COLOR_TEXT, selectcolor=COLOR_PANEL,
                        activebackground=COLOR_BG, activeforeground=COLOR_TEXT, font=FONT_SMALL
                        ).pack(anchor="w")
        tk.Label(autostart_frame,
                 text="Runs on its own via the OS startup mechanism \u2014 works even if Command Vault isn't set to autostart.",
                 bg=COLOR_BG, fg=COLOR_SUBTEXT, font=("Segoe UI", 8), wraplength=380, justify="left"
                 ).pack(anchor="w")

        # Buttons
        btn_frame = tk.Frame(self, bg=COLOR_BG)
        btn_frame.grid(row=14, column=0, columnspan=2, sticky="we", padx=16, pady=(6, 16))
        tk.Button(btn_frame, text="Cancel", command=self._cancel, bg=COLOR_PANEL, fg=COLOR_TEXT,
                  relief="flat", font=FONT_NORMAL, padx=14, pady=4).pack(side="right")
        tk.Button(btn_frame, text="Save", command=self._save, bg=COLOR_ACCENT, fg=COLOR_SIDEBAR,
                  relief="flat", font=("Segoe UI", 10, "bold"), padx=14, pady=4).pack(side="right", padx=(0, 8))

        self._sync_command_widget()
        name_entry.focus_set()

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

        tk.Button(self, text="Close", command=self.destroy, bg=COLOR_PANEL, fg=COLOR_TEXT,
                  relief="flat", padx=14, pady=4).pack(pady=(0, 16))

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
# Main application
# ---------------------------------------------------------------------------
class CommandVault(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Command Vault")
        self.geometry("860x540")
        self.minsize(700, 440)
        self.configure(bg=COLOR_BG)

        self.data = load_data()
        self.selected_category = ALL_CATEGORY

        self._build_style()
        self._build_layout()
        self._refresh_categories()
        self._refresh_list()

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
        action_bar.pack(fill="x", padx=20, pady=(0, 20))

        tk.Button(action_bar, text="\u25B6 Run", command=self._run_selected, bg=COLOR_GREEN, fg=COLOR_SIDEBAR,
                  font=("Segoe UI", 10, "bold"), relief="flat", padx=16, pady=6).pack(side="left")
        tk.Button(action_bar, text="Edit", command=self._edit_selected, bg=COLOR_PANEL, fg=COLOR_TEXT,
                  font=FONT_NORMAL, relief="flat", padx=16, pady=6).pack(side="left", padx=(8, 0))
        tk.Button(action_bar, text="Delete", command=self._delete_selected, bg=COLOR_PANEL, fg=COLOR_RED,
                  font=FONT_NORMAL, relief="flat", padx=16, pady=6).pack(side="left", padx=(8, 0))

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
        for i, cmd in enumerate(self._visible_commands()):
            mode_label = "Silent" if cmd.get("run_mode") == "silent" else "Terminal"
            if cmd.get("entry_type") == "appimage":
                mode_label += " \u00b7 AppImage"
            boot_label = "\u2713" if cmd.get("autostart") else ""
            tag = "even" if i % 2 else "odd"
            self.tree.insert("", tk.END, iid=cmd["id"],
                              values=(cmd.get("icon", DEFAULT_ICON), cmd["name"], cmd["category"], mode_label,
                                      boot_label),
                              tags=(tag,))

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
            self._refresh_categories()
            self._refresh_list()

    def _run_selected(self):
        entry = self._get_selected_entry()
        if not entry:
            messagebox.showinfo("No selection", "Select an entry to run first.")
            return
        run_entry(entry)


if __name__ == "__main__":
    app = CommandVault()
    app.mainloop()
