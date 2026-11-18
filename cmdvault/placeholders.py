"""placeholders -- split out of the former monolithic main.py."""
import re
import tkinter as tk
from .theme import COLOR_BG, COLOR_GREEN, COLOR_PANEL, COLOR_SIDEBAR, COLOR_SUBTEXT, COLOR_TEXT, FONT_HEADING, FONT_NORMAL, FONT_SMALL


# Templated commands: {{name}}, {{name:default}} or {{name:default|Label}} prompts for a value
# each run. The label (optional) is the question shown next to the box, e.g.
# {{who:world|Who should I greet?}}; without one the name is shown.
# ---------------------------------------------------------------------------
PLACEHOLDER_RE = re.compile(r"\{\{(\w+)(?::([^}|]*))?(?:\|([^}]*))?\}\}")


def placeholder_labels(command):
    """{name: label} for placeholders that have a label."""
    labels = {}
    for m in PLACEHOLDER_RE.finditer(command or ""):
        if m.group(3) and m.group(3).strip() and m.group(1) not in labels:
            labels[m.group(1)] = m.group(3).strip()
    return labels


def extract_placeholders(command):
    """Returns an ordered list of (name, default) for each unique {{name}}
    or {{name:default}} found in the command."""
    seen = {}
    order = []
    for m in PLACEHOLDER_RE.finditer(command):
        name, default = m.group(1), m.group(2) or ""
        if name not in seen:
            seen[name] = default
            order.append(name)
    return [(name, seen[name]) for name in order]


def fill_placeholders(command, values):
    def repl(m):
        name = m.group(1)
        return values.get(name, m.group(0))
    return PLACEHOLDER_RE.sub(repl, command)


class PlaceholderDialog(tk.Toplevel):
    """Prompts for {{name}} values before running a templated command."""
    def __init__(self, entry_name, placeholders, command=None, labels=None):
        super().__init__()
        labels = labels or {}
        self.result = None
        self.title(f"Run: {entry_name}")
        self.configure(bg=COLOR_BG)
        self.resizable(False, False)
        self.grab_set()

        tk.Label(self, text=f'Fill in values to run "{entry_name}"', bg=COLOR_BG, fg=COLOR_TEXT,
                 font=FONT_HEADING, wraplength=340, justify="left").pack(anchor="w", padx=16, pady=(16, 10))

        self.vars = {}
        self._command = command
        self._preview = None
        if command:
            tk.Label(self, text="Command (your values go where the {{boxes}} are)", bg=COLOR_BG, fg=COLOR_SUBTEXT,
                     font=FONT_SMALL, anchor="w").pack(fill="x", padx=16)
            self._preview = tk.Text(self, height=min(6, max(2, command.count("\n") + 2)), width=52, wrap="word",
                                    font=("Consolas", 9), bg=COLOR_PANEL, fg=COLOR_TEXT, relief="flat")
            self._preview.pack(fill="x", padx=16, pady=(2, 10))
            self._preview.tag_configure("slot", foreground=COLOR_GREEN, font=("Consolas", 9, "bold"))
        first_entry = None
        for name, default in placeholders:
            caption = f"{labels[name]}  ({name})" if name in labels else name
            tk.Label(self, text=caption, bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, anchor="w"
                      ).pack(fill="x", padx=16)
            var = tk.StringVar(value=default)
            entry = tk.Entry(self, textvariable=var, width=42, font=FONT_NORMAL, bg=COLOR_PANEL,
                              fg=COLOR_TEXT, insertbackground=COLOR_TEXT, relief="flat")
            entry.pack(fill="x", padx=16, pady=(2, 8))
            entry.bind("<Return>", lambda e: self._confirm())
            self.vars[name] = var
            var.trace_add("write", lambda *a: self._update_preview())
            if first_entry is None:
                first_entry = entry

        btn_frame = tk.Frame(self, bg=COLOR_BG)
        btn_frame.pack(fill="x", padx=16, pady=(4, 16))
        tk.Button(btn_frame, text="Cancel", command=self._cancel, bg=COLOR_PANEL, fg=COLOR_TEXT,
                  relief="flat", padx=14, pady=4).pack(side="right")
        tk.Button(btn_frame, text="Run", command=self._confirm, bg=COLOR_GREEN, fg=COLOR_SIDEBAR,
                  relief="flat", padx=14, pady=4, font=("Segoe UI", 10, "bold")).pack(side="right", padx=(0, 8))

        self._update_preview()
        if first_entry:
            first_entry.focus_set()
            first_entry.select_range(0, tk.END)

    def _update_preview(self):
        """Shows the command with the typed values filled in, highlighted, and empty boxes as {{name}}."""
        if not self._preview:
            return
        self._preview.configure(state="normal")
        self._preview.delete("1.0", tk.END)
        pos = 0
        for m in PLACEHOLDER_RE.finditer(self._command):
            self._preview.insert(tk.END, self._command[pos:m.start()])
            var = self.vars.get(m.group(1))
            value = var.get() if var is not None else ""
            self._preview.insert(tk.END, value if value else "{{" + m.group(1) + "}}", "slot")
            pos = m.end()
        self._preview.insert(tk.END, self._command[pos:])
        self._preview.configure(state="disabled")

    def _confirm(self):
        self.result = {name: var.get() for name, var in self.vars.items()}
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


# ---------------------------------------------------------------------------
