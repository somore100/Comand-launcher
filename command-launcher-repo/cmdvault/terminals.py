"""terminals -- split out of the former monolithic main.py."""
from tkinter import messagebox
import os
import shlex
import subprocess
import threading
from .browser import prefix_exec_cmd
from .data import _load_config
from .execution import resolve_exec_command
from .placeholders import PlaceholderDialog, extract_placeholders, fill_placeholders


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

    try:
        exec_cmd = prefix_exec_cmd(entry, exec_cmd)
    except OSError as e:
        messagebox.showerror("Browser profile folder", f"Couldn't create the browser profile folder:\n{e}")
        return

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
