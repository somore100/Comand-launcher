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
WEB_STEP_TYPES = {
    "goto": {
        "label": "Open a web page",
        "fields": [("url", "Web address", "text", "https://example.com")],
        "describe": "Open {url}",
    },
    "click": {
        "label": "Click a button or link",
        "fields": [("target", "Its text (or selector)", "text", "Start")],
        "uses_by": True, "uses_alt": True,
        "describe": "Click “{target}”",
    },
    "fill": {
        "label": "Type into a box",
        "fields": [("target", "Box label / placeholder (or selector)", "text", "Email"),
                   ("value", "Text to type", "text", "")],
        "uses_by": True, "uses_alt": True,
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

# Steps for desktop programs (Linux/X11, via xdotool)
APP_STEP_TYPES = {
    "launch": {
        "label": "Start a program",
        "fields": [("command", "Program or command", "text", "firefox")],
        "describe": "Start {command}",
    },
    "wait_window": {
        "label": "Wait for a window to appear",
        "fields": [("target", "Window title contains", "text", "Firefox")],
        "uses_alt": True,
        "describe": "Wait for a window titled \u201c{target}\u201d",
    },
    "focus_window": {
        "label": "Bring a window to the front",
        "fields": [("target", "Window title contains", "text", "Firefox")],
        "uses_alt": True,
        "describe": "Focus the window \u201c{target}\u201d",
    },
    "keys": {
        "label": "Press keys",
        "fields": [("keys", "Keys (e.g. ctrl+shift+t, Return)", "text", "ctrl+t")],
        "describe": "Press {keys}",
    },
    "type": {
        "label": "Type text",
        "fields": [("text", "Text to type", "text", "")],
        "describe": "Type \u201c{text}\u201d",
    },
    "wait": WEB_STEP_TYPES["wait"],
}

STEP_TYPES = {**WEB_STEP_TYPES, **APP_STEP_TYPES}
KINDS = {"web": ("A website", WEB_STEP_TYPES), "app": ("A desktop program", APP_STEP_TYPES)}

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


def _s(step_type, **kw):
    step = new_step(step_type)
    step.update(kw)
    return step


# Ready-made starting points: kind -> [(name, what it does, steps)]
def get_templates():
    return {
    "web": [
        ("Open a page and click a button",
         "Loads a page and clicks a button or link by its text. Change the address and the button text.",
         [_s("goto", url="https://example.com"),
          _s("click", target="More information", on_fail="retry")]),
        ("Start a game server (Aternos style)",
         "Opens the server page, clicks Start, accepts a possible confirmation, and waits until it says Online. "
         "Log in once with Test run first. Check the site's rules allow automation.",
         [_s("goto", url="https://aternos.org/servers/"),
          _s("click", target="Start", alt="Start server", on_fail="retry", retries=3),
          _s("click", target="Confirm", alt="Yes", on_fail="skip", timeout=20),
          _s("wait_text", text="Online", timeout=300)]),
        ("Log in with saved session, then click",
         "Opens a site that you logged in to once (Test run), waits for a word that only shows when logged in, "
         "then clicks a button.",
         [_s("goto", url="https://example.com/dashboard"),
          _s("wait_text", text="Welcome"),
          _s("click", target="Check in", on_fail="retry")]),
    ],
    "app": [
        ("Open Firefox",
         "Starts Firefox and brings it to the front. To get your last tabs back every time, turn on Firefox "
         "Settings > General > Startup > \"Open previous windows and tabs\".",
         [_s("launch", command="firefox"),
          _s("wait_window", target="Firefox", alt="Mozilla", timeout=30),
          _s("focus_window", target="Firefox", alt="Mozilla", on_fail="skip")]),
        ("Open a program and press keys",
         "Starts a program, waits for its window, then presses a shortcut. Change the program and the keys.",
         [_s("launch", command="gedit"),
          _s("wait_window", target="gedit", timeout=20),
          _s("focus_window", target="gedit"),
          _s("keys", keys="ctrl+n")]),
    ],
}


def new_step(step_type):
    step = {"type": step_type, "on_fail": "stop", "retries": 2, "timeout": 15}
    if STEP_TYPES[step_type].get("uses_by"):
        step["by"] = "text"
    if STEP_TYPES[step_type].get("uses_alt"):
        step["alt"] = ""
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
_THIN_SCRIPT = r'''#!/usr/bin/env python3
"""Generated by Command Vault from the routine "__NAME__".
Change the steps in Command Vault (Edit entry -> Edit steps); edits here are overwritten.
The helpers it uses (cvauto) are documented under the (i) button in Command Vault."""
import json
import sys

sys.path.insert(0, __LIB__)
import cvauto

STEPS = json.loads(__STEPS__)

if __name__ == "__main__":
    sys.exit(cvauto.run_routine(STEPS, kind=__KIND__, show_browser=__SHOW__, fail_shot=__SHOT__))
'''


_RECORDER = r'''#!/usr/bin/env python3
# Command Vault recorder: opens a browser, prints one JSON step per line for
# what you click/type. Close the browser window to stop.
import json
import os
import sys
import time
from playwright.sync_api import sync_playwright

JS = r"""
(() => {
  if (window.__cvRec) return; window.__cvRec = true;
  const rec = (o) => { try { window.cvRecord(JSON.stringify(o)); } catch (e) {} };
  const clean = (t) => (t || '').replace(/\s+/g, ' ').trim().slice(0, 60);
  const cssPath = (el) => {
    if (el.id) return '#' + CSS.escape(el.id);
    const parts = [];
    while (el && el.nodeType === 1 && parts.length < 4) {
      let part = el.tagName.toLowerCase();
      const same = el.parentElement ? Array.from(el.parentElement.children).filter(c => c.tagName === el.tagName) : [];
      if (same.length > 1) part += ':nth-of-type(' + (same.indexOf(el) + 1) + ')';
      parts.unshift(part); el = el.parentElement;
    }
    return parts.join(' > ');
  };
  const fieldStep = (el) => {
    const label = clean((el.labels && el.labels[0] && el.labels[0].innerText) || el.getAttribute('placeholder') || el.getAttribute('aria-label'));
    return label ? {target: label, by: 'text'} : {target: cssPath(el), by: 'selector'};
  };
  const flush = (el) => {
    if (!/^(INPUT|TEXTAREA)$/.test(el.tagName)) return;
    if (['checkbox', 'radio', 'submit', 'button', 'file'].includes(el.type)) return;
    if (el.__cvLast === el.value) return;
    el.__cvLast = el.value;
    const step = Object.assign({type: 'fill', value: el.type === 'password' ? '' : el.value}, fieldStep(el));
    if (el.type === 'password') step.note = 'password';
    rec(step);
  };
  document.addEventListener('click', e => {
    const el = e.target.closest('button,a,[role=button],input[type=submit],input[type=button],label') || e.target;
    if (/^(INPUT|TEXTAREA)$/.test(el.tagName) && !['submit', 'button'].includes(el.type)) return;
    const t = clean(el.innerText || el.value || el.getAttribute('aria-label') || el.title);
    rec(t ? {type: 'click', target: t, by: 'text'} : {type: 'click', target: cssPath(el), by: 'selector'});
  }, true);
  document.addEventListener('change', e => flush(e.target), true);
  document.addEventListener('keydown', e => {
    if (e.key === 'Enter' && /^(INPUT|TEXTAREA)$/.test(e.target.tagName)) { flush(e.target); rec({type: 'press', key: 'Enter'}); }
  }, true);
})();
"""


def emit(obj):
    print(json.dumps(obj), flush=True)


def main():
    profile = os.environ.get("COMMAND_VAULT_BROWSER_PROFILE")
    start = sys.argv[1] if len(sys.argv) > 1 else ""
    with sync_playwright() as pw:
        ctx = (pw.chromium.launch_persistent_context(profile, headless=False) if profile
               else pw.chromium.launch(headless=False).new_context())
        closed = []
        ctx.on("close", lambda *_: closed.append(1))
        ctx.expose_binding("cvRecord", lambda source, payload: emit(json.loads(payload)))
        ctx.add_init_script(JS)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if start:
            emit({"type": "goto", "url": start})
            page.goto(start)
        while not closed:
            try:
                page.wait_for_timeout(300)
            except Exception:
                time.sleep(0.3)
                if not ctx.pages:
                    break
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
    return (_THIN_SCRIPT
            .replace("__NAME__", safe_name)
            .replace("__LIB__", repr(lib_dir()))
            .replace("__STEPS__", repr(json.dumps(steps)))
            .replace("__KIND__", repr(routine.get("kind", "web")))
            .replace("__SHOW__", repr(bool(routine.get("show_browser", True))))
            .replace("__SHOT__", repr(failure_screenshot_path(entry_id))))


def lib_dir():
    """Folder holding cvauto.py, the helper library for routines and for
    hand-written scripts (`sys.path.insert(0, <this folder>)`)."""
    return os.path.join(app_config_dir(), "lib")


def write_lib():
    """(Re)writes cvauto.py so scripts always see the version that matches
    this Command Vault. Returns the file path."""
    from .cvauto_source import SOURCE
    os.makedirs(lib_dir(), exist_ok=True)
    path = os.path.join(lib_dir(), "cvauto.py")
    try:
        with open(path, "r", encoding="utf-8") as f:
            if f.read() == SOURCE:
                return path
    except OSError:
        pass
    with open(path, "w", encoding="utf-8") as f:
        f.write(SOURCE)
    return path


def write_script(entry_id, name, routine):
    write_lib()
    path = routine_script_path(entry_id)
    with open(path, "w", encoding="utf-8") as f:
        f.write(generate_script(entry_id, name, routine))
    os.chmod(path, 0o700)
    return path


def recorder_script_path():
    path = os.path.join(routines_dir(), "recorder.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_RECORDER)
    return path


def recorded_to_steps(items):
    """Turns recorder output (dicts) into routine steps: drops repeated clicks
    on the same thing and fills in default fields."""
    steps = []
    for item in items:
        kind = item.get("type")
        if kind not in WEB_STEP_TYPES:
            continue
        step = new_step(kind)
        for key in ("url", "target", "value", "key", "by"):
            if key in item:
                step[key] = item[key]
        if item.get("note"):
            step["note"] = item["note"]
        if kind == "click" and steps and steps[-1].get("type") == "click" and steps[-1].get("target") == step.get("target"):
            continue
        steps.append(step)
    return steps


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
