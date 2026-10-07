"""execution -- split out of the former monolithic main.py."""
import os
from .platform_utils import is_windows


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
