"""feedback -- reusable "Leave Feedback" core (no GUI, no app-specific imports).

Copy this file (plus feedback_dialog.py) into another app and configure it with
a FeedbackConfig. A report is delivered one of two ways:

  relay   POST JSON to a small web endpoint you own (see
          examples/feedback_relay.gs, a Google Apps Script) which emails it to
          the support address. The app holds only the endpoint URL and a
          shared token -- never an email password or API key.
  mailto  open the user's own mail app with the subject/body filled in; the
          user presses Send. Used when no relay is configured or it fails.

System information is opt-in and limited to: OS + version, architecture, CPU
model, GPU model, RAM and the app version. No username, hostname, serials,
IP address or file paths.
"""
import json
import os
import platform
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass

REPORT_TYPES = {
    "Bug Report": "BUG",
    "Feature Suggestion": "FEATURE",
    "General Feedback": "FEEDBACK",
    "Question": "QUESTION",
    "Other": "OTHER",
}

MAX_TITLE = 120
MAX_DESCRIPTION = 8000
MAILTO_BODY_LIMIT = 1800  # many mail clients/OSes choke on longer mailto: URLs


@dataclass
class FeedbackConfig:
    app_name: str
    app_version: str
    support_email: str
    relay_url: str = ""    # "" = no relay, use mailto
    relay_token: str = ""  # shared secret checked by the relay (not a mail credential)


def _run(cmd, timeout=4):
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return res.stdout.strip() if res.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _cpu():
    system = platform.system()
    if system == "Linux":
        try:
            with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.lower().startswith("model name"):
                        return line.split(":", 1)[1].strip()
        except OSError:
            pass
    elif system == "Darwin":
        name = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
        if name:
            return name
    elif system == "Windows":
        out = _run(["powershell", "-NoProfile", "-Command",
                    "(Get-CimInstance Win32_Processor | Select-Object -First 1).Name"])
        if out:
            return out
    return platform.processor() or "unknown"


def _gpu():
    system = platform.system()
    if system == "Linux":
        out = _run(["lspci"])
        names = []
        for line in out.splitlines():
            if re.search(r"VGA compatible|3D controller|Display controller", line):
                names.append(line.split(": ", 1)[-1].strip())
        return "; ".join(names) or "unknown"
    if system == "Darwin":
        out = _run(["system_profiler", "SPDisplaysDataType"], timeout=8)
        names = [l.split(":", 1)[1].strip() for l in out.splitlines() if "Chipset Model" in l]
        return "; ".join(names) or "unknown"
    if system == "Windows":
        out = _run(["powershell", "-NoProfile", "-Command",
                    "(Get-CimInstance Win32_VideoController).Name -join '; '"])
        return out or "unknown"
    return "unknown"


def _ram_gb():
    system = platform.system()
    try:
        if system == "Linux":
            with open("/proc/meminfo", encoding="utf-8") as f:
                kb = int(f.readline().split()[1])
            return f"{kb / 1024 / 1024:.1f} GB"
        if system == "Darwin":
            return f"{int(_run(['sysctl', '-n', 'hw.memsize'])) / 1024 ** 3:.1f} GB"
        if system == "Windows":
            out = _run(["powershell", "-NoProfile", "-Command",
                        "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"])
            return f"{int(out) / 1024 ** 3:.1f} GB"
    except (OSError, ValueError):
        pass
    return "unknown"


def _os_name():
    if platform.system() == "Linux":
        try:
            info = {}
            with open("/etc/os-release", encoding="utf-8") as f:
                for line in f:
                    if "=" in line:
                        k, v = line.rstrip().split("=", 1)
                        info[k] = v.strip('"')
            if info.get("PRETTY_NAME"):
                return f'{info["PRETTY_NAME"]} (kernel {platform.release()})'
        except OSError:
            pass
    if platform.system() == "Darwin":
        return f"macOS {platform.mac_ver()[0]}"
    return f"{platform.system()} {platform.release()} {platform.version()}".strip()


def collect_system_info(app_version):
    """Ordered (label, value) pairs; the dialog shows these before sending."""
    return [
        ("Operating system", _os_name()),
        ("Architecture", platform.machine() or "unknown"),
        ("CPU", _cpu()),
        ("GPU", _gpu()),
        ("RAM", _ram_gb()),
        ("App version", app_version),
        ("Python", platform.python_version()),
    ]


def validate(report_type, title, description):
    """Returns an error message, or '' if the report is acceptable."""
    if report_type not in REPORT_TYPES:
        return "Choose a report type."
    if not title.strip():
        return "Please enter a title."
    if len(title) > MAX_TITLE:
        return f"The title is too long (max {MAX_TITLE} characters)."
    if not description.strip():
        return "Please describe the problem or suggestion."
    if len(description) > MAX_DESCRIPTION:
        return f"The description is too long (max {MAX_DESCRIPTION} characters)."
    return ""


def build_subject(cfg, report_type, title):
    clean = re.sub(r"\s+", " ", title).strip()
    return f"[{cfg.app_name}] [{REPORT_TYPES[report_type]}] {clean}"


def build_body(cfg, report_type, title, description, name="", sysinfo=None):
    lines = [
        f"App: {cfg.app_name}",
        f"Version: {cfg.app_version}",
        f"Type: {report_type}",
        f"From: {name.strip() or '(not given)'}",
        f"Title: {title.strip()}",
        "",
        "--- Description ---",
        description.strip(),
        "",
        "--- System information ---",
    ]
    if sysinfo:
        lines += [f"{label}: {value}" for label, value in sysinfo]
    else:
        lines.append("(not included by the user)")
    return "\n".join(lines) + "\n"


def send_via_relay(cfg, subject, body, timeout=20):
    """POSTs the report to the relay. Returns (ok, message)."""
    payload = json.dumps({"token": cfg.relay_token, "subject": subject, "body": body,
                          "app": cfg.app_name}).encode("utf-8")
    req = urllib.request.Request(cfg.relay_url, data=payload, method="POST",
                                 headers={"Content-Type": "text/plain;charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read(4096).decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError) as e:
        return False, f"Couldn't reach the feedback service: {e}"
    try:
        result = json.loads(text)
    except ValueError:
        return False, "The feedback service gave an unexpected answer."
    if result.get("ok"):
        return True, "Thanks! Your feedback was sent."
    return False, f"The feedback service refused it: {result.get('error', 'unknown error')}"


def build_mailto(cfg, subject, body):
    """(url, truncated). Long bodies are cut so mail clients accept the link;
    the caller should offer 'copy full report' when truncated is True."""
    truncated = len(body) > MAILTO_BODY_LIMIT
    if truncated:
        body = body[:MAILTO_BODY_LIMIT] + "\n[...cut; full report was copied to your clipboard]"
    query = urllib.parse.urlencode({"subject": subject, "body": body}, quote_via=urllib.parse.quote)
    return f"mailto:{cfg.support_email}?{query}", truncated


def open_mailto(url):
    try:
        return bool(webbrowser.open(url))
    except webbrowser.Error:
        return False
