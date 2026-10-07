"""autostart -- split out of the former monolithic main.py."""
import os
import sys
from .browser import browser_env_line
from .execution import resolve_exec_command
from .platform_utils import is_linux, is_windows


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
        env_line = browser_env_line(entry)
        if env_line:
            lines.append(env_line)
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
        env_line = browser_env_line(entry)
        if env_line:
            cd_part += env_line + "\n"
        with open(path, "w") as f:
            f.write(f"@echo off\n{cd_part}{exec_cmd}\n")


# ---------------------------------------------------------------------------
