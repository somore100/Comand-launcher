"""apps -- split out of the former monolithic main.py."""
import glob
import os
import re
from .platform_utils import is_linux, is_windows


# Installed-app discovery (for "Pick Installed App")
# ---------------------------------------------------------------------------
def find_linux_apps():
    dirs = ["/usr/share/applications", os.path.expanduser("~/.local/share/applications")]
    apps = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for fname in glob.glob(os.path.join(d, "*.desktop")):
            name, exec_line, no_display = None, None, False
            try:
                with open(fname, "r", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("Name=") and name is None:
                            name = line[len("Name="):]
                        elif line.startswith("Exec=") and exec_line is None:
                            exec_line = line[len("Exec="):]
                        elif line.startswith("NoDisplay=true"):
                            no_display = True
            except OSError:
                continue
            if name and exec_line and not no_display:
                clean = re.sub(r"%[a-zA-Z]", "", exec_line).strip()
                apps.append((name, clean, fname))
    apps.sort(key=lambda a: a[0].lower())
    return apps


def find_windows_apps():
    apps = []
    dirs = []
    appdata = os.getenv("APPDATA")
    programdata = os.getenv("PROGRAMDATA")
    if appdata:
        dirs.append(os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs"))
    if programdata:
        dirs.append(os.path.join(programdata, "Microsoft", "Windows", "Start Menu", "Programs"))
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for fname in files:
                if fname.lower().endswith(".lnk"):
                    full = os.path.join(root, fname)
                    name = os.path.splitext(fname)[0]
                    apps.append((name, f'start "" "{full}"', full))
    apps.sort(key=lambda a: a[0].lower())
    return apps


def find_installed_apps():
    if is_linux():
        return find_linux_apps()
    if is_windows():
        return find_windows_apps()
    return []


# ---------------------------------------------------------------------------
