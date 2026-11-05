"""cvauto_source -- the text of `cvauto.py`, the automation helper library.

Command Vault writes this to a folder (see routine.lib_dir()) so that both the
scripts it generates for routines and hand-written scripts can `import cvauto`.
It is kept as a string, not a normal module, so it also exists in packaged
builds where .py source files aren't shipped.
"""

SOURCE = r'''"""cvauto -- helpers for scripts that drive websites and desktop programs.

Written by Command Vault. Use it from any Python script:

    import sys
    sys.path.insert(0, "<the lib folder shown in Command Vault's info (i) window>")
    import cvauto

Website (needs Playwright; Command Vault's "Set up browser automation" installs it):

    with cvauto.web(show=True) as b:
        b.goto("https://example.com")
        b.click("More information", alt="More info", retries=2)
        b.fill("Email", "me@example.com")
        b.press("Enter")
        b.wait_text("Welcome", timeout=30)
        # b.page is the Playwright page for anything else

Desktop program (Linux/X11 needs xdotool; Windows uses PowerShell; macOS uses
osascript and needs Accessibility permission):

    cvauto.app.launch("firefox")
    cvauto.app.wait_window("Firefox", alt="Mozilla", timeout=30)
    cvauto.app.focus("Firefox")
    cvauto.app.keys("ctrl+t")
    cvauto.app.type_text("hello")
    cvauto.app.wait(2)

Every call raises cvauto.StepError with a plain-language message on failure, so
wrap steps in try/except for your own fallbacks. The "stay logged in" browser
profile of a Command Vault entry is used automatically through the
COMMAND_VAULT_BROWSER_PROFILE environment variable.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

__all__ = ["StepError", "web", "app", "run_routine"]


class StepError(Exception):
    """A step could not be done (not found, timed out, tool missing...)."""


def _first_line(exc):
    text = str(exc).strip()
    return text.splitlines()[0] if text else type(exc).__name__


def _attempt(do, targets, retries=0, pause=2):
    """Calls do(target) for each target until one works; repeats the whole
    round `retries` more times. Raises StepError with the last problem."""
    error = None
    for n in range(retries + 1):
        for target in targets:
            try:
                return do(target)
            except Exception as exc:  # noqa: BLE001 - report whatever went wrong
                error = exc
        if n < retries:
            time.sleep(pause)
    raise StepError(_first_line(error))


# ---------------------------------------------------------------------------
# Websites (Playwright)
# ---------------------------------------------------------------------------
class Web:
    def __init__(self, show=True, profile=None):
        self.show = show
        self.profile = profile or os.environ.get("COMMAND_VAULT_BROWSER_PROFILE")
        self.page = None
        self._pw = self._ctx = None

    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise StepError("Playwright isn't installed. In Command Vault: Edit entry > Edit steps > "
                            "Set up browser automation.")
        has_display = (sys.platform in ("win32", "darwin") or os.environ.get("DISPLAY")
                       or os.environ.get("WAYLAND_DISPLAY"))
        headless = not (self.show and has_display)
        self._pw = sync_playwright().start()
        try:
            if self.profile:
                self._ctx = self._pw.chromium.launch_persistent_context(self.profile, headless=headless)
            else:
                self._ctx = self._pw.chromium.launch(headless=headless).new_context()
        except Exception as exc:  # noqa: BLE001
            self._pw.stop()
            raise StepError("Couldn't start the browser (is another run using the same profile?): "
                            + _first_line(exc))
        self.page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        return self

    def __exit__(self, *exc):
        try:
            self._ctx.close()
        finally:
            self._pw.stop()
        return False

    def _find(self, target, by):
        if by == "selector":
            return self.page.locator(target).first
        return (self.page.get_by_role("button", name=target)
                .or_(self.page.get_by_role("link", name=target))
                .or_(self.page.get_by_text(target))).first

    def _find_field(self, target, by):
        if by == "selector":
            return self.page.locator(target).first
        return self.page.get_by_label(target).or_(self.page.get_by_placeholder(target)).first

    def goto(self, url, timeout=30):
        _attempt(lambda _t: self.page.goto(url, timeout=int(timeout * 1000)), [None])

    def click(self, target, by="text", alt=None, retries=0, timeout=15):
        def do(t):
            loc = self._find(t, by)
            loc.wait_for(state="visible", timeout=int(timeout * 1000))
            loc.click(timeout=int(timeout * 1000))
        _attempt(do, [target] + ([alt] if alt else []), retries)

    def fill(self, target, value, by="text", alt=None, retries=0, timeout=15):
        def do(t):
            loc = self._find_field(t, by)
            loc.wait_for(state="visible", timeout=int(timeout * 1000))
            loc.fill(value, timeout=int(timeout * 1000))
        _attempt(do, [target] + ([alt] if alt else []), retries)

    def press(self, key):
        _attempt(lambda _t: self.page.keyboard.press(key), [None])

    def wait_text(self, text, timeout=15, retries=0):
        _attempt(lambda _t: self.page.get_by_text(text).first.wait_for(state="visible",
                                                                        timeout=int(timeout * 1000)),
                 [None], retries)

    def wait(self, seconds):
        time.sleep(float(seconds))

    def screenshot(self, path):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self.page.screenshot(path=path)
            return True
        except Exception:  # noqa: BLE001
            return False


def web(show=True, profile=None):
    """Context manager: `with cvauto.web() as b:` (see the module docstring)."""
    return Web(show=show, profile=profile)


# ---------------------------------------------------------------------------
# Desktop programs
# ---------------------------------------------------------------------------
_SENDKEYS = {"return": "{ENTER}", "enter": "{ENTER}", "tab": "{TAB}", "escape": "{ESC}", "esc": "{ESC}",
             "delete": "{DEL}", "backspace": "{BS}", "up": "{UP}", "down": "{DOWN}", "left": "{LEFT}",
             "right": "{RIGHT}", "home": "{HOME}", "end": "{END}", "page_up": "{PGUP}", "page_down": "{PGDN}",
             "space": " "}
_MAC_CODES = {"return": 36, "enter": 36, "tab": 48, "space": 49, "escape": 53, "esc": 53, "delete": 51,
              "backspace": 51, "left": 123, "right": 124, "down": 125, "up": 126, "home": 115, "end": 119,
              "page_up": 116, "page_down": 121}
_MAC_FKEYS = {f"f{i}": c for i, c in enumerate([122, 120, 99, 118, 96, 97, 98, 100, 101, 109, 103, 111], 1)}


def parse_keys(combo):
    """'ctrl+shift+t' -> ({'ctrl', 'shift'}, 't')."""
    parts = [p.strip() for p in combo.replace(" ", "").split("+") if p.strip()]
    if not parts:
        raise StepError("No keys given.")
    mods = {"ctrl" if p.lower() in ("ctrl", "control") else p.lower()
            for p in parts[:-1]}
    return mods, parts[-1]


def _ps_quote(text):
    return "'" + text.replace("'", "''") + "'"


def _sendkeys_escape(text):
    return "".join("{" + c + "}" if c in "+^%~(){}[]" else c for c in text)


def _applescript_quote(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


class _App:
    """Desktop-program helpers; the OS-specific parts are small and separate."""

    def _run(self, cmd, **kw):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=kw.pop("timeout", 20), **kw)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise StepError(_first_line(exc))

    # -- helpers per OS ------------------------------------------------------
    def _xdo(self, *args):
        if not shutil.which("xdotool"):
            raise StepError("This needs 'xdotool' (Fedora: sudo dnf install xdotool; Ubuntu/Pop!_OS: "
                            "sudo apt install xdotool) and an X11 desktop session.")
        if not os.environ.get("DISPLAY"):
            raise StepError("No graphical session (DISPLAY is empty). Run this while you're logged in.")
        res = self._run(["xdotool"] + list(args))
        if res.returncode != 0:
            raise StepError((res.stderr or "xdotool failed").strip().splitlines()[0])
        return res.stdout

    def _ps(self, script):
        res = self._run(["powershell", "-NoProfile", "-Command", script])
        if res.returncode != 0:
            raise StepError((res.stderr or "PowerShell failed").strip().splitlines()[0])
        return res.stdout.strip()

    def _osa(self, script):
        res = self._run(["osascript", "-e", script])
        if res.returncode != 0:
            msg = (res.stderr or "osascript failed").strip()
            if "not allowed" in msg or "assistive" in msg.lower():
                msg = ("macOS blocked this. Allow Terminal/Command Vault in System Settings > Privacy & "
                       "Security > Accessibility.")
            raise StepError(msg.splitlines()[0])
        return res.stdout.strip()

    # -- public API ----------------------------------------------------------
    def launch(self, command):
        """Starts a program (any shell command, e.g. 'firefox' or 'open -a Safari')."""
        try:
            subprocess.Popen(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             **({"start_new_session": True} if os.name != "nt" else {}))
        except OSError as exc:
            raise StepError(_first_line(exc))

    def _find(self, title):
        """An OS handle for a visible window whose title contains `title`, or None."""
        if sys.platform.startswith("linux"):
            ids = self._xdo("search", "--onlyvisible", "--name", title).split()
            return ids[-1] if ids else None
        if sys.platform == "win32":
            out = self._ps("Get-Process | Where-Object { $_.MainWindowTitle -like '*' + "
                           + _ps_quote(title) + " + '*' } | Select-Object -First 1 -ExpandProperty Id")
            return out or None
        script = ('set AppleScript\'s text item delimiters to linefeed\n'
                  'tell application "System Events"\n set out to {}\n'
                  ' repeat with p in (every process whose background only is false)\n'
                  '  set pn to name of p\n  set end of out to pn\n'
                  '  try\n   repeat with w in (every window of p)\n'
                  '    set end of out to pn & " | " & (name of w)\n   end repeat\n  end try\n'
                  ' end repeat\n return out as text\nend tell')
        for line in self._osa(script).splitlines():
            if title.lower() in line.lower():
                return line.split(" | ")[0].strip()
        return None

    def wait_window(self, title, alt=None, timeout=15):
        end = time.time() + timeout
        while True:
            for t in [title] + ([alt] if alt else []):
                if self._find(t):
                    return
            if time.time() >= end:
                raise StepError("No window with '%s' in its title appeared in %d seconds." % (title, timeout))
            time.sleep(0.5)

    def focus(self, title, alt=None):
        def do(t):
            handle = self._find(t)
            if not handle:
                raise StepError("No window with '%s' in its title." % t)
            if sys.platform.startswith("linux"):
                self._xdo("windowactivate", "--sync", handle)
            elif sys.platform == "win32":
                self._ps("Add-Type -AssemblyName Microsoft.VisualBasic; "
                         "[Microsoft.VisualBasic.Interaction]::AppActivate(%s)" % int(handle))
            else:
                self._osa('tell application "System Events" to set frontmost of process %s to true'
                          % _applescript_quote(handle))
        _attempt(do, [title] + ([alt] if alt else []))

    def keys(self, combo):
        """Press a shortcut, e.g. 'ctrl+shift+t', 'alt+F4', 'Return'."""
        mods, key = parse_keys(combo)
        if sys.platform.startswith("linux"):
            self._xdo("key", "--clearmodifiers", combo.replace(" ", ""))
        elif sys.platform == "win32":
            low = key.lower()
            sk = _SENDKEYS.get(low) or ("{%s}" % key.upper() if re.fullmatch(r"f\d{1,2}", low)
                                        else _sendkeys_escape(key))
            prefix = ("^" if "ctrl" in mods else "") + ("%" if "alt" in mods else "") + ("+" if "shift" in mods else "")
            self._ps("Add-Type -AssemblyName System.Windows.Forms; "
                     "[System.Windows.Forms.SendKeys]::SendWait(%s)" % _ps_quote(prefix + sk))
        else:
            names = {"ctrl": "control down", "alt": "option down", "shift": "shift down", "cmd": "command down",
                     "super": "command down", "meta": "command down", "command": "command down"}
            using = ", ".join(names[m] for m in sorted(mods) if m in names)
            tail = (" using {%s}" % using) if using else ""
            low = key.lower()
            code = _MAC_CODES.get(low) or _MAC_FKEYS.get(low)
            action = ("key code %d" % code) if code else ("keystroke " + _applescript_quote(key))
            self._osa('tell application "System Events" to %s%s' % (action, tail))

    def type_text(self, text):
        if sys.platform.startswith("linux"):
            self._xdo("type", "--clearmodifiers", "--delay", "40", text)
        elif sys.platform == "win32":
            self._ps("Add-Type -AssemblyName System.Windows.Forms; "
                     "[System.Windows.Forms.SendKeys]::SendWait(%s)" % _ps_quote(_sendkeys_escape(text)))
        else:
            self._osa('tell application "System Events" to keystroke ' + _applescript_quote(text))

    def wait(self, seconds):
        time.sleep(float(seconds))


app = _App()


# ---------------------------------------------------------------------------
# Running a routine (the step list Command Vault's editor builds)
# ---------------------------------------------------------------------------
def _web_step(b, step):
    kind = step["type"]
    t = float(step.get("timeout", 15))
    retries = int(step.get("retries", 2)) if step.get("on_fail") == "retry" else 0
    alt = step.get("alt") or None
    by = step.get("by", "text")
    if kind == "goto":
        b.goto(step["url"], timeout=t * 2)
    elif kind == "click":
        b.click(step["target"], by=by, alt=alt, retries=retries, timeout=t)
    elif kind == "fill":
        b.fill(step["target"], step.get("value", ""), by=by, alt=alt, retries=retries, timeout=t)
    elif kind == "press":
        b.press(step["key"])
    elif kind == "wait_text":
        b.wait_text(step["text"], timeout=t, retries=retries)
    elif kind == "wait":
        b.wait(step.get("seconds", 1))
    else:
        raise StepError("unknown step type " + str(kind))


def _app_step(a, step):
    kind = step["type"]
    t = float(step.get("timeout", 15))
    alt = step.get("alt") or None
    retries = int(step.get("retries", 2)) if step.get("on_fail") == "retry" else 0

    def once():
        if kind == "launch":
            a.launch(step["command"])
        elif kind == "wait_window":
            a.wait_window(step["target"], alt=alt, timeout=t)
        elif kind == "focus_window":
            a.focus(step["target"], alt=alt)
        elif kind == "keys":
            a.keys(step["keys"])
        elif kind == "type":
            a.type_text(step.get("text", ""))
        elif kind == "wait":
            a.wait(step.get("seconds", 1))
        else:
            raise StepError("unknown step type " + str(kind))
    _attempt(lambda _t: once(), [None], retries)


def run_routine(steps, kind="web", show_browser=True, fail_shot=None):
    """Runs a routine's steps; prints progress; returns a process exit code
    (0 ok, 1 a step failed, 2/3 couldn't start)."""
    total = len(steps)

    def go(do_step, shot=None):
        for i, step in enumerate(steps, 1):
            desc = step.get("desc", step["type"])
            print("[%d/%d] %s" % (i, total, desc), flush=True)
            try:
                do_step(step)
            except StepError as exc:
                if step.get("on_fail") == "skip":
                    print("    skipped: %s" % exc, flush=True)
                    continue
                print("FAILED at step %d: %s" % (i, desc))
                print("    %s" % exc)
                if shot and shot():
                    print("    Screenshot of the page: " + fail_shot)
                return 1
        print("Routine finished.")
        return 0

    if kind == "app":
        return go(lambda s: _app_step(app, s))
    try:
        with web(show=show_browser) as b:
            return go(lambda s: _web_step(b, s), (lambda: fail_shot and b.screenshot(fail_shot)) if fail_shot else None)
    except StepError as exc:
        print(str(exc))
        return 2 if "isn't installed" in str(exc) else 3
'''
