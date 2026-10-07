"""scheduling -- split out of the former monolithic main.py."""
import os
import subprocess
from .browser import browser_env_line
from .execution import resolve_exec_command
from .platform_utils import is_windows
from .runstatus import clear_run_status, posix_status_wrapper, windows_status_wrapper


# Per-entry scheduling (run daily or on chosen weekdays, at a specific time)
# ---------------------------------------------------------------------------
# Same philosophy as autostart above: generate a small, self-contained
# wrapper script per entry and register it with whatever OS mechanism
# actually runs unattended jobs, rather than depending on Command Vault's
# own process being open at the scheduled moment -- an in-app timer loop
# would only fire while the app/tray happens to be running, which quietly
# defeats the point for anything meant to run overnight. Linux and macOS
# both ship `cron`, so one codepath covers both; Windows uses Task
# Scheduler (`schtasks`).
#
# On Linux/macOS this reads and rewrites the user's crontab -- but never
# wholesale. Every line Command Vault adds carries a unique per-entry
# marker comment at the end (`# command-vault-schedule:<id>`), and the
# read/modify/write cycle only ever touches lines carrying that marker,
# leaving every other line in the user's crontab -- their own jobs --
# untouched. (A trailing `#...` on a cron job line is itself just a shell
# comment to whatever runs the command, so it's inert at execution time
# and only serves as a tag for us to find our own line again later.)

CRON_WEEKDAY_CODES = {"SU": 0, "MO": 1, "TU": 2, "WE": 3, "TH": 4, "FR": 5, "SA": 6}
SCHEDULE_WEEKDAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def linux_schedule_scripts_dir():
    d = os.path.expanduser("~/.config/command-vault/schedule-scripts")
    os.makedirs(d, exist_ok=True)
    return d


def windows_schedule_scripts_dir():
    appdata = os.getenv("APPDATA", "")
    d = os.path.join(appdata, "CommandVault", "schedule-scripts")
    os.makedirs(d, exist_ok=True)
    return d


def _cron_marker(entry_id):
    return f"# command-vault-schedule:{entry_id}"


def _build_cron_schedule_line(entry, script_path):
    """Pure line-building, kept separate from subprocess/crontab I/O so it's
    unit-testable without a real cron installation. schedule_days uses the
    same "empty list = every day" convention as the rest of the app."""
    hh, mm = entry["schedule_time"].split(":")
    days = entry.get("schedule_days") or []
    dow = ",".join(str(CRON_WEEKDAY_CODES[d]) for d in days) if days else "*"
    return f'{int(mm)} {int(hh)} * * {dow} bash "{script_path}" {_cron_marker(entry["id"])}'


def _cron_lines_without_marker(lines, entry_id):
    """Pure filter: every crontab line EXCEPT the one (if any) owned by this
    entry. Used both to remove a schedule and, remove-then-append, to
    replace one -- so an edited schedule never leaves a stale second line
    for the same entry behind."""
    marker = _cron_marker(entry_id)
    return [line for line in lines if marker not in line]


def _schtasks_create_args(entry, script_path):
    """Pure arg-list building for the Windows Task Scheduler path, kept
    separate from subprocess.run so the args themselves are testable on
    any OS even though schtasks itself only exists on Windows."""
    hh, mm = entry["schedule_time"].split(":")
    days = entry.get("schedule_days") or []
    task_name = f"CommandVault-{entry['id']}"
    base = ["schtasks", "/create", "/tn", task_name, "/tr", f'"{script_path}"', "/f"]
    if days:
        return base + ["/sc", "WEEKLY", "/d", ",".join(days), "/st", f"{hh}:{mm}"]
    return base + ["/sc", "DAILY", "/st", f"{hh}:{mm}"]


def _read_crontab_lines():
    """Returns (lines, crontab_available). crontab_available is False only
    if the `crontab` command itself couldn't be run at all (not installed)
    -- distinct from "no crontab for this user yet", which is a normal
    empty starting point, not an error, and still returns True."""
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    except OSError:
        return [], False
    if result.returncode != 0:
        return [], True  # typically "no crontab for <user>" -- fine, empty is correct
    return result.stdout.splitlines(), True


def _write_crontab_lines(lines):
    try:
        text = "\n".join(lines)
        if text:
            text += "\n"
        subprocess.run(["crontab", "-"], input=text, text=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def entry_schedule_registered(entry_id):
    """Whether entry_id currently has a schedule actually registered with
    the OS -- the source of truth, the same role entry_autostart_enabled()
    plays for autostart, independent of the schedule_enabled JSON field
    (which just records what the dialog last showed)."""
    if is_windows():
        try:
            result = subprocess.run(
                ["schtasks", "/query", "/tn", f"CommandVault-{entry_id}"],
                capture_output=True, text=True
            )
            return result.returncode == 0
        except OSError:
            return False
    lines, available = _read_crontab_lines()
    if not available:
        return False
    return any(_cron_marker(entry_id) in line for line in lines)


def set_entry_schedule(entry, enabled):
    entry_id = entry["id"]

    if is_windows():
        task_name = f"CommandVault-{entry_id}"
        script_path = os.path.join(windows_schedule_scripts_dir(), f"cv-{entry_id}.bat")
        if not enabled:
            subprocess.run(["schtasks", "/delete", "/tn", task_name, "/f"], capture_output=True)
            if os.path.exists(script_path):
                os.remove(script_path)
            clear_run_status(entry_id)
            return

        exec_cmd = resolve_exec_command(entry["command"])
        working_dir = entry.get("working_dir") or ""
        body = []
        if working_dir:
            body.append(f'cd /d "{working_dir}"')
        env_line = browser_env_line(entry)
        if env_line:
            body.append(env_line)
        body.append(f"call {exec_cmd}")
        with open(script_path, "w") as f:
            f.write("@echo off\n" + "\n".join(windows_status_wrapper(entry_id, body)) + "\n")

        try:
            subprocess.run(_schtasks_create_args(entry, script_path), check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError) as e:
            raise RuntimeError(f"Couldn't register the scheduled task: {e}") from e
        return

    # Linux / macOS, via cron
    script_path = os.path.join(linux_schedule_scripts_dir(), f"cv-{entry_id}.sh")
    if not enabled:
        if os.path.exists(script_path):
            os.remove(script_path)
        clear_run_status(entry_id)
        lines, available = _read_crontab_lines()
        if not available:
            return
        new_lines = _cron_lines_without_marker(lines, entry_id)
        if new_lines != lines:
            _write_crontab_lines(new_lines)
        return

    exec_cmd = resolve_exec_command(entry["command"])
    working_dir = entry.get("working_dir") or ""
    body = []
    if working_dir:
        body.append(f'cd "{working_dir}" || exit 1')
    env_line = browser_env_line(entry)
    if env_line:
        body.append(env_line)
    body.append(exec_cmd)
    with open(script_path, "w") as f:
        f.write("\n".join(["#!/bin/bash"] + posix_status_wrapper(entry_id, body)) + "\n")
    os.chmod(script_path, 0o755)

    lines, available = _read_crontab_lines()
    if not available:
        raise NotImplementedError(
            "Scheduling needs the 'crontab' command, which isn't available on this system."
        )
    lines = _cron_lines_without_marker(lines, entry_id)
    lines.append(_build_cron_schedule_line(entry, script_path))
    if not _write_crontab_lines(lines):
        raise RuntimeError("Couldn't update the crontab. Check that cron is set up for your user.")


# ---------------------------------------------------------------------------
