"""execution -- split out of the former monolithic main.py."""
import os
from .platform_utils import is_linux, is_mac, is_windows


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


# Program entries: an app file rather than a typed command
# ---------------------------------------------------------------------------
PROGRAM_HINT = {
    "linux": "Program path (AppImage, binary or .desktop file)",
    "mac": "App path (.app) or program",
    "windows": "Program path (.exe, .lnk or .bat)",
}


def program_type_label():
    if is_windows():
        return "Program (.exe)"
    if is_mac():
        return "App (.app)"
    return "AppImage / program"


def program_path_hint():
    return PROGRAM_HINT["windows" if is_windows() else "mac" if is_mac() else "linux"]


def is_program_path(path):
    """True when `path` is something a Program entry can run: a file, or a
    macOS .app bundle (a folder)."""
    path = (path or "").strip()
    return os.path.isfile(path) or (path.lower().endswith(".app") and os.path.isdir(path))


def looks_like_program(path):
    return (path or "").lower().endswith((".appimage", ".exe", ".lnk", ".app", ".desktop", ".msi"))


def program_command(path):
    """The shell command that launches a Program entry's path."""
    path = path.strip()
    low = path.lower()
    if is_mac() and low.endswith(".app"):
        return f'open "{path}"'
    if is_windows() and low.endswith((".lnk", ".url", ".msi")):
        return f'start "" "{path}"'
    if is_linux() and low.endswith(".desktop"):
        return f'gio launch "{path}"'
    return f'"{path}"'
