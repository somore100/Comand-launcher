"""theme -- split out of the former monolithic main.py."""
import platform
import re


# ---------------------------------------------------------------------------
# Theme (Catppuccin Mocha inspired)
# ---------------------------------------------------------------------------
COLOR_BG = "#1e1e2e"
COLOR_SIDEBAR = "#181825"
COLOR_PANEL = "#242438"
COLOR_TEXT = "#cdd6f4"
COLOR_SUBTEXT = "#a6adc8"
COLOR_ACCENT = "#89b4fa"
COLOR_ACCENT_DIM = "#5876a8"
COLOR_GREEN = "#a6e3a1"
COLOR_RED = "#f38ba8"
COLOR_YELLOW = "#f9e2af"
COLOR_ROW_ALT = "#28283f"
COLOR_SELECT = "#33344d"
FONT_TITLE = ("Segoe UI", 18, "bold")
FONT_HEADING = ("Segoe UI", 11, "bold")
FONT_NORMAL = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)
FONT_MONO = ("Consolas", 10) if platform.system() == "Windows" else ("DejaVu Sans Mono", 10)

DEFAULT_ICON = "\U0001F4E6"  # package
ALL_CATEGORY = "All"
UNCATEGORIZED = "Uncategorized"
SCHEDULE_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")  # 24h "HH:MM"

EMOJI_CHOICES = [
    "\U0001F680", "\u2699\uFE0F", "\U0001F527", "\U0001F6E0\uFE0F", "\U0001F4BB", "\U0001F5A5\uFE0F",
    "\U0001F4E6", "\U0001F40D", "\U0001F916", "\U0001F3A8", "\U0001F4CA", "\U0001F525",
    "\u2B50", "\u2705", "\u274C", "\U0001F310", "\U0001F4C1", "\U0001F5C2\uFE0F",
    "\U0001F579\uFE0F", "\U0001F3AE", "\U0001F3B5", "\U0001F3AC", "\U0001F4F7", "\u26A1",
    "\U0001F9E9", "\U0001F512", "\U0001F511", "\U0001F4DD", "\u270F\uFE0F", "\U0001F4CC",
    "\U0001F9E0", "\U0001F433", "\u2601\uFE0F", "\U0001F5C4\uFE0F", "\U0001F4E1", "\U0001F9EA",
    "\U0001F578\uFE0F", "\U0001F50C", "\U0001F5B1\uFE0F", "\u2328\uFE0F", "\U0001F4DC", "\U0001F50D",
    "\U0001F9F0", "\U0001F3AF", "\u23F0", "\U0001F514",
]


# ---------------------------------------------------------------------------
