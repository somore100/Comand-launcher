"""updates -- split out of the former monolithic main.py."""
import json
import threading
import time
import urllib.request
import urllib.error
from .config import APP_NAME, APP_VERSION, GITHUB_REPO
from .data import _load_config, _save_config


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
