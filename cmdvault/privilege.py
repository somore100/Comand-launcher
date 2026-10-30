"""privilege -- optional administrator rights for entries that use `sudo`.

Three per-entry modes (Linux/macOS):

  off       leave the command alone (default).
  ask       the OS asks for the password each run. In a terminal that is just
            sudo's own prompt; for silent runs a small graphical askpass
            helper is used (zenity/kdialog on Linux, a dialog on macOS).
  remember  the user approves ONCE, in the OS's own password prompt (pkexec /
            macOS admin dialog), and Command Vault installs a sudoers rule that
            lets this user run exactly the `sudo ...` commands found in the
            entry without a password. Nothing secret is stored anywhere; the
            rule covers only those exact commands. Runs then use `sudo -n`, so
            a missing rule fails immediately instead of hanging on a prompt.

Windows has no sudo; elevation there (UAC / a highest-privileges scheduled
task) is not implemented yet.
"""
import getpass
import hashlib
import os
import re
import shlex
import shutil
import subprocess
from .platform_utils import is_linux, is_mac

ADMIN_OFF = "off"
ADMIN_ASK = "ask"
ADMIN_REMEMBER = "remember"
ADMIN_MODES = (ADMIN_OFF, ADMIN_ASK, ADMIN_REMEMBER)

SUDOERS_DIR = "/etc/sudoers.d"

_USER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*\$?$")
_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_SEPARATORS = set(";&|()")
_LEADING_KEYWORDS = {"then", "do", "else", "elif", "if", "while", "until", "!", "{", "time"}
_BAD_ARG_CHARS = set("*?[]\\\"'`$<>&|;(){}\n\r\t")


def supports_admin():
    return is_linux() or is_mac()


# ---------------------------------------------------------------------------
# Finding the `sudo` calls in an entry
# ---------------------------------------------------------------------------
def entry_sudo_text(command):
    """The text to scan for sudo calls: the command itself, plus the file's
    contents when the command is just a path to a script (so `sudo apt update`
    inside ~/update.sh is found). Never raises."""
    text = command or ""
    stripped = text.strip()
    if stripped and "\n" not in stripped and os.path.isfile(stripped):
        try:
            if os.path.getsize(stripped) <= 1024 * 1024:
                with open(stripped, "r", encoding="utf-8", errors="replace") as f:
                    text += "\n" + f.read()
        except OSError:
            pass
    return text


def _tokenize_line(line):
    lex = shlex.shlex(line, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = "#"
    return list(lex)


def _segments(tokens):
    seg = []
    for tok in tokens:
        if tok and set(tok) <= _SEPARATORS:
            if seg:
                yield seg
            seg = []
        else:
            seg.append(tok)
    if seg:
        yield seg


def find_sudo_calls(text):
    """Returns (calls, problems). `calls` is a list of (run_as, argv) for each
    `sudo <command...>` found; `problems` is a list of human-readable reasons
    something couldn't be understood. Only the simple, common shapes are
    understood on purpose: anything fancier is reported, never guessed at."""
    calls, problems = [], []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "sudo" not in line:
            continue
        try:
            tokens = _tokenize_line(line)
        except ValueError:
            problems.append(f"Couldn't read this line: {line}")
            continue
        for seg in _segments(tokens):
            while seg and (seg[0] in _LEADING_KEYWORDS or _ASSIGNMENT_RE.match(seg[0])):
                seg = seg[1:]
            if not seg or seg[0] != "sudo":
                if any(t == "sudo" for t in seg):
                    problems.append(f"sudo used in a way I can't read: {line}")
                continue
            rest, run_as = seg[1:], "root"
            while rest and rest[0].startswith("-"):
                opt = rest.pop(0)
                if opt in ("-n", "--non-interactive"):
                    continue
                if opt in ("-u", "--user") and rest:
                    run_as = rest.pop(0)
                    continue
                problems.append(f"Unsupported sudo option {opt}: {line}")
                rest = []
                break
            if not rest:
                problems.append(f"sudo with no command: {line}")
                continue
            if "{{" in " ".join(rest):
                problems.append(f"A {{{{placeholder}}}} can't be part of a remembered sudo command: {line}")
                continue
            if not _USER_RE.match(run_as):
                problems.append(f"Odd user name for sudo -u: {run_as}")
                continue
            calls.append((run_as, rest))
    return calls, problems


def _resolve_binary(name):
    if "/" in name:
        return os.path.abspath(os.path.expanduser(name))
    found = shutil.which(name)
    return os.path.abspath(found) if found else None


def _user_controlled(path):
    """The first location along `path` (the file, then each parent) that the
    current user can write to, or None. A passwordless rule for a file the user
    can swap out would hand root to anything running as that user."""
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return None
    p = os.path.realpath(path)
    while True:
        if os.access(p, os.W_OK):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            return None
        p = parent


# ---------------------------------------------------------------------------
# Building the sudoers rule
# ---------------------------------------------------------------------------
def _escape_sudoers(text):
    return re.sub(r"([,:=\\ ])", r"\\\1", text)


def build_rule_specs(calls):
    """(specs, problems): one (run_as, spec_string) per distinct call, where
    spec_string is the sudoers command spec matching exactly that command line.
    Rejects anything that would widen the rule (wildcards, unresolvable or
    user-writable binaries/files)."""
    specs, problems, seen = [], [], set()
    for run_as, argv in calls:
        binary = _resolve_binary(argv[0])
        if not binary:
            problems.append(f"Can't find the command '{argv[0]}' to allow.")
            continue
        args = argv[1:]
        bad = next((a for a in args if any(c in _BAD_ARG_CHARS for c in a)), None)
        if bad is not None:
            problems.append(
                f"Argument '{bad}' has characters that can't be matched exactly in a sudoers rule "
                f"(wildcards, quotes, $ ...). Use a plain command, or choose 'Ask each time'.")
            continue
        for path in [binary] + [a for a in args if os.path.exists(a)]:
            writable = _user_controlled(path)
            if writable:
                problems.append(
                    f"'{path}' can be modified by your user ({writable} is writable), so a "
                    f"passwordless rule for it would let anything running as you gain root. Use a "
                    f"command in a system folder, or choose 'Ask each time'.")
                break
        else:
            spec = _escape_sudoers(binary)
            spec += " " + " ".join(_escape_sudoers(a) for a in args) if args else ' ""'
            if (run_as, spec) not in seen:
                seen.add((run_as, spec))
                specs.append((run_as, spec))
    return specs, problems


def build_sudoers_text(user, specs):
    lines = ["# Managed by Command Vault -- exact commands this user may run without a password.",
             "# Remove the entry (or switch it off) in Command Vault to delete this file."]
    for run_as, spec in specs:
        lines.append(f"{user} ALL=({run_as}) NOPASSWD: {spec}")
    return "\n".join(lines) + "\n"


def plan_admin(entry):
    """Everything 'remember' needs for an entry: {'specs', 'problems', 'text',
    'user'}. Pure apart from reading files; never touches the system."""
    calls, problems = find_sudo_calls(entry_sudo_text(entry.get("command", "")))
    specs, more = build_rule_specs(calls)
    problems = problems + more
    user = getpass.getuser()
    if not _USER_RE.match(user):
        problems.append(f"Unusual user name '{user}'.")
    if not specs and not problems:
        problems.append("No 'sudo' command found in this entry, so there is nothing to remember.")
    return {"specs": specs, "problems": problems, "user": user,
            "text": build_sudoers_text(user, specs) if specs else ""}


def rule_filename(entry_id):
    return "command-vault-" + re.sub(r"[^A-Za-z0-9_-]", "_", entry_id or "entry")


def rule_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Installing / removing the rule (one OS password prompt)
# ---------------------------------------------------------------------------
def _install_script(text, dst):
    return (
        't=$(mktemp) || exit 1; '
        f"printf '%s' {shlex.quote(text)} > \"$t\" && visudo -cf \"$t\" >/dev/null && "
        f'install -m 0440 -o root -g root "$t" {shlex.quote(dst)}; rc=$?; rm -f "$t"; exit $rc'
    )


def _remove_script(dst):
    return f"rm -f {shlex.quote(dst)}"


def _run_elevated(script):
    """Runs a sh script as root through the OS's own password prompt.
    Returns (ok, message)."""
    if is_mac():
        esc = script.replace("\\", "\\\\").replace('"', '\\"')
        cmd = ["osascript", "-e", f'do shell script "{esc}" with administrator privileges']
    elif shutil.which("pkexec"):
        cmd = ["pkexec", "sh", "-c", script]
    else:
        return False, "pkexec (polkit) isn't installed, so I can't ask for administrator rights."
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    if res.returncode == 0:
        return True, ""
    detail = (res.stderr or res.stdout or "").strip()
    if res.returncode in (126, 127) or "cancel" in detail.lower():
        return False, "Administrator approval was cancelled or refused."
    return False, detail or f"exit code {res.returncode}"


def install_rule(entry, plan):
    dst = os.path.join(SUDOERS_DIR, rule_filename(entry["id"]))
    return _run_elevated(_install_script(plan["text"], dst))


def remove_rule(entry):
    dst = os.path.join(SUDOERS_DIR, rule_filename(entry["id"]))
    return _run_elevated(_remove_script(dst))


def command_allowed(run_as, argv):
    """True when sudo already allows this command without a password
    (`sudo -n -l <cmd>` exits 0 without prompting)."""
    try:
        res = subprocess.run(["sudo", "-n", "-u", run_as, "-l"] + list(argv),
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return res.returncode == 0


# ---------------------------------------------------------------------------
# Run-time: rewriting `sudo` for the chosen mode
# ---------------------------------------------------------------------------
def askpass_path():
    from .data import app_config_dir
    return os.path.join(app_config_dir(), "askpass.sh")


def ensure_askpass():
    """Writes the small password-dialog helper SUDO_ASKPASS points at. Returns
    its path, or None where nothing sensible exists."""
    if is_mac():
        body = ('#!/bin/sh\nosascript -e \'text returned of (display dialog '
                '"Command Vault needs your administrator password:" default answer "" '
                'with hidden answer with title "Command Vault")\'\n')
    elif is_linux():
        body = (
            '#!/bin/sh\n'
            'P="${1:-Administrator password:}"\n'
            'if command -v zenity >/dev/null 2>&1; then\n'
            '  exec zenity --password --title="Command Vault"\n'
            'elif command -v kdialog >/dev/null 2>&1; then\n'
            '  exec kdialog --title "Command Vault" --password "$P"\n'
            'fi\n'
            'for h in /usr/libexec/openssh/gnome-ssh-askpass /usr/lib/ssh/ssh-askpass /usr/bin/ssh-askpass; do\n'
            '  [ -x "$h" ] && exec "$h" "$P"\n'
            'done\n'
            'exit 1\n'
        )
    else:
        return None
    path = askpass_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(body)
        os.chmod(path, 0o700)
    except OSError:
        return None
    return path


def admin_prefix(entry, silent=False, unattended=False):
    """A shell snippet to put in front of the entry's command (or '' for none).
    It redefines `sudo` for the chosen mode, so the user's command text stays
    exactly as written. `silent`: no terminal to type a password into.
    `unattended`: scheduled/boot run, nobody to answer a dialog."""
    mode = entry.get("admin_mode", ADMIN_OFF)
    if not supports_admin():
        return ""
    if mode == ADMIN_REMEMBER:
        return 'sudo() { command sudo -n "$@"; }'
    if mode == ADMIN_ASK and silent and not unattended:
        helper = ensure_askpass()
        if helper:
            return f'export SUDO_ASKPASS={shlex.quote(helper)}; sudo() {{ command sudo -A "$@"; }}'
    return ""


def apply_admin(entry, exec_cmd, silent=False, unattended=False):
    prefix = admin_prefix(entry, silent=silent, unattended=unattended)
    return f"{prefix}\n{exec_cmd}" if prefix else exec_cmd
