"""runstatus -- record and read the outcome of unattended (scheduled) runs.

A scheduled run happens with no window and nobody watching, so a bot that
starts failing would otherwise fail silently forever. The wrapper script the
OS scheduler runs captures the entry's output to a per-entry log and writes a
tiny per-entry status file when it finishes; the app reads those to show a
warning marker, log failures to the console, and show the last run's output.

Status file format (plain text so a bash or cmd.exe wrapper can write it):
    line 1: the exit code (integer)
    line 2: finish time as human-readable local time
"""
import os
import shlex
from .data import app_config_dir

MAX_LOG_BYTES = 64 * 1024


def run_status_dir():
    return os.path.join(app_config_dir(), "run-status")


def status_path(entry_id):
    return os.path.join(run_status_dir(), f"{entry_id}.status")


def log_path(entry_id):
    return os.path.join(run_status_dir(), f"{entry_id}.log")


def read_run_status(entry_id):
    """{'exit_code', 'when', 'mtime', 'failed'} for the entry's last recorded
    scheduled run, or None if there isn't one (or the file is unreadable)."""
    path = status_path(entry_id)
    try:
        mtime = os.path.getmtime(path)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        code = int(lines[0].strip())
    except (OSError, ValueError, IndexError):
        return None
    return {
        "exit_code": code,
        "when": lines[1].strip() if len(lines) > 1 else "",
        "mtime": mtime,
        "failed": code != 0,
    }


def read_run_log_tail(entry_id, max_bytes=MAX_LOG_BYTES):
    try:
        with open(log_path(entry_id), "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def clear_run_status(entry_id):
    for p in (status_path(entry_id), log_path(entry_id)):
        try:
            os.remove(p)
        except OSError:
            pass


def posix_status_wrapper(entry_id, body_lines):
    """Script lines (bash) that run `body_lines` in a subshell with output
    captured to the entry's log, then record the exit code. A subshell, so a
    body that calls `exit N` (or fails its `cd`) still gets recorded."""
    d = shlex.quote(run_status_dir())
    log = shlex.quote(log_path(entry_id))
    status = shlex.quote(status_path(entry_id))
    return [
        f"mkdir -p {d}",
        "(",
        *body_lines,
        f") > {log} 2>&1",
        "cv_rc=$?",
        f'{{ echo "$cv_rc"; date "+%Y-%m-%d %H:%M:%S"; }} > {status}',
        f"tail -c {MAX_LOG_BYTES} {log} > {log}.tmp && mv {log}.tmp {log}",
        'exit "$cv_rc"',
    ]


def windows_status_wrapper(entry_id, body_lines):
    """Batch-file lines doing the same. The body lives in a labelled
    subroutine rather than a ( ) block, so a stray ')' in a command can't
    break the script."""
    log = log_path(entry_id)
    status = status_path(entry_id)
    return [
        f'if not exist "{run_status_dir()}" mkdir "{run_status_dir()}"',
        f'call :cv_body > "{log}" 2>&1',
        "set CV_RC=%ERRORLEVEL%",
        f'> "{status}" echo %CV_RC%',
        f'>> "{status}" echo %date% %time%',
        "exit /b %CV_RC%",
        ":cv_body",
        *body_lines,
        "exit /b %ERRORLEVEL%",
    ]
