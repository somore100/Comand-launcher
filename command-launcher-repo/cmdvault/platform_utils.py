"""platform_utils -- split out of the former monolithic main.py."""
import platform


# Platform helpers
# ---------------------------------------------------------------------------
def is_windows():
    return platform.system() == "Windows"


def is_linux():
    return platform.system() == "Linux"


def is_mac():
    return platform.system() == "Darwin"


# ---------------------------------------------------------------------------
