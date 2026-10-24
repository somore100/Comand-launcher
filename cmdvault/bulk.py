"""bulk -- parse a pasted block of lines into several entries at once.

One entry per line. Optional "Name :: command" (or Name<TAB>command) syntax; without a name, one is
derived from the command. Blank lines and lines starting with '#' are skipped.

For the common "many scripts, each in its own folder under one parent" case,
names come from the file's name (extension dropped), falling back to the
parent folder's name when several lines would otherwise get the same name
(e.g. .../alpha/run.sh and .../beta/run.sh become "alpha" and "beta").
"""
import os
import shlex
from .data import _blank_entry
from .platform_utils import is_windows

NAME_MAX_LEN = 40


def _unquote(line):
    s = line.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    return s


def _first_token(line):
    try:
        parts = shlex.split(line, posix=not is_windows())
    except ValueError:
        parts = line.split()
    return _unquote(parts[0]) if parts else ""


def command_path(command):
    """The filesystem path a command line points at, or '' if it isn't a
    plain path. Handles unquoted paths containing spaces (the whole line is
    tried first, then just the first token)."""
    whole = os.path.expanduser(_unquote(command))
    if os.path.exists(whole):
        return whole
    tok = os.path.expanduser(_first_token(command))
    if os.sep in tok or (os.altsep and os.altsep in tok) or tok.startswith("~"):
        return tok
    return ""


def _stem(path):
    base = os.path.basename(path.rstrip("/\\")) or path
    root, _ext = os.path.splitext(base)
    return root or base


def _parent_name(path):
    return os.path.basename(os.path.dirname(os.path.abspath(path.rstrip("/\\"))))


def parse_bulk_lines(text):
    """-> list of dicts {name, command, path} in input order. Names are made
    unique within the batch."""
    rows = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name = ""
        # NOT "|": that's a shell pipe and would silently mangle "ls | grep x"
        for sep in ("\t", " :: "):
            if sep in line:
                head, _, rest = line.partition(sep)
                if head.strip() and rest.strip():
                    name, line = head.strip(), rest.strip()
                    break
        path = command_path(line)
        rows.append({"name": name, "command": line, "path": path, "explicit": bool(name)})

    # derive missing names
    for r in rows:
        if r["explicit"]:
            continue
        r["name"] = _stem(r["path"]) if r["path"] else r["command"][:NAME_MAX_LEN].rstrip()
    # resolve collisions among derived names: prefer the parent folder name
    counts = {}
    for r in rows:
        counts[r["name"]] = counts.get(r["name"], 0) + 1
    for r in rows:
        if counts[r["name"]] > 1 and r["path"] and not r["explicit"]:
            parent = _parent_name(r["path"])
            if parent:
                r["name"] = parent
    # anything still colliding gets a numeric suffix
    seen = {}
    for r in rows:
        n = seen.get(r["name"], 0) + 1
        seen[r["name"]] = n
        if n > 1:
            r["name"] = f"{r['name']} {n}"
    return rows


def build_entries(rows, category, run_mode, use_script_folder):
    """Turn parsed rows into full entry dicts ready for the vault."""
    entries = []
    for r in rows:
        e = _blank_entry(r["name"], r["command"])
        e["category"] = category
        e["run_mode"] = run_mode
        path = r["path"]
        if path and path.lower().endswith(".appimage") and os.path.isfile(r["command"].strip()):
            e["entry_type"] = "appimage"
            e["command"] = os.path.abspath(r["command"].strip())
        if use_script_folder and path and os.path.isabs(path):
            wd = path if os.path.isdir(path) else os.path.dirname(path)
            if wd and os.path.isdir(wd):
                e["working_dir"] = wd
        entries.append(e)
    return entries
