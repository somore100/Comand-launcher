"""automation_help_dialog -- the (i) window: how scripts can drive websites and
desktop programs through the cvauto helper library, with copyable examples."""
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from . import routine as rt
from .scrollframe import ScrollableBody, fit_dialog
from .theme import (COLOR_ACCENT, COLOR_ACCENT_DIM, COLOR_BG, COLOR_PANEL, COLOR_SIDEBAR, COLOR_SUBTEXT,
                    COLOR_TEXT, FONT_HEADING, FONT_MONO, FONT_NORMAL, FONT_SMALL)

INTRO = ("You don't have to use the step editor. Any Python script can control a website or a desktop program "
         "with the small helper library Command Vault keeps up to date for you. Save a script, make an entry "
         "that runs it (Command / Script), and it works with Run, startup and schedules like any other entry. "
         "Each call raises cvauto.StepError with a plain message if it fails, so you can add your own fallbacks "
         "with try/except.")

WEB_EXAMPLE = '''import sys
sys.path.insert(0, r"{lib}")
import cvauto

with cvauto.web(show=True) as b:           # reuses the entry's "stay logged in" profile
    b.goto("https://example.com")
    try:
        b.click("Start", alt="Start server", retries=2)   # text on the button, with an alternative
    except cvauto.StepError:
        b.click("More information")                        # your own fallback
    b.fill("Search", "hello")              # box label or placeholder
    b.press("Enter")
    b.wait_text("Results", timeout=30)
    # b.page is the Playwright page if you need more
'''

APP_EXAMPLE = '''import sys
sys.path.insert(0, r"{lib}")
import cvauto

cvauto.app.launch("firefox")                                   # any shell command
cvauto.app.wait_window("Firefox", alt="Mozilla", timeout=30)   # title contains...
cvauto.app.focus("Firefox")
cvauto.app.keys("ctrl+t")                                      # ctrl+shift+t, alt+F4, Return, ...
cvauto.app.type_text("example.com")
cvauto.app.keys("Return")
'''

NOTES = (
         "- Websites: needs Playwright. Click \"Set up browser automation\" in Edit steps once, then run scripts "
         "with the private Python shown under \"Where things are\".\n"
         "- Linux programs: needs the xdotool package and an X11 session (XWayland windows work, native Wayland "
         "ones don't).\n"
         "- Windows programs: uses PowerShell, nothing to install.\n"
         "- macOS programs: uses osascript; allow Terminal/Command Vault under System Settings > Privacy & "
         "Security > Accessibility.\n"
         "Browser: websites are driven in Playwright's own copy of Chromium that Command Vault downloads into its "
         "private folder (about 150 MB). It is separate from your Firefox/Chrome, so your normal logins and "
         "bookmarks aren't touched; the \"Stay logged in\" profile keeps the bot's own logins.\n"
         "Passwords: never put them in a script. Log in once by hand with \"Stay logged in\" turned on.")


class AutomationHelpDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Automation helpers (info)")
        self.configure(bg=COLOR_BG)
        self.resizable(True, True)
        self.transient(master)
        self.bind("<Escape>", lambda e: self.destroy())
        try:
            lib = rt.write_lib()
        except OSError as e:
            lib = f"(couldn't write the helper: {e})"
        self.lib_folder = rt.lib_dir()

        scroll = ScrollableBody(self)
        scroll.pack(fill="both", expand=True)
        body = scroll.inner
        tk.Label(body, text="Automate websites and programs from scripts", bg=COLOR_BG, fg=COLOR_TEXT,
                 font=FONT_HEADING).pack(anchor="w", padx=16, pady=(14, 4))
        tk.Label(body, text=INTRO, bg=COLOR_BG, fg=COLOR_SUBTEXT, font=FONT_SMALL, wraplength=520,
                 justify="left").pack(anchor="w", padx=16)

        py = rt.automation_python()
        self._section(body, "Where things are",
                      f"Helper library: {lib}\nLibrary folder (put this on sys.path): {self.lib_folder}\n"
                      f"Python with Playwright: {py or 'not set up yet (Edit steps > Set up browser automation)'}",
                      None)
        self._section(body, "Website example", WEB_EXAMPLE.format(lib=self.lib_folder), "web_example.py")
        self._section(body, "Desktop program example", APP_EXAMPLE.format(lib=self.lib_folder), "app_example.py")
        self._section(body, "Where it works", NOTES, None, wrap=True)
        tk.Frame(body, bg=COLOR_BG, height=10).pack()

        bar = tk.Frame(scroll.footer, bg=COLOR_BG)
        bar.pack(fill="x", padx=16, pady=(6, 12))
        tk.Button(bar, text="Close", command=self.destroy, bg=COLOR_ACCENT_DIM, fg=COLOR_TEXT, relief="flat",
                  font=FONT_NORMAL, padx=14, pady=4).pack(side="right")
        fit_dialog(self, master)

    def _section(self, body, title, text, save_name, wrap=False):
        tk.Label(body, text=title, bg=COLOR_BG, fg=COLOR_TEXT, font=("Segoe UI", 10, "bold")
                 ).pack(anchor="w", padx=16, pady=(12, 2))
        holder = tk.Frame(body, bg=COLOR_BG)
        holder.pack(anchor="w", padx=16, fill="x")
        lines = text.count("\n") + 1 + (sum(len(l) // 80 for l in text.splitlines()) if wrap else 0)
        box = tk.Text(holder, height=min(16, lines), width=80, font=FONT_MONO if not wrap else FONT_SMALL,
                      bg=COLOR_PANEL, fg=COLOR_TEXT, relief="flat", wrap="word" if wrap else "none")
        box.insert("1.0", text)
        box.configure(state="disabled")  # read-only but still selectable/copyable
        box.pack(side="top", fill="x")
        if not wrap:
            xs = ttk.Scrollbar(holder, orient="horizontal", command=box.xview)
            box.configure(xscrollcommand=xs.set)
            xs.pack(side="top", fill="x")
        row = tk.Frame(body, bg=COLOR_BG)
        row.pack(anchor="w", padx=16, pady=(4, 0))
        tk.Button(row, text="Copy", command=lambda: self._copy(text), bg=COLOR_PANEL, fg=COLOR_TEXT,
                  relief="flat", font=FONT_SMALL, padx=10).pack(side="left")
        if save_name:
            tk.Button(row, text="Save as a script...", command=lambda: self._save(text, save_name),
                      bg=COLOR_PANEL, fg=COLOR_TEXT, relief="flat", font=FONT_SMALL, padx=10
                      ).pack(side="left", padx=(6, 0))

    def _copy(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)

    def _save(self, text, default_name):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".py", initialfile=default_name,
                                            title="Save example script")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as e:
            messagebox.showerror("Couldn't save", str(e), parent=self)
            return
        messagebox.showinfo("Saved", f"Saved to {path}\n\nMake a Command / Script entry that points to it "
                                     f"(use the Python shown under \"Where things are\" for websites).", parent=self)
