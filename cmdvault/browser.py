"""browser -- persistent browser-profile support for automation-bot entries.

A Playwright/Selenium script that launches a fresh browser every run has to
log in every run. With "Persistent browser profile" ticked on an entry,
Command Vault creates a profile folder for that entry and hands its path to
the script in the COMMAND_VAULT_BROWSER_PROFILE environment variable, so the
script can reuse cookies/logins between runs, e.g. in Python/Playwright:

    ctx = p.chromium.launch_persistent_context(
        os.environ["COMMAND_VAULT_BROWSER_PROFILE"], headless=True)

The variable is injected the same way for every way an entry can run
(Run button in either mode, autostart, and scheduled runs), by prefixing the
shell command / wrapper script rather than relying on process environment
inheritance (terminal emulators like gnome-terminal don't pass it along).
"""
import os
import shlex
from .platform_utils import is_mac, is_windows

BROWSER_PROFILE_ENV = "COMMAND_VAULT_BROWSER_PROFILE"


def browser_profiles_root():
    """Default parent folder for per-entry profiles. Kept outside the
    (user-relocatable, exportable) data folder: profiles can be large and
    hold live login sessions, so they shouldn't travel with vault exports."""
    if is_windows():
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "CommandVault", "browser-profiles")
    if is_mac():
        return os.path.expanduser("~/Library/Application Support/CommandVault/browser-profiles")
    return os.path.expanduser("~/.local/share/command-vault/browser-profiles")


def default_profile_dir(entry_id):
    return os.path.join(browser_profiles_root(), entry_id)


def browser_profile_path(entry):
    """The profile folder this entry should use, or None if the feature is
    off for it. Pure (no filesystem access)."""
    if not entry.get("browser_profile"):
        return None
    custom = (entry.get("browser_profile_dir") or "").strip()
    if custom:
        return os.path.abspath(os.path.expanduser(custom))
    return default_profile_dir(entry["id"])


def ensure_browser_profile_dir(entry):
    """Creates the profile folder (owner-only, it holds login cookies) and
    returns its path, or None if the feature is off. Raises OSError if the
    folder can't be created."""
    path = browser_profile_path(entry)
    if path:
        os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def browser_env_line(entry):
    """One shell line setting the env var (for wrapper scripts), creating the
    profile folder as a side effect. '' when the feature is off."""
    path = ensure_browser_profile_dir(entry)
    if not path:
        return ""
    if is_windows():
        return f'set "{BROWSER_PROFILE_ENV}={path}"'
    return f"export {BROWSER_PROFILE_ENV}={shlex.quote(path)}"


def prefix_exec_cmd(entry, exec_cmd):
    """exec_cmd with the env var set in front of it, for single-string
    launches (terminal/silent Run). Unchanged when the feature is off."""
    line = browser_env_line(entry)
    if not line:
        return exec_cmd
    return f"{line} && {exec_cmd}" if is_windows() else f"{line}; {exec_cmd}"
