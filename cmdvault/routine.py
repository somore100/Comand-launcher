"""routine -- no-code "web routines": a list of simple steps (open a page, click
a button, type text, wait...) that Command Vault turns into a Playwright script.

Why a generated script: the result is an ordinary entry command, so Run,
autostart and scheduling (headless, unattended) all work with no new machinery,
and the user can still open the script to see what it does.

Each step has an "If this fails" policy so a changed page doesn't just crash the
run: stop (report which step failed, with a screenshot), skip, or retry. A step
can also name an alternative thing to look for, tried when the first one isn't
found. Passwords never go in a routine: log in once by hand with the entry's
persistent browser profile ("Test run" shows the browser) and the cookies are
reused by later runs.
"""
import json
import os
import shutil
import subprocess
import sys
from .data import app_config_dir
from .platform_utils import is_windows

# What each step type needs. Drives the editor form, validation and the text
# shown in the step list. field kinds: text | choice | number
STEP_TYPES = {
    "goto": {
        "label": "Open a web page",
        "fields": [("url", "Web address", "text", "https://example.com")],
        "describe": "Open {url}",
    },
    "click": {
        "label": "Click a button or link",
        "fields": [("target", "Its text (or selector)", "text", "Start")],
        "uses_by": True,
        "describe": "Click “{target}”",
    },
    "fill": {
        "label": "Type into a box",
        "fields": [("target", "Box label / placeholder (or selector)", "text", "Email"),
                   ("value", "Text to type", "text", "")],
        "uses_by": True,
        "describe": "Type “{value}” into “{target}”",
    },
    "press": {
        "label": "Press a key",
        "fields": [("key", "Key", "text", "Enter")],
        "describe": "Press {key}",
    },
    "wait_text": {
        "label": "Wait until text shows up",
        "fields": [("text", "Text to wait for", "text", "Online")],
        "describe": "Wait for “{text}”",
    },
    "wait": {
        "label": "Wait a few seconds",
        "fields": [("seconds", "Seconds", "number", "5")],
        "describe": "Wait {seconds} s",
    },
}

ON_FAIL_CHOICES = {
    "stop": "Stop and report the problem",
    "skip": "Skip it and carry on",
    "retry": "Try again, then stop",
}

BY_CHOICES = {"text": "Visible text", "selector": "CSS selector (advanced)"}

EXAMPLE_STEPS = [
    {"type": "goto", "url": "https://example.com"},
    {"type": "click", "target": "More information", "by": "text", "on_fail": "retry", "retries": 2},
    {"type": "wait", "seconds": 3},
]


def new_step(step_type):
    step = {"type": step_type, "on_fail": "stop", "retries": 2, "timeout": 15}
    if STEP_TYPES[step_type].get("uses_by"):
        step["by"] = "text"
    for key, _label, kind, default in STEP_TYPES[step_type]["fields"]:
        step[key] = default if kind != "number" else float(default or 0)
    return step


def describe_step(step):
    spec = STEP_TYPES.get(step.get("type"))
    if not spec:
        return f"(unknown step {step.get('type')!r})"
    values = {k: step.get(k, "") for k, *_ in spec["fields"]}
    text = spec["describe"].format(**values)
    if step.get("seconds") is not None and step["type"] == "wait":
        s = step["seconds"]
        text = f"Wait {int(s) if float(s).is_integer() else s} s"
    extras = []
    if step.get("alt"):
        extras.append(f"or “{step['alt']}”")
    if step.get("on_fail") == "skip":
        extras.append("optional")
    elif step.get("on_fail") == "retry":
        extras.append(f"retry {step.get('retries', 2)}×")
    return text + (f"   ({', '.join(extras)})" if extras else "")


def validate_step(step):
    """Error message for an incomplete step, or ''."""
    spec = STEP_TYPES.get(step.get("type"))
    if not spec:
        return "Unknown step type."
    for key, label, kind, _d in spec["fields"]:
        val = step.get(key)
        if kind == "number":
            try:
                if float(val) < 0:
                    return f"{label} can't be negative."
            except (TypeError, ValueError):
                return f"{label} must be a number."
        elif key != "value" and not str(val or "").strip():
            return f"Please fill in: {label}."
    if step.get("type") == "goto":
        url = step["url"].strip()
        if not url.lower().startswith(("http://", "https://")):
            return "The web address must start with http:// or https://"
    return ""


def validate_steps(steps):
    if not steps:
        return "Add at least one step."
    for i, step in enumerate(steps, 1):
        err = validate_step(step)
        if err:
            return f"Step {i}: {err}"
    return ""


# ---------------------------------------------------------------------------
# Script generation
# ---------------------------------------------------------------------------
_SCRIPT = r'''#!/usr/bin/env python3
"""Generated by Command Vault from the routine "__NAME__".
Change the steps in Command Vault (Edit entry -> Edit steps); edits here are overwritten."""
import json
import os
import sys
import time

STEPS = json.loads(__STEPS__)
SHOW_BROWSER = __SHOW__
FAIL_SHOT = __FAILSHOT__


def locate(page, by, target):
    if by == "selector":
        return page.locator(target).first
    return (page.get_by_role("button", name=target)
            .or_(page.get_by_role("link", name=target))
            .or_(page.get_by_text(target))).first


def locate_field(page, by, target):
    if by == "selector":
        return page.locator(target).first
    return page.get_by_label(target).or_(page.get_by_placeholder(target)).first


def do_step(page, step, target):
    kind = step["type"]
    ms = int(float(step.get("timeout", 15)) * 1000)
    if kind == "goto":
        page.goto(step["url"], timeout=ms * 2)
    elif kind == "click":
        loc = locate(page, step.get("by", "text"), target)
        loc.wait_for(state="visible", timeout=ms)
        loc.click(timeout=ms)
    elif kind == "fill":
        loc = locate_field(page, step.get("by", "text"), target)
        loc.wait_for(state="visible", timeout=ms)
        loc.fill(step.get("value", ""), timeout=ms)
    elif kind == "press":
        page.keyboard.press(step["key"])
    elif kind == "wait_text":
        page.get_by_text(step["text"]).first.wait_for(state="visible", timeout=ms)
    elif kind == "wait":
        time.sleep(float(step.get("seconds", 1)))
    else:
        raise ValueError("unknown step type " + str(kind))


def run_step(page, step):
    """(ok, error). Tries the main target, then the alternative, and repeats
    the whole thing when the step says to retry."""
    targets = [step.get("target")]
    if step.get("alt"):
        targets.append(step["alt"])
    rounds = 1 + (int(step.get("retries", 2)) if step.get("on_fail") == "retry" else 0)
    error = None
    for n in range(rounds):
        for target in targets:
            try:
                do_step(page, step, target)
                return True, None
            except Exception as exc:  # noqa: BLE001 - report whatever went wrong
                error = exc
        if n < rounds - 1:
            time.sleep(2)
    return False, error


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright isn't installed. In Command Vault: Edit entry -> Edit steps -> Set up browser automation.")
        return 2
    profile = os.environ.get("COMMAND_VAULT_BROWSER_PROFILE")
    has_display = sys.platform in ("win32", "darwin") or os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    headless = not (SHOW_BROWSER and has_display)
    with sync_playwright() as pw:
        try:
            if profile:
                ctx = pw.chromium.launch_persistent_context(profile, headless=headless)
            else:
                ctx = pw.chromium.launch(headless=headless).new_context()
        except Exception as exc:  # noqa: BLE001
            print("Couldn't start the browser (is another run using the same profile?): " + str(exc).splitlines()[0])
            return 3
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        total = len(STEPS)
        for i, step in enumerate(STEPS, 1):
            print("[%d/%d] %s" % (i, total, step.get("desc", step["type"])), flush=True)
            ok, error = run_step(page, step)
            if ok:
                continue
            first_line = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
            if step.get("on_fail") == "skip":
                print("    skipped (not found): " + first_line, flush=True)
                continue
            print("FAILED at step %d: %s" % (i, step.get("desc", step["type"])))
            print("    " + first_line)
            try:
                os.makedirs(os.path.dirname(FAIL_SHOT), exist_ok=True)
                page.screenshot(path=FAIL_SHOT)
                print("    Screenshot of the page: " + FAIL_SHOT)
            except Exception:  # noqa: BLE001
                pass
            ctx.close()
            return 1
        ctx.close()
    print("Routine finished.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def routines_dir():
    d = os.path.join(app_config_dir(), "routines")
    os.makedirs(d, exist_ok=True)
    return d


def routine_script_path(entry_id):
    return os.path.join(routines_dir(), f"{entry_id}.py")


def failure_screenshot_path(entry_id):
    return os.path.join(app_config_dir(), "run-status", f"{entry_id}-failure.png")


def generate_script(entry_id, name, routine):
    """The full Python source for a routine {'steps': [...], 'show_browser': bool}."""
    steps = []
    for step in routine["steps"]:
        s = dict(step)
        s["desc"] = describe_step(step)
        steps.append(s)
    safe_name = name.replace('"', "'").replace("\\", "/").replace("\n", " ")
    return (_SCRIPT
            .replace("__NAME__", safe_name)
            .replace("__STEPS__", repr(json.dumps(steps)))
            .replace("__SHOW__", repr(bool(routine.get("show_browser", True))))
            .replace("__FAILSHOT__", repr(failure_screenshot_path(entry_id))))


def write_script(entry_id, name, routine):
    path = routine_script_path(entry_id)
    with open(path, "w", encoding="utf-8") as f:
        f.write(generate_script(entry_id, name, routine))
    os.chmod(path, 0o700)
    return path


def routine_command(entry_id):
    """The shell command an entry runs to execute its routine."""
    return f'"{automation_python() or "python3"}" "{routine_script_path(entry_id)}"'


# ---------------------------------------------------------------------------
# One-click setup of the browser-automation environment
# ---------------------------------------------------------------------------
def automation_env_dir():
    return os.path.join(app_config_dir(), "automation-venv")


def automation_python():
    """The venv's python if automation has been set up, else None."""
    exe = os.path.join(automation_env_dir(), "Scripts" if is_windows() else "bin",
                       "python.exe" if is_windows() else "python")
    return exe if os.path.isfile(exe) else None


def _system_python():
    for name in (("py", "python") if is_windows() else ("python3", "python")):
        found = shutil.which(name)
        if found:
            return found
    return None


def setup_automation(log=print):
    """Creates the venv, installs Playwright and downloads Chromium (~150 MB).
    Blocking; run it in a thread. Returns (ok, message)."""
    base = _system_python()
    if not base:
        return False, "Python 3 wasn't found on this computer. Install Python 3 first."
    env_dir = automation_env_dir()

    def run(cmd, what):
        log(what + "...")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            tail = (res.stderr or res.stdout).strip().splitlines()[-3:]
            raise RuntimeError(what + " failed: " + " ".join(tail))

    try:
        if not automation_python():
            run([base, "-m", "venv", env_dir], "Creating a private Python environment")
        py = automation_python()
        if not py:
            return False, "The environment was created but its Python wasn't found."
        run([py, "-m", "pip", "install", "--quiet", "--upgrade", "pip", "playwright"], "Installing Playwright")
        run([py, "-m", "playwright", "install", "chromium"], "Downloading the browser (about 150 MB)")
    except (RuntimeError, OSError) as e:
        return False, str(e)
    return True, "Browser automation is ready."
